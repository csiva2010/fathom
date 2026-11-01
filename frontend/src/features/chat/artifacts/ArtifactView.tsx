import { Component, type ReactNode } from "react";

import type { Artifact, Freshness, IndexQuote, Quote } from "@/api/types";
import { FreshnessBadge } from "@/components/badges/FreshnessBadge";
import { formatChange, formatPrice } from "@/lib/format/number";
import { formatPercent, formatShare, formatUsd } from "@/lib/format/money";

import { SCENARIOS } from "@/components/charts/chartMath";
import { PriceChart as PriceLine, ProjectionChart, ShareBars, type ProjectionSeriesPoint } from "@/components/charts/charts";

/*
 * Chart and table payloads that agents attach to answers (CH-06). The backend sends
 * `data` as an open object per `kind`; the shapes below mirror the agent code.
 */

interface Sourced<T> {
  value: T;
  freshness: Freshness;
}
interface Slice {
  label: string;
  value: number;
  weight: number;
}
interface NewsItem {
  id: string;
  headline: string;
  source: string;
  url: string;
  published_at: string;
}
interface Scenario {
  scenario: string;
  annual_return_percent: number;
  final_value: number;
  final_value_real: number;
  reaches_target: boolean;
  required_monthly_contribution: number;
}
type Data = Record<string, unknown>;

const ASSET_CLASS_LABELS: Record<string, string> = {
  stock: "Stocks",
  etf: "Stock funds (ETFs)",
  bond_etf: "Bond funds",
  cash: "Cash",
  other: "Other",
};
const assetClassLabel = (label: string) => ASSET_CLASS_LABELS[label] ?? label;

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

function Card({ title, freshness, children }: { title: string; freshness?: Freshness[]; children: ReactNode }) {
  const stamps = (freshness ?? []).filter(
    (f, i, all) => all.findIndex((g) => g.source === f.source && g.status === f.status) === i,
  );
  return (
    <section
      aria-label={title}
      className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
    >
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        <div className="flex gap-1">
          {stamps.map((f) => (
            <FreshnessBadge key={`${f.source}-${f.status}`} freshness={f} />
          ))}
        </div>
      </header>
      {children}
    </section>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-800/60">
      <dt className="text-xs text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="text-base font-semibold tabular-nums">{value}</dd>
      {hint && <dd className="text-xs text-slate-500 dark:text-slate-400">{hint}</dd>}
    </div>
  );
}

function changeClass(change: number | null | undefined): string {
  if (!change) return "text-slate-600 dark:text-slate-300";
  return change > 0 ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400";
}

// --- One renderer per kind --------------------------------------------------------------

function QuoteCard({ title, data }: { title: string; data: Data }) {
  const quote = data.quote as Quote;
  return (
    <Card title={title} freshness={[data.freshness as Freshness]}>
      <p className="flex items-baseline gap-3">
        <span className="text-2xl font-semibold tabular-nums">{formatPrice(quote.price)}</span>
        <span className={`text-sm tabular-nums ${changeClass(quote.change)}`}>
          {formatChange(quote.change, quote.change_percent)}
        </span>
      </p>
    </Card>
  );
}

function IndicatorsCard({ title, data }: { title: string; data: Data }) {
  const pct = (key: string, signed = true) => {
    const v = num(data[key]);
    return v === null ? "n/a" : formatPercent(v, { signed });
  };
  const low = num(data.week52_low);
  const high = num(data.week52_high);
  return (
    <Card title={title} freshness={[data.freshness as Freshness]}>
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="vs 50-day average" value={pct("price_vs_sma_50_percent")} />
        <Stat label="vs 200-day average" value={pct("price_vs_sma_200_percent")} />
        <Stat
          label="52-week range"
          value={low !== null && high !== null ? `${formatPrice(low)}–${formatPrice(high)}` : "n/a"}
        />
        <Stat label="Volatility (30d, yearly)" value={pct("volatility_30d_percent", false)} />
      </dl>
    </Card>
  );
}

