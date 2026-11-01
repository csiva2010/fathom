import type { ReactNode } from "react";

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center dark:border-slate-700">
      <p className="font-medium text-slate-800 dark:text-slate-100">{title}</p>
      {children && <div className="mt-2 text-sm text-slate-600 dark:text-slate-300">{children}</div>}
    </div>
  );
}
