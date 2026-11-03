import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Artifact, ChatEvent, ChatMessage, Conversation, TraceStep } from "@/api/types";
import { ME, traceStep } from "@/test/fixtures";
import { mockFetch } from "@/test/mockFetch";
import { renderApp } from "@/test/renderApp";

const NOW = new Date().toISOString();
const CONVERSATION: Conversation = { id: "c1", title: "What is a Roth IRA?", created_at: NOW, updated_at: NOW };
const FRESH = { source: "alpaca", as_of: NOW, status: "live" as const };
const CITATION = {
  article_id: "roth-ira",
  title: "Roth IRA basics",
  section: "How it works",
  source_name: "IRS",
  source_url: "https://www.irs.gov/roth",
};
const QUOTE_CARD: Artifact = {
  kind: "quote_card",
  title: "AAPL",
  data: { quote: { symbol: "AAPL", price: 225.41, change: -3.1, change_percent: -1.35, as_of: NOW }, freshness: FRESH },
};
const LOAD_STEP = traceStep("load_context", 4, { detail: { level: "beginner", has_portfolio: false, goals: 0 } });
const ROUTER_STEP = traceStep("router", 610, {
  llm_calls: 1,
  input_tokens: 900,
  output_tokens: 60,
  models: ["gemini:gemini-2.5-flash"],
  detail: { method: "llm", agents: ["tax_education"], confidence: 0.9 },
});
const TRACE: TraceStep[] = [
  LOAD_STEP,
  ROUTER_STEP,
  traceStep("tax_education", 1800, {
    llm_calls: 2,
    input_tokens: 2400,
    output_tokens: 300,
    models: ["gemini:gemini-2.5-flash"],
    tools: ["search_kb"],
    detail: { citations: 1, artifacts: [], attempts: 1 },
  }),
  traceStep("synthesizer", 1, { detail: { agents: 1, merged_by: "passthrough" } }),
  traceStep("compliance", 2, { detail: { issues: [], disclaimer_added: true } }),
];
const ANSWER: ChatMessage = {
  id: "m1",
  role: "assistant",
  kind: "answer",
  has_image: false,
  content: "A **Roth IRA** uses after-tax money [1].\n\n*Educational information only, not investment advice.*",
  agents: ["tax_education"],
  citations: [CITATION],
  artifacts: [QUOTE_CARD],
  freshness: [FRESH],
  follow_ups: ["What is a traditional IRA?"],
  trace: TRACE,
};
const STREAM: ChatEvent[] = [
  { type: "trace", step: LOAD_STEP },
  { type: "trace", step: ROUTER_STEP },
  { type: "route", kind: "answer", agents: ["tax_education"], confidence: 0.9 },
  { type: "agent_start", agent: "tax_education" },
  { type: "token", text: "A **Roth IRA** uses " },
  { type: "token", text: "after-tax money [1]." },
  { type: "artifact", artifact: QUOTE_CARD },
  { type: "citation", number: 1, citation: CITATION },
  { type: "freshness", freshness: FRESH },
  { type: "token", text: "\n\n*Educational information only, not investment advice.*" },
  { type: "done", message: ANSWER },
];

