import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createGoal, deleteGoal, listGoals, projectGoal, updateGoal } from "@/api/endpoints/goals";
import { getRiskQuestionnaire, submitRiskQuestionnaire } from "@/api/endpoints/me";
import { queryKeys } from "@/api/queryKeys";
import type { GoalIn, ProjectionRequest } from "@/api/types";

export function useGoals() {
  return useQuery({ queryKey: queryKeys.goals, queryFn: listGoals });
}

export function useSaveGoal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: GoalIn }) => (id ? updateGoal(id, body) : createGoal(body)),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: queryKeys.goals, exact: true }),
  });
}

export function useDeleteGoal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteGoal,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: queryKeys.goals, exact: true }),
  });
}

/** Live projection for slider inputs; keeps the last chart on screen while it updates. */
export function useProjection(inputs: ProjectionRequest | null) {
  return useQuery({
    queryKey: queryKeys.projection(inputs),
    queryFn: () => projectGoal(inputs as ProjectionRequest),
    enabled: inputs !== null,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
  });
}

export function useRiskQuestionnaire(enabled: boolean) {
  return useQuery({ queryKey: queryKeys.riskQuestionnaire, queryFn: getRiskQuestionnaire, enabled, staleTime: Infinity });
}

export function useSubmitRisk() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: submitRiskQuestionnaire,
    onSuccess: (result) => {
      queryClient.setQueryData(queryKeys.me, result.me);
      // New goals default to the profile; existing goals keep the one they were saved with.
      void queryClient.invalidateQueries({ queryKey: queryKeys.goals, exact: true });
    },
  });
}
