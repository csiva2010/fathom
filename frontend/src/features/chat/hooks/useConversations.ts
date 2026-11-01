import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { deleteConversation, getConversation, listConversations } from "@/api/endpoints/chat";
import { queryKeys } from "@/api/queryKeys";

export function useConversations() {
  return useQuery({ queryKey: queryKeys.conversations, queryFn: listConversations });
}

export function useConversation(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.conversation(id ?? ""),
    queryFn: () => getConversation(id ?? ""),
    enabled: Boolean(id),
  });
}

export function useDeleteConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteConversation,
    onSuccess: (_data, id) => {
      queryClient.removeQueries({ queryKey: queryKeys.conversation(id) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.conversations, exact: true });
    },
  });
}
