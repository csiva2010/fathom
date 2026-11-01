import type { IndexOut } from "@/api/types";
import { FreshnessBadge } from "@/components/badges/FreshnessBadge";
import { direction, formatChange, formatPrice } from "@/lib/format/number";

const TONE = {
  up: "text-emerald-700 dark:text-emerald-400",
  down: "text-rose-700 dark:text-rose-400",
  flat: "text-slate-600 dark:text-slate-300",
} as const;

const ARROW = { up: "▲", down: "▼", flat: "■" } as const;

export function IndexCard({ item }: { item: IndexOut }) {
  const { index, freshness } = item;
  const dir = direction(index.change_percent ?? index.change);
  return (
    <article className="rounded-xl border border-slate-200 p-5 dark:border-slate-800" aria-label={index.name}>
      <div className="flex items-start justify-between gap-2">
        <h2 className="font-medium">{index.name}</h2>
        <FreshnessBadge freshness={freshness} />
      </div>
      <p className="mt-3 text-3xl font-semibold tabular-nums">{formatPrice(index.price)}</p>
      <p className={`mt-1 text-sm font-medium tabular-nums ${TONE[dir]}`}>
        <span aria-hidden>{ARROW[dir]} </span>
        {formatChange(index.change, index.change_percent)}
      </p>
      {index.is_proxy && (
        <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
          Shown via the {index.symbol} ETF, which tracks this index. Its price differs from the index level but
          its daily % move is very similar.
        </p>
      )}
    </article>
  );
}
