import type { AgentName } from "@/api/types";

import { AGENT_LABELS } from "../agents";

/** Which agents produced (or are producing) an answer (CH-03). */
export function AgentBadges({ agents, working = false }: { agents: AgentName[]; working?: boolean }) {
  if (agents.length === 0) return null;
  return (
    <ul aria-label="Answered by" className="flex flex-wrap gap-1.5">
      {agents.map((agent) => (
        <li
          key={agent}
          className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-200"
        >
          {working && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-600" aria-hidden />}
          {AGENT_LABELS[agent]}
        </li>
      ))}
    </ul>
  );
}
