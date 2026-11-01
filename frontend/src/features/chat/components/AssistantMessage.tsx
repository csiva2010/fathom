import { FreshnessBadge } from "@/components/badges/FreshnessBadge";
import { Button } from "@/components/ui/Button";

import { AGENT_LABELS } from "../agents";
import { ArtifactView } from "../artifacts/ArtifactView";
import type { DraftAnswer } from "../hooks/chatState";
import { AgentBadges } from "./AgentBadges";
import { FollowUps } from "./FollowUps";
import { MessageMarkdown } from "./MessageMarkdown";
import { SourceCards } from "./SourceCards";

interface AssistantMessageProps {
  id: string;
  answer: DraftAnswer;
  onAsk?: (question: string) => void;
  onRetry?: () => void;
  busy?: boolean;
}

function Working({ answer }: { answer: DraftAnswer }) {
  const label =
    answer.status === "routing"
      ? "Working out who should answer"
      : `Asking ${answer.agents.map((a) => AGENT_LABELS[a]).join(" and ")}`;
  return (
    <p role="status" className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
      <span className="h-3 w-3 animate-spin rounded-full border-2 border-slate-300 border-t-emerald-600" aria-hidden />
      {label}…
    </p>
  );
}

export function AssistantMessage({ id, answer, onAsk, onRetry, busy }: AssistantMessageProps) {
  const working = answer.status === "routing" || answer.status === "streaming";
  const stamps = answer.freshness.filter(
    (f, i, all) => all.findIndex((g) => g.source === f.source && g.status === f.status) === i,
  );
  return (
    <article aria-label="Assistant answer" aria-busy={working} className="space-y-3">
      <AgentBadges agents={answer.agents} working={working} />
      {answer.content ? (
        <MessageMarkdown content={answer.content} messageId={id} citationCount={answer.citations.length} />
      ) : (
        working && <Working answer={answer} />
      )}
      {answer.artifacts.map((artifact, index) => (
        <ArtifactView key={`${artifact.kind}-${index}`} artifact={artifact} />
      ))}
      {stamps.length > 0 && answer.status === "done" && (
        <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
          Data:
          {stamps.map((f) => (
            <FreshnessBadge key={`${f.source}-${f.status}`} freshness={f} />
          ))}
        </div>
      )}
      <SourceCards citations={answer.citations} messageId={id} />
      {answer.status === "error" && (
        <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-200">
          <p>{answer.error?.message ?? "Something went wrong."}</p>
          {onRetry && answer.error?.retryable && (
            <Button variant="secondary" className="mt-2" onClick={onRetry}>
              Try again
            </Button>
          )}
        </div>
      )}
      {answer.status === "done" && onAsk && <FollowUps questions={answer.followUps} onAsk={onAsk} disabled={busy} />}
    </article>
  );
}
