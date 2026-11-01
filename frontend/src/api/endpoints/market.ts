import { apiFetch } from "../client";
import type { MarketOverview, QuotesResponse } from "../types";

export function getMarketOverview(): Promise<MarketOverview> {
  return apiFetch<MarketOverview>("/market/overview");
}

export function getQuotes(symbols: string[]): Promise<QuotesResponse> {
  const query = new URLSearchParams({ symbols: symbols.join(",") });
  return apiFetch<QuotesResponse>(`/market/quotes?${query}`);
}
