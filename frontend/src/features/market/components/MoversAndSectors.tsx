import type { QuoteOut } from "@/api/types";
import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import { Card } from "@/components/ui/Card";
import { formatPercent } from "@/lib/format/money";

import { useMovers, useSectors } from "../hooks/useMarketData";

function changeClass(v: number | null | undefined) {
  if (!v) return "text-slate-600 dark:text-slate-300";
  return v > 0 ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400";
}

function MoverList({ title, items, onSelect }: { title: string; items: QuoteOut[]; onSelect: (s: string) => void }) {
  return (
    <div>
      <h3 className="mb-1 text-xs font-medium text-slate-500 dark:text-slate-400">{title}</h3>
      <ul className="space-y-0.5 text-sm">
        {items.map(({ quote }) => (
          <li key={quote.symbol}>
            <button type="button" onClick={() => onSelect(quote.symbol)} className="flex w-full justify-between rounded px-1 py-0.5 tabular-nums hover:bg-slate-50 dark:hover:bg-slate-800">
              <span className="font-medium">{quote.symbol}</span>
              <span className={changeClass(quote.change_percent)}>
                {quote.change_percent != null ? formatPercent(quote.change_percent, { decimals: 2, signed: true }) : "—"}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** MD-08: today's biggest moves among liquid names, and sectors via their ETFs. */
export function MoversAndSectors({ onSelect }: { onSelect: (s: string) => void }) {
  const movers = useMovers();
  const sectors = useSectors();
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Today's movers" freshness={movers.data?.gainers.map((q) => q.freshness)}>
        {movers.isPending && <LoadingState label="Loading movers" />}
        {movers.isError && <ErrorState title="Movers are unavailable" error={movers.error} onRetry={() => void movers.refetch()} />}
        {movers.data && (
          <div className="grid grid-cols-2 gap-4">
            <MoverList title="Gainers" items={movers.data.gainers} onSelect={onSelect} />
            <MoverList title="Losers" items={movers.data.losers} onSelect={onSelect} />
          </div>
        )}
      </Card>
      <Card title="Sectors today" freshness={sectors.data?.sectors.map((s) => s.freshness)}>
        {sectors.isPending && <LoadingState label="Loading sectors" />}
        {sectors.isError && <ErrorState title="Sector data is unavailable" error={sectors.error} onRetry={() => void sectors.refetch()} />}
        {sectors.data && (
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-slate-500 dark:text-slate-400">
              <tr>
                <th className="py-1 font-medium">Sector</th>
                <th className="py-1 font-medium">ETF</th>
                <th className="py-1 text-right font-medium">Today</th>
              </tr>
            </thead>
            <tbody>
              {sectors.data.sectors.map(({ sector }) => (
                <tr key={sector.symbol} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-1">{sector.sector}</td>
                  <td className="py-1">
                    <button type="button" onClick={() => onSelect(sector.symbol)} className="text-emerald-700 hover:underline dark:text-emerald-300">
                      {sector.symbol}
                    </button>
                  </td>
                  <td className={`py-1 text-right tabular-nums ${changeClass(sector.change_percent)}`}>
                    {sector.change_percent != null ? formatPercent(sector.change_percent, { decimals: 2, signed: true }) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
