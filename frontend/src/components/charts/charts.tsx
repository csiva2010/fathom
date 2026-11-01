import { useId, useState, type PointerEvent, type ReactNode } from "react";

import { formatPrice } from "@/lib/format/number";
import { formatPercent, formatShare, formatUsd } from "@/lib/format/money";

import { niceTicks, SCENARIOS, spreadLabels } from "./chartMath";

/*
 * Hand-written SVG charts (UI-07). Colors come from the validated `.viz-root` tokens in
 * index.css; text always uses text tokens, never a series color. Every plot has a hover
 * crosshair or per-mark tooltip, and a legend whenever it shows two or more series.
 */

const W = 560;

/** Index of the point nearest the pointer, from the pointer's x within the SVG. */
function nearestIndex(event: PointerEvent<SVGElement>, xs: number[]): number {
  const svg = event.currentTarget.ownerSVGElement ?? (event.currentTarget as SVGSVGElement);
  const rect = svg.getBoundingClientRect();
  const x = ((event.clientX - rect.left) / (rect.width || 1)) * W;
  let best = 0;
  xs.forEach((value, i) => {
    if (Math.abs(value - x) < Math.abs((xs[best] ?? 0) - x)) best = i;
  });
  return best;
}

function Tooltip({ left, children }: { left: number; children: ReactNode }) {
  const fraction = left / W;
  return (
    <div
      role="tooltip"
      className="pointer-events-none absolute top-2 z-10 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs shadow-md dark:border-slate-700 dark:bg-slate-900"
      style={fraction > 0.6 ? { right: `${(1 - fraction) * 100 + 2}%` } : { left: `${fraction * 100 + 2}%` }}
    >
      {children}
    </div>
  );
}

function HoverRect({ x, y, width, height, xs, onHover }: {
  x: number;
  y: number;
  width: number;
  height: number;
  xs: number[];
  onHover: (index: number | null) => void;
}) {
  return (
    <rect
      x={x}
      y={y}
      width={width}
      height={height}
      fill="transparent"
      onPointerMove={(e) => onHover(nearestIndex(e, xs))}
      onPointerLeave={() => onHover(null)}
    />
  );
}

function Crosshair({ x, top, bottom }: { x: number | undefined; top: number; bottom: number }) {
  return <line x1={x} x2={x} y1={top} y2={bottom} stroke="var(--viz-text-muted)" strokeWidth={1} />;
}

function Marker({ cx, cy, color }: { cx: number | undefined; cy: number; color: string }) {
  return <circle cx={cx} cy={cy} r={4} fill={color} stroke="var(--viz-surface)" strokeWidth={2} />;
}

function LegendLine({ color, dashed = false, band = false, children }: { color: string; dashed?: boolean; band?: boolean; children: ReactNode }) {
  return (
    <li className="flex items-center gap-1.5">
      {band ? (
        <span className="inline-block h-2.5 w-4 rounded-sm" style={{ background: color, opacity: 0.25 }} aria-hidden />
      ) : (
        <span
          className={`inline-block w-4 ${dashed ? "border-t-2 border-dashed" : "h-0.5 rounded"}`}
          style={dashed ? { borderColor: color } : { background: color }}
          aria-hidden
        />
      )}
      {children}
    </li>
  );
}

// --- Goal projection (GL-03, UI-06) -----------------------------------------------------

export interface ProjectionSeriesPoint {
  month: number;
  date: string;
  contributed: number;
  values: Record<string, number>;
}

