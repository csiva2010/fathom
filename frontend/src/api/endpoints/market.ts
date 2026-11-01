import { apiFetch } from "../client";
import type {
  IndicatorsResponse,
  MarketOverview,
  Movers,
  PriceHistoryResponse,
  PriceRange,
  QuotesResponse,
  Sectors,
  SymbolSearch,
} from "../types";

export function getMarketOverview(): Promise<MarketOverview> {
  return apiFetch<MarketOverview>("/market/overview");
}

export function getQuotes(symbols: string[]): Promise<QuotesResponse> {
  const query = new URLSearchParams({ symbols: symbols.join(",") });
  return apiFetch<QuotesResponse>(`/market/quotes?${query}`);
}

export function getHistory(symbol: string, range: PriceRange): Promise<PriceHistoryResponse> {
  return apiFetch<PriceHistoryResponse>(`/market/history/${encodeURIComponent(symbol)}?range=${range}`);
}

export function getMovers(limit = 5): Promise<Movers> {
  return apiFetch<Movers>(`/market/movers?limit=${limit}`);
}

export function getSectors(): Promise<Sectors> {
  return apiFetch<Sectors>("/market/sectors");
}

export function searchSymbols(q: string): Promise<SymbolSearch> {
  return apiFetch<SymbolSearch>(`/market/symbols?${new URLSearchParams({ q, limit: "8" })}`);
}

export function getIndicators(symbol: string): Promise<IndicatorsResponse> {
  return apiFetch<IndicatorsResponse>(`/market/indicators/${encodeURIComponent(symbol)}`);
}
