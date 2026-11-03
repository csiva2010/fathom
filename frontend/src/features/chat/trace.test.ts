import { describe, expect, it } from "vitest";

import type { TraceStep } from "@/api/types";
import { traceStep } from "@/test/fixtures";

import { applyEvent, emptyDraft } from "./hooks/chatState";
import { describeStep, formatMs, modelName, nodeLabel, timeline, totals } from "./trace";

const step = traceStep;

describe("trace timeline", () => {
  it("runs parallel agents side by side and the rest one after another", () => {
    const { rows, total } = timeline([
      step("load_context", 10),
      step("router", 100),
      step("finance_qa", 500),
      step("market_analysis", 800),
      step("synthesizer", 300),
      step("compliance", 5),
    ]);
    expect(rows.map((r) => [r.step.node, r.start])).toEqual([
      ["load_context", 0],
      ["router", 10],
      ["finance_qa", 110],
      ["market_analysis", 110],
      ["synthesizer", 910],
      ["compliance", 1210],
    ]);
    expect(total).toBe(1215);
    expect(timeline([])).toEqual({ rows: [], total: 0 });
  });

  it("totals usage across steps and keeps each model once", () => {
    const sums = totals([
      step("router", 1, { llm_calls: 1, input_tokens: 10, output_tokens: 2, models: ["a:x"] }),
      step("finance_qa", 1, { llm_calls: 2, input_tokens: 5, models: ["a:x", "b:y"], tools: ["search_kb", "define_term"], fallbacks: 1 }),
      step("compliance", 1),
    ]);
    expect(sums).toEqual({ llmCalls: 3, inputTokens: 15, outputTokens: 2, tools: 2, fallbacks: 1, models: ["a:x", "b:y"] });
  });

  it("formats times, names and labels", () => {
    expect(formatMs(42.4)).toBe("42 ms");
    expect(formatMs(2450)).toBe("2.5 s");
    expect(modelName("anthropic:claude-sonnet")).toBe("claude-sonnet");
    expect(modelName("plain")).toBe("plain");
    expect(nodeLabel("router")).toBe("Chose the agents");
    expect(nodeLabel("goal_planning")).toBe("Goal Planning agent");
    expect(nodeLabel("something_new")).toBe("something new");
  });
});

describe("describeStep", () => {
  it("says what each node decided", () => {
    const cases: [TraceStep, string | null][] = [
      [step("load_context", 1, { detail: { level: "advanced", has_portfolio: true, goals: 1 } }), "advanced level · saved portfolio · 1 goal"],
      [step("router", 1, { detail: { advice: true } }), "Advice request: answered with an educational redirect"],
      [step("router", 1, { detail: { clarify: true } }), "Not sure what was asked: asked a clarifying question"],
      [step("router", 1, { detail: { method: "rules", agents: ["market_analysis", "x"] } }), "Picked Market Analysis, x using keyword rules (no model available)"],
      [step("router", 1, { detail: {} }), "Picked an agent using the language model"],
      [step("read_screenshot", 1, { detail: { status: "read", holdings: 4 } }), "Found 4 holdings"],
      [step("read_screenshot", 1, { detail: { status: "empty" } }), "Screenshot empty"],
      [step("synthesizer", 1, { detail: { merged_by: "llm", agents: 2 } }), "Merged 2 agent answers"],
      [step("synthesizer", 1, { detail: { merged_by: "joined", agents: 2 } }), "Joined 2 agent answers"],
      [step("synthesizer", 1, { detail: { merged_by: "none" } }), null],
      [step("compliance", 1, { detail: { issues: ["advice_language"], rewritten: true } }), "Fixed: advice language · rewrote advice-like wording"],
      [step("market_analysis", 1, { detail: { citations: 0, artifacts: ["quote_card", "indicators"], attempts: 2 } }), "0 sources · 2 charts · 2 attempts"],
      [step("finance_qa", 1, { detail: { citations: 1 } }), "1 source"],
      [step("news_synthesizer", 1, { detail: { error: "timeout" } }), "Failed: timeout"],
      [step("clarify", 1), null],
    ];
    for (const [input, expected] of cases) expect(describeStep(input)).toBe(expected);
  });
});

describe("applyEvent trace", () => {
  it("collects steps while streaming and takes the message's trace when done", () => {
    let draft = applyEvent(emptyDraft(), { type: "trace", step: step("load_context", 3) });
    draft = applyEvent(draft, { type: "agent_start", agent: "finance_qa" });
    expect(draft.trace.map((s) => s.node)).toEqual(["load_context"]);
    draft = applyEvent(draft, {
      type: "done",
      message: { id: "m", role: "assistant", kind: "answer", content: "x", has_image: false, trace: [step("router", 1)] },
    });
    expect(draft.trace.map((s) => s.node)).toEqual(["router"]);
  });
});