/** Expected path inside a pessimistic-to-optimistic band, against the target. */
export function ProjectionChart({ series, target }: { series: ProjectionSeriesPoint[]; target: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const titleId = useId();
  if (series.length < 2) return null;

  const H = 220;
  const m = { left: 52, right: 136, top: 14, bottom: 24 };
  const lastMonth = series[series.length - 1]?.month ?? 1;
  const maxValue = Math.max(target, ...series.flatMap((p) => Object.values(p.values)));
  const ticks = niceTicks(0, maxValue * 1.05);
  const yMax = ticks[ticks.length - 1] ?? maxValue;
  const x = (month: number) => m.left + (month / lastMonth) * (W - m.left - m.right);
  const y = (value: number) => H - m.bottom - (value / yMax) * (H - m.top - m.bottom);
  const xs = series.map((p) => x(p.month));
  const at = (p: ProjectionSeriesPoint, key: string) => p.values[key] ?? 0;
  const line = (key: string) => series.map((p, i) => `${i === 0 ? "M" : "L"}${xs[i]?.toFixed(1)},${y(at(p, key)).toFixed(1)}`).join("");
  const band =
    series.map((p, i) => `${i === 0 ? "M" : "L"}${xs[i]?.toFixed(1)},${y(at(p, "optimistic")).toFixed(1)}`).join("") +
    [...series].reverse().map((p, i) => `L${xs[series.length - 1 - i]?.toFixed(1)},${y(at(p, "pessimistic")).toFixed(1)}`).join("") +
    "Z";

  const last = series[series.length - 1];
  const endYs = spreadLabels(SCENARIOS.map((s) => y(last ? at(last, s.key) : 0)), 14, m.top + 4, H - m.bottom);
  const point = hover === null ? undefined : series[hover];
  const year = (iso: string) => iso.slice(0, 4);

  return (
    <figure className="viz-root space-y-2" aria-labelledby={titleId}>
      <figcaption id={titleId} className="sr-only">
        Projected savings: expected path with a pessimistic to optimistic range, against a target of {formatUsd(target)}
      </figcaption>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600 dark:text-slate-300" aria-label="Legend">
        <LegendLine color="var(--viz-series-1)">Expected</LegendLine>
        <LegendLine color="var(--viz-series-1)" band>
          Pessimistic to optimistic
        </LegendLine>
        <LegendLine color="var(--viz-text-muted)" dashed>
          Target
        </LegendLine>
      </ul>
      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-hidden>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={m.left} x2={W - m.right} y1={y(t)} y2={y(t)} stroke="var(--viz-grid)" strokeWidth={1} />
              <text x={m.left - 6} y={y(t)} dy="0.32em" textAnchor="end" fontSize={10} fill="var(--viz-text-muted)">
                {formatUsd(t, { compact: true })}
              </text>
            </g>
          ))}
          <text x={m.left} y={H - 6} fontSize={10} fill="var(--viz-text-muted)">
            {year(series[0]?.date ?? "")}
          </text>
          <text x={W - m.right} y={H - 6} fontSize={10} textAnchor="end" fill="var(--viz-text-muted)">
            {year(last?.date ?? "")}
          </text>
          <path d={band} fill="var(--viz-series-1)" opacity={0.18} />
          <line x1={m.left} x2={W - m.right} y1={y(target)} y2={y(target)} stroke="var(--viz-text-muted)" strokeWidth={1.5} strokeDasharray="5 4" />
          <path d={line("expected")} fill="none" stroke="var(--viz-series-1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          {SCENARIOS.map((s, i) => (
            <text key={s.key} x={W - m.right + 8} y={endYs[i]} dy="0.32em" fontSize={10} fill={s.key === "expected" ? "var(--viz-text)" : "var(--viz-text-muted)"}>
              {s.label} {formatUsd(last ? at(last, s.key) : 0, { compact: true })}
            </text>
          ))}
          {point && hover !== null && (
            <g>
              <Crosshair x={xs[hover]} top={m.top} bottom={H - m.bottom} />
              <Marker cx={xs[hover]} cy={y(at(point, "expected"))} color="var(--viz-series-1)" />
            </g>
          )}
          <HoverRect x={m.left} y={m.top} width={W - m.left - m.right} height={H - m.top - m.bottom} xs={xs} onHover={setHover} />
        </svg>
        {point && hover !== null && (
          <Tooltip left={xs[hover] ?? 0}>
            <p className="font-medium">{new Date(point.date).toLocaleDateString("en-US", { month: "short", year: "numeric", timeZone: "UTC" })}</p>
            {SCENARIOS.map((s) => (
              <p key={s.key}>
                {s.label}: {formatUsd(at(point, s.key))}
              </p>
            ))}
            <p className="text-slate-500 dark:text-slate-400">Put in: {formatUsd(point.contributed)}</p>
          </Tooltip>
        )}
      </div>
    </figure>
  );
}

// --- Price history ---------------------------------------------------------------------------

