import type { DataStatus, Freshness } from "@/api/types";
import { timeAgo } from "@/lib/format/time";

const STYLES: Record<DataStatus, { label: string; className: string }> = {
  live: {
    label: "Live",
    className: "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/50 dark:text-emerald-200",
  },
  cached: {
    label: "Cached",
    className: "bg-amber-100 text-amber-900 dark:bg-amber-900/50 dark:text-amber-200",
  },
  mock: {
    label: "Sample data",
    className: "bg-slate-200 text-slate-800 dark:bg-slate-700 dark:text-slate-100",
  },
};

/** Shows where a number came from and how fresh it is (MD-07, UI-08). */
export function FreshnessBadge({ freshness }: { freshness: Freshness }) {
  const style = STYLES[freshness.status];
  const when = timeAgo(freshness.as_of);
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${style.className}`}
      title={`Source: ${freshness.source} · ${new Date(freshness.as_of).toLocaleString()}`}
    >
      {style.label}
      <span className="opacity-75">· {when}</span>
    </span>
  );
}
