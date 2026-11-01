import { useState, type FormEvent } from "react";

import type { Goal, GoalIn, GoalType, RiskProfileName } from "@/api/types";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { INPUT_CLASS, LABEL_CLASS } from "@/components/ui/styles";

import { useSaveGoal } from "../hooks/useGoals";
import { GOAL_TYPES, RISK_PROFILES } from "../labels";

function inYears(years: number): string {
  const d = new Date();
  d.setFullYear(d.getFullYear() + years);
  return d.toISOString().slice(0, 10);
}

/** GL-02: type, target amount and date, current savings, monthly contribution. */
export function GoalForm({ goal, onDone }: { goal?: Goal; onDone: (saved?: Goal) => void }) {
  const save = useSaveGoal();
  const [type, setType] = useState<GoalType>(goal?.type ?? "house");
  const [name, setName] = useState(goal?.name ?? "");
  const [target, setTarget] = useState(String(goal?.target_amount ?? ""));
  const [date, setDate] = useState(goal?.target_date ?? inYears(5));
  const [savings, setSavings] = useState(String(goal?.current_savings ?? "0"));
  const [monthly, setMonthly] = useState(String(goal?.monthly_contribution ?? "0"));
  const [profile, setProfile] = useState<RiskProfileName | "">(goal?.risk_profile ?? "");

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    const body: GoalIn = {
      type,
      name,
      target_amount: Number(target),
      target_date: date,
      current_savings: Number(savings) || 0,
      monthly_contribution: Number(monthly) || 0,
      risk_profile: profile || null,
    };
    save.mutate({ id: goal?.id, body }, { onSuccess: (saved) => onDone(saved) });
  };

  return (
    <Card title={goal ? "Edit goal" : "Add a goal"}>
      <form onSubmit={onSubmit} className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="goal-type" className={LABEL_CLASS}>
            Goal type
          </label>
          <select id="goal-type" value={type} onChange={(e) => setType(e.target.value as GoalType)} className={INPUT_CLASS}>
            {GOAL_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="goal-name" className={LABEL_CLASS}>
            Name (optional)
          </label>
          <input id="goal-name" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} className={INPUT_CLASS} />
        </div>
        <div>
          <label htmlFor="goal-target" className={LABEL_CLASS}>
            Target amount ($)
          </label>
          <input id="goal-target" type="number" min={1} step="any" required value={target} onChange={(e) => setTarget(e.target.value)} className={INPUT_CLASS} />
        </div>
        <div>
          <label htmlFor="goal-date" className={LABEL_CLASS}>
            Target date
          </label>
          <input id="goal-date" type="date" required value={date} onChange={(e) => setDate(e.target.value)} className={INPUT_CLASS} />
        </div>
        <div>
          <label htmlFor="goal-savings" className={LABEL_CLASS}>
            Saved so far ($)
          </label>
          <input id="goal-savings" type="number" min={0} step="any" value={savings} onChange={(e) => setSavings(e.target.value)} className={INPUT_CLASS} />
        </div>
        <div>
          <label htmlFor="goal-monthly" className={LABEL_CLASS}>
            Monthly contribution ($)
          </label>
          <input id="goal-monthly" type="number" min={0} step="any" value={monthly} onChange={(e) => setMonthly(e.target.value)} className={INPUT_CLASS} />
        </div>
        <div className="sm:col-span-2">
          <label htmlFor="goal-profile" className={LABEL_CLASS}>
            Risk profile for this goal
          </label>
          <select id="goal-profile" value={profile} onChange={(e) => setProfile(e.target.value as RiskProfileName | "")} className={INPUT_CLASS}>
            <option value="">Use my profile</option>
            {RISK_PROFILES.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
        {save.isError && (
          <div className="sm:col-span-2">
            <ErrorState title="Couldn't save the goal" error={save.error} />
          </div>
        )}
        <div className="flex gap-2 sm:col-span-2">
          <Button type="submit" disabled={save.isPending || !target}>
            {save.isPending ? "Saving…" : goal ? "Save changes" : "Add goal"}
          </Button>
          <Button variant="ghost" onClick={() => onDone()}>
            Cancel
          </Button>
        </div>
      </form>
    </Card>
  );
}
