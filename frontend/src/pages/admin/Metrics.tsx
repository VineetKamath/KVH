import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../../api/client";
import { ChartOrTable, Empty, ErrorNote, SectionTitle, Skeleton, Stat, Tag } from "../../components/ui";

type MetricsResp = {
  backtest: null | {
    window_days: number;
    pickup: Record<string, number>; naive: Record<string, number>; hindsight_oracle?: Record<string, number>; always_zero?: Record<string, number>;
    improvement_vs_naive: Record<string, number>;
    interval: Record<string, { coverage: number; interval_score: number }>;
  };
  ai_evals: null | { mode: string; whatif: { valid_parsed: number; valid_total: number; malformed_rejected: number; malformed_total: number };
    events: { micro_precision: number; rows: number } };
  model_selection: { as_of_date: string; component: string; champion: string; challenger: string | null; decision: string; dm_p_value: string | null }[];
  narration_gate: { total: number; passed: number; llm_written: number };
  live_prices: Record<string, number>;
  starter_queries: { events_by_month: { month: string; searches: number; bookings: number; cancellations: number }[];
    conversion_by_lead_time: { lead: string; searches: number; bookings: number }[] };
};

const p = (v: number) => `${(v * 100).toFixed(1)}%`;

export default function Metrics() {
  const q = useQuery({ queryKey: ["metrics"], queryFn: () => api.admin.get<MetricsResp>("/v1/metrics") });
  const m = q.data;
  return (
    <div>
      <SectionTitle n={6} title="Metrics" />
      <p className="mb-4 max-w-[75ch] text-[13px] text-ink-muted">Every number on this page is produced by code: the rolling-origin backtest runs through the production forecaster, the AI evals run against labelled sets, and live counts are queried now. Nothing is typed in.</p>
      {q.isLoading && <Skeleton lines={10} />}
      {q.isError && <ErrorNote error={q.error} />}
      {m && (
        <div className="space-y-6">
          {m.backtest && (
            <section>
              <h2 className="mb-3 text-[18px]">Forecast accuracy · held-out June–July 2026</h2>
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <Stat label="National weekly accuracy" value={p(m.backtest.pickup.national_week_accuracy)} sub={`naive ${p(m.backtest.naive.national_week_accuracy)}`} />
                <Stat label="National daily accuracy" value={p(m.backtest.pickup.national_day_accuracy)} sub={`naive ${p(m.backtest.naive.national_day_accuracy)}`} />
                <Stat label="City×day error vs naive" value={`−${p(m.backtest.improvement_vs_naive.city_day_mae)}`} sub="mean absolute error" />
                <Stat label="Deviance vs naive" value={`−${p(m.backtest.improvement_vs_naive.city_day_poisson_deviance)}`} sub="Poisson, city × day" />
              </div>
              {m.backtest.hindsight_oracle && (() => {
                const o = m.backtest.hindsight_oracle!, pk = m.backtest.pickup, nv = m.backtest.naive;
                const acc = (v: number) => (v <= 0 ? "≈ 0%" : p(v));
                return (
                  <div className="mt-4">
                    <h3 className="text-[15px] font-medium">How close to the best possible?</h3>
                    <p className="mt-1 max-w-[80ch] text-[13px] text-ink-muted">Bookings arrive at random. The <em>hindsight oracle</em> cheats: it predicts each day with the real average of the
                      surrounding month, known only afterwards. Its gap to 100% is randomness no forecast can remove, so a model level with it has learned everything
                      the booking level can teach. Fewer bookings per cell means more randomness, which is why pricing pools city → region → national by credibility.</p>
                    <table className="card mt-2 w-full text-[13px]">
                      <thead><tr className="text-left text-[11px] uppercase tracking-wider text-ink-muted">
                        <th className="px-4 py-2 font-medium">Level × grain</th><th className="font-medium">Bookings / week</th>
                        <th className="font-medium">Ours (pickup)</th><th className="font-medium">Naive</th><th className="font-medium">Hindsight oracle</th></tr></thead>
                      <tbody>{(["national", "region", "city"] as const).flatMap((g) => (["week", "day"] as const).map((gr) => (
                        <tr key={`${g}-${gr}`} className="border-t border-rule">
                          <td className="px-4 py-2 capitalize">{g} × {gr}</td>
                          <td className="num">{pk[`${g}_week_mean_bookings`]?.toFixed(1)}</td>
                          <td className="num font-medium">{acc(pk[`${g}_${gr}_accuracy`])}</td>
                          <td className="num text-ink-muted">{acc(nv[`${g}_${gr}_accuracy`])}</td>
                          <td className="num text-ink-muted">{acc(o[`${g}_${gr}_accuracy`])}</td>
                        </tr>)))}</tbody>
                    </table>
                    {m.backtest.always_zero && (() => {
                      const z = m.backtest.always_zero!;
                      const cols = [["Ours (pickup)", pk], ["Naive", nv], ["Always zero", z], ["Hindsight oracle", o]] as const;
                      return (
                        <div className="mt-4">
                          <h3 className="text-[15px] font-medium">City level: measures built for small counts</h3>
                          <p className="mt-1 max-w-[80ch] text-[13px] text-ink-muted">A city gets well under one booking a week, so a forecast of <em>zero bookings everywhere</em> already
                            scores ≈0% on 1 − WAPE. These measures tell a real forecast apart from doing nothing.</p>
                          <table className="card mt-2 w-full text-[13px]">
                            <thead><tr className="text-left text-[11px] uppercase tracking-wider text-ink-muted"><th className="px-4 py-2 font-medium">City × week</th>
                              {cols.map(([l]) => <th key={l} className="font-medium">{l}</th>)}</tr></thead>
                            <tbody>
                              <tr className="border-t border-rule"><td className="px-4 py-2">Within ±1 booking</td>{cols.map(([l, v]) => <td key={l} className="num">{p(v.city_week_within_1)}</td>)}</tr>
                              <tr className="border-t border-rule"><td className="px-4 py-2">Poisson deviance (lower is better)</td>{cols.map(([l, v]) => <td key={l} className="num">{v.city_week_deviance.toFixed(3)}</td>)}</tr>
                            </tbody>
                          </table>
                        </div>
                      );
                    })()}
                  </div>
                );
              })()}
              <table className="card mt-3 w-full text-[13px]">
                <thead><tr className="text-left text-[11px] uppercase tracking-wider text-ink-muted"><th className="px-4 py-2 font-medium">Uncertainty band</th><th className="font-medium">Coverage (target 80%)</th><th className="font-medium">Interval score (lower better)</th></tr></thead>
                <tbody>{Object.entries(m.backtest.interval).map(([k, v]) => (
                  <tr key={k} className="border-t border-rule"><td className="px-4 py-2">{k.replaceAll("_", " ")}</td><td className="num">{p(v.coverage)}</td><td className="num">{v.interval_score.toFixed(3)}</td></tr>))}</tbody>
              </table>
            </section>
          )}

          <section>
            <h2 className="mb-3 text-[18px]">Model selection on this deployment's own history</h2>
            {m.model_selection.length === 0 && <Empty title="No model selection recorded yet">The forecaster records its champion and challenger each time it refits, at the next pricing cycle.</Empty>}
            <ul className="card ledger text-[13px]">
              {m.model_selection.map((s, i) => (
                <li key={i} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2">
                  <span><span className="num text-ink-muted">{s.as_of_date}</span> · {s.component === "p50" ? "central forecast" : "uncertainty band"}: <strong>{s.champion.replaceAll("_", " ")}</strong>{s.challenger ? <span className="text-ink-muted"> vs {s.challenger.replaceAll("_", " ")}</span> : null}</span>
                  <span className="flex items-center gap-2">{s.dm_p_value && <span className="num text-[11px] text-ink-faint">p = {Number(s.dm_p_value).toExponential(1)}</span>}
                    <Tag tone={s.decision === "fallback_naive" ? "vermilion" : s.decision === "switch" ? "saffron" : "teal"}>{s.decision.replaceAll("_", " ")}</Tag></span>
                </li>
              ))}
            </ul>
          </section>

          <section className="grid gap-3 lg:grid-cols-3">
            {m.ai_evals && <>
              <Stat label={`A4 what-if parser · ${m.ai_evals.mode}`} value={`${m.ai_evals.whatif.valid_parsed}/${m.ai_evals.whatif.valid_total}`} sub={`${m.ai_evals.whatif.malformed_rejected}/${m.ai_evals.whatif.malformed_total} malformed rejected`} />
              <Stat label={`A3 event extractor · ${m.ai_evals.mode}`} value={p(m.ai_evals.events.micro_precision)} sub={`precision on ${m.ai_evals.events.rows} labelled rows`} />
            </>}
            <Stat label="A2 narration gate" value={`${m.narration_gate.passed}/${m.narration_gate.total}`} sub={`${m.narration_gate.llm_written} written by the LLM; the rest are gated templates`} />
          </section>

          <section className="grid gap-5 lg:grid-cols-2">
            <div className="card p-5">
              <p className="eyebrow mb-2">Organiser starter query 2 · bookings by lead time</p>
              <ChartOrTable label="Lead time" chart={
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={[...m.starter_queries.conversion_by_lead_time].sort((a, b) => parseInt(a.lead) - parseInt(b.lead))}>
                    <CartesianGrid stroke="var(--rule)" strokeWidth={0.6} vertical={false} />
                    <XAxis dataKey="lead" tick={{ fontSize: 11, fontFamily: "var(--font-mono)", fill: "var(--ink-faint)" }} axisLine={{ stroke: "var(--rule)" }} tickLine={false} />
                    <YAxis tick={{ fontSize: 11, fontFamily: "var(--font-mono)", fill: "var(--ink-faint)" }} axisLine={false} tickLine={false} width={40} />
                    <Tooltip contentStyle={{ fontFamily: "var(--font-mono)", fontSize: 12, borderRadius: 6 }} />
                    <Bar dataKey="bookings" fill="var(--indigo)" isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>} table={
                <table className="num w-full text-[12px]"><tbody>{[...m.starter_queries.conversion_by_lead_time].sort((a, b) => parseInt(a.lead) - parseInt(b.lead)).map((r) => <tr key={r.lead} className="border-t border-rule"><td className="py-1">{r.lead} days</td><td>{r.searches} searches</td><td>{r.bookings} bookings</td></tr>)}</tbody></table>} />
            </div>
            <div className="card p-5">
              <p className="eyebrow mb-2">Organiser starter query 1 · events by month</p>
              <ChartOrTable label="Events by month" chart={
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={m.starter_queries.events_by_month}>
                    <CartesianGrid stroke="var(--rule)" strokeWidth={0.6} vertical={false} />
                    <XAxis dataKey="month" tick={{ fontSize: 10, fontFamily: "var(--font-mono)", fill: "var(--ink-faint)" }} axisLine={{ stroke: "var(--rule)" }} tickLine={false} />
                    <YAxis tick={{ fontSize: 11, fontFamily: "var(--font-mono)", fill: "var(--ink-faint)" }} axisLine={false} tickLine={false} width={40} />
                    <Tooltip contentStyle={{ fontFamily: "var(--font-mono)", fontSize: 12, borderRadius: 6 }} />
                    <Bar dataKey="bookings" fill="var(--teal)" isAnimationActive={false} />
                    <Bar dataKey="cancellations" fill="var(--saffron)" isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>} table={
                <table className="num w-full text-[12px]"><tbody>{m.starter_queries.events_by_month.map((r) => <tr key={r.month} className="border-t border-rule"><td className="py-1">{r.month}</td><td>{r.bookings} bookings</td><td>{r.cancellations} cancellations</td></tr>)}</tbody></table>} />
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
