import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { getHistory, getIndicators, getMovers, getQuotes, getSectors, searchSymbols } from "@/api/endpoints/market";
import { queryKeys } from "@/api/queryKeys";
import type { PriceRange } from "@/api/types";

export function useMovers() {
  return useQuery({ queryKey: queryKeys.movers, queryFn: () => getMovers(5), refetchInterval: 60_000, staleTime: 30_000 });
}

export function useSectors() {
  return useQuery({ queryKey: queryKeys.sectors, queryFn: getSectors, refetchInterval: 60_000, staleTime: 30_000 });
}

export function useQuotes(symbols: string[]) {
  return useQuery({
    queryKey: queryKeys.quotes(symbols),
    queryFn: () => getQuotes(symbols),
    enabled: symbols.length > 0,
    placeholderData: keepPreviousData,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}

export function useHistory(symbol: string, range: PriceRange) {
  return useQuery({
    queryKey: queryKeys.history(symbol, range),
    queryFn: () => getHistory(symbol, range),
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });
}

export function useIndicators(symbol: string) {
  return useQuery({ queryKey: queryKeys.indicators(symbol), queryFn: () => getIndicators(symbol), staleTime: 5 * 60_000 });
}

export function useSymbolSearch(q: string) {
  return useQuery({
    queryKey: queryKeys.symbolSearch(q),
    queryFn: () => searchSymbols(q),
    enabled: q.length > 0,
    staleTime: 5 * 60_000,
  });
}

const DEFAULT_WATCHLIST = ["SPY", "AAPL", "VTI"];
const MAX_WATCHLIST = 20;

function readWatchlist(key: string): string[] {
  try {
    const saved: unknown = JSON.parse(window.localStorage.getItem(key) ?? "null");
    return Array.isArray(saved) ? saved.filter((s): s is string => typeof s === "string").slice(0, MAX_WATCHLIST) : DEFAULT_WATCHLIST;
  } catch {
    return DEFAULT_WATCHLIST;
  }
}

/** The user's watchlist, kept in this browser per account (no server state needed). */
export function useWatchlist(userId: string) {
  const key = `fathom.watchlist.${userId}`;
  const [state, setState] = useState(() => ({ key, symbols: readWatchlist(key) }));
  // A different account (sign out and back in) reads its own list.
  const symbols = state.key === key ? state.symbols : readWatchlist(key);

  const save = (next: string[]) => {
    setState({ key, symbols: next });
    window.localStorage.setItem(key, JSON.stringify(next));
  };
  return {
    symbols,
    add: (symbol: string) => {
      if (!symbols.includes(symbol) && symbols.length < MAX_WATCHLIST) save([...symbols, symbol]);
    },
    remove: (symbol: string) => save(symbols.filter((s) => s !== symbol)),
  };
}
