import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ME } from "@/test/fixtures";
import { mockFetch } from "@/test/mockFetch";
import { renderApp } from "@/test/renderApp";
import { ARTICLE, ARTICLES } from "@/test/viewFixtures";

describe("Learn", () => {
  it("browses, filters and opens an article", async () => {
    const queries: string[] = [];
    mockFetch({
      "GET /me": () => ({ body: ME }),
      "GET /kb/articles": () => ({ body: ARTICLES }),
      "GET /kb/articles/wash-sale-rule": () => ({ body: ARTICLE }),
    });
    const fetchSpy = globalThis.fetch as unknown as { mock: { calls: [RequestInfo][] } };
    renderApp("/learn");

    expect(await screen.findByText("2 articles")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /^Tax/ }));
    await userEvent.type(screen.getByLabelText("Search articles"), "wash");
    await waitFor(() => {
      for (const [url] of fetchSpy.mock.calls) queries.push(String(url));
      expect(queries.some((u) => u.includes("category=tax") && u.includes("q=wash"))).toBe(true);
    });
    expect(window.location.search).toContain("category=tax");

    await userEvent.click(screen.getByRole("link", { name: /The Wash Sale Rule/ }));
    expect(await screen.findByText("you sell at a loss", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "IRS" })).toHaveAttribute("href", "https://www.irs.gov/p550");
    expect(screen.getByText("2 min read")).toBeInTheDocument();

    // What to read next, and a hand-off to Chat with the question waiting in the composer.
    const next = screen.getByRole("region", { name: "Keep learning" });
    expect(within(next).getByRole("link", { name: /Tax-Loss Harvesting/ })).toHaveAttribute("href", "/learn/tax-loss-harvesting");
    mockFetch({
      "GET /me": () => ({ body: ME }),
      "GET /conversations": () => ({ body: { conversations: [] } }),
    });
    await userEvent.click(screen.getByRole("link", { name: "Ask Fathom about this" }));
    expect(await screen.findByLabelText("Ask a question")).toHaveValue('Help me understand "The Wash Sale Rule" with an example.');
    expect(window.location.pathname).toBe("/chat");
  });

  it("searches the glossary and follows related terms", async () => {
    mockFetch({
      "GET /me": () => ({ body: ME }),
      "GET /kb/articles": () => ({ body: ARTICLES }),
      "GET /kb/glossary": () => ({
        body: {
          total: 2,
          terms: [{ term: "Roth IRA", definition: "An IRA funded with after-tax money.", level: "beginner", related: ["Traditional IRA"], aliases: [] }],
        },
      }),
    });
    renderApp("/learn");
    await userEvent.click(await screen.findByRole("tab", { name: "Glossary" }));
    const term = await screen.findByText("An IRA funded with after-tax money.");
    await userEvent.click(within(term.closest("div") as HTMLElement).getByRole("button", { name: "Traditional IRA" }));
    expect(screen.getByLabelText("Search the glossary")).toHaveValue("Traditional IRA");
  });

  it("shows empty and error states", async () => {
    mockFetch({
      "GET /me": () => ({ body: ME }),
      "GET /kb/articles": () => ({ body: { ...ARTICLES, articles: [] } }),
      "GET /kb/articles/missing": () => ({ status: 404, body: { error: { code: "not_found", message: "That article doesn't exist.", retryable: false } } }),
    });
    renderApp("/learn?q=zebra");
    expect(await screen.findByText("No articles match")).toBeInTheDocument();
    renderApp("/learn/missing");
    expect(await screen.findByText("That article doesn't exist.")).toBeInTheDocument();
  });
});
