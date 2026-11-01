import type { ReactNode } from "react";

import type { Freshness } from "@/api/types";
import { FreshnessBadge } from "@/components/badges/FreshnessBadge";

/** A titled panel; freshness stamps are de-duplicated by source and status (UI-08). */
export function Card({
  title,
  freshness,
  actions,
  children,
  className = "",
}: {
  title: string;
  freshness?: Freshness[];
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const stamps = (freshness ?? []).filter(
    (f, i, all) => all.findIndex((g) => g.source === f.source && g.status === f.status) === i,
  );
  return (
    <section
      aria-label={title}
      className={`space-y-3 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900 ${className}`}
    >
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">{title}</h2>
        <div className="flex flex-wrap items-center gap-1.5">
          {stamps.map((f) => (
            <FreshnessBadge key={`${f.source}-${f.status}`} freshness={f} />
          ))}
          {actions}
        </div>
      </header>
      {children}
    </section>
  );
}

export function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-800/60">
      <dt className="text-xs text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="text-base font-semibold tabular-nums">{value}</dd>
      {hint && <dd className="text-xs text-slate-500 dark:text-slate-400">{hint}</dd>}
    </div>
  );
}
