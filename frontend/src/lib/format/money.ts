const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const usdCents = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const usdCompact = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 1,
});

/** "$12,345"; `cents` keeps two decimals, `compact` gives "$12.3K". */
export function formatUsd(value: number, { cents = false, compact = false } = {}): string {
  if (compact) return usdCompact.format(value);
  return (cents ? usdCents : usd).format(value);
}

/** `value` is already a percentage (1.5 means 1.5%). */
export function formatPercent(value: number, { decimals = 1, signed = false } = {}): string {
  const sign = signed && value > 0 ? "+" : "";
  return `${sign}${value.toFixed(decimals)}%`;
}

/** A fraction as a percentage label (0.253 -> "25.3%"). */
export function formatShare(fraction: number, decimals = 1): string {
  return formatPercent(fraction * 100, { decimals });
}
