import { apiFetch } from "../client";
import type { Me, ProfileUpdate } from "../types";

export function getMe(): Promise<Me> {
  return apiFetch<Me>("/me");
}

export function updateProfile(update: ProfileUpdate): Promise<Me> {
  return apiFetch<Me>("/me/profile", { method: "PUT", body: JSON.stringify(update) });
}
