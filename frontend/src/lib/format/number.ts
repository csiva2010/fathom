const priceFormat = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatPrice(value: number): string {
  return priceFormat.format(value);
}

/** "+1.23 (+0.45%)" style change label; returns an em dash when unknown. */
export function formatChange(change?: number | null, percent?: number | null): string {
  if (change == null && percent == null) return "—";
  const sign = (n: number) => (n > 0 ? "+" : "");
  const parts: string[] = [];
  if (change != null) parts.push(`${sign(change)}${priceFormat.format(change)}`);
  if (percent != null) parts.push(`(${sign(percent)}${percent.toFixed(2)}%)`);
  return parts.join(" ");
}

export type Direction = "up" | "down" | "flat";

export function direction(change?: number | null): Direction {
  if (change == null || change === 0) return "flat";
  return change > 0 ? "up" : "down";
}
