import { toPlotNumber } from "../lib/money";

/** A 90-night price trail: a hairline path with a soft fill, the cheapest night marked, and (optionally) the
 * traveller's check-in night highlighted. Pure SVG, labelled for screen readers. */
export function Sparkline({ points, width = 220, height = 44, label, highlight }: {
  points: { d: string; p: string }[]; width?: number; height?: number; label: string; highlight?: string | null;
}) {
  if (points.length < 2) return null;
  const ys = points.map((p) => toPlotNumber(p.p) ?? 0);
  const min = Math.min(...ys), max = Math.max(...ys);
  const span = max - min || 1;
  const x = (i: number) => (i / (points.length - 1)) * (width - 6) + 3;
  const y = (v: number) => height - 5 - ((v - min) / span) * (height - 10);
  const path = ys.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const area = `${path} L${x(ys.length - 1).toFixed(1)},${height} L${x(0).toFixed(1)},${height} Z`;
  const iMin = ys.indexOf(min);
  const iHi = highlight ? points.findIndex((p) => p.d === highlight) : -1;
  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label={label} style={{ maxWidth: width }}>
      <path d={area} fill="var(--indigo)" opacity="0.06" />
      <line x1="0" x2={width} y1={height - 0.5} y2={height - 0.5} stroke="var(--rule-strong)" />
      <path d={path} fill="none" stroke="var(--indigo)" strokeWidth="1.3" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      <circle cx={x(iMin)} cy={y(min)} r="2.6" fill="var(--surface)" stroke="var(--teal)" strokeWidth="1.5" />
      {iHi >= 0 && (<>
        <line x1={x(iHi)} x2={x(iHi)} y1={0} y2={height} stroke="var(--brass)" strokeWidth="1" strokeDasharray="2 2" />
        <circle cx={x(iHi)} cy={y(ys[iHi])} r="3" fill="var(--brass)" />
      </>)}
    </svg>
  );
}
