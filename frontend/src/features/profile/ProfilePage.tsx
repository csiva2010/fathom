import { PageHeader } from "@/components/layout/PageHeader";
import { useAuth } from "@/lib/auth/useAuth";

import { AccountCard } from "./components/AccountCard";
import { SystemStatusCard } from "./components/SystemStatusCard";

export function ProfilePage() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <section>
      <PageHeader title="Profile" description="Your account, learning level and the app's data connections." />
      <div className="grid gap-4 lg:grid-cols-2">
        <AccountCard user={user} />
        <SystemStatusCard />
      </div>
    </section>
  );
}
