import { apiFetch } from "../client";
import type { ApiTokenCreated, ApiTokenList } from "../types";

/** Personal access tokens for the MCP server (MCP-03). Managed only from a browser session. */
export function listTokens(): Promise<ApiTokenList> {
  return apiFetch<ApiTokenList>("/me/tokens");
}

export function createToken(name: string): Promise<ApiTokenCreated> {
  return apiFetch<ApiTokenCreated>("/me/tokens", { method: "POST", body: JSON.stringify({ name }) });
}

export async function revokeToken(id: string): Promise<void> {
  await apiFetch<undefined>(`/me/tokens/${encodeURIComponent(id)}`, { method: "DELETE" });
}
