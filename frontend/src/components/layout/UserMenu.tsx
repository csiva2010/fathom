import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { useAuth } from "@/lib/auth/useAuth";

export function UserMenu() {
  const { user, signOut } = useAuth();
  const [busy, setBusy] = useState(false);
  if (!user) return null;

  const initials = (user.name || user.email).slice(0, 1).toUpperCase();

  async function handleSignOut() {
    setBusy(true);
    try {
      await signOut();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-3">
      {user.avatar_url ? (
        <img src={user.avatar_url} alt="" className="h-8 w-8 rounded-full" referrerPolicy="no-referrer" />
      ) : (
        <span aria-hidden className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-100 text-sm font-semibold text-emerald-900">
          {initials}
        </span>
      )}
      <span className="hidden text-sm text-slate-700 md:inline dark:text-slate-200">{user.name || user.email}</span>
      <Button variant="ghost" onClick={handleSignOut} disabled={busy}>
        Sign out
      </Button>
    </div>
  );
}
