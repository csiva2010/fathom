import { useState } from "react";

import type { PriceRange } from "@/api/types";
import { AllocationDonut, PerformanceChart, ShareBars, type PerformancePoint } from "@/components/charts/charts";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import { Card, Stat } from "@/components/ui/Card";
import { chipClass } from "@/components/ui/styles";
import { formatPrice } from "@/lib/format/number";
import { formatPercent, formatShare, formatUsd } from "@/lib/format/money";

import { ASSET_CLASSES, assetClassLabel } from "../assetClasses";
import { useAnalysis } from "../hooks/usePortfolios";

const RANGES: PriceRange[] = ["1M", "3M", "6M", "1Y", "5Y"];

const FIT_TEXT: Record<string, string> = {
  within: "in line with",
  above: "riskier than",
  below: "calmer than",
};

function gainClass(value: number | null | undefined): string {
  if (!value) return "";
  return value > 0 ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400";
}

/** PF-02 to PF-06 and UI-04: metrics, allocation donut, sector bars, benchmark line. */
export function PortfolioAnalysisView({ portfolioId }: { portfolioId: string }) {
  const [range, setRange] = useState<PriceRange>("1Y");
  const analysis = useAnalysis(portfolioId, range);

  if (analysis.isPending) return <LoadingState label="Analyzing portfolio" />;
  if (analysis.isError)
    return <ErrorState title="Couldn't analyze this portfolio" error={analysis.error} onRetry={() => void analysis.refetch()} />;
  const a = analysis.data;
  // Lists the backend defaults to empty arrive as optional in the generated types.
  const unpriced = a.unpriced ?? [];
  const performance = a.performance ?? [];
  const drivers = a.diversification.drivers ?? [];
  const observations = a.observations ?? [];
  if (a.holdings.length === 0)
    return (
      <EmptyState title="Nothing to analyze yet">
        {unpriced.length > 0 ? `We couldn't price ${unpriced.join(", ")} right now.` : "Add holdings to see the analysis."}
      </EmptyState>
    );

  const byClass = new Map(a.allocation_by_asset_class.map((s) => [s.label, s]));
  const slices = ASSET_CLASSES.flatMap((c) => {
    const slice = byClass.get(c.value);
    return slice ? [{ key: c.value, label: c.label, weight: slice.weight, value: slice.value, color: c.color }] : [];
  });
  const risk = a.risk;
  const benchmark = a.benchmark;

  return (
    <div className="space-y-4" aria-busy={analysis.isFetching}>
      <Card title="Key metrics" freshness={a.freshness}>
        <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <Stat
            label="Value"
            value={formatUsd(a.total_value)}
            hint={
              a.total_gain != null && a.total_gain_percent != null
                ? `${formatUsd(a.total_gain)} (${formatPercent(a.total_gain_percent, { signed: true })}) vs cost`
                : undefined
            }
          />
          <Stat label="Diversification score" value={`${a.diversification.score}/100`} />
          <Stat label="Yearly fund fees" value={a.weighted_expense_ratio != null ? formatShare(a.weighted_expense_ratio, 2) : "n/a"} />
          <Stat label="Beta (vs market)" value={risk.weighted_beta != null ? risk.weighted_beta.toFixed(2) : "n/a"} />
          <Stat label="Volatility (yearly)" value={risk.annualized_volatility_percent != null ? formatPercent(risk.annualized_volatility_percent) : "n/a"} />
          <Stat label="Worst drop" value={risk.max_drawdown_percent != null ? formatPercent(Math.abs(risk.max_drawdown_percent)) : "n/a"} />
        </dl>
        {risk.risk_level && (
          <p className="text-sm text-slate-600 dark:text-slate-300">
            Its past swings look like a <strong>{risk.risk_level}</strong> mix
            {risk.profile && risk.profile_fit ? (
              <>
                , {FIT_TEXT[risk.profile_fit]} your {risk.profile} profile.
              </>
            ) : (
              <>. Take the risk questionnaire on the Goals tab to compare it with your profile.</>
            )}
          </p>
        )}
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Allocation by asset class">
          <AllocationDonut slices={slices} label="Allocation by asset class" />
        </Card>
        <Card title="Sector exposure (looking through funds)">
          <ShareBars label="Sector exposure" data={a.allocation_by_sector.slice(0, 8).map((s) => ({ label: s.label, weight: s.weight, value: s.value }))} />
        </Card>
      </div>

      <Card
        title="Compared with the S&P 500"
        actions={
          <div role="group" aria-label="Comparison period" className="flex gap-1">
            {RANGES.map((r) => (
              <button key={r} type="button" className={chipClass(r === range)} aria-pressed={r === range} onClick={() => setRange(r)}>
                {r}
              </button>
            ))}
          </div>
        }
      >
        {benchmark && performance.length > 1 ? (
          <>
            <PerformanceChart points={performance as PerformancePoint[]} benchmarkLabel={`S&P 500 (${benchmark.benchmark_symbol})`}
              benchmarkShort={benchmark.benchmark_symbol}
            />
            <p className="text-sm text-slate-600 dark:text-slate-300">
              Holding today&apos;s positions over {benchmark.range}, the portfolio returned{" "}
              <strong>{formatPercent(benchmark.portfolio_return_percent, { signed: true })}</strong> against{" "}
              {formatPercent(benchmark.benchmark_return_percent, { signed: true })} for {benchmark.benchmark_symbol}. Past returns
              don&apos;t predict future ones.
            </p>
          </>
        ) : (
          <EmptyState title="Not enough shared price history for this period" />
        )}
      </Card>

      <Card title="Holdings">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[36rem] text-sm">
            <thead className="text-left text-xs text-slate-500 dark:text-slate-400">
              <tr>
                <th className="py-1 font-medium">Holding</th>
                <th className="py-1 font-medium">Type</th>
                <th className="py-1 text-right font-medium">Shares</th>
                <th className="py-1 text-right font-medium">Price</th>
                <th className="py-1 text-right font-medium">Value</th>
                <th className="py-1 text-right font-medium">Weight</th>
                <th className="py-1 text-right font-medium">Gain</th>
              </tr>
            </thead>
            <tbody>
              {a.holdings.map((h) => (
                <tr key={h.symbol} className="border-t border-slate-100 tabular-nums dark:border-slate-800">
                  <td className="py-1.5">
                    <span className="font-medium">{h.symbol}</span>
                    {h.name && <span className="block text-xs text-slate-500 dark:text-slate-400">{h.name}</span>}
                  </td>
                  <td className="py-1.5">{assetClassLabel(h.asset_class)}</td>
                  <td className="py-1.5 text-right">{h.quantity}</td>
                  <td className="py-1.5 text-right">{formatPrice(h.price)}</td>
                  <td className="py-1.5 text-right">{formatUsd(h.market_value)}</td>
                  <td className="py-1.5 text-right">{formatShare(h.weight)}</td>
                  <td className={`py-1.5 text-right ${gainClass(h.gain)}`}>
                    {h.gain_percent != null ? formatPercent(h.gain_percent, { signed: true }) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {unpriced.length > 0 && (
          <p className="text-xs text-amber-700 dark:text-amber-300">Not priced right now, so left out: {unpriced.join(", ")}.</p>
        )}
      </Card>

      <Card title="Things worth understanding">
        <ul className="list-disc space-y-1.5 pl-5 text-sm">
          {drivers.map((d) => (
            <li key={d}>{d}</li>
          ))}
          {observations.map((o) => (
            <li key={o.code}>{o.message}</li>
          ))}
        </ul>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          These are learning points about how the portfolio is built, not suggestions to change it.
        </p>
      </Card>
    </div>
  );
}
