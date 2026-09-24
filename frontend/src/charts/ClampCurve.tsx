/**
 * The Clamp Report curve (the signature visual). Custom SVG, because each clamped point needs its own shape,
 * a ghost dot at the raw price and a dashed whisker to the published price — a per-point geometry that
 * general charting libraries do not draw cleanly (docs/DECISIONS.md D-12). Keyboard: ←/→ move, Enter opens.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import type { Bound, CurvePoint } from "../api/types";
import { BOUND_META } from "../components/ui";
import { formatDate } from "../lib/dates";
import { formatMoney, toPlotNumber } from "../lib/money";

const H = 360;
const M = { l: 70, r: 92, t: 18, b: 36 };

function Marker({ bound, x, y }: { bound: Bound; x: number; y: number }) {
  const c = BOUND_META[bound].color;
  const s = 6.5;
  if (bound === "ceiling") return <path d={`M${x},${y - s} L${x + s},${y + s * 0.75} L${x - s},${y + s * 0.75} Z`} fill={c} />;
  if (bound === "floor") return <path d={`M${x},${y + s} L${x + s},${y - s * 0.75} L${x - s},${y - s * 0.75} Z`} fill={c} />;
  if (bound === "max_daily_movement") return <path d={`M${x},${y - s} L${x + s},${y} L${x},${y + s} L${x - s},${y} Z`} fill={c} />;
  return <rect x={x - s * 0.8} y={y - s * 0.8} width={s * 1.6} height={s * 1.6} fill={c} />;
}

export function ClampCurve({ points, currency, onSelect, selected }: {
  points: CurvePoint[]; currency: string; onSelect: (p: CurvePoint) => void; selected?: string | null;
}) {
  const wrap = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(900);
  const [hover, setHover] = useState<number | null>(null);
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(560, Math.floor(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const geo = useMemo(() => {
    const vals = points.flatMap((p) => [p.floor, p.ceiling, p.raw, p.published, p.pending?.price].filter(Boolean).map((v) => toPlotNumber(v!)!));
    const lo = Math.min(...vals), hi = Math.max(...vals);
    const pad = (hi - lo) * 0.06 || 1;
    const y0 = lo - pad, y1 = hi + pad;
    const iw = w - M.l - M.r, ih = H - M.t - M.b;
    const x = (i: number) => M.l + (points.length <= 1 ? iw / 2 : (i / (points.length - 1)) * iw);
    const y = (v: string) => M.t + ih - ((toPlotNumber(v)! - y0) / (y1 - y0)) * ih;
    const ticks = Array.from({ length: 5 }, (_, k) => y0 + ((y1 - y0) * k) / 4);
    return { x, y, iw, ih, ticks, y0, y1 };
  }, [points, w]);

  if (points.length === 0) return null;
  const { x, y, ih, ticks, y0, y1 } = geo;
  const yNum = (v: number) => M.t + ih - ((v - y0) / (y1 - y0)) * ih;
  const floor = points[0].floor, ceiling = points[0].ceiling;
  const clamped = points.filter((p) => p.clamp_status === "clamped" && p.clamp_bound);
  const step = Math.max(1, Math.round(points.length / 8));
  const hp = hover !== null ? points[hover] : null;
  const summaryLabel = `Price curve for ${points.length} stay dates between ${formatMoney(floor, currency)} and ${formatMoney(ceiling, currency)}; ${clamped.length} clamped.`;

  const onKey = (e: React.KeyboardEvent) => {
    const i = hover ?? points.findIndex((p) => p.decision_id === selected);
    if (e.key === "ArrowRight") { e.preventDefault(); setHover(Math.min(points.length - 1, (i < 0 ? -1 : i) + 1)); }
    if (e.key === "ArrowLeft") { e.preventDefault(); setHover(Math.max(0, (i < 0 ? 1 : i) - 1)); }
    if (e.key === "Enter" && hover !== null) onSelect(points[hover]);
  };

  // segments: dashed where either end is a manual override or kill-switch price
  const segs = points.slice(1).map((p, i) => {
    const a = points[i];
    const dashed = a.source !== "engine" || p.source !== "engine";
    return <line key={p.for_date} x1={x(i)} y1={y(a.published)} x2={x(i + 1)} y2={y(p.published)}
      stroke="var(--indigo)" strokeWidth={1.8} strokeDasharray={dashed ? "5 4" : undefined} strokeLinecap="round" />;
  });

  return (
    <div ref={wrap} className="relative w-full">
      <svg width={w} height={H} role="img" aria-label={summaryLabel} tabIndex={0} onKeyDown={onKey}
        onMouseLeave={() => setHover(null)} className="block outline-none">
        {/* floor–ceiling band */}
        <rect x={M.l} y={y(ceiling)} width={w - M.l - M.r} height={Math.max(0, y(floor) - y(ceiling))} fill="var(--band)" />
        <line x1={M.l} x2={w - M.r} y1={y(ceiling)} y2={y(ceiling)} stroke="var(--saffron)" strokeDasharray="2 3" />
        <line x1={M.l} x2={w - M.r} y1={y(floor)} y2={y(floor)} stroke="var(--teal)" strokeDasharray="2 3" />
        <text x={w - M.r + 8} y={y(ceiling) + 4} className="num" fontSize="11" fill="var(--saffron-text)">ceiling</text>
        <text x={w - M.r + 8} y={y(ceiling) + 17} className="num" fontSize="11" fill="var(--ink-muted)">{formatMoney(ceiling, currency, "en-IN", false).replace(/\.00$/, "")}</text>
        <text x={w - M.r + 8} y={y(floor) + 4} className="num" fontSize="11" fill="var(--teal)">floor</text>
        <text x={w - M.r + 8} y={y(floor) + 17} className="num" fontSize="11" fill="var(--ink-muted)">{formatMoney(floor, currency, "en-IN", false).replace(/\.00$/, "")}</text>

        {/* y axis: hairlines + mono labels */}
        {ticks.map((t) => (
          <g key={t}>
            <line x1={M.l} x2={w - M.r} y1={yNum(t)} y2={yNum(t)} stroke="var(--rule)" strokeWidth={0.6} />
            <text x={M.l - 10} y={yNum(t) + 4} textAnchor="end" fontSize="11" className="num" fill="var(--ink-faint)">
              {new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(t)}
            </text>
          </g>
        ))}
        {/* x axis */}
        {points.map((p, i) => i % step === 0 && (
          <text key={p.for_date} x={x(i)} y={H - 12} textAnchor="middle" fontSize="11" className="num" fill="var(--ink-faint)">{formatDate(p.for_date)}</text>
        ))}

        {/* baseline (the static price the engine starts from) */}
        <path d={points.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.baseline)}`).join(" ")} fill="none" stroke="var(--ink-faint)" strokeWidth={1} strokeDasharray="1 3" />
        {segs}

        {/* pending approvals: hollow at the proposed price */}
        {points.map((p, i) => p.pending && (
          <circle key={`pend-${p.for_date}`} cx={x(i)} cy={y(p.pending.price)} r={4} fill="var(--surface)" stroke="var(--vermilion)" strokeWidth={1.4} />
        ))}

        {/* clamped points: whisker from raw (ghost) to published, then the bound's marker */}
        {clamped.map((p) => {
          const i = points.indexOf(p);
          return (
            <g key={`c-${p.for_date}`}>
              <line x1={x(i)} x2={x(i)} y1={y(p.raw)} y2={y(p.published)} stroke={BOUND_META[p.clamp_bound!].color} strokeWidth={1.2} strokeDasharray="3 3" />
              <circle cx={x(i)} cy={y(p.raw)} r={3.6} fill="var(--surface)" stroke="var(--ink-faint)" strokeWidth={1.2} />
              <Marker bound={p.clamp_bound!} x={x(i)} y={y(p.published)} />
            </g>
          );
        })}

        {/* selection + hover */}
        {points.map((p, i) => p.decision_id === selected && (
          <circle key={`sel-${p.for_date}`} cx={x(i)} cy={y(p.published)} r={9} fill="none" stroke="var(--indigo)" strokeWidth={1.5} />
        ))}
        {hp && (
          <g pointerEvents="none">
            <line x1={x(hover!)} x2={x(hover!)} y1={M.t} y2={H - M.b} stroke="var(--rule-strong)" />
            <circle cx={x(hover!)} cy={y(hp.published)} r={4} fill="var(--indigo)" />
          </g>
        )}
        {/* hit columns */}
        {points.map((p, i) => (
          <rect key={`hit-${p.for_date}`} x={x(i) - (w - M.l - M.r) / points.length / 2} y={M.t} width={(w - M.l - M.r) / points.length} height={H - M.t - M.b}
            fill="transparent" onMouseEnter={() => setHover(i)} onClick={() => onSelect(p)} style={{ cursor: "pointer" }} />
        ))}
      </svg>

      {hp && (
        <div className="pointer-events-none absolute top-2 rounded-[6px] border border-rule bg-surface px-3 py-2 text-[12px]"
          style={{ left: Math.min(Math.max(x(hover!) + 12, 8), w - 230), boxShadow: "var(--shadow-drawer)" }}>
          <p className="num text-ink-muted">{formatDate(hp.for_date, "en-IN", { weekday: "short", day: "numeric", month: "short" })}</p>
          <p className="num text-[15px] text-ink">{formatMoney(hp.published, currency)}</p>
          {hp.clamp_status === "clamped" && hp.clamp_bound && (
            <p className="num text-ink-muted">raw {formatMoney(hp.raw, currency)} · <span style={{ color: BOUND_META[hp.clamp_bound].color }}>{BOUND_META[hp.clamp_bound].glyph} {BOUND_META[hp.clamp_bound].label}</span></p>
          )}
          {hp.source !== "engine" && <p className="text-indigo">{hp.source === "override" ? "Manual override" : "Kill switch: base rate"}</p>}
          {hp.pending && <p className="text-vermilion">Pending approval: {formatMoney(hp.pending.price, currency)}</p>}
        </div>
      )}
    </div>
  );
}

export function ClampLegend() {
  return (
    <ul className="flex flex-wrap items-center gap-x-5 gap-y-1 text-[12px] text-ink-muted">
      <li className="flex items-center gap-1.5"><span className="inline-block h-[2px] w-5 bg-indigo" /> Published</li>
      <li className="flex items-center gap-1.5"><span className="inline-block h-3 w-5 border-y border-dashed border-rule-strong" style={{ background: "var(--band)" }} /> Floor–ceiling band</li>
      {(Object.keys(BOUND_META) as Bound[]).map((b) => (
        <li key={b} className="flex items-center gap-1.5"><span style={{ color: BOUND_META[b].color }}>{BOUND_META[b].glyph}</span> {BOUND_META[b].label}</li>
      ))}
      <li className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-2.5 rounded-full border border-ink-faint" /> Raw model price</li>
      <li className="flex items-center gap-1.5"><span className="inline-block w-5 border-t-2 border-dashed border-indigo" /> Override</li>
      <li className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-2.5 rounded-full border border-vermilion" /> Pending</li>
    </ul>
  );
}
