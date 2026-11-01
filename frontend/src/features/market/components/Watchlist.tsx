import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import { Card } from "@/components/ui/Card";
import { direction, formatChange, formatPrice } from "@/lib/format/number";

import { useQuotes } from "../hooks/useMarketData";
import { SymbolSearch } from "./SymbolSearch";

const TONE = {
  up: "text-emerald-700 dark:text-emerald-400",
  down: "text-rose-700 dark:text-rose-400",
  flat: "text-slate-600 dark:text-slate-300",
};

export function Watchlist({
  symbols,
  selected,
  onSelect,
  onAdd,
  onRemove,
}: {
  symbols: string[];
  selected: string;
  onSelect: (s: string) => void;
  onAdd: (s: string) => void;
  onRemove: (s: string) => void;
}) {
  const quotes = useQuotes(symbols);
  const bySymbol = new Map((quotes.data?.quotes ?? []).map((q) => [q.quote.symbol, q]));

  return (
    <Card title="Watchlist" freshness={quotes.data?.quotes.map((q) => q.freshness)}>
      <SymbolSearch
        onPick={(s) => {
          onAdd(s);
          onSelect(s);
        }}
      />
      {symbols.length === 0 && <p className="text-sm text-slate-500 dark:text-slate-400">Add tickers to follow them here.</p>}
      {quotes.isPending && symbols.length > 0 && <LoadingState label="Loading quotes" />}
      {quotes.isError && <ErrorState title="Quotes are unavailable" error={quotes.error} onRetry={() => void quotes.refetch()} />}
      {symbols.length > 0 && !quotes.isPending && (
        <ul className="divide-y divide-slate-100 dark:divide-slate-800">
          {symbols.map((symbol) => {
            const item = bySymbol.get(symbol);
            const tone = TONE[direction(item?.quote.change)];
            return (
              <li key={symbol} className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => onSelect(symbol)}
                  aria-current={symbol === selected}
                  className={`flex flex-1 items-center justify-between rounded-md px-2 py-2 text-left text-sm ${
                    symbol === selected ? "bg-emerald-50 dark:bg-emerald-900/30" : "hover:bg-slate-50 dark:hover:bg-slate-800"
                  }`}
                >
                  <span className="font-semibold">{symbol}</span>
                  {item ? (
                    <span className="text-right tabular-nums">
                      {formatPrice(item.quote.price)}
                      <span className={`block text-xs ${tone}`}>{formatChange(item.quote.change, item.quote.change_percent)}</span>
                    </span>
                  ) : (
                    <span className="text-xs text-slate-500">not found</span>
                  )}
                </button>
                <button
                  type="button"
                  aria-label={`Remove ${symbol}`}
                  onClick={() => onRemove(symbol)}
                  className="rounded p-1 text-slate-400 hover:text-rose-700"
                >
                  ✕
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
