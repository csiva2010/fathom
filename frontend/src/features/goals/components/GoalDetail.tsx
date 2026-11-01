import { useState } from "react";

import type { Goal, ProjectionRequest } from "@/api/types";
import { ProjectionChart, ShareBars, type ProjectionSeriesPoint } from "@/components/charts/charts";
import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { formatUsd } from "@/lib/format/money";
import { useDebounced } from "@/lib/hooks/useDebounced";

import { useDeleteGoal, useProjection, useSaveGoal } from "../hooks/useGoals";
import { goalTitle } from "../labels";

const SCENARIO_ORDER = ["expected", "pessimistic", "optimistic"];

function sliderMax(goal: Goal): number {
  const needed = Math.max(0, ...(goal.projection?.scenarios.map((s) => s.required_monthly_contribution) ?? [0]));
  return Math.max(500, Math.ceil((Math.max(needed, goal.monthly_contribution) * 1.5) / 100) * 100);
}

/** GL-03, UI-06: projection band with a contribution slider that recalculates live. */
export function GoalDetail({ goal, onEdit, onDeleted }: { goal: Goal; onEdit: () => void; onDeleted: () => void }) {
  // The page keys this component by goal id, so the slider starts fresh for each goal.
  const [monthly, setMonthly] = useState(goal.monthly_contribution);
  const debounced = useDebounced(monthly, 150);
  const inputs: ProjectionRequest | null = goal.projection
    ? {
        target_amount: goal.target_amount,
        target_date: goal.target_date,
        current_savings: goal.current_savings,
        monthly_contribution: debounced,
        risk_profile: goal.risk_profile,
      }
    : null;
  const live = useProjection(inputs);
  const save = useSaveGoal();
  const remove = useDeleteGoal();
  const projection = live.data?.projection ?? goal.projection;
  const max = sliderMax(goal);
  const changed = monthly !== goal.monthly_contribution;

  const onDelete = () => {
    if (window.confirm(`Delete "${goalTitle(goal)}"?`)) remove.mutate(goal.id, { onSuccess: onDeleted });
  };
  const saveMonthly = () =>
    save.mutate({
      id: goal.id,
      body: {
        type: goal.type,
        name: goal.name,
        target_amount: goal.target_amount,
        target_date: goal.target_date,
        current_savings: goal.current_savings,
        monthly_contribution: monthly,
        risk_profile: goal.risk_profile,
      },
    });

  const expected = projection?.scenarios.find((s) => s.scenario === "expected");
  const scenarios = [...(projection?.scenarios ?? [])].sort((a, b) => SCENARIO_ORDER.indexOf(a.scenario) - SCENARIO_ORDER.indexOf(b.scenario));
  const targetDate = new Date(goal.target_date).toLocaleDateString("en-US", { month: "short", year: "numeric", timeZone: "UTC" });

  return (
    <div className="space-y-4">
      <Card
        title={goalTitle(goal)}
        actions={
          <>
            <Button variant="ghost" onClick={onEdit}>
              Edit
            </Button>
            <Button variant="ghost" onClick={onDelete} disabled={remove.isPending}>
              Delete
            </Button>
          </>
        }
      >
        <p className="text-sm text-slate-600 dark:text-slate-300">
          {formatUsd(goal.target_amount)} by {targetDate} · {formatUsd(goal.current_savings)} saved · {goal.risk_profile} assumptions
        </p>
        {!projection && (
          <ErrorState title="This goal can't be projected" error={new Error(goal.projection_error ?? "Check the goal's target date.")} />
        )}
        {projection && (
          <>
            <ProjectionChart series={projection.series as ProjectionSeriesPoint[]} target={goal.target_amount} />
            <div className="space-y-2 rounded-lg bg-slate-50 p-3 dark:bg-slate-800/60">
              <label htmlFor="monthly-slider" className="flex items-baseline justify-between text-sm font-medium">
                Monthly contribution
                <span className="tabular-nums">{formatUsd(monthly)} a month</span>
              </label>
              <input
                id="monthly-slider"
                type="range"
                min={0}
                max={max}
                step={25}
                value={monthly}
                onChange={(e) => setMonthly(Number(e.target.value))}
                aria-valuetext={`${formatUsd(monthly)} a month`}
                className="w-full accent-emerald-700"
              />
              {expected && (
                <p className="text-sm" aria-live="polite">
                  In the expected scenario you'd reach about <strong>{formatUsd(expected.final_value)}</strong>
                  {expected.reaches_target ? (
                    <>, which meets the target.</>
                  ) : (
                    <>
                      , {formatUsd(expected.shortfall)} short. Reaching the target in that scenario takes about{" "}
                      <strong>{formatUsd(expected.required_monthly_contribution)} a month</strong>.
                    </>
                  )}
                  {live.isFetching && <span className="sr-only"> Updating…</span>}
                </p>
              )}
              {changed && (
                <div className="flex gap-2">
                  <Button onClick={saveMonthly} disabled={save.isPending}>
                    Save {formatUsd(monthly)} a month
                  </Button>
                  <Button variant="ghost" onClick={() => setMonthly(goal.monthly_contribution)}>
                    Reset
                  </Button>
                </div>
              )}
            </div>
            <table className="w-full text-sm">
              <caption className="sr-only">Projection by scenario</caption>
              <thead className="text-left text-xs text-slate-500 dark:text-slate-400">
                <tr>
                  <th className="py-1 font-medium">Scenario</th>
                  <th className="py-1 text-right font-medium">Ends near</th>
                  <th className="py-1 text-right font-medium">In today&apos;s $</th>
                  <th className="py-1 text-right font-medium">Monthly needed</th>
                </tr>
              </thead>
              <tbody>
                {scenarios.map((s) => (
                  <tr key={s.scenario} className="border-t border-slate-100 tabular-nums dark:border-slate-800">
                    <td className="py-1">
                      <span className="capitalize">{s.scenario}</span> ({s.annual_return_percent}%/yr)
                    </td>
                    <td className="py-1 text-right">
                      {formatUsd(s.final_value)} {s.reaches_target ? "✓" : ""}
                      <span className="sr-only">{s.reaches_target ? "reaches target" : "short of target"}</span>
                    </td>
                    <td className="py-1 text-right">{formatUsd(s.final_value_real)}</td>
                    <td className="py-1 text-right">{formatUsd(s.required_monthly_contribution)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="text-xs text-slate-500 dark:text-slate-400">{projection.assumptions}</p>
          </>
        )}
        {live.isError && <ErrorState title="Couldn't update the projection" error={live.error} />}
      </Card>
      {live.isPending && inputs && <LoadingState label="Loading example mix" />}
      {live.data && (
        <Card title={`Example ${live.data.example_allocation.risk_profile} mix (education only)`}>
          <ShareBars
            label="Example allocation"
            data={live.data.example_allocation.slices.map((s) => ({ label: s.asset_class.charAt(0).toUpperCase() + s.asset_class.slice(1), weight: s.weight }))}
          />
          <p className="text-xs text-slate-500 dark:text-slate-400">{live.data.example_allocation.note}</p>
        </Card>
      )}
    </div>
  );
}
