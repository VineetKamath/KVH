import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, Languages, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../../api/client";
import type { Curve, CurvePoint, Explain } from "../../api/types";
import { ClampCurve, ClampLegend } from "../../charts/ClampCurve";
import { Waterfall } from "../../charts/Waterfall";
import { BOUND_META, Button, ChartOrTable, Drawer, ErrorNote, SectionTitle, Skeleton, Stamp, Tag } from "../../components/ui";
import { formatDate } from "../../lib/dates";
import { formatMoney, toPlotNumber, type Locale } from "../../lib/money";
import { RoomPicker, useDesk } from "./Desk";

function Headline({ c }: { c: Curve }) {
  const s = c.summary;
  return (
    <div className="card mb-5 flex flex-wrap items-center justify-between gap-4 px-5 py-4">
      <div>
        <p className="eyebrow">Guardrail clamp report · live prices</p>
        <p className="font-display mt-1 text-[22px] leading-snug text-ink" aria-live="polite">{s.headline}</p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {(Object.keys(BOUND_META) as (keyof typeof BOUND_META)[]).map((b) => (
          <span key={b} className={`stamp ${BOUND_META[b].cls} ${s.by_bound[b] ? "" : "opacity-40"}`}>
            {BOUND_META[b].glyph} {BOUND_META[b].label} <span className="num">{s.by_bound[b]}</span>
          </span>
        ))}
        {s.controlled > 0 && <Tag tone="indigo">{s.controlled} set by control (never counted)</Tag>}
      </div>
    </div>
  );
}

function ForecastFan({ points }: { points: CurvePoint[] }) {
  const data = points.filter((p) => p.forecast).map((p) => ({
    d: p.for_date, band: [toPlotNumber(p.forecast!.p10), toPlotNumber(p.forecast!.p90)], p50: toPlotNumber(p.forecast!.p50),
  }));
  if (!data.length) return <p className="text-[13px] text-ink-muted">No forecast rows for these dates.</p>;
  return (
    <ChartOrTable label="Forecast fan"
      chart={
        <ResponsiveContainer width="100%" height={200}>
          <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="var(--rule)" strokeWidth={0.6} vertical={false} />
            <XAxis dataKey="d" tickFormatter={(v) => formatDate(v)} tick={{ fontSize: 11, fontFamily: "var(--font-mono)", fill: "var(--ink-faint)" }}
              interval={Math.max(0, Math.round(data.length / 8))} axisLine={{ stroke: "var(--rule)" }} tickLine={false} />
            <YAxis tick={{ fontSize: 11, fontFamily: "var(--font-mono)", fill: "var(--ink-faint)" }} axisLine={false} tickLine={false} width={40} />
            <Tooltip contentStyle={{ fontFamily: "var(--font-mono)", fontSize: 12, border: "1px solid var(--rule)", borderRadius: 6 }}
              formatter={(v: unknown) => (Array.isArray(v) ? v.map((x) => Number(x).toFixed(2)).join(" – ") : Number(v).toFixed(2))} labelFormatter={(l) => formatDate(String(l))} />
            <Area dataKey="band" stroke="none" fill="var(--indigo)" fillOpacity={0.1} isAnimationActive={false} name="P10–P90" />
            <Line dataKey="p50" stroke="var(--indigo)" dot={false} strokeWidth={1.6} isAnimationActive={false} name="P50" />
          </ComposedChart>
        </ResponsiveContainer>
      }
      table={
        <table className="w-full text-[12px]"><thead><tr className="text-left text-ink-muted"><th className="py-1">Stay date</th><th>P10</th><th>P50</th><th>P90</th></tr></thead>
          <tbody className="num">{data.map((r) => <tr key={r.d} className="border-t border-rule"><td className="py-1">{r.d}</td><td>{r.band[0]?.toFixed(2)}</td><td>{r.p50?.toFixed(2)}</td><td>{r.band[1]?.toFixed(2)}</td></tr>)}</tbody></table>
      } />
  );
}

function DecisionDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const ex = useQuery({ queryKey: ["explain", id], queryFn: () => api.admin.get<Explain>(`/v1/decisions/${id}/explain`), enabled: !!id });
  const narrate = useMutation({
    mutationFn: (loc: Locale) => api.admin.post<{ sentences: string[]; source: string; gate_passed: boolean; locale: string }>(`/v1/narrate/${id}?locale=${loc}`),
  });
  useEffect(() => { narrate.reset(); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps
  const e = ex.data;
  return (
    <Drawer open={!!id} onClose={onClose} title={
      e ? (
        <div>
          <p className="eyebrow">Decision · {formatDate(e.for_date, "en-IN", { weekday: "short", day: "numeric", month: "long" })}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {e.clamp.bound ? <Stamp bound={e.clamp.bound} value={e.clamp.bound_value} currency={e.currency} />
              : <Tag tone={e.source === "engine" ? "teal" : "indigo"}>{e.source === "engine" ? "Accepted: inside every guardrail" : e.source === "override" ? "Manual override" : "Kill switch"}</Tag>}
            {e.approval.status === "pending_approval" && <Tag tone="vermilion">Pending approval</Tag>}
          </div>
        </div>
      ) : <p className="eyebrow">Decision</p>
    }>
      {ex.isLoading && <Skeleton lines={8} />}
      {ex.isError && <ErrorNote error={ex.error} />}
      {e && (
        <div className="space-y-6">
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 rounded-[6px] border border-rule bg-paper px-4 py-4">
            <div><p className="eyebrow">Raw model price</p><p className="num mt-1 text-[20px] text-ink-muted">{formatMoney(e.raw, e.currency)}</p></div>
            <ArrowRight size={18} strokeWidth={1.5} className="text-ink-faint" />
            <div><p className="eyebrow">Published</p><p className="display-price mt-1 text-[26px] text-indigo">{formatMoney(e.published, e.currency)}</p></div>
          </div>
          {e.clamp.bound && (
            <p className="text-[14px]">Clamped by <strong style={{ color: BOUND_META[e.clamp.bound].color }}>{BOUND_META[e.clamp.bound].label.toUpperCase()}</strong>
              {" "}at <span className="num">{formatMoney(e.clamp.bound_value!, e.currency)}</span>.</p>
          )}

          <section>
            <p className="eyebrow mb-2">Guardrail chain</p>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-[13px]">
              <dt className="text-ink-muted">Daily anchor (live at D−1)</dt><dd className="num text-right">{formatMoney(e.anchors.daily, e.currency)}</dd>
              <dt className="text-ink-muted">Weekly anchor (live at D−7)</dt><dd className="num text-right">{formatMoney(e.anchors.weekly, e.currency)}</dd>
              <dt className="text-ink-muted">Price before this cycle</dt><dd className="num text-right">{formatMoney(e.live_before, e.currency)}</dd>
            </dl>
            {e.clamp.chain.length > 0 ? (
              <ol className="ledger mt-2 rounded-[6px] border border-rule text-[13px]">
                {e.clamp.chain.map((s, i) => (
                  <li key={i} className="flex items-center justify-between px-3 py-1.5"><span>{s.guardrail.replaceAll("_", " ")}</span>
                    <span className="num text-ink-muted">{formatMoney(s.before, e.currency)} → {formatMoney(s.after, e.currency)}</span></li>
                ))}
              </ol>
            ) : <p className="mt-2 text-[13px] text-ink-muted">No guardrail changed the model price.</p>}
          </section>

          <section>
            <p className="eyebrow mb-2">Why: factor waterfall</p>
            <Waterfall baseline={e.baseline} published={e.published} steps={e.waterfall} currency={e.currency} />
            <p className="mt-2 text-[12px] text-ink-muted">Top drivers: {e.top_drivers.map((d) => d.replaceAll("_", " ")).join(", ")}</p>
          </section>

          {e.forecast && (
            <section>
              <p className="eyebrow mb-2">Forecast behind the demand factor</p>
              <p className="num text-[13px]">7-day demand P10 {e.forecast.p10} · P50 {e.forecast.p50} · P90 {e.forecast.p90} (normal {e.forecast.normal})</p>
              <p className="mt-1 text-[12px] text-ink-muted">{e.forecast.level} level · credibility {Number(e.forecast.credibility).toFixed(2)} · {e.forecast.band} confidence · {e.forecast.method}</p>
            </section>
          )}

          <section>
            <p className="eyebrow mb-2">Traveller explanation (AI, numerically gated)</p>
            <div className="flex flex-wrap gap-2">
              {(["hi", "kn", "en-IN"] as Locale[]).map((l) => (
                <Button key={l} onClick={() => narrate.mutate(l)} disabled={narrate.isPending}><Languages size={14} strokeWidth={1.5} />
                  {{ hi: "हिन्दी", kn: "ಕನ್ನಡ", "en-IN": "English" }[l]}</Button>
              ))}
            </div>
            {narrate.isPending && <div className="mt-3"><Skeleton lines={3} /></div>}
            {narrate.data && (
              <div className="mt-3 rounded-[6px] border border-rule bg-paper px-4 py-3" lang={narrate.data.locale}>
                <ul className="space-y-1.5 text-[14px]">{narrate.data.sentences.map((s, i) => <li key={i}>{s}</li>)}</ul>
                <p className="mt-2 text-[11px] text-ink-muted">{narrate.data.source === "llm" ? "Written by Claude from this decision's numbers" : "Deterministic template (LLM offline or gated out)"} ·
                  {" "}gate {narrate.data.gate_passed ? "passed" : "failed"}</p>
              </div>
            )}
            {narrate.isError && <div className="mt-3"><ErrorNote error={narrate.error} /></div>}
          </section>

          <section className="grid grid-cols-2 gap-2 border-t border-rule pt-4 text-[12px]">
            <span className="flex items-center gap-1.5">{e.reconstruction_ok ? <CheckCircle2 size={14} className="text-teal" /> : <XCircle size={14} className="text-vermilion" />} Reconstructs to the paisa</span>
            <span className="flex items-center gap-1.5">{e.replay_ok ? <CheckCircle2 size={14} className="text-teal" /> : e.replay_ok === null ? <span className="text-ink-faint">—</span> : <XCircle size={14} className="text-vermilion" />} Replays exactly from stored inputs</span>
            <span className="num col-span-2 text-ink-faint">bounds v{e.versions.bounds} · engine v{e.versions.engine_config} · {e.versions.model} · {e.decision_id}</span>
          </section>
        </div>
      )}
    </Drawer>
  );
}

export default function ClampReport() {
  const { room } = useDesk();
  const [params, setParams] = useSearchParams();
  const [selected, setSelected] = useState<string | null>(null);
  const curve = useQuery({ queryKey: ["curve", room], queryFn: () => api.admin.get<Curve>(`/v1/prices/curve?entity_id=${room}`) });
  const dateParam = params.get("date");
  useEffect(() => {
    if (dateParam && curve.data) {
      const p = curve.data.points.find((x) => x.for_date === dateParam);
      if (p) setSelected(p.decision_id);
    }
  }, [dateParam, curve.data]);
  const close = () => { setSelected(null); if (dateParam) { const p = new URLSearchParams(params); p.delete("date"); setParams(p); } };
  const c = curve.data;
  return (
    <div>
      <SectionTitle n={1} title={c?.room.hotel_name ? `${c.room.hotel_name} · ${c.room.room_name}` : "Curve & clamps"}><RoomPicker /></SectionTitle>
      {curve.isLoading && <Skeleton lines={10} />}
      {curve.isError && <ErrorNote error={curve.error} />}
      {c && (
        <>
          <Headline c={c} />
          <div className="card p-5">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <p className="eyebrow">{c.points.length} stay dates · click any point to open its decision</p>
              <ClampLegend />
            </div>
            <ChartOrTable label="Price curve"
              chart={<ClampCurve points={c.points} currency={c.currency} selected={selected} onSelect={(p) => setSelected(p.decision_id)} />}
              table={
                <table className="w-full text-[12px]">
                  <thead><tr className="text-left text-ink-muted"><th className="py-1">Stay date</th><th>Raw</th><th>Published</th><th>Status</th><th /></tr></thead>
                  <tbody>{c.points.map((p) => (
                    <tr key={p.for_date} className="border-t border-rule">
                      <td className="num py-1">{p.for_date}</td><td className="num">{p.raw}</td><td className="num">{p.published}</td>
                      <td>{p.clamp_bound ? `${BOUND_META[p.clamp_bound].glyph} ${BOUND_META[p.clamp_bound].label}` : p.source !== "engine" ? p.source : "accepted"}</td>
                      <td><button className="text-indigo underline" onClick={() => setSelected(p.decision_id)}>open</button></td>
                    </tr>))}</tbody>
                </table>} />
          </div>
          <div className="card mt-5 p-5">
            <p className="eyebrow mb-2">Demand forecast behind these prices (7-day window, P10–P90)</p>
            <ForecastFan points={c.points} />
          </div>
        </>
      )}
      <DecisionDrawer id={selected} onClose={close} />
    </div>
  );
}
