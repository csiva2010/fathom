import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import type { PortfolioOut } from "@/api/types";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";

import { PortfolioAnalysisView } from "./components/PortfolioAnalysisView";
import { PortfolioEditor } from "./components/PortfolioEditor";
import { useDeletePortfolio, usePortfolios } from "./hooks/usePortfolios";

/** The Portfolio tab (PF-01 to PF-07, UI-04). */
export function PortfolioPage() {
  const portfolios = usePortfolios();
  const remove = useDeletePortfolio();
  const [params, setParams] = useSearchParams();
  const [editing, setEditing] = useState<"new" | "edit" | null>(null);
  const list = portfolios.data?.portfolios ?? [];
  const selected = list.find((p) => p.id === params.get("id")) ?? list[0];
  const select = (id?: string) => setParams(id ? { id } : {}, { replace: true });
  const own = list.filter((p) => !p.is_sample);
  const samples = list.filter((p) => p.is_sample);

  const onDelete = (p: PortfolioOut) => {
    if (window.confirm(`Delete "${p.name}"? This can't be undone.`)) remove.mutate(p.id, { onSuccess: () => select() });
  };

  const group = (title: string, items: PortfolioOut[]) =>
    items.length > 0 && (
      <div>
        <h2 className="mb-1 px-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{title}</h2>
        <ul className="space-y-1">
          {items.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                onClick={() => {
                  setEditing(null);
                  select(p.id);
                }}
                aria-current={selected?.id === p.id}
                className={`w-full rounded-md px-2 py-1.5 text-left text-sm ${
                  selected?.id === p.id
                    ? "bg-emerald-50 font-medium text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-100"
                    : "hover:bg-slate-100 dark:hover:bg-slate-800"
                }`}
              >
                {p.name}
                <span className="block text-xs font-normal text-slate-500 dark:text-slate-400">
                  {p.holdings.length} holding{p.holdings.length === 1 ? "" : "s"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    );

  return (
    <section className="space-y-6">
      <PageHeader
        title="Portfolio"
        description="Enter or import holdings and see what the numbers say. Your latest saved portfolio is what the chat agents use."
        actions={editing === null && <Button onClick={() => setEditing("new")}>New portfolio</Button>}
      />
      {portfolios.isPending && <LoadingState label="Loading portfolios" />}
      {portfolios.isError && <ErrorState title="Couldn't load portfolios" error={portfolios.error} onRetry={() => void portfolios.refetch()} />}
      {portfolios.data && (
        <div className="grid gap-6 lg:grid-cols-[14rem_1fr]">
          <nav aria-label="Portfolios" className="space-y-4">
            {group("Yours", own)}
            {group("Samples", samples)}
            {list.length === 0 && <p className="px-1 text-sm text-slate-500 dark:text-slate-400">No portfolios yet.</p>}
          </nav>
          <div className="min-w-0 space-y-4">
            {editing && (
              <PortfolioEditor
                key={editing === "edit" ? selected?.id : "new"}
                portfolio={editing === "edit" ? selected : undefined}
                onDone={(saved) => {
                  setEditing(null);
                  if (saved) select(saved.id);
                }}
              />
            )}
            {!editing && !selected && (
              <EmptyState title="Add your first portfolio">
                Type in your holdings or import a CSV from your broker. Nothing is ever traded; this is for learning.
              </EmptyState>
            )}
            {!editing && selected && (
              <>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h2 className="text-lg font-semibold">{selected.name}</h2>
                    {selected.description && <p className="text-sm text-slate-600 dark:text-slate-300">{selected.description}</p>}
                  </div>
                  <div className="flex gap-2">
                    <Button variant="secondary" onClick={() => setEditing("edit")}>
                      {selected.is_sample ? "Copy and edit" : "Edit"}
                    </Button>
                    {!selected.is_sample && (
                      <Button variant="ghost" onClick={() => onDelete(selected)} disabled={remove.isPending}>
                        Delete
                      </Button>
                    )}
                  </div>
                </div>
                <PortfolioAnalysisView portfolioId={selected.id} />
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
