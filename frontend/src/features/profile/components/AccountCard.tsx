import type { Me } from "@/api/types";

const LEVEL_LABEL = { beginner: "Beginner", intermediate: "Intermediate", advanced: "Advanced" } as const;

export function AccountCard({ user }: { user: Me }) {
  const { profile } = user;
  return (
    <section aria-labelledby="account-heading" className="rounded-xl border border-slate-200 p-5 dark:border-slate-800">
      <h2 id="account-heading" className="font-medium">
        Account
      </h2>
      <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
        <dt className="text-slate-500 dark:text-slate-400">Name</dt>
        <dd>{user.name || "—"}</dd>
        <dt className="text-slate-500 dark:text-slate-400">Email</dt>
        <dd>{user.is_guest ? "Guest account" : user.email}</dd>
        <dt className="text-slate-500 dark:text-slate-400">Experience</dt>
        <dd>{LEVEL_LABEL[profile.experience_level]}</dd>
        <dt className="text-slate-500 dark:text-slate-400">Risk profile</dt>
        <dd className="capitalize">{profile.risk_profile ?? "Not set yet"}</dd>
      </dl>
      {user.is_guest && (
        <p className="mt-4 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:bg-amber-900/30 dark:text-amber-200">
          You're using a guest account. Signing out, clearing cookies or a long break ends the session, and
          your saved portfolios and goals can't be recovered.
        </p>
      )}
    </section>
  );
}
