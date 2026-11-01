import { describe, expect, it } from "vitest";

import { readEventStream } from "@/api/sse";

import { niceTicks, spreadLabels } from "./artifacts/chartMath";
import { linkCitations } from "./citations";
import { applyEvent, emptyDraft } from "./hooks/chatState";

function streamOf(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      chunks.forEach((c) => controller.enqueue(encoder.encode(c)));
      controller.close();
    },
  });
}

describe("readEventStream", () => {
  it("parses events split across chunks and skips keep-alive comments", async () => {
    const seen: unknown[] = [];
    await readEventStream(
      streamOf('data: {"type":"tok', 'en","text":"Hi"}\r\n\r\n: ping\n\n', 'event: x\ndata: {"type":"done"}'),
      (data) => seen.push(data),
    );
    expect(seen).toEqual([{ type: "token", text: "Hi" }, { type: "done" }]);
  });
});

describe("applyEvent", () => {
  it("builds the draft and lets replace and done supersede streamed text", () => {
    let draft = applyEvent(emptyDraft(), { type: "route", kind: "answer", agents: ["finance_qa"], confidence: 0.8 });
    expect(draft.status).toBe("streaming");
    draft = applyEvent(draft, { type: "token", text: "You should buy" });
    draft = applyEvent(draft, { type: "replace", text: "Index funds hold many stocks." });
    expect(draft.content).toBe("Index funds hold many stocks.");
    draft = applyEvent(draft, { type: "error", code: "x", message: "Oops", retryable: true });
    expect(draft.error).toEqual({ message: "Oops", retryable: true });
    draft = applyEvent(draft, {
      type: "done",
      message: { id: "m", role: "assistant", kind: "redirect", content: "Final", follow_ups: ["Next?"] },
    });
    expect(draft).toMatchObject({ status: "done", kind: "redirect", content: "Final", followUps: ["Next?"], agents: [] });
  });
});

describe("linkCitations", () => {
  it("links only markers that have a source and leaves links alone", () => {
    expect(linkCitations("A [1] B [3] [x](y) [2](z)", "m", 2)).toBe("A [1](#cite-m-1) B [3] [x](y) [2](z)");
  });
});

describe("chart math", () => {
  it("picks nice ticks", () => {
    expect(niceTicks(0, 63_000)).toEqual([0, 20_000, 40_000, 60_000, 80_000]);
    expect(niceTicks(5, 5)).toEqual([5]);
  });

  it("spreads colliding end labels while keeping their order and bounds", () => {
    expect(spreadLabels([50, 52, 120], 14, 10, 200)).toEqual([50, 64, 120]);
    expect(spreadLabels([198, 199], 14, 10, 200)).toEqual([186, 200]);
  });
});
