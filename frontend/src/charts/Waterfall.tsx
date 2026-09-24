/** Ledger-style horizontal waterfall. Every bar is a real contribution; the column sums exactly to the price. */
import Decimal from "decimal.js";
import type { WaterfallStep } from "../api/types";
import { formatMoney } from "../lib/money";

const LABELS: Record<string, string> = {
  seasonality: "Seasonality", demand: "Demand pressure", pace: "Booking pace", lead_time: "Lead time", event: "Approved event",
  competitor: "Competitive parity (simulated)", cancellation: "Cancellation risk", uncertainty: "Uncertainty damper",
  guardrail: "Guardrail clamp", rounding: "Rounding", override: "Manual override", kill_switch: "Kill switch",
};

export function Waterfall({ baseline, published, steps, currency }: { baseline: string; published: string; steps: WaterfallStep[]; currency: string }) {
  let running = new Decimal(baseline);
  const rows = steps.map((s) => {
    const start = running;
    running = running.plus(new Decimal(s.contribution));
    return { ...s, start, end: running };
  });
  const all = [new Decimal(baseline), ...rows.map((r) => r.end), ...rows.map((r) => r.start)];
  const lo = Decimal.min(...all), hi = Decimal.max(...all);
  const span = hi.minus(lo).isZero() ? new Decimal(1) : hi.minus(lo);
  const pos = (v: Decimal) => v.minus(lo).div(span).times(100).toNumber(); // % of track width (layout only)
  const total = rows.reduce((a, r) => a.plus(new Decimal(r.contribution)), new Decimal(0));
  const exact = total.equals(new Decimal(published).minus(new Decimal(baseline)));

  return (
    <div>
      <ul className="ledger text-[13px]">
        <li className="grid grid-cols-[170px_1fr_104px] items-center gap-3 py-2">
          <span className="text-ink-muted">Reference rate</span>
          <span className="relative h-3"><span className="absolute top-0 h-3 w-[2px] bg-ink" style={{ left: `${pos(new Decimal(baseline))}%` }} /></span>
          <span className="num text-right">{formatMoney(baseline, currency)}</span>
        </li>
        {rows.filter((r) => !new Decimal(r.contribution).isZero()).map((r) => {
          const up = new Decimal(r.contribution).gt(0);
          const a = pos(Decimal.min(r.start, r.end)), b = pos(Decimal.max(r.start, r.end));
          return (
            <li key={r.step} className="grid grid-cols-[170px_1fr_104px] items-center gap-3 py-2">
              <span className="truncate">{LABELS[r.step] ?? r.step}{r.multiplier ? <span className="num ml-1.5 text-[11px] text-ink-faint">×{new Decimal(r.multiplier).toFixed(3)}</span> : null}</span>
              <span className="relative h-3 rounded-[2px] bg-paper-deep/60">
                <span className="absolute top-0 h-3 rounded-[2px]" style={{ left: `${a}%`, width: `${Math.max(b - a, 0.6)}%`, background: up ? "var(--saffron)" : "var(--teal)" }} />
              </span>
              <span className={`num text-right ${up ? "text-saffron-text" : "text-teal"}`}>{up ? "+" : "−"}{formatMoney(new Decimal(r.contribution).abs().toFixed(2), currency)}</span>
            </li>
          );
        })}
        <li className="grid grid-cols-[170px_1fr_104px] items-center gap-3 py-2 font-medium">
          <span>Published price</span>
          <span className="relative h-3"><span className="absolute top-0 h-3 w-[2px] bg-indigo" style={{ left: `${pos(new Decimal(published))}%` }} /></span>
          <span className="num text-right text-indigo">{formatMoney(published, currency)}</span>
        </li>
      </ul>
      <p className={`num mt-2 text-[11px] ${exact ? "text-teal" : "text-vermilion"}`}>
        {exact ? "✓ contributions sum exactly to the published price" : "✗ reconstruction mismatch"}
      </p>
    </div>
  );
}
