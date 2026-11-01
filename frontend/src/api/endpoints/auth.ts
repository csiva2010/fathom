import { API_PREFIX, apiFetch } from "../client";
import type { AuthConfig } from "../types";

/** Full-page navigation: the backend runs the Google OAuth flow and sets the cookie. */
export const GOOGLE_LOGIN_URL = `${API_PREFIX}/auth/google/login`;

/** Which sign-in options the server has enabled (AUTH__MODE). */
export function getAuthConfig(): Promise<AuthConfig> {
  return apiFetch<AuthConfig>("/auth/config");
}

/** Creates a new guest account; the backend sets the session cookie. */
export async function guestLogin(): Promise<void> {
  await apiFetch<undefined>("/auth/guest", { method: "POST" });
}

export async function logout(): Promise<void> {
  await apiFetch<undefined>("/auth/logout", { method: "POST" });
}
