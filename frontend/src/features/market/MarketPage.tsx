import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import { PageHeader } from "@/components/layout/PageHeader";

import { IndexCard } from "./components/IndexCard";
import { useMarketOverview } from "./hooks/useMarketOverview";

/** Day 1: index cards. Watchlist, price chart and movers land with the full Market view. */
export function MarketPage() {
  const overview = useMarketOverview();

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
    </section>
  );
}
