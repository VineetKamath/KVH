import { toPlotNumber } from "../lib/money";

/** A 90-night price trail: a hairline path with the cheapest night marked. Pure SVG, decorative + labelled. */
export function Sparkline({ points, width = 220, height = 44, label }: { points: { d: string; p: string }[]; width?: number; height?: number; label: string }) {
  if (points.length < 2) return null;
  const ys = points.map((p) => toPlotNumber(p.p) ?? 0);
  const min = Math.min(...ys), max = Math.max(...ys);
  const span = max - min || 1;
  const x = (i: number) => (i / (points.length - 1)) * (width - 4) + 2;
  const y = (v: number) => height - 4 - ((v - min) / span) * (height - 8);
  const path = ys.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const iMin = ys.indexOf(min);
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
      <line x1="0" x2={width} y1={height - 1} y2={height - 1} stroke="var(--rule)" />
      <path d={path} fill="none" stroke="var(--indigo)" strokeWidth="1.4" strokeLinejoin="round" />
      <circle cx={x(iMin)} cy={y(min)} r="2.6" fill="var(--surface)" stroke="var(--teal)" strokeWidth="1.5" />
    </svg>
  );
}
