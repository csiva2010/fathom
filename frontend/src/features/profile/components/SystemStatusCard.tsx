import type { ProviderHealth } from "@/api/types";
import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";

import { useHealth } from "../hooks/useHealth";

const PROVIDER_LABEL: Record<string, string> = {
  alpaca: "Alpaca (quotes, history, news)",
  alpha_vantage: "Alpha Vantage (indexes, reference data)",
};

function providerState(p: ProviderHealth): { text: string; ok: boolean } {
  if (!p.configured) return { text: "Not configured, using sample data", ok: false };
  if (p.circuit === "open") return { text: "Temporarily unavailable", ok: false };
  return { text: "Connected", ok: true };
}

function Row({ label, ok, text }: { label: string; ok: boolean; text: string }) {
  return (
    <li className="flex items-center justify-between gap-4 py-2">
      <span>{label}</span>
      <span className={`flex items-center gap-2 ${ok ? "text-emerald-700 dark:text-emerald-400" : "text-amber-700 dark:text-amber-400"}`}>
        <span aria-hidden className={`h-2 w-2 rounded-full ${ok ? "bg-emerald-500" : "bg-amber-500"}`} />
        {text}
      </span>
    </li>
  );
}

/** Day-1 gate visibility: is the API up, and which data providers are live? */
export function SystemStatusCard() {
  const health = useHealth();
  return (
    <section aria-labelledby="status-heading" className="rounded-xl border border-slate-200 p-5 dark:border-slate-800">
      <h2 id="status-heading" className="font-medium">
        System status
      </h2>
      {health.isPending && <LoadingState label="Checking services" />}
      {health.isError && <ErrorState error={health.error} onRetry={() => void health.refetch()} />}
      {health.data && (
        <ul className="mt-2 divide-y divide-slate-100 text-sm dark:divide-slate-800">
          <Row label="Database" ok={health.data.database} text={health.data.database ? "OK" : "Unavailable"} />
          <Row
            label="Knowledge base index"
            ok={health.data.knowledge_index}
            text={health.data.knowledge_index ? "Built" : "Not built yet"}
          />
          {health.data.providers.map((p) => {
            const state = providerState(p);
            return <Row key={p.name} label={PROVIDER_LABEL[p.name] ?? p.name} ok={state.ok} text={state.text} />;
          })}
        </ul>
      )}
    </section>
  );
}
