import { apiFetch } from "../client";
import type { Goal, GoalIn, ProjectionOut, ProjectionRequest } from "../types";

export function listGoals(): Promise<{ goals: Goal[] }> {
  return apiFetch<{ goals: Goal[] }>("/goals");
}

export function createGoal(body: GoalIn): Promise<Goal> {
  return apiFetch<Goal>("/goals", { method: "POST", body: JSON.stringify(body) });
}

export function updateGoal(id: string, body: GoalIn): Promise<Goal> {
  return apiFetch<Goal>(`/goals/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(body) });
}

export async function deleteGoal(id: string): Promise<void> {
  await apiFetch<undefined>(`/goals/${encodeURIComponent(id)}`, { method: "DELETE" });
}

/** Stateless projection for the live contribution slider (UI-06). */
export function projectGoal(body: ProjectionRequest): Promise<ProjectionOut> {
  return apiFetch<ProjectionOut>("/goals/project", { method: "POST", body: JSON.stringify(body) });
}
