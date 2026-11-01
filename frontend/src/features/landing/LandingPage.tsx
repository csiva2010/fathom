import { Navigate, useSearchParams } from "react-router-dom";

import { DisclaimerBar } from "@/components/layout/DisclaimerBar";
import { useAuth } from "@/lib/auth/useAuth";

import { SignInButton } from "./components/SignInButton";

const AUTH_ERRORS: Record<string, string> = {
  cancelled: "Sign-in was cancelled. You can try again whenever you're ready.",
  sign_in_failed: "We couldn't complete Google sign-in. Please try again.",
  google_disabled: "Google sign-in is turned off on this server. Continue as a guest instead.",
};

const FEATURES = [
  ["Ask anything", "Plain-language answers to finance questions, with sources you can check."],
  ["Check your portfolio", "See allocation, fees and diversification in clear charts."],
  ["Watch the market", "Live quotes and index moves, explained for beginners."],
  ["Plan your goals", "Project savings for a house, retirement or an emergency fund."],
] as const;

/** The only page signed-out visitors can see (AU-01). */
export function LandingPage() {
  const { status } = useAuth();
  const [params] = useSearchParams();
  const authError = AUTH_ERRORS[params.get("auth_error") ?? ""];

  if (status === "signedIn") return <Navigate to="/chat" replace />;

  return (
    <div className="flex min-h-screen flex-col bg-gradient-to-b from-emerald-50 to-white dark:from-slate-900 dark:to-slate-950">
      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center px-6 py-16">
        <p className="text-sm font-medium text-emerald-800 dark:text-emerald-300">AI Finance Assistant</p>
        <h1 className="mt-2 text-4xl font-bold tracking-tight text-slate-900 dark:text-white">
          Learn investing without the jargon.
        </h1>
        <p className="mt-4 text-lg text-slate-700 dark:text-slate-300">
          A team of specialist AI guides that explain concepts, review a portfolio you enter, show live market
          context and help you plan goals at your own risk level.
        </p>

        {authError && (
          <p role="alert" className="mt-6 rounded-lg bg-amber-100 px-4 py-3 text-sm text-amber-900 dark:bg-amber-900/40 dark:text-amber-200">
            {authError}
          </p>
        )}

        <div className="mt-8">
          <SignInButton />
        </div>

        <ul className="mt-12 grid gap-4 sm:grid-cols-2">
          {FEATURES.map(([title, text]) => (
            <li key={title} className="rounded-xl border border-slate-200 bg-white/70 p-4 dark:border-slate-800 dark:bg-slate-900/60">
              <p className="font-medium text-slate-900 dark:text-white">{title}</p>
              <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{text}</p>
            </li>
          ))}
        </ul>
      </main>
      <DisclaimerBar />
    </div>
  );
}

