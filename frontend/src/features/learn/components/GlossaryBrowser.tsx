import { useState } from "react";

import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import { INPUT_CLASS } from "@/components/ui/styles";
import { useDebounced } from "@/lib/hooks/useDebounced";

import { useGlossary } from "../hooks/useLearn";
import { LevelBadge } from "./LevelBadge";

/** Search the glossary; related terms are one click away. */
export function GlossaryBrowser() {
  const [q, setQ] = useState("");
  const glossary = useGlossary(useDebounced(q.trim()));

  return (
    <div className="space-y-4">
      <div>
        <label htmlFor="glossary-search" className="sr-only">
          Search the glossary
        </label>
        <input
          id="glossary-search"
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Look up a term, e.g. expense ratio"
          className={INPUT_CLASS}
        />
      </div>
      {glossary.isPending && <LoadingState label="Loading glossary" />}
      {glossary.isError && <ErrorState title="Couldn't load the glossary" error={glossary.error} onRetry={() => void glossary.refetch()} />}
      {glossary.data && glossary.data.terms.length === 0 && <EmptyState title={`No terms match "${q}"`} />}
      {glossary.data && glossary.data.terms.length > 0 && (
        <dl className="divide-y divide-slate-100 rounded-xl border border-slate-200 dark:divide-slate-800 dark:border-slate-700">
          {glossary.data.terms.map((t) => (
            <div key={t.term} className="space-y-1 p-4">
              <dt className="flex flex-wrap items-center gap-2 font-semibold">
                {t.term}
                <LevelBadge level={t.level ?? "beginner"} />
              </dt>
              <dd className="text-sm text-slate-700 dark:text-slate-200">{t.definition}</dd>
              {t.related && t.related.length > 0 && (
                <dd className="flex flex-wrap items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
                  Related:
                  {t.related.map((r) => (
                    <button key={r} type="button" onClick={() => setQ(r)} className="text-emerald-700 underline dark:text-emerald-300">
                      {r}
                    </button>
                  ))}
                </dd>
              )}
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
