import { useState, type FormEvent } from "react";

import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { useAuth } from "@/lib/auth/useAuth";

import { useRiskQuestionnaire, useSubmitRisk } from "../hooks/useGoals";
import { RISK_PROFILES } from "../labels";

/** GL-01: the questionnaire sets the profile used for projections and example mixes. */
export function RiskProfileCard() {
  const { user } = useAuth();
  const profile = user?.profile.risk_profile ?? null;
  const [retaking, setRetaking] = useState(false);
  const open = !profile || retaking;
  const questionnaire = useRiskQuestionnaire(open);
  const submit = useSubmitRisk();
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const described = RISK_PROFILES.find((p) => p.value === profile);
  const questions = questionnaire.data?.questions ?? [];
  const complete = questions.length > 0 && questions.every((q) => answers[q.id]);

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!complete) return;
    submit.mutate(answers, { onSuccess: () => setRetaking(false) });
  };

  if (!open && described) {
    return (
      <Card
        title="Your risk profile"
        actions={
          <Button variant="ghost" onClick={() => setRetaking(true)}>
            Retake questionnaire
          </Button>
        }
      >
        <p className="text-sm">
          <span className="font-semibold">{described.label}.</span> {described.blurb} Projections use illustrative returns for this
          profile.
        </p>
      </Card>
    );
  }

  return (
    <Card title={profile ? "Retake the risk questionnaire" : "First, a quick risk questionnaire"}>
      <p className="text-sm text-slate-600 dark:text-slate-300">
        Six questions place you in a conservative, moderate or aggressive profile. It's a learning aid that sets example
        assumptions, not advice.
      </p>
      {questionnaire.isPending && <LoadingState label="Loading questions" />}
      {questionnaire.isError && (
        <ErrorState title="Couldn't load the questionnaire" error={questionnaire.error} onRetry={() => void questionnaire.refetch()} />
      )}
      {questions.length > 0 && (
        <form onSubmit={onSubmit} className="space-y-4">
          <ol className="space-y-4">
            {questions.map((q, index) => (
              <li key={q.id}>
                <fieldset>
                  <legend className="mb-2 text-sm font-medium">
                    {index + 1}. {q.prompt}
                  </legend>
                  <div className="grid gap-1.5 sm:grid-cols-2">
                    {q.options.map((o) => (
                      <label
                        key={o.id}
                        className="flex cursor-pointer items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm has-[:checked]:border-emerald-600 has-[:checked]:bg-emerald-50 dark:border-slate-700 dark:has-[:checked]:bg-emerald-900/30"
                      >
                        <input
                          type="radio"
                          name={q.id}
                          value={o.id}
                          checked={answers[q.id] === o.id}
                          onChange={() => setAnswers((prev) => ({ ...prev, [q.id]: o.id }))}
                          className="accent-emerald-700"
                        />
                        {o.label}
                      </label>
                    ))}
                  </div>
                </fieldset>
              </li>
            ))}
          </ol>
          {submit.isError && <ErrorState title="Couldn't save your answers" error={submit.error} />}
          <div className="flex gap-2">
            <Button type="submit" disabled={!complete || submit.isPending}>
              {submit.isPending ? "Saving…" : "See my profile"}
            </Button>
            {profile && (
              <Button variant="ghost" onClick={() => setRetaking(false)}>
                Cancel
              </Button>
            )}
          </div>
        </form>
      )}
    </Card>
  );
}
