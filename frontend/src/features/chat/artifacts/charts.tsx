import { useId, useState, type PointerEvent } from "react";

import { formatUsd, formatShare } from "@/lib/format/money";

import { niceTicks, SCENARIOS, spreadLabels } from "./chartMath";

/*
 * Small hand-written SVG charts for chat answers. Colors come from the validated
 * `.viz-root` tokens in index.css; text always uses text tokens, never a series color.
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

function Tooltip({ left, children }: { left: number; children: React.ReactNode }) {
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

// --- Goal projection ---------------------------------------------------------------

export interface ProjectionSeriesPoint {
  month: number;
  date: string;
  contributed: number;
  values: Record<string, number>;
}

export function ProjectionChart({ series, target }: { series: ProjectionSeriesPoint[]; target: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const titleId = useId();
  if (series.length < 2) return null;

  const H = 220;
  const m = { left: 52, right: 92, top: 14, bottom: 24 };
  const lastMonth = series[series.length - 1]?.month ?? 1;
  const maxValue = Math.max(target, ...series.flatMap((p) => Object.values(p.values)));
  const ticks = niceTicks(0, maxValue * 1.05);
  const yMax = ticks[ticks.length - 1] ?? maxValue;
  const x = (month: number) => m.left + (month / lastMonth) * (W - m.left - m.right);
  const y = (value: number) => H - m.bottom - (value / yMax) * (H - m.top - m.bottom);
  const xs = series.map((p) => x(p.month));
  const path = (key: string) =>
    series.map((p, i) => `${i === 0 ? "M" : "L"}${x(p.month).toFixed(1)},${y(p.values[key] ?? 0).toFixed(1)}`).join("");

  const last = series[series.length - 1];
  const endYs = spreadLabels(
    SCENARIOS.map((s) => y(last?.values[s.key] ?? 0)),
    14,
    m.top + 4,
    H - m.bottom,
  );
  const point = hover === null ? undefined : series[hover];
  const year = (iso: string) => iso.slice(0, 4);

  return (
    <figure className="viz-root space-y-2" aria-labelledby={titleId}>
      <figcaption id={titleId} className="sr-only">
        Projected savings under three return scenarios against a target of {formatUsd(target)}
      </figcaption>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600 dark:text-slate-300" aria-label="Legend">
        {SCENARIOS.map((s) => (
          <li key={s.key} className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-4 rounded" style={{ background: s.color }} aria-hidden />
            {s.label}
          </li>
        ))}
        <li className="flex items-center gap-1.5">
          <span className="inline-block w-4 border-t-2 border-dashed" style={{ borderColor: "var(--viz-text-muted)" }} aria-hidden />
          Target
        </li>
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
          <line
            x1={m.left}
            x2={W - m.right}
            y1={y(target)}
            y2={y(target)}
            stroke="var(--viz-text-muted)"
            strokeWidth={1.5}
            strokeDasharray="5 4"
          />
          {SCENARIOS.map((s) => (
            <path key={s.key} d={path(s.key)} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          ))}
          {SCENARIOS.map((s, i) => (
            <g key={s.key}>
              <circle cx={W - m.right + 8} cy={endYs[i]} r={3} fill={s.color} />
              <text x={W - m.right + 14} y={endYs[i]} dy="0.32em" fontSize={10} fill="var(--viz-text)">
                {formatUsd(last?.values[s.key] ?? 0, { compact: true })}
              </text>
            </g>
          ))}
          {point && hover !== null && (
            <g>
              <line x1={xs[hover]} x2={xs[hover]} y1={m.top} y2={H - m.bottom} stroke="var(--viz-text-muted)" strokeWidth={1} />
              {SCENARIOS.map((s) => (
                <circle
                  key={s.key}
                  cx={xs[hover]}
                  cy={y(point.values[s.key] ?? 0)}
                  r={4}
                  fill={s.color}
                  stroke="var(--viz-surface)"
                  strokeWidth={2}
                />
              ))}
            </g>
          )}
          <rect
            x={m.left}
            y={m.top}
            width={W - m.left - m.right}
            height={H - m.top - m.bottom}
            fill="transparent"
            onPointerMove={(e) => setHover(nearestIndex(e, xs))}
            onPointerLeave={() => setHover(null)}
          />
        </svg>
        {point && hover !== null && (
          <Tooltip left={xs[hover] ?? 0}>
            <p className="font-medium">{new Date(point.date).toLocaleDateString("en-US", { month: "short", year: "numeric" })}</p>
            {SCENARIOS.map((s) => (
              <p key={s.key} className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full" style={{ background: s.color }} aria-hidden />
                {s.label}: {formatUsd(point.values[s.key] ?? 0)}
              </p>
            ))}
            <p className="text-slate-500 dark:text-slate-400">Put in: {formatUsd(point.contributed)}</p>
          </Tooltip>
        )}
      </div>
    </figure>
  );
}

// --- Price sparkline -----------------------------------------------------------------

export function PriceSparkline({ points, label }: { points: { t: string; close: number }[]; label: string }) {
  const [hover, setHover] = useState<number | null>(null);
  if (points.length < 2) return null;
  const H = 140;
  const m = { left: 8, right: 64, top: 10, bottom: 10 };
  const closes = points.map((p) => p.close);
  const lo = Math.min(...closes);
  const hi = Math.max(...closes);
  const pad = (hi - lo) * 0.08 || 1;
  const x = (i: number) => m.left + (i / (points.length - 1)) * (W - m.left - m.right);
  const y = (v: number) => H - m.bottom - ((v - (lo - pad)) / (hi - lo + 2 * pad)) * (H - m.top - m.bottom);
  const xs = points.map((_, i) => x(i));
  const d = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.close).toFixed(1)}`).join("");
  const lastClose = closes[closes.length - 1] ?? 0;
  const point = hover === null ? undefined : points[hover];

  return (
    <figure className="viz-root relative" aria-label={label}>
      <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-hidden>
        <path d={d} fill="none" stroke="var(--viz-series-1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={xs[xs.length - 1]} cy={y(lastClose)} r={4} fill="var(--viz-series-1)" stroke="var(--viz-surface)" strokeWidth={2} />
        <text x={W - m.right + 8} y={y(lastClose)} dy="0.32em" fontSize={11} fill="var(--viz-text)">
          {formatUsd(lastClose, { cents: true })}
        </text>
        {point && hover !== null && (
          <g>
            <line x1={xs[hover]} x2={xs[hover]} y1={m.top} y2={H - m.bottom} stroke="var(--viz-text-muted)" strokeWidth={1} />
            <circle cx={xs[hover]} cy={y(point.close)} r={4} fill="var(--viz-series-1)" stroke="var(--viz-surface)" strokeWidth={2} />
          </g>
        )}
        <rect
          x={m.left}
          y={0}
          width={W - m.left - m.right}
          height={H}
          fill="transparent"
          onPointerMove={(e) => setHover(nearestIndex(e, xs))}
          onPointerLeave={() => setHover(null)}
        />
      </svg>
      {point && hover !== null && (
        <Tooltip left={xs[hover] ?? 0}>
          <p className="font-medium">{new Date(point.t).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}</p>
          <p>Close: {formatUsd(point.close, { cents: true })}</p>
        </Tooltip>
      )}
    </figure>
  );
}

// --- Horizontal bars -------------------------------------------------------------------

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
            <span
              className="block h-full rounded-r"
              style={{ width: `${Math.max(1, (d.weight / max) * 100)}%`, background: "var(--viz-series-1)" }}
            />
          </span>
          <span className="text-right tabular-nums text-slate-700 dark:text-slate-200">{formatShare(d.weight)}</span>
        </li>
      ))}
    </ul>
  );
}