function IndexCards({ title, data }: { title: string; data: Data }) {
  const indices = (data.indices as Sourced<IndexQuote>[]) ?? [];
  return (
    <Card title={title} freshness={indices.map((i) => i.freshness)}>
      <ul className="grid gap-2 sm:grid-cols-3">
        {indices.map(({ value }) => (
          <li key={value.id} className="rounded-lg bg-slate-50 px-3 py-2 text-sm dark:bg-slate-800/60">
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {value.name}
              {value.is_proxy && ` (via ${value.symbol})`}
            </p>
            <p className="font-semibold tabular-nums">{formatPrice(value.price)}</p>
            <p className={`text-xs tabular-nums ${changeClass(value.change)}`}>{formatChange(value.change, value.change_percent)}</p>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Movers({ title, data }: { title: string; data: Data }) {
  const groups: [string, Sourced<Quote>[]][] = [
    ["Gainers", (data.gainers as Sourced<Quote>[]) ?? []],
    ["Losers", (data.losers as Sourced<Quote>[]) ?? []],
  ];
  return (
    <Card title={title} freshness={groups.flatMap(([, quotes]) => quotes.map((q) => q.freshness))}>
      <div className="grid gap-3 sm:grid-cols-2">
        {groups.map(([label, quotes]) => (
          <div key={label}>
            <h4 className="mb-1 text-xs font-medium text-slate-500 dark:text-slate-400">{label}</h4>
            <ul className="space-y-1 text-sm">
              {quotes.map(({ value }) => (
                <li key={value.symbol} className="flex justify-between tabular-nums">
                  <span className="font-medium">{value.symbol}</span>
                  <span className={changeClass(value.change_percent)}>
                    {value.change_percent != null ? formatPercent(value.change_percent, { decimals: 2, signed: true }) : "—"}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </Card>
  );
}

function SectorTable({ title, data }: { title: string; data: Data }) {
  const sectors = (data.sectors as { sector: string; symbol: string; change_percent: number | null }[]) ?? [];
  return (
    <Card title={title}>
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-slate-500 dark:text-slate-400">
          <tr>
            <th className="py-1 font-medium">Sector</th>
            <th className="py-1 font-medium">ETF</th>
            <th className="py-1 text-right font-medium">Today</th>
          </tr>
        </thead>
        <tbody>
          {sectors.map((s) => (
            <tr key={s.symbol} className="border-t border-slate-100 dark:border-slate-800">
              <td className="py-1">{s.sector}</td>
              <td className="py-1 text-slate-500 dark:text-slate-400">{s.symbol}</td>
              <td className={`py-1 text-right tabular-nums ${changeClass(s.change_percent)}`}>
                {s.change_percent != null ? formatPercent(s.change_percent, { decimals: 2, signed: true }) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function PriceChart({ title, data }: { title: string; data: Data }) {
  return (
    <Card title={title} freshness={[data.freshness as Freshness]}>
      <PriceLine points={(data.points as { t: string; close: number }[]) ?? []} label={`${title} closing prices`} />
    </Card>
  );
}

function PortfolioMetrics({ title, data }: { title: string; data: Data }) {
  const value = num(data.total_value) ?? 0;
  const gain = num(data.total_gain);
  const gainPct = num(data.total_gain_percent);
  const beta = num(data.weighted_beta);
  const vol = num(data.volatility_percent);
  const drawdown = num(data.max_drawdown_percent);
  const fees = num(data.weighted_expense_ratio);
  const benchmark = data.benchmark as
    | { benchmark_symbol: string; range: string; portfolio_return_percent: number; benchmark_return_percent: number }
    | null;
  return (
    <Card title={title} freshness={data.freshness as Freshness[]}>
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <Stat
          label="Value"
          value={formatUsd(value)}
          hint={gain !== null && gainPct !== null ? `${formatUsd(gain)} (${formatPercent(gainPct, { signed: true })})` : undefined}
        />
        <Stat label="Diversification" value={`${num(data.diversification_score) ?? 0}/100`} />
        <Stat label="Beta" value={beta !== null ? beta.toFixed(2) : "n/a"} />
        <Stat label="Volatility (yearly)" value={vol !== null ? formatPercent(vol) : "n/a"} />
        <Stat label="Worst drop" value={drawdown !== null ? formatPercent(Math.abs(drawdown)) : "n/a"} />
        <Stat label="Yearly fund fees" value={fees !== null ? formatShare(fees, 2) : "n/a"} />
      </dl>
      {benchmark && (
        <p className="text-xs text-slate-600 dark:text-slate-300">
          Over {benchmark.range}: {formatPercent(benchmark.portfolio_return_percent, { signed: true })} vs{" "}
          {formatPercent(benchmark.benchmark_return_percent, { signed: true })} for {benchmark.benchmark_symbol}.
        </p>
      )}
    </Card>
  );
}

function Allocation({ title, data }: { title: string; data: Data }) {
  const classes = (data.by_asset_class as Slice[]) ?? [];
  const sectors = ((data.by_sector as Slice[]) ?? []).slice(0, 6);
  return (
    <Card title={title} freshness={data.freshness as Freshness[]}>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <h4 className="text-xs font-medium text-slate-500 dark:text-slate-400">By asset class</h4>
          <ShareBars label="Allocation by asset class" data={classes.map((s) => ({ label: assetClassLabel(s.label), weight: s.weight, value: s.value }))} />
        </div>
        <div className="space-y-1.5">
          <h4 className="text-xs font-medium text-slate-500 dark:text-slate-400">Largest sector exposures</h4>
          <ShareBars label="Allocation by sector" data={sectors.map((s) => ({ label: s.label, weight: s.weight, value: s.value }))} />
        </div>
      </div>
    </Card>
  );
}

function Projection({ title, data }: { title: string; data: Data }) {
  const scenarios = (data.scenarios as Scenario[]) ?? [];
  const target = num(data.target_amount) ?? 0;
  const order = SCENARIOS.map((s) => s.key as string);
  const sorted = [...scenarios].sort((a, b) => order.indexOf(a.scenario) - order.indexOf(b.scenario));
  return (
    <Card title={title}>
      <ProjectionChart series={(data.series as ProjectionSeriesPoint[]) ?? []} target={target} />
      <table className="w-full text-xs">
        <caption className="sr-only">Projection by scenario</caption>
        <thead className="text-left text-slate-500 dark:text-slate-400">
          <tr>
            <th className="py-1 font-medium">Scenario</th>
            <th className="py-1 text-right font-medium">Ends near</th>
            <th className="py-1 text-right font-medium">In today&apos;s $</th>
            <th className="py-1 text-right font-medium">Monthly needed</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((s) => (
            <tr key={s.scenario} className="border-t border-slate-100 tabular-nums dark:border-slate-800">
              <td className="py-1">
                <span className="capitalize">{s.scenario}</span> ({s.annual_return_percent}%/yr)
              </td>
              <td className="py-1 text-right">
                {formatUsd(s.final_value)} {s.reaches_target ? "✓" : ""}
                <span className="sr-only">{s.reaches_target ? "reaches target" : "short of target"}</span>
              </td>
              <td className="py-1 text-right">{formatUsd(s.final_value_real)}</td>
              <td className="py-1 text-right">{formatUsd(s.required_monthly_contribution)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {typeof data.assumptions === "string" && <p className="text-xs text-slate-500 dark:text-slate-400">{data.assumptions}</p>}
    </Card>
  );
}

function ExampleAllocation({ title, data }: { title: string; data: Data }) {
  const slices = (data.slices as { asset_class: string; weight: number }[]) ?? [];
  return (
    <Card title={title}>
      <ShareBars
        label={title}
        data={slices.map((s) => ({ label: s.asset_class.charAt(0).toUpperCase() + s.asset_class.slice(1), weight: s.weight }))}
      />
      {typeof data.note === "string" && <p className="text-xs text-slate-500 dark:text-slate-400">{data.note}</p>}
    </Card>
  );
}

function NewsList({ title, data }: { title: string; data: Data }) {
  const items = (data.items as NewsItem[]) ?? [];
  return (
    <Card title={title} freshness={[data.freshness as Freshness]}>
      <ul className="space-y-2 text-sm">
        {items.map((n) => (
          <li key={n.id}>
            {n.url ? (
              <a href={n.url} target="_blank" rel="noopener noreferrer" className="font-medium text-emerald-800 hover:underline dark:text-emerald-300">
                {n.headline}
              </a>
            ) : (
              <span className="font-medium">{n.headline}</span>
            )}
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {[n.source, new Date(n.published_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })].filter(Boolean).join(" · ")}
            </p>
          </li>
        ))}
      </ul>
    </Card>
  );
}

const RENDERERS: Record<Artifact["kind"], (props: { title: string; data: Data }) => ReactNode> = {
  quote_card: QuoteCard,
  indicators: IndicatorsCard,
  index_cards: IndexCards,
  movers: Movers,
  sector_table: SectorTable,
  price_chart: PriceChart,
  portfolio_metrics: PortfolioMetrics,
  allocation: Allocation,
  projection: Projection,
  example_allocation: ExampleAllocation,
  news_list: NewsList,
};

/** A malformed payload hides its card instead of breaking the conversation. */
class ArtifactBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed ? null : this.props.children;
  }
}

export function ArtifactView({ artifact }: { artifact: Artifact }) {
  const Renderer = RENDERERS[artifact.kind];
  if (!Renderer) return null;
  return (
    <ArtifactBoundary>
      <Renderer title={artifact.title} data={artifact.data} />
    </ArtifactBoundary>
  );
}
