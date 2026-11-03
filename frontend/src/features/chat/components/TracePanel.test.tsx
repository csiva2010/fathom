import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { traceStep } from "@/test/fixtures";

import { TracePanel } from "./TracePanel";

describe("TracePanel", () => {
  it("renders nothing without steps", () => {
    const { container } = render(<TracePanel steps={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("explains a rules-only turn and marks failed steps and fallbacks", () => {
    render(
      <TracePanel
        live
        steps={[
          traceStep("router", 2, { detail: { method: "rules", agents: ["news_synthesizer"] } }),
          traceStep("news_synthesizer", 30000, { detail: { error: "timeout", attempts: 2 } }),
        ]}
      />,
    );
    expect(screen.getByText("running…")).toBeInTheDocument();
    expect(screen.getByText("2 steps · 30.0 s")).toBeInTheDocument();
    expect(screen.getByText("Failed: timeout")).toBeInTheDocument();
    expect(screen.getByText(/No language model was used/)).toBeInTheDocument();
  });

  it("reports a fallback model", () => {
    render(
      <TracePanel
        steps={[traceStep("router", 900, { llm_calls: 1, fallbacks: 1, models: ["anthropic:claude-haiku"] })]}
      />,
    );
    expect(screen.getByText("1 step · 900 ms · 1 model call")).toBeInTheDocument();
    expect(screen.getByText(/· fallback model/)).toBeInTheDocument();
    expect(screen.getByText("Model: claude-haiku · 1 answered by a fallback model")).toBeInTheDocument();
  });
});
