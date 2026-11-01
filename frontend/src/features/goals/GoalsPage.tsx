import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import type { Goal } from "@/api/types";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { formatUsd } from "@/lib/format/money";

import { GoalDetail } from "./components/GoalDetail";
import { GoalForm } from "./components/GoalForm";
import { RiskProfileCard } from "./components/RiskProfileCard";
import { useGoals } from "./hooks/useGoals";
import { goalTitle } from "./labels";

function onTrack(goal: Goal): boolean | null {
  const expected = goal.projection?.scenarios.find((s) => s.scenario === "expected");
  return expected ? expected.reaches_target : null;
}

/** The Goals tab (GL-01 to GL-04, UI-06). */
export function GoalsPage() {
  const goals = useGoals();
  const [params, setParams] = useSearchParams();
  const [editing, setEditing] = useState<"new" | "edit" | null>(null);
  const list = goals.data?.goals ?? [];
  const selected = list.find((g) => g.id === params.get("goal")) ?? list[0];
  const select = (id?: string) => setParams(id ? { goal: id } : {}, { replace: true });

  return (
    <section className="space-y-6">
      <PageHeader
        title="Goals"
        description="Project savings goals under three return scenarios at your risk level. Illustrations, not predictions."
        actions={
          editing === null && (
            <Button onClick={() => setEditing("new")} disabled={!goals.data}>
              Add a goal
            </Button>
          )
        }
      />
      <RiskProfileCard />
      {goals.isPending && <LoadingState label="Loading goals" />}
      {goals.isError && <ErrorState title="Couldn't load your goals" error={goals.error} onRetry={() => void goals.refetch()} />}
      {editing && (
        <GoalForm
          goal={editing === "edit" ? selected : undefined}
          onDone={(saved) => {
            setEditing(null);
            if (saved) select(saved.id);
          }}
        />
      )}
      {goals.data && list.length === 0 && !editing && (
        <EmptyState title="No goals yet">
          Add a goal such as a home deposit, an emergency fund or retirement to see how it could grow.
          <div className="mt-3">
            <Button onClick={() => setEditing("new")}>Add your first goal</Button>
          </div>
        </EmptyState>
      )}
      {list.length > 0 && selected && editing === null && (
        <div className="grid gap-4 lg:grid-cols-[16rem_1fr]">
          <ul aria-label="Your goals" className="space-y-2">
            {list.map((g) => {
              const status = onTrack(g);
              return (
                <li key={g.id}>
                  <button
                    type="button"
                    onClick={() => select(g.id)}
                    aria-current={g.id === selected.id}
                    className={`w-full rounded-xl border p-3 text-left text-sm ${
                      g.id === selected.id
                        ? "border-emerald-600 bg-emerald-50 dark:bg-emerald-900/30"
                        : "border-slate-200 hover:border-emerald-600 dark:border-slate-700"
                    }`}
                  >
                    <span className="block font-medium">{goalTitle(g)}</span>
                    <span className="block text-xs text-slate-500 dark:text-slate-400">
                      {formatUsd(g.target_amount)} by {g.target_date.slice(0, 4)}
                    </span>
                    {status !== null && (
                      <span className={`mt-1 inline-block text-xs font-medium ${status ? "text-emerald-700 dark:text-emerald-300" : "text-amber-700 dark:text-amber-300"}`}>
                        {status ? "✓ On track (expected case)" : "Short in the expected case"}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
          <GoalDetail key={selected.id} goal={selected} onEdit={() => setEditing("edit")} onDeleted={() => select()} />
        </div>
      )}
    </section>
  );
}
