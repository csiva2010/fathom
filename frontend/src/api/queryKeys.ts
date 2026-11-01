/** Central TanStack Query keys so invalidation stays consistent across features. */
export const queryKeys = {
  me: ["me"] as const,
  authConfig: ["auth", "config"] as const,
  health: ["health"] as const,
  marketOverview: ["market", "overview"] as const,
  quotes: (symbols: string[]) => ["market", "quotes", ...symbols] as const,
};
