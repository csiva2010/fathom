import type { AssetClass } from "@/api/types";

/** Fixed color per asset class (colors follow the category, never its rank). */
export const ASSET_CLASSES: { value: AssetClass; label: string; color: string }[] = [
  { value: "stock", label: "Stocks", color: "var(--viz-series-1)" },
  { value: "etf", label: "Stock funds (ETFs)", color: "var(--viz-series-2)" },
  { value: "bond_etf", label: "Bond funds", color: "var(--viz-series-3)" },
  { value: "cash", label: "Cash", color: "var(--viz-series-4)" },
  { value: "other", label: "Other", color: "var(--viz-series-5)" },
];

export function assetClassLabel(value: string): string {
  return ASSET_CLASSES.find((c) => c.value === value)?.label ?? value;
}