/** One price series. `axis` adds price gridlines and start/end dates (Market view). */
export function PriceChart({ points, label, axis = false }: { points: { t: string; close: number }[]; label: string; axis?: boolean }) {
  const [hover, setHover] = useState<number | null>(null);
  if (points.length < 2) return null;
  const H = axis ? 220 : 140;
  const m = axis ? { left: 52, right: 64, top: 10, bottom: 24 } : { left: 8, right: 64, top: 10, bottom: 10 };
  const closes = points.map((p) => p.close);
  const ticks = axis ? niceTicks(Math.min(...closes), Math.max(...closes), 4) : [];
  const pad = (Math.max(...closes) - Math.min(...closes)) * 0.08 || 1;
  const lo = axis ? (ticks[0] ?? 0) : Math.min(...closes) - pad;
  const hi = axis ? (ticks[ticks.length - 1] ?? 1) : Math.max(...closes) + pad;
  const x = (i: number) => m.left + (i / (points.length - 1)) * (W - m.left - m.right);
  const y = (v: number) => H - m.bottom - ((v - lo) / (hi - lo || 1)) * (H - m.top - m.bottom);
  const xs = points.map((_, i) => x(i));
  const d = points.map((p, i) => `${i === 0 ? "M" : "L"}${xs[i]?.toFixed(1)},${y(p.close).toFixed(1)}`).join("");
  const lastClose = closes[closes.length - 1] ?? 0;
  const point = hover === null ? undefined : points[hover];
  const intraday = new Date(points[points.length - 1]?.t ?? 0).getTime() - new Date(points[0]?.t ?? 0).getTime() < 3 * 86_400_000;
  const when = (iso: string) =>
    new Date(iso).toLocaleString("en-US", intraday ? { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" } : { month: "short", day: "numeric", year: "numeric" });

  return (
    <figure className="viz-root relative" aria-label={label}>
      <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-hidden>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={m.left} x2={W - m.right} y1={y(t)} y2={y(t)} stroke="var(--viz-grid)" strokeWidth={1} />
            <text x={m.left - 6} y={y(t)} dy="0.32em" textAnchor="end" fontSize={10} fill="var(--viz-text-muted)">
              {formatPrice(t)}
            </text>
          </g>
        ))}
        {axis && (
          <>
            <text x={m.left} y={H - 6} fontSize={10} fill="var(--viz-text-muted)">
              {when(points[0]?.t ?? "")}
            </text>
            <text x={W - m.right} y={H - 6} fontSize={10} textAnchor="end" fill="var(--viz-text-muted)">
              {when(points[points.length - 1]?.t ?? "")}
            </text>
          </>
        )}
        <path d={d} fill="none" stroke="var(--viz-series-1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        <Marker cx={xs[xs.length - 1]} cy={y(lastClose)} color="var(--viz-series-1)" />
        <text x={W - m.right + 8} y={y(lastClose)} dy="0.32em" fontSize={11} fill="var(--viz-text)">
          {formatUsd(lastClose, { cents: true })}
        </text>
        {point && hover !== null && (
          <g>
            <Crosshair x={xs[hover]} top={m.top} bottom={H - m.bottom} />
            <Marker cx={xs[hover]} cy={y(point.close)} color="var(--viz-series-1)" />
          </g>
        )}
        <HoverRect x={m.left} y={0} width={W - m.left - m.right} height={H} xs={xs} onHover={setHover} />
      </svg>
      {point && hover !== null && (
        <Tooltip left={xs[hover] ?? 0}>
          <p className="font-medium">{when(point.t)}</p>
          <p>Close: {formatUsd(point.close, { cents: true })}</p>
        </Tooltip>
      )}
    </figure>
  );
}

// --- Portfolio vs benchmark (PF-05, UI-04) ------------------------------------------------------

export interface PerformancePoint {
  date: string;
  portfolio: number;
  benchmark: number;
}

const PERFORMANCE_SERIES = [
  { key: "portfolio", color: "var(--viz-series-1)" },
  { key: "benchmark", color: "var(--viz-series-2)" },
] as const;

