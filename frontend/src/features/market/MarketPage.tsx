import { useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import { PageHeader } from "@/components/layout/PageHeader";

import { useAuth } from "@/lib/auth/useAuth";

import { IndexCard } from "./components/IndexCard";
import { MoversAndSectors } from "./components/MoversAndSectors";
import { SymbolDetail } from "./components/SymbolDetail";
import { Watchlist } from "./components/Watchlist";
import { useWatchlist } from "./hooks/useMarketData";
import { useMarketOverview } from "./hooks/useMarketOverview";

/** The Market tab (UI-05): index cards, watchlist, price chart with ranges, movers, sectors. */
export function MarketPage() {
  const overview = useMarketOverview();
  const { user } = useAuth();
  const watchlist = useWatchlist(user?.id ?? "anonymous");
  const [params, setParams] = useSearchParams();
  const selected = params.get("symbol") ?? watchlist.symbols[0] ?? "SPY";
  const select = (symbol: string) => setParams({ symbol }, { replace: true });

  return (
    <section>
      <PageHeader title="Market" description="Major US indexes. Every number shows where it came from and how fresh it is." />
      {overview.isPending && <LoadingState label="Loading market overview" />}
      {overview.isError && (
        <ErrorState title="Market data is unavailable" error={overview.error} onRetry={() => void overview.refetch()} />
      )}
      {overview.data &&
        (overview.data.indices.length === 0 ? (
          <EmptyState title="No indexes configured" />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {overview.data.indices.map((item) => (
              <IndexCard key={item.index.id} item={item} />
            ))}
          </div>
        ))}
      <div className="mt-6 grid gap-4 lg:grid-cols-[18rem_1fr]">
        <Watchlist symbols={watchlist.symbols} selected={selected} onSelect={select} onAdd={watchlist.add} onRemove={watchlist.remove} />
        <SymbolDetail key={selected} symbol={selected} />
      </div>
      <div className="mt-6">
        <MoversAndSectors onSelect={select} />
      </div>
    </section>
  );
}
