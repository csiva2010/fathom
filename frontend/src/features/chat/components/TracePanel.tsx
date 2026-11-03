import type { TraceStep } from "@/api/types";
import { formatCount } from "@/lib/format/number";

import { describeStep, formatMs, isAgentNode, modelName, nodeLabel, timeline, totals } from "../trace";

/**
 * "How I answered" (OR-08, INN-01): the path a turn took through the workflow, with each
 * step's time, LLM calls, tokens and tool calls. Steps arrive live while the answer streams;
 * the finished message carries the complete trace.
 */
export function TracePanel({ steps, live = false }: { steps: TraceStep[]; live?: boolean }) {
  if (steps.length === 0) return null;
  const { rows, total } = timeline(steps);
  const sums = totals(steps);
  const tokens = sums.inputTokens + sums.outputTokens;
  const scale = Math.max(total, 1);

  return (
    <details className="group rounded-lg border border-slate-200 text-sm dark:border-slate-700">
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-2 gap-y-1 px-3 py-2 text-xs text-slate-600 dark:text-slate-300">
        <span className="font-semibold text-slate-800 dark:text-slate-100">How I answered</span>
        <span>
          {steps.length} step{steps.length === 1 ? "" : "s"} · {formatMs(total)}
          {sums.llmCalls > 0 && ` · ${sums.llmCalls} model call${sums.llmCalls === 1 ? "" : "s"}`}
          {tokens > 0 && ` · ${formatCount(tokens)} tokens`}
          {sums.tools > 0 && ` · ${sums.tools} tool call${sums.tools === 1 ? "" : "s"}`}
        </span>
        {live && <span className="text-emerald-700 dark:text-emerald-300">running…</span>}
        <span className="ml-auto group-open:rotate-180" aria-hidden>
          ▾
        </span>
      </summary>
      <div className="space-y-3 border-t border-slate-100 px-3 py-3 dark:border-slate-800">
        <ol aria-label="Workflow steps" className="space-y-2.5">
          {rows.map(({ step, start }, index) => {
            const detail = describeStep(step);
            const failed = typeof (step.detail as Record<string, unknown> | undefined)?.error === "string";
            const stepTokens = (step.input_tokens ?? 0) + (step.output_tokens ?? 0);
            return (
              <li key={`${step.node}-${index}`} className="space-y-1">
                <div className="flex flex-wrap items-baseline gap-x-2 text-xs">
                  <span className={`font-medium ${failed ? "text-rose-700 dark:text-rose-300" : "text-slate-800 dark:text-slate-100"}`}>
                    {nodeLabel(step.node)}
                  </span>
                  <span className="tabular-nums text-slate-500 dark:text-slate-400">{formatMs(step.latency_ms)}</span>
                  {(step.llm_calls ?? 0) > 0 && (
                    <span className="text-slate-500 dark:text-slate-400">
                      {step.llm_calls} model call{step.llm_calls === 1 ? "" : "s"}
                      {stepTokens > 0 && ` · ${formatCount(stepTokens)} tokens`}
                      {(step.fallbacks ?? 0) > 0 && " · fallback model"}
                    </span>
                  )}
                </div>
                {/* Bar position and width show when the step ran within the turn. */}
                <div className="relative h-1.5 rounded-full bg-slate-100 dark:bg-slate-800" aria-hidden>
                  <div
                    className={`absolute inset-y-0 rounded-full ${
                      failed ? "bg-rose-500" : isAgentNode(step.node) ? "bg-emerald-600 dark:bg-emerald-400" : "bg-slate-400 dark:bg-slate-500"
                    }`}
                    style={{
                      left: `${(start / scale) * 100}%`,
                      width: `max(2px, ${(step.latency_ms / scale) * 100}%)`,
                    }}
                  />
                </div>
                {detail && <p className="text-xs text-slate-600 dark:text-slate-300">{detail}</p>}
                {step.tools && step.tools.length > 0 && (
                  <ul aria-label="Tools called" className="flex flex-wrap gap-1">
                    {step.tools.map((tool, i) => (
                      <li key={`${tool}-${i}`} className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-700 dark:bg-slate-800 dark:text-slate-200">
                        {tool}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ol>
        {sums.models.length > 0 && (
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Model{sums.models.length === 1 ? "" : "s"}: {sums.models.map(modelName).join(", ")}
            {sums.inputTokens + sums.outputTokens > 0 &&
              ` · ${formatCount(sums.inputTokens)} in / ${formatCount(sums.outputTokens)} out tokens`}
            {sums.fallbacks > 0 && ` · ${sums.fallbacks} answered by a fallback model`}
          </p>
        )}
        {sums.llmCalls === 0 && (
          <p className="text-xs text-slate-500 dark:text-slate-400">No language model was used: this answer came from rules and templates.</p>
        )}
      </div>
    </details>
  );
}
