import { apiFetch } from "../client";
import type { Health } from "../types";

export function getHealth(): Promise<Health> {
  return apiFetch<Health>("/health");
}
