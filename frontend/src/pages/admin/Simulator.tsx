import { useMutation } from "@tanstack/react-query";
import { ArrowRight, FlaskConical, Sparkles } from "lucide-react";
import { useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../../api/client";
import type { SimResult, WhatIfParse } from "../../api/types";
import { Button, ChartOrTable, ErrorNote, SectionTitle, Stat, Tag } from "../../components/ui";
import { formatDate } from "../../lib/dates";
import { formatMoney, toPlotNumber } from "../../lib/money";
import { RoomPicker, useDesk } from "./Desk";

const EXAMPLES = [
  "cap the event uplift at 5% and lower the ceiling by 10%",
  "switch off the competitor factor for October",
  "raise the floor by 8% in November",
];

function pct(v: number) { return `${v > 0 ? "+" : ""}${v.toFixed(1)}%`; }

export default function Simulator() {
  const { room, entities } = useDesk();
  const cur = entities.find((e) => e.entity_id === room)?.currency ?? "INR";
  const [prompt, setPrompt] = useState(EXAMPLES[0]);
  const parse = useMutation({ mutationFn: () => api.admin.post<WhatIfParse>("/v1/whatif/parse", { prompt }) });
  const sim = useMutation({
    mutationFn: () => api.admin.post<SimResult>("/v1/simulate", { entity_id: room, config: parse.data!.config, name: prompt.slice(0, 80), prompt_text: prompt }),
  });
  const cfg = parse.data?.config as Record<string, unknown> | null | undefined;
  const r = sim.data;
  const data = r?.per_date.map((d) => ({ d: d.for_date, a: toPlotNumber(d.a), b: toPlotNumber(d.b) })) ?? [];

  return (
    <div>
      <SectionTitle n={5} title="What-if simulator"><RoomPicker /></SectionTitle>
      <div className="grid gap-5 xl:grid-cols-[1.1fr_1fr]">
        <section className="card p-5">
          <p className="eyebrow">Ask in plain language</p>
          <textarea className="input mt-2 w-full text-[15px]" rows={3} maxLength={500} value={prompt} onChange={(e) => setPrompt(e.target.value)} />
          <div className="mt-2 flex flex-wrap gap-2">
            {EXAMPLES.map((e) => <button key={e} onClick={() => setPrompt(e)} className="rounded-[4px] border border-rule px-2 py-1 text-[12px] text-ink-muted hover:border-rule-strong hover:text-ink">{e}</button>)}
          </div>
          <div className="mt-4 flex items-center justify-between gap-3">
            <p className="text-[12px] text-ink-muted">The model only turns words into a validated config. The pricing engine computes every number.</p>
            <Button variant="primary" onClick={() => { sim.reset(); parse.mutate(); }} disabled={parse.isPending || prompt.trim().length < 3}>
              <Sparkles size={14} strokeWidth={1.5} />{parse.isPending ? "Reading…" : "Understand"}</Button>
          </div>
          {parse.isError && <div className="mt-3"><ErrorNote error={parse.error} /></div>}
        </section>

        <section className="card p-5">
          <p className="eyebrow">Scenario B · validated config</p>
          {!parse.data && <p className="mt-3 text-[13px] text-ink-muted">Nothing parsed yet.</p>}
          {parse.data && !parse.data.accepted && (
            <div className="mt-3 space-y-1">
              <Tag tone="vermilion">rejected, not coerced</Tag>
              <ul className="list-disc pl-5 text-[13px] text-vermilion">{parse.data.errors.map((e) => <li key={e}>{e}</li>)}</ul>
            </div>
          )}
          {parse.data?.accepted && cfg && (
            <>
              <dl className="ledger mt-2 text-[13px]">
                {Object.entries(cfg).filter(([, v]) => v !== null && v !== "" && !(Array.isArray(v) && !v.length) && !(typeof v === "object" && v && !Array.isArray(v) && !Object.keys(v).length)).map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-4 py-1.5"><dt className="text-ink-muted">{k.replaceAll("_", " ")}</dt>
                    <dd className="num text-right">{typeof v === "object" ? JSON.stringify(v).replaceAll('"', "").replaceAll(",", ", ") : String(v)}</dd></div>
                ))}
              </dl>
              <p className="mt-2 text-[11px] text-ink-faint">parsed by {parse.data.source}</p>
              <Button variant="primary" className="mt-3" onClick={() => sim.mutate()} disabled={sim.isPending}>
                <FlaskConical size={14} strokeWidth={1.5} />{sim.isPending ? "Running the engine…" : "Run A vs B through the engine"}<ArrowRight size={14} strokeWidth={1.5} /></Button>
            </>
          )}
          {sim.isError && <div className="mt-3"><ErrorNote error={sim.error} /></div>}
        </section>
      </div>

      {r && (
        <section className="mt-5 space-y-5">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Avg price A → B" value={<>{formatMoney(r.A.avg_price, cur)} → {formatMoney(r.B.avg_price, cur)}</>} />
            <Stat label="Clamped A → B" value={`${r.A.clamped} → ${r.B.clamped}`} sub={`ceiling ${r.B.clamps.ceiling} · floor ${r.B.clamps.floor} · daily ${r.B.clamps.max_daily_movement}`} />
            <Stat label="Approvals needed A → B" value={`${r.A.approvals_needed} → ${r.B.approvals_needed}`} />
            <Stat label="Revenue change (range)" value={`${pct(r.revenue_change_range_pct[0])} … ${pct(r.revenue_change_range_pct[1])}`}
              sub="across elasticity assumptions" />
          </div>
          <div className="card p-5">
            <p className="eyebrow mb-2">Simulated price curve · A solid (live), B dashed</p>
            <ChartOrTable label="Simulation"
              chart={
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
                    <CartesianGrid stroke="var(--rule)" strokeWidth={0.6} vertical={false} />
                    <XAxis dataKey="d" tickFormatter={(v) => formatDate(v)} tick={{ fontSize: 11, fontFamily: "var(--font-mono)", fill: "var(--ink-faint)" }}
                      interval={Math.max(0, Math.round(data.length / 8))} axisLine={{ stroke: "var(--rule)" }} tickLine={false} />
                    <YAxis tick={{ fontSize: 11, fontFamily: "var(--font-mono)", fill: "var(--ink-faint)" }} axisLine={false} tickLine={false} width={56} domain={["auto", "auto"]} />
                    <Tooltip contentStyle={{ fontFamily: "var(--font-mono)", fontSize: 12, border: "1px solid var(--rule)", borderRadius: 6 }} labelFormatter={(l) => formatDate(String(l))} />
                    <Line dataKey="a" name="A (live)" stroke="var(--indigo)" dot={false} strokeWidth={1.8} isAnimationActive={false} />
                    <Line dataKey="b" name="B (scenario)" stroke="var(--saffron)" strokeDasharray="6 4" dot={false} strokeWidth={1.8} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              }
              table={
                <table className="w-full text-[12px]"><thead><tr className="text-left text-ink-muted"><th className="py-1">Stay date</th><th>A</th><th>B</th><th>B bound</th></tr></thead>
                  <tbody className="num">{r.per_date.map((d) => <tr key={d.for_date} className="border-t border-rule"><td className="py-1">{d.for_date}</td><td>{d.a}</td><td>{d.b}</td><td>{d.b_bound ?? ""}</td></tr>)}</tbody></table>
              } />
          </div>
          <div className="card p-5 text-[13px]">
            <p className="eyebrow mb-2">Assumptions (shown, not hidden)</p>
            <p>Price response: elasticity <span className="num">{r.assumptions.elasticity.elasticity.toFixed(2)}</span> (80%: <span className="num">{r.assumptions.elasticity.interval80[0].toFixed(2)} … {r.assumptions.elasticity.interval80[1].toFixed(2)}</span>),
              {" "}{r.assumptions.elasticity.method}, {r.assumptions.elasticity.cells} cells. The data shows little measurable response to price, so the revenue range also includes the literature prior (−1.0).</p>
            <ul className="num mt-2 grid grid-cols-2 gap-1 text-[12px] text-ink-muted lg:grid-cols-4">
              {Object.entries(r.revenue_change_pct).map(([k, v]) => <li key={k}>{k.replaceAll("_", " ")}: {pct(v)}</li>)}
            </ul>
            <p className="num mt-2 text-[11px] text-ink-faint">experiment {r.experiment_id} · window {r.window[0]} → {r.window[1]}</p>
          </div>
        </section>
      )}
    </div>
  );
}