/** Both lines rebased to 100 at the start, so the gap is the difference in return. */
export function PerformanceChart({
  points,
  benchmarkLabel,
  benchmarkShort = benchmarkLabel,
}: {
  points: PerformancePoint[];
  benchmarkLabel: string;
  /** Used for the end label beside the line, where space is tight. */
  benchmarkShort?: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  if (points.length < 2) return null;
  const labels = { portfolio: "This portfolio", benchmark: benchmarkLabel };
  const short = { portfolio: "Portfolio", benchmark: benchmarkShort };
  const H = 220;
  const m = { left: 44, right: 120, top: 10, bottom: 24 };
  const values = points.flatMap((p) => [p.portfolio, p.benchmark]);
  const ticks = niceTicks(Math.min(...values), Math.max(...values), 4);
  const lo = ticks[0] ?? 0;
  const hi = ticks[ticks.length - 1] ?? 1;
  const x = (i: number) => m.left + (i / (points.length - 1)) * (W - m.left - m.right);
  const y = (v: number) => H - m.bottom - ((v - lo) / (hi - lo || 1)) * (H - m.top - m.bottom);
  const xs = points.map((_, i) => x(i));
  const path = (key: "portfolio" | "benchmark") => points.map((p, i) => `${i === 0 ? "M" : "L"}${xs[i]?.toFixed(1)},${y(p[key]).toFixed(1)}`).join("");
  const last = points[points.length - 1];
  const change = (v: number) => formatPercent(v - 100, { signed: true });
  const endYs = spreadLabels(PERFORMANCE_SERIES.map((s) => y(last?.[s.key] ?? 100)), 14, m.top + 4, H - m.bottom);
  const point = hover === null ? undefined : points[hover];
  const day = (iso: string) => new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });

  return (
    <figure className="viz-root space-y-2" aria-label={`This portfolio compared with ${benchmarkLabel}`}>
      <ul className="flex flex-wrap gap-x-4 text-xs text-slate-600 dark:text-slate-300" aria-label="Legend">
        {PERFORMANCE_SERIES.map((s) => (
          <LegendLine key={s.key} color={s.color}>
            {labels[s.key]}
          </LegendLine>
        ))}
      </ul>
      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-hidden>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={m.left} x2={W - m.right} y1={y(t)} y2={y(t)} stroke="var(--viz-grid)" strokeWidth={t === 100 ? 1.5 : 1} />
              <text x={m.left - 6} y={y(t)} dy="0.32em" textAnchor="end" fontSize={10} fill="var(--viz-text-muted)">
                {change(t)}
              </text>
            </g>
          ))}
          <text x={m.left} y={H - 6} fontSize={10} fill="var(--viz-text-muted)">
            {day(points[0]?.date ?? "")}
          </text>
          <text x={W - m.right} y={H - 6} fontSize={10} textAnchor="end" fill="var(--viz-text-muted)">
            {day(last?.date ?? "")}
          </text>
          {PERFORMANCE_SERIES.map((s) => (
            <path key={s.key} d={path(s.key)} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          ))}
          {PERFORMANCE_SERIES.map((s, i) => (
            <g key={s.key}>
              <circle cx={W - m.right + 8} cy={endYs[i]} r={3} fill={s.color} />
              <text x={W - m.right + 14} y={endYs[i]} dy="0.32em" fontSize={10} fill="var(--viz-text)">
                {short[s.key]} {change(last?.[s.key] ?? 100)}
              </text>
            </g>
          ))}
          {point && hover !== null && (
            <g>
              <Crosshair x={xs[hover]} top={m.top} bottom={H - m.bottom} />
              {PERFORMANCE_SERIES.map((s) => (
                <Marker key={s.key} cx={xs[hover]} cy={y(point[s.key])} color={s.color} />
              ))}
            </g>
          )}
          <HoverRect x={m.left} y={m.top} width={W - m.left - m.right} height={H - m.top - m.bottom} xs={xs} onHover={setHover} />
        </svg>
        {point && hover !== null && (
          <Tooltip left={xs[hover] ?? 0}>
            <p className="font-medium">{day(point.date)}</p>
            {PERFORMANCE_SERIES.map((s) => (
              <p key={s.key} className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full" style={{ background: s.color }} aria-hidden />
                {labels[s.key]}: {change(point[s.key])}
              </p>
            ))}
          </Tooltip>
        )}
      </div>
    </figure>
  );
}

// --- Allocation donut (UI-04) ------------------------------------------------------------------

