import { useState } from "react";

import type { PriceRange } from "@/api/types";
import { PriceChart } from "@/components/charts/charts";
import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import { Card, Stat } from "@/components/ui/Card";
import { chipClass } from "@/components/ui/styles";
import { formatPrice } from "@/lib/format/number";
import { formatPercent } from "@/lib/format/money";

import { useHistory, useIndicators } from "../hooks/useMarketData";

const RANGES: PriceRange[] = ["1D", "5D", "1M", "3M", "6M", "1Y", "5Y"];

const pct = (v: number | null | undefined, signed = true) => (v == null ? "n/a" : formatPercent(v, { signed }));

/** UI-05 price chart with a range selector, plus the MD-08 insights in plain words. */
export function SymbolDetail({ symbol }: { symbol: string }) {
  const [range, setRange] = useState<PriceRange>("6M");
  const history = useHistory(symbol, range);
  const indicators = useIndicators(symbol);
  const points = (history.data?.history.bars ?? []).map((b) => ({ t: b.t, close: b.close }));
  const i = indicators.data?.indicators;

  return (
    <div className="space-y-4">
      <Card
        title={`${symbol} price`}
        freshness={history.data ? [history.data.freshness] : undefined}
        actions={
          <div role="group" aria-label="Chart range" className="flex flex-wrap gap-1">
            {RANGES.map((r) => (
              <button key={r} type="button" className={chipClass(r === range)} aria-pressed={r === range} onClick={() => setRange(r)}>
                {r}
              </button>
            ))}
          </div>
        }
      >
        {history.isPending && <LoadingState label="Loading price history" />}
        {history.isError && <ErrorState title="Price history is unavailable" error={history.error} onRetry={() => void history.refetch()} />}
        {history.data && points.length < 2 && <p className="text-sm text-slate-500">No price history for this range.</p>}
        {points.length >= 2 && (
          <div aria-busy={history.isFetching}>
            <PriceChart points={points} label={`${symbol} closing prices, ${range}`} axis />
          </div>
        )}
      </Card>
      <Card title={`${symbol} trend and risk`} freshness={indicators.data ? [indicators.data.freshness] : undefined}>
        {indicators.isPending && <LoadingState label="Loading indicators" />}
        {indicators.isError && <ErrorState title="Indicators are unavailable" error={indicators.error} />}
        {i && (
          <>
            <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Stat label="vs 50-day average" value={pct(i.price_vs_sma_50_percent)} hint={i.sma_50 != null ? `avg ${formatPrice(i.sma_50)}` : undefined} />
              <Stat label="vs 200-day average" value={pct(i.price_vs_sma_200_percent)} hint={i.sma_200 != null ? `avg ${formatPrice(i.sma_200)}` : undefined} />
              <Stat
                label="52-week range"
                value={i.week52_low != null && i.week52_high != null ? `${formatPrice(i.week52_low)}–${formatPrice(i.week52_high)}` : "n/a"}
                hint={i.week52_position_percent != null ? `${Math.round(i.week52_position_percent)}% of the way up` : undefined}
              />
              <Stat label="Volatility (30-day, yearly)" value={pct(i.volatility_30d_percent, false)} />
            </dl>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Trading above a moving average means the price has been trending up over that window. Volatility describes how
              widely the price swings; it isn&apos;t a forecast.
            </p>
          </>
        )}
      </Card>
    </div>
  );
}
