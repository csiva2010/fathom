/** Suggested next questions (CH-05); clicking one sends it. */
export function FollowUps({ questions, onAsk, disabled }: { questions: string[]; onAsk: (q: string) => void; disabled?: boolean }) {
  if (questions.length === 0) return null;
  return (
    <div aria-label="Suggested follow-ups" role="group" className="flex flex-wrap gap-2">
      {questions.map((question) => (
        <button
          key={question}
          type="button"
          disabled={disabled}
          onClick={() => onAsk(question)}
          className="rounded-full border border-slate-300 px-3 py-1 text-xs text-slate-700 hover:border-emerald-600 hover:text-emerald-800 disabled:opacity-50 dark:border-slate-600 dark:text-slate-200 dark:hover:border-emerald-400 dark:hover:text-emerald-200"
        >
          {question}
        </button>
      ))}
    </div>
  );
}