describe("Chat", () => {
  it("starts a conversation and streams a cited answer with agents, charts and follow-ups", async () => {
    let created = false;
    let sent: unknown = null;
    const fetchSpy = mockFetch({
      "GET /me": () => ({ body: ME }),
      "GET /conversations": () => ({ body: { conversations: created ? [CONVERSATION] : [] } }),
      "POST /conversations": () => {
        created = true;
        return { status: 201, body: { ...CONVERSATION, title: "New conversation" } };
      },
      // Like the server: the history includes each turn once it has been answered.
      "GET /conversations/c1": () => ({
        body: {
          conversation: CONVERSATION,
          messages: sent ? [{ id: "m1-q", role: "user", kind: "answer", content: "What is a Roth IRA?" }, ANSWER] : [],
        },
      }),
      "POST /conversations/c1/messages": (init) => {
        sent = JSON.parse(String(init?.body));
        return { sse: STREAM };
      },
    });
    renderApp("/chat");
    expect(await screen.findByText("No conversations yet.")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Ask a question"), "What is a Roth IRA?{Enter}");

    const answer = await screen.findByRole("article", { name: "Assistant answer" });
    await waitFor(() => expect(answer).toHaveAttribute("aria-busy", "false"));
    expect(sent).toEqual({ content: "What is a Roth IRA?", image: null });
    expect(window.location.pathname).toBe("/chat/c1");
    expect(screen.getByText("What is a Roth IRA?", { selector: "p" })).toBeInTheDocument();

    expect(within(answer).getByRole("list", { name: "Answered by" })).toHaveTextContent("Tax Education");
    expect(within(answer).getByText("Roth IRA", { selector: "strong" })).toBeInTheDocument();
    const marker = within(answer).getByRole("link", { name: "Source 1" });
    expect(marker).toHaveAttribute("href", "#cite-m1-1");
    const sources = within(answer).getByRole("region", { name: "Sources" });
    expect(within(sources).getByText("Roth IRA basics")).toBeInTheDocument();
    expect(within(sources).getByRole("link", { name: "IRS" })).toHaveAttribute("href", "https://www.irs.gov/roth");
    expect(within(answer).getByRole("region", { name: "AAPL" })).toHaveTextContent("225.41");
    expect(within(answer).getAllByText(/Live/).length).toBeGreaterThan(0);

    // "How I answered" opens to the agent path, tools and token use (INN-01).
    await userEvent.click(within(answer).getByText("How I answered"));
    expect(within(answer).getByText(/5 steps · 2\.4 s · 3 model calls · 3,660 tokens · 1 tool call/)).toBeInTheDocument();
    const steps = within(answer).getByRole("list", { name: "Workflow steps" });
    expect(within(steps).getByText("Tax Education agent")).toBeInTheDocument();
    expect(within(steps).getByText("Picked Tax Education using the language model, 90% confident")).toBeInTheDocument();
    expect(within(steps).getByText("search_kb")).toBeInTheDocument();
    expect(within(steps).getByText("Passed · added the disclaimer")).toBeInTheDocument();
    expect(within(answer).getByText(/Model: gemini-2\.5-flash/)).toBeInTheDocument();

    // The conversation list picks up the new title.
    expect(await screen.findByRole("link", { name: "What is a Roth IRA?" })).toBeInTheDocument();

    // Follow-ups send the next question.
    await userEvent.click(within(answer).getByRole("button", { name: "What is a traditional IRA?" }));
    await waitFor(() =>
      expect(fetchSpy.mock.calls.filter(([url]) => String(url).endsWith("/conversations/c1/messages"))).toHaveLength(2),
    );
  });

  it("reloads a conversation's history and deletes it", async () => {
    let deleted = false;
    mockFetch({
      "GET /me": () => ({ body: ME }),
      "GET /conversations": () => ({ body: { conversations: deleted ? [] : [CONVERSATION] } }),
      "GET /conversations/c1": () => ({
        body: {
          conversation: CONVERSATION,
          messages: [{ id: "q1", role: "user", kind: "answer", content: "What is a Roth IRA?" }, ANSWER],
        },
      }),
      "DELETE /conversations/c1": () => {
        deleted = true;
        return { status: 204 };
      },
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderApp("/chat/c1");

    const answer = await screen.findByRole("article", { name: "Assistant answer" });
    expect(within(answer).getByText("Tax Education")).toBeInTheDocument();
    expect(within(answer).getByRole("button", { name: "What is a traditional IRA?" })).toBeInTheDocument();
    expect(within(answer).getByText("How I answered")).toBeInTheDocument(); // kept with history

    await userEvent.click(screen.getByRole("button", { name: "Delete What is a Roth IRA?" }));
    expect(await screen.findByText("No conversations yet.")).toBeInTheDocument();
    expect(window.location.pathname).toBe("/chat");
  });

  it("shows a failure mid-answer and lets the user try again", async () => {
    let attempts = 0;
    mockFetch({
      "GET /me": () => ({ body: ME }),
      "GET /conversations": () => ({ body: { conversations: [CONVERSATION] } }),
      "GET /conversations/c1": () => ({ body: { conversation: CONVERSATION, messages: [] } }),
      "POST /conversations/c1/messages": () => {
        attempts += 1;
        return attempts === 1
          ? {
              sse: [
                { type: "route", kind: "answer", agents: ["finance_qa"], confidence: 0.9 },
                { type: "error", code: "internal_error", message: "Something went wrong while answering.", retryable: true },
              ],
            }
          : { sse: STREAM };
      },
    });
    renderApp("/chat/c1");
    await userEvent.type(await screen.findByLabelText("Ask a question"), "What is a Roth IRA?{Enter}");

    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong while answering.");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("link", { name: "Source 1" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(attempts).toBe(2);
  });

  it("reports a request the server rejects before streaming", async () => {
    mockFetch({
      "GET /me": () => ({ body: ME }),
      "GET /conversations": () => ({ body: { conversations: [] } }),
      "GET /conversations/gone": () => ({ status: 404, body: { error: { code: "not_found", message: "That conversation doesn't exist.", retryable: false } } }),
      "POST /conversations/gone/messages": () => ({
        status: 404,
        body: { error: { code: "not_found", message: "That conversation doesn't exist.", retryable: false } },
      }),
    });
    renderApp("/chat/gone");
    expect(await screen.findByText("Couldn't load this conversation")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Ask a question"), "hello{Enter}");
    const alerts = await screen.findAllByRole("alert");
    expect(alerts.some((a) => a.textContent?.includes("That conversation doesn't exist."))).toBe(true);
  });

  it("blocks messages over the length limit", async () => {
    mockFetch({ "GET /me": () => ({ body: ME }), "GET /conversations": () => ({ body: { conversations: [] } }) });
    renderApp("/chat");
    const input = await screen.findByLabelText("Ask a question");
    await userEvent.click(input);
    await userEvent.paste("x".repeat(4001));
    expect(screen.getByRole("alert")).toHaveTextContent(/under 4000 characters/);
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("sends a pasted or picked portfolio screenshot and shows the holdings read from it", async () => {
    let sent: { content: string; image: { media_type: string; data: string } | null } | null = null;
    const holdings: Artifact = {
      kind: "screenshot_holdings",
      title: "Holdings read from your screenshot",
      data: {
        rows: [
          { symbol: "VTI", name: "Vanguard Total Stock Market ETF", quantity: 12, screenshot_price: 270, live_price: 281.5, market_value: 3378 },
          { symbol: "ZZZZ", name: "", quantity: 3, screenshot_price: null, live_price: null, market_value: null },
        ],
        unpriced: ["ZZZZ"],
        freshness: [FRESH],
      },
    };
    const reply: ChatMessage = {
      ...ANSWER,
      id: "m9",
      agents: ["portfolio_analysis"],
      content: "Your screenshot holds one broad fund.",
      citations: [],
      artifacts: [holdings],
      follow_ups: [],
    };
    mockFetch({
      "GET /me": () => ({ body: ME }),
      "GET /conversations": () => ({ body: { conversations: [CONVERSATION] } }),
      "GET /conversations/c1": () => ({
        body: {
          conversation: CONVERSATION,
          messages: sent
            ? [{ id: "m9-q", role: "user", kind: "answer", content: "Analyze the portfolio in this screenshot.", has_image: true }, reply]
            : [],
        },
      }),
      "POST /conversations/c1/messages": (init) => {
        sent = JSON.parse(String(init?.body));
        return {
          sse: [
            { type: "route", kind: "answer", agents: ["portfolio_analysis"], confidence: 0.9 },
            { type: "artifact", artifact: holdings },
            { type: "token", text: "Your screenshot holds one broad fund." },
            { type: "done", message: reply },
          ] satisfies ChatEvent[],
        };
      },
    });
    renderApp("/chat/c1");
    const input = await screen.findByLabelText("Ask a question");

    // A non-image file is refused with a message.
    await userEvent.upload(screen.getByTestId("screenshot-input"), new File(["a,b"], "holdings.csv", { type: "text/csv" }), {
      applyAccept: false,
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("Attach a PNG, JPEG or WebP image.");

    // Picking an image shows a preview that can be removed; pasting one attaches it again.
    const png = new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], "positions.png", { type: "image/png" });
    await userEvent.upload(screen.getByTestId("screenshot-input"), png);
    expect(await screen.findByRole("img", { name: "Attached screenshot" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Remove screenshot" }));
    expect(screen.queryByRole("img", { name: "Attached screenshot" })).not.toBeInTheDocument();

    await userEvent.click(input);
    await userEvent.paste({ files: [png], items: [], getData: () => "", types: ["Files"] } as unknown as DataTransfer);
    expect(await screen.findByRole("img", { name: "Attached screenshot" })).toBeInTheDocument();

    // An image alone can be sent; the default question goes with it.
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    const answer = await screen.findByRole("article", { name: "Assistant answer" });
    await waitFor(() => expect(answer).toHaveAttribute("aria-busy", "false"));
    expect(sent).toMatchObject({ content: "Analyze the portfolio in this screenshot.", image: { media_type: "image/png" } });
    expect(sent).toMatchObject({ image: { data: btoa(String.fromCharCode(0x89, 0x50, 0x4e, 0x47)) } });

    const table = within(answer).getByRole("region", { name: "Holdings read from your screenshot" });
    expect(table).toHaveTextContent("VTI");
    expect(table).toHaveTextContent("281.50");
    expect(table).toHaveTextContent("Couldn't price: ZZZZ.");
    expect(await screen.findByText("Screenshot attached (not stored)")).toBeInTheDocument();
  });
});
