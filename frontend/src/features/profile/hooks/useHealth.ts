import { useQuery } from "@tanstack/react-query";

import { getHealth } from "@/api/endpoints/health";
import { queryKeys } from "@/api/queryKeys";

export function useHealth() {
  return useQuery({ queryKey: queryKeys.health, queryFn: getHealth, staleTime: 15_000 });
}
