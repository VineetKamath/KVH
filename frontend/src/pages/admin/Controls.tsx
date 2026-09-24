import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { OctagonX, Play, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { Button, ErrorNote, SectionTitle, Skeleton, Tag } from "../../components/ui";
import { addDays } from "../../lib/dates";
import { formatMoney } from "../../lib/money";
import { RoomPicker, useDesk } from "./Desk";

type BoundsResp = { bounds: Record<string, string>; versions: Record<string, string>[] };
type Engine = { version: number; auto_band_pct: string; kill_switch_active: boolean; config: { factor_bounds: Record<string, { lo: string; hi: string; enabled: boolean }> } };
type Override = { override_id: string; entity_id: string; from_date: string; to_date: string; price: string; currency: string; reason: string; expires_at: string; status: string };

function Panel({ title, children, tone }: { title: string; children: React.ReactNode; tone?: "danger" }) {
  return (
    <section className={`card p-5 ${tone === "danger" ? "border-vermilion/40" : ""}`}>
      <h2 className="mb-3 text-[18px]">{title}</h2>
      {children}
    </section>
  );
}

function BoundsEditor() {
  const { room } = useDesk();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["bounds", room], queryFn: () => api.admin.get<BoundsResp>(`/v1/bounds/${room}`) });
  const [form, setForm] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");
  useEffect(() => { if (q.data) setForm({ ...q.data.bounds }); }, [q.data]);
  const save = useMutation({
    mutationFn: () => {
      const b = q.data!.bounds;
      const changes: Record<string, string> = {};
      for (const k of ["floor_price", "ceiling_price", "max_daily_move_pct", "max_weekly_move_pct", "rounding_step"]) if (form[k] !== b[k]) changes[k] = form[k];
      return api.admin.put(`/v1/bounds/${room}`, { ...changes, reason });
    },
    onSuccess: () => { setReason(""); qc.invalidateQueries(); },
  });
  if (q.isLoading) return <Skeleton />;
  if (!q.data) return <ErrorNote error={q.error} />;
  const cur = q.data.bounds.currency;
  const fields: [string, string][] = [["floor_price", `Floor (${cur})`], ["ceiling_price", `Ceiling (${cur})`], ["max_daily_move_pct", "Max daily move %"],
    ["max_weekly_move_pct", "Max weekly move %"], ["rounding_step", `Rounding step (${cur})`]];
  return (
    <Panel title="Guardrails for this room">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {fields.map(([k, label]) => (
          <label key={k} className="field"><span>{label}</span>
            <input className="input num" value={form[k] ?? ""} onChange={(e) => setForm({ ...form, [k]: e.target.value })} inputMode="decimal" /></label>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <label className="field min-w-[280px] flex-1"><span>Reason (required, audited)</span>
          <input className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Tighten ceiling for Diwali fairness policy" /></label>
        <Button variant="primary" disabled={reason.trim().length < 5 || save.isPending} onClick={() => save.mutate()}><Save size={14} strokeWidth={1.5} />Save new version</Button>
      </div>
      {save.isError && <div className="mt-2"><ErrorNote error={save.error} /></div>}
      <details className="mt-4">
        <summary className="cursor-pointer text-[12px] text-ink-muted">Version history ({q.data.versions.length})</summary>
        <ul className="ledger mt-2 text-[12px]">
          {q.data.versions.map((v) => (
            <li key={v.version} className="grid grid-cols-[48px_1fr_1fr_auto] gap-2 py-1.5">
              <span className="num">v{v.version}</span><span className="num">{formatMoney(v.floor_price, cur)} – {formatMoney(v.ceiling_price, cur)}</span>
              <span className="num text-ink-muted">daily {v.max_daily_move_pct}% · weekly {v.max_weekly_move_pct}%</span><span className="text-ink-muted">{v.reason}</span>
            </li>
          ))}
        </ul>
      </details>
    </Panel>
  );
}

function OverridesPanel() {
  const { room } = useDesk();
  const qc = useQueryClient();
  const clock = useQuery({ queryKey: ["clock"], queryFn: () => api.admin.get<{ business_date: string }>("/v1/clock") });
  const list = useQuery({ queryKey: ["overrides"], queryFn: () => api.admin.get<{ overrides: Override[] }>("/v1/overrides") });
  const [f, setF] = useState({ from: "", to: "", price: "", reason: "", hours: "4" });
  useEffect(() => { if (clock.data && !f.from) { const d = addDays(clock.data.business_date, 14); setF((x) => ({ ...x, from: d, to: d })); } }, [clock.data]); // eslint-disable-line
  const create = useMutation({
    mutationFn: () => api.admin.post("/v1/overrides", { entity_id: room, from_date: f.from, to_date: f.to, price: f.price, reason: f.reason,
      expires_at: new Date(Date.now() + Number(f.hours) * 3600_000).toISOString().replace(/\.\d{3}Z$/, "Z") }),
    onSuccess: () => { setF({ ...f, price: "", reason: "" }); qc.invalidateQueries(); },
  });
  const revoke = useMutation({ mutationFn: (id: string) => api.admin.post(`/v1/overrides/${id}/revoke`, { reason: "Released from the desk" }), onSuccess: () => qc.invalidateQueries() });
  const active = (list.data?.overrides ?? []).filter((o) => o.status === "active");
  return (
    <Panel title="Manual overrides">
      <p className="mb-3 text-[12px] text-ink-muted">Hold a price for chosen dates. An override needs a reason and an expiry, must sit inside the room's floor and ceiling, and is never counted as a clamp.</p>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-[1fr_1fr_1fr_90px]">
        <label className="field"><span>From</span><input type="date" className="input num" value={f.from} onChange={(e) => setF({ ...f, from: e.target.value })} /></label>
        <label className="field"><span>To</span><input type="date" className="input num" value={f.to} onChange={(e) => setF({ ...f, to: e.target.value })} /></label>
        <label className="field"><span>Price</span><input className="input num" placeholder="5555.00" value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} /></label>
        <label className="field"><span>Expires (h)</span><input className="input num" value={f.hours} onChange={(e) => setF({ ...f, hours: e.target.value.replace(/\D/g, "") })} /></label>
      </div>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <label className="field min-w-[260px] flex-1"><span>Reason</span><input className="input" value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} placeholder="e.g. Wedding group block" /></label>
        <Button variant="primary" disabled={!/^\d+\.\d{2}$/.test(f.price) || f.reason.trim().length < 5 || !f.hours || create.isPending} onClick={() => create.mutate()}>Hold price</Button>
      </div>
      {create.isError && <div className="mt-2"><ErrorNote error={create.error} /></div>}
      {active.length > 0 && (
        <ul className="ledger mt-4 text-[13px]">
          {active.map((o) => (
            <li key={o.override_id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span><span className="num">{o.from_date === o.to_date ? o.from_date : `${o.from_date} → ${o.to_date}`}</span> · <span className="num">{formatMoney(o.price, o.currency)}</span> · {o.reason}</span>
              <span className="flex items-center gap-2"><span className="num text-[11px] text-ink-faint">until {o.expires_at.slice(0, 16).replace("T", " ")}</span>
                <Button variant="ghost" onClick={() => revoke.mutate(o.override_id)}>Release</Button></span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function EnginePanel() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["engine"], queryFn: () => api.admin.get<Engine>("/v1/engine-config") });
  const [band, setBand] = useState("");
  const [reason, setReason] = useState("");
  useEffect(() => { if (q.data) setBand(q.data.auto_band_pct); }, [q.data]);
  const save = useMutation({ mutationFn: () => api.admin.put("/v1/engine-config", { auto_band_pct: band, reason }), onSuccess: () => { setReason(""); qc.invalidateQueries(); } });
  if (!q.data) return <Skeleton />;
  const fb = q.data.config.factor_bounds;
  return (
    <Panel title={`Engine settings · v${q.data.version}`}>
      <table className="w-full text-[13px]">
        <thead><tr className="text-left text-[11px] uppercase tracking-wider text-ink-muted"><th className="py-1 font-medium">Factor</th><th className="font-medium">Lower bound</th><th className="font-medium">Upper bound</th><th className="font-medium">State</th></tr></thead>
        <tbody>{Object.entries(fb).map(([k, v]) => (
          <tr key={k} className="border-t border-rule"><td className="py-1.5">{k.replaceAll("_", " ")}</td><td className="num">{v.lo}</td><td className="num">{v.hi}</td>
            <td>{v.enabled ? <Tag tone="teal">on</Tag> : <Tag>off</Tag>}</td></tr>))}</tbody>
      </table>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <label className="field w-[140px]"><span>Auto-apply band %</span><input className="input num" value={band} onChange={(e) => setBand(e.target.value)} /></label>
        <label className="field min-w-[240px] flex-1"><span>Reason</span><input className="input" value={reason} onChange={(e) => setReason(e.target.value)} /></label>
        <Button disabled={reason.trim().length < 5 || save.isPending} onClick={() => save.mutate()}><Save size={14} strokeWidth={1.5} />Save v{q.data.version + 1}</Button>
      </div>
      {save.isError && <div className="mt-2"><ErrorNote error={save.error} /></div>}
      <p className="mt-2 text-[12px] text-ink-muted">Factor bounds are edited through the what-if simulator first (§5), so every change is tested before it ships.</p>
    </Panel>
  );
}

function KillSwitch() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["engine"], queryFn: () => api.admin.get<Engine>("/v1/engine-config") });
  const [reason, setReason] = useState("");
  const flip = useMutation({ mutationFn: (active: boolean) => api.admin.post("/v1/killswitch", { active, reason }), onSuccess: () => { setReason(""); qc.invalidateQueries(); } });
  const on = q.data?.kill_switch_active;
  return (
    <Panel title="Kill switch" tone="danger">
      <p className="text-[13px] text-ink-muted">{on ? "Dynamic pricing is paused: every room is at its base rate." : "Revert every room to its base rate immediately. Live traveller holds are honoured until they expire."}</p>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <label className="field min-w-[260px] flex-1"><span>Reason (required)</span><input className="input" value={reason} onChange={(e) => setReason(e.target.value)} /></label>
        {on ? (
          <Button variant="primary" disabled={reason.trim().length < 5 || flip.isPending} onClick={() => flip.mutate(false)}><Play size={14} strokeWidth={1.5} />Resume dynamic pricing</Button>
        ) : (
          <Button variant="danger" disabled={reason.trim().length < 5 || flip.isPending} onClick={() => flip.mutate(true)}><OctagonX size={14} strokeWidth={1.5} />Revert all to base rates</Button>
        )}
      </div>
      {flip.isError && <div className="mt-2"><ErrorNote error={flip.error} /></div>}
    </Panel>
  );
}

export default function Controls() {
  return (
    <div>
      <SectionTitle n={3} title="Controls"><RoomPicker /></SectionTitle>
      <div className="grid gap-5 xl:grid-cols-2">
        <div className="xl:col-span-2"><BoundsEditor /></div>
        <OverridesPanel />
        <div className="space-y-5"><KillSwitch /><EnginePanel /></div>
      </div>
    </div>
  );
}
