import { Outlet } from "react-router-dom";

import { DisclaimerBar } from "./DisclaimerBar";
import { TopNav } from "./TopNav";

export function AppShell() {
  return (
    <div className="flex min-h-screen flex-col bg-white text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <TopNav />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        <Outlet />
      </main>
      <DisclaimerBar />
    </div>
  );
}
