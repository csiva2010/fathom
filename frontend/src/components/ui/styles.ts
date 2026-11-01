/** Shared form-control classes so every view's inputs look and focus the same. */
export const INPUT_CLASS =
  "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-emerald-600 focus-visible:ring-2 focus-visible:ring-emerald-600/30 dark:border-slate-600 dark:bg-slate-900";

export const LABEL_CLASS = "mb-1 block text-xs font-medium text-slate-600 dark:text-slate-300";

export function chipClass(active: boolean): string {
  return `whitespace-nowrap rounded-full border px-3 py-1 text-xs font-medium ${
    active
      ? "border-emerald-700 bg-emerald-700 text-white dark:border-emerald-500 dark:bg-emerald-600"
      : "border-slate-300 text-slate-700 hover:border-emerald-600 dark:border-slate-600 dark:text-slate-200"
  }`;
}
