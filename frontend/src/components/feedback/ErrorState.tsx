import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";

interface ErrorStateProps {
  error: unknown;
  title?: string;
  onRetry?: () => void;
}

export function ErrorState({ error, title = "Something went wrong", onRetry }: ErrorStateProps) {
  const message = error instanceof Error ? error.message : "Please try again.";
  const retryable = !(error instanceof ApiError) || error.retryable;
  return (
    <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-5 text-sm dark:border-rose-900 dark:bg-rose-950/40">
      <p className="font-medium text-rose-900 dark:text-rose-200">{title}</p>
      <p className="mt-1 text-rose-800 dark:text-rose-300">{message}</p>
      {onRetry && retryable && (
        <Button variant="secondary" className="mt-3" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
