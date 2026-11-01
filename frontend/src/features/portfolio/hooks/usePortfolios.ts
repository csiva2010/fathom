import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createPortfolio, deletePortfolio, getAnalysis, importCsv, listPortfolios, updatePortfolio } from "@/api/endpoints/portfolios";
import { queryKeys } from "@/api/queryKeys";
import type { PortfolioIn, PriceRange } from "@/api/types";

export function usePortfolios() {
  return useQuery({ queryKey: queryKeys.portfolios, queryFn: listPortfolios });
}

export function useAnalysis(id: string | undefined, range: PriceRange) {
  return useQuery({
    queryKey: queryKeys.analysis(id ?? "", range),
    queryFn: () => getAnalysis(id ?? "", range),
    enabled: Boolean(id),
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });
}

export function useSavePortfolio() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: PortfolioIn }) => (id ? updatePortfolio(id, body) : createPortfolio(body)),
    onSuccess: (saved) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.portfolios, exact: true });
      void queryClient.invalidateQueries({ queryKey: ["portfolios", saved.id] });
    },
  });
}

export function useDeletePortfolio() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deletePortfolio,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: queryKeys.portfolios, exact: true }),
  });
}

export function useImportCsv() {
  return useMutation({ mutationFn: importCsv });
}
