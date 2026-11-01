/** Pure helpers for the chat charts (kept apart from components for fast refresh). */

function niceStep(range: number, ticks: number): number {
  const raw = range / ticks;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const normalized = raw / magnitude;
  const nice = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return nice * magnitude;
}

/** Evenly spaced "nice" gridline values covering [min, max]. */
export function niceTicks(min: number, max: number, count = 4): number[] {
  if (max <= min) return [min];
  const step = niceStep(max - min, count);
  const start = Math.floor(min / step) * step;
  const ticks = [start];
  // Keep adding gridlines until one is at or above the maximum, so the data fits.
  while ((ticks[ticks.length - 1] ?? max) < max) ticks.push(Number((start + ticks.length * step).toFixed(10)));
  return ticks;
}

/** Spread end labels so they never overlap (at least `gap` px apart, order kept). */
export function spreadLabels(ys: number[], gap: number, top: number, bottom: number): number[] {
  const order = ys.map((y, i) => ({ y, i })).sort((a, b) => a.y - b.y);
  const placed: number[] = [];
  order.forEach(({ y }, k) => {
    placed[k] = Math.max(y, k === 0 ? top : (placed[k - 1] ?? top) + gap);
  });
  const overflow = (placed[placed.length - 1] ?? bottom) - bottom;
  const shifted = overflow > 0 ? placed.map((y) => y - overflow) : placed;
  const out = new Array<number>(ys.length);
  order.forEach(({ i }, k) => {
    out[i] = Math.max(top, shifted[k] ?? top);
  });
  return out;
}

/** Goal scenarios in fixed color order: slot 1 for the expected case. */
export const SCENARIOS = [
  { key: "expected", label: "Expected", color: "var(--viz-series-1)" },
  { key: "pessimistic", label: "Pessimistic", color: "var(--viz-series-2)" },
  { key: "optimistic", label: "Optimistic", color: "var(--viz-series-3)" },
] as const;
