import { useQuery } from "@tanstack/react-query";

import { getMarketOverview } from "@/api/endpoints/market";
import { queryKeys } from "@/api/queryKeys";

export function useMarketOverview() {
  return useQuery({
    queryKey: queryKeys.marketOverview,
    queryFn: getMarketOverview,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}