export interface DonutSlice {
  key: string;
  label: string;
  weight: number;
  value: number;
  color: string;
}

/** Share of the whole by category. Colors follow the category, never its rank. */
export function AllocationDonut({ slices, label }: { slices: DonutSlice[]; label: string }) {
  const [hover, setHover] = useState<string | null>(null);
  if (slices.length === 0) return null;
  const size = 160;
  const r = 62;
  const stroke = 22;
  const circumference = 2 * Math.PI * r;
  const gap = slices.length > 1 ? 2 : 0; // surface gap between segments
  // Where each segment starts along the ring.
  const starts = slices.map((_, i) => slices.slice(0, i).reduce((sum, s) => sum + s.weight * circumference, 0));
  const active = slices.find((s) => s.key === hover);

  return (
    <figure className="viz-root flex flex-wrap items-center gap-4" aria-label={label}>
      <svg viewBox={`0 0 ${size} ${size}`} className="h-36 w-36 shrink-0" role="img" aria-hidden>
        <g transform={`rotate(-90 ${size / 2} ${size / 2})`}>
          {slices.map((s, i) => {
            const length = Math.max(0, s.weight * circumference - gap);
            return (
              <circle
                key={s.key}
                cx={size / 2}
                cy={size / 2}
                r={r}
                fill="none"
                stroke={s.color}
                strokeWidth={hover === s.key ? stroke + 4 : stroke}
                strokeDasharray={`${length} ${circumference - length}`}
                strokeDashoffset={-(starts[i] ?? 0)}
                onPointerEnter={() => setHover(s.key)}
                onPointerLeave={() => setHover(null)}
              />
            );
          })}
        </g>
        <text x={size / 2} y={size / 2 - 4} textAnchor="middle" fontSize={12} fill="var(--viz-text-muted)">
          {active ? active.label : "Total"}
        </text>
        <text x={size / 2} y={size / 2 + 14} textAnchor="middle" fontSize={14} fontWeight={600} fill="var(--viz-text)">
          {active ? formatShare(active.weight) : formatUsd(slices.reduce((sum, s) => sum + s.value, 0), { compact: true })}
        </text>
      </svg>
      <ul className="min-w-40 flex-1 space-y-1 text-sm" aria-label={`${label} legend`}>
        {slices.map((s) => (
          <li key={s.key} className="flex items-center gap-2" onPointerEnter={() => setHover(s.key)} onPointerLeave={() => setHover(null)}>
            <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: s.color }} aria-hidden />
            <span className="flex-1 text-slate-700 dark:text-slate-200">{s.label}</span>
            <span className="tabular-nums text-slate-700 dark:text-slate-200">{formatShare(s.weight)}</span>
            <span className="w-16 text-right tabular-nums text-slate-500 dark:text-slate-400">{formatUsd(s.value, { compact: true })}</span>
          </li>
        ))}
      </ul>
    </figure>
  );
}

// --- Horizontal bars -------------------------------------------------------------------------

export interface BarDatum {
  label: string;
  weight: number; // fraction of the whole
  value?: number; // dollars, when known
}

/** Share-of-whole bars, every row labeled with its percentage (no legend needed). */
export function ShareBars({ data, label }: { data: BarDatum[]; label: string }) {
  if (data.length === 0) return null;
  const max = Math.max(...data.map((d) => d.weight)) || 1;
  return (
    <ul aria-label={label} className="viz-root space-y-0.5 text-xs">
      {data.map((d) => (
        <li
          key={d.label}
          className="grid grid-cols-[10.5rem_1fr_3.5rem] items-center gap-2"
          title={d.value !== undefined ? `${d.label}: ${formatShare(d.weight)} (${formatUsd(d.value)})` : `${d.label}: ${formatShare(d.weight)}`}
        >
          <span className="truncate text-slate-700 dark:text-slate-200">{d.label}</span>
          <span className="h-3">
            <span className="block h-full rounded-r" style={{ width: `${Math.max(1, (d.weight / max) * 100)}%`, background: "var(--viz-series-1)" }} />
          </span>
          <span className="text-right tabular-nums text-slate-700 dark:text-slate-200">{formatShare(d.weight)}</span>
        </li>
      ))}
    </ul>
  );
}
