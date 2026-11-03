import type { AgentName, TraceStep } from "@/api/types";

import { AGENT_LABELS } from "./agents";

/** What each workflow node did, in the words the "How I answered" panel uses (INN-01). */
const NODE_LABELS: Record<string, string> = {
  load_context: "Loaded your profile",
  read_screenshot: "Read the screenshot",
  router: "Chose the agents",
  clarify: "Asked a clarifying question",
  advice_redirect: "Redirected an advice request",
  synthesizer: "Wrote the final answer",
  compliance: "Compliance check",
};

export function isAgentNode(node: string): node is AgentName {
  return node in AGENT_LABELS;
}

export function nodeLabel(node: string): string {
  if (isAgentNode(node)) return `${AGENT_LABELS[node]} agent`;
  return NODE_LABELS[node] ?? node.replace(/_/g, " ");
}

export interface TimedStep {
  step: TraceStep;
  start: number; // ms from the start of the turn
}

/**
 * Lay the steps out on a timeline. The graph runs in supersteps: agents planned for the
 * same turn run in parallel and the next node waits for the slowest, so consecutive agent
 * steps share a start time. Everything else runs one after another.
 */
export function timeline(steps: TraceStep[]): { rows: TimedStep[]; total: number } {
  const rows: TimedStep[] = [];
  let clock = 0;
  let index = 0;
  const agentAt = (i: number) => isAgentNode(steps[i]?.node ?? "");
  while (index < steps.length) {
    let end = index + 1;
    if (agentAt(index)) {
      while (end < steps.length && agentAt(end)) end += 1;
    }
    const stage = steps.slice(index, end);
    for (const step of stage) rows.push({ step, start: clock });
    clock += Math.max(...stage.map((s) => s.latency_ms));
    index = end;
  }
  return { rows, total: clock };
}

export interface TraceTotals {
  llmCalls: number;
  inputTokens: number;
  outputTokens: number;
  tools: number;
  fallbacks: number;
  models: string[];
}

export function totals(steps: TraceStep[]): TraceTotals {
  const models: string[] = [];
  for (const step of steps) for (const m of step.models ?? []) if (!models.includes(m)) models.push(m);
  return {
    llmCalls: sum(steps, (s) => s.llm_calls ?? 0),
    inputTokens: sum(steps, (s) => s.input_tokens ?? 0),
    outputTokens: sum(steps, (s) => s.output_tokens ?? 0),
    tools: sum(steps, (s) => s.tools?.length ?? 0),
    fallbacks: sum(steps, (s) => s.fallbacks ?? 0),
    models,
  };
}

function sum(steps: TraceStep[], pick: (s: TraceStep) => number): number {
  return steps.reduce((acc, s) => acc + pick(s), 0);
}

export function formatMs(ms: number): string {
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;
}

/** "gemini:gemini-2.5-flash" -> "gemini-2.5-flash" */
export function modelName(model: string): string {
  return model.includes(":") ? model.slice(model.indexOf(":") + 1) : model;
}

type Detail = Record<string, unknown>;

/** One plain-language line about what a step decided, from its `detail`. */
export function describeStep(step: TraceStep): string | null {
  const d = (step.detail ?? {}) as Detail;
  if (typeof d.error === "string") return `Failed: ${d.error.replace(/_/g, " ")}`;
  switch (step.node) {
    case "load_context": {
      const parts = [`${String(d.level ?? "beginner")} level`];
      parts.push(d.has_portfolio ? "saved portfolio" : "no saved portfolio");
      if (typeof d.goals === "number") parts.push(`${d.goals} goal${d.goals === 1 ? "" : "s"}`);
      return parts.join(" · ");
    }
    case "router": {
      if (d.advice) return "Advice request: answered with an educational redirect";
      if (d.clarify) return "Not sure what was asked: asked a clarifying question";
      const agents = Array.isArray(d.agents) ? (d.agents as string[]) : [];
      const how = d.method === "rules" ? "keyword rules (no model available)" : "the language model";
      const names = agents.map((a) => (isAgentNode(a) ? AGENT_LABELS[a] : a)).join(", ");
      const confidence = typeof d.confidence === "number" ? `, ${Math.round(d.confidence * 100)}% confident` : "";
      return `Picked ${names || "an agent"} using ${how}${confidence}`;
    }
    case "read_screenshot":
      return d.status === "read" ? `Found ${String(d.holdings)} holdings` : `Screenshot ${String(d.status ?? "not read")}`;
    case "synthesizer":
      return d.merged_by === "llm"
        ? `Merged ${String(d.agents)} agent answers`
        : d.merged_by === "joined"
          ? `Joined ${String(d.agents)} agent answers`
          : d.merged_by === "passthrough"
            ? "Passed one agent's answer through"
            : null;
    case "compliance": {
      const issues = Array.isArray(d.issues) ? (d.issues as string[]) : [];
      const parts = [issues.length ? `Fixed: ${issues.map((i) => i.replace(/_/g, " ")).join(", ")}` : "Passed"];
      if (d.rewritten) parts.push("rewrote advice-like wording");
      if (d.disclaimer_added) parts.push("added the disclaimer");
      return parts.join(" · ");
    }
  }
  if (isAgentNode(step.node)) {
    const sources = typeof d.citations === "number" ? d.citations : 0;
    const artifacts = Array.isArray(d.artifacts) ? d.artifacts.length : 0;
    const parts = [`${sources} source${sources === 1 ? "" : "s"}`];
    if (artifacts) parts.push(`${artifacts} chart${artifacts === 1 ? "" : "s"}`);
    if (typeof d.attempts === "number" && d.attempts > 1) parts.push(`${d.attempts} attempts`);
    return parts.join(" · ");
  }
  return null;
}
