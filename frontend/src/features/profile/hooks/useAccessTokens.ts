import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createToken, listTokens, revokeToken } from "@/api/endpoints/tokens";
import { queryKeys } from "@/api/queryKeys";

export function useAccessTokens() {
  return useQuery({ queryKey: queryKeys.tokens, queryFn: listTokens });
}

export function useCreateToken() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createToken,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: queryKeys.tokens, exact: true }),
  });
}

export function useRevokeToken() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: revokeToken,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: queryKeys.tokens, exact: true }),
  });
}
