import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { useAuth } from "@/lib/auth/useAuth";

import { GoogleIcon } from "./GoogleIcon";

/** Google sign-in, or "Continue as guest" when the server runs with AUTH__MODE=guest. */
export function SignInButton() {
  const { status, config, signIn } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const guest = config?.guest_enabled ?? false;

  async function handleClick() {
    setBusy(true);
    setError(null);
    try {
      await signIn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sign-in failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <Button onClick={handleClick} disabled={status === "loading" || busy} className="px-6 py-3 text-base">
        {guest ? "Continue as guest" : (
          <>
            <GoogleIcon />
            Sign in with Google
          </>
        )}
      </Button>
      {guest && (
        <p className="mt-3 text-sm text-slate-600 dark:text-slate-400">
          No account needed. Your data is kept for as long as this browser stays signed in.
        </p>
      )}
      {error && (
        <p role="alert" className="mt-3 text-sm text-rose-700 dark:text-rose-400">
          {error}
        </p>
      )}
    </div>
  );
}
