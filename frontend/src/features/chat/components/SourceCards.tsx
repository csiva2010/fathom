import { Link } from "react-router-dom";

import type { Citation } from "@/api/types";

import { citationAnchor } from "../citations";

/** Expandable source cards; card n matches the answer's [n] marker (CH-04). */
export function SourceCards({ citations, messageId }: { citations: Citation[]; messageId: string }) {
  if (citations.length === 0) return null;
  return (
    <section aria-label="Sources" className="space-y-1.5">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Sources</h3>
      <ol className="space-y-1.5">
        {citations.map((citation, index) => (
          <li key={`${citation.article_id}-${citation.section}`} id={citationAnchor(messageId, index + 1)} className="scroll-mt-24">
            <details className="group rounded-lg border border-slate-200 bg-white text-sm open:shadow-sm dark:border-slate-700 dark:bg-slate-900">
              <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2">
                <span className="font-semibold text-emerald-700 dark:text-emerald-300">[{index + 1}]</span>
                <span className="flex-1 truncate font-medium">{citation.title}</span>
                <span className="text-xs text-slate-500 group-open:rotate-180 dark:text-slate-400" aria-hidden>
                  ▾
                </span>
              </summary>
              <div className="space-y-1 border-t border-slate-100 px-3 py-2 text-xs text-slate-600 dark:border-slate-800 dark:text-slate-300">
                <p>
                  Section: <span className="font-medium text-slate-800 dark:text-slate-100">{citation.section}</span>
                </p>
                <p>
                  <Link to={`/learn/${citation.article_id}`} className="font-medium text-emerald-700 underline dark:text-emerald-300">
                    Read the full article
                  </Link>
                </p>
                <p>
                  Source:{" "}
                  <a href={citation.source_url} target="_blank" rel="noopener noreferrer" className="text-emerald-700 underline dark:text-emerald-300">
                    {citation.source_name}
                  </a>
                </p>
              </div>
            </details>
          </li>
        ))}
      </ol>
    </section>
  );
}
