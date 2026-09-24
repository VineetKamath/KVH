import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Command, KeyRound, LogOut } from "lucide-react";
import { createContext, lazy, Suspense, useContext, useEffect, useMemo, useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate, useSearchParams } from "react-router-dom";
import { api, isSignedIn, onAuthChange, setAdminToken, signIn } from "../../api/client";
import type { CycleSummary, Entity } from "../../api/types";
import { Button, ErrorNote, Skeleton } from "../../components/ui";
import { formatDate } from "../../lib/dates";
import { Wordmark } from "../traveller/TravellerLayout";

const ClampReport = lazy(() => import("./ClampReport"));
const Approvals = lazy(() => import("./Approvals"));
const Controls = lazy(() => import("./Controls"));
const Signals = lazy(() => import("./Signals"));
const Simulator = lazy(() => import("./Simulator"));
const Metrics = lazy(() => import("./Metrics"));
const Audit = lazy(() => import("./Audit"));
const ProofPanel = lazy(() => import("./ProofPanel"));

export const HERO = "rmt_039a87b5";
export const SECTIONS = [
  { n: 1, path: "curve", label: "Curve & clamps" },
  { n: 2, path: "approvals", label: "Approvals" },
  { n: 3, path: "controls", label: "Controls" },
  { n: 4, path: "signals", label: "Event signals" },
  { n: 5, path: "simulator", label: "What-if" },
  { n: 6, path: "metrics", label: "Metrics" },
  { n: 7, path: "audit", label: "Audit log" },
  { n: 8, path: "proof", label: "Proof" },
] as const;

type DeskCtx = { room: string; setRoom: (r: string) => void; entities: Entity[] };
const Ctx = createContext<DeskCtx>({ room: HERO, setRoom: () => {}, entities: [] });
export const useDesk = () => useContext(Ctx);

function Login() {
  const [token, setToken] = useState("");
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    const ok = await signIn(token.trim());
    setBusy(false);
    setError(!ok);
    setToken("");
  };
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <form onSubmit={submit} className="card w-full max-w-[400px] p-7">
        <Wordmark compact />
        <h1 className="mt-6 text-[26px]">Revenue desk</h1>
        <p className="mt-1 text-[13px] text-ink-muted">Enter the admin token from your <span className="num">.env</span>. It stays in this tab's memory only and is forgotten on reload.</p>
        <label className="field mt-5">
          <span>Admin token</span>
          <input className="input num" type="password" autoComplete="off" spellCheck={false} value={token}
            onChange={(e) => setToken(e.target.value)} required minLength={16} />
        </label>
        {error && <div className="mt-3"><ErrorNote error={{ message: "That token was not accepted." }} /></div>}
        <Button variant="primary" type="submit" className="mt-5 w-full" disabled={busy || token.length < 16}>
          <KeyRound size={15} strokeWidth={1.5} /> Sign in
        </Button>
      </form>
    </div>
  );
}

function LedgerPage() {
  const qc = useQueryClient();
  const clock = useQuery({ queryKey: ["clock"], queryFn: () => api.admin.get<{ business_date: string }>("/v1/clock") });
  const advance = useMutation({
    mutationFn: () => api.admin.post<CycleSummary>("/v1/clock/advance", { reason: "advance business day from the desk" }),
    onSuccess: () => qc.invalidateQueries(),
  });
  const d = clock.data?.business_date;
  return (
    <div className="card mx-3 px-4 py-3">
      <p className="eyebrow">Ledger page</p>
      <p className="font-display mt-0.5 text-[22px] leading-tight">{d ? formatDate(d, "en-IN", { day: "numeric", month: "long" }) : "—"}</p>
      <p className="num text-[11px] text-ink-muted">{d ? formatDate(d, "en-IN", { weekday: "long", year: "numeric" }) : ""} · business date</p>
      <Button className="mt-3 w-full" onClick={() => advance.mutate()} disabled={advance.isPending}>
        {advance.isPending ? "Pricing next day…" : "Advance day"} <ArrowRight size={14} strokeWidth={1.5} />
      </Button>
      {advance.data && <p className="num mt-2 text-[11px] text-ink-muted">{advance.data.decisions} prices · {advance.data.clamped_live} clamped · {advance.data.pending_approval} to approve</p>}
      {advance.isError && <div className="mt-2"><ErrorNote error={advance.error} /></div>}
    </div>
  );
}

function Palette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [q, setQ] = useState("");
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const items = useMemo(() => {
    const base: { key: string; label: string; go: () => void }[] =
      SECTIONS.map((s) => ({ key: s.path as string, label: `§${s.n} ${s.label}`, go: () => navigate(`/desk/${s.path}?${params}`) }));
    if (/^\d{4}-\d{2}-\d{2}$/.test(q.trim())) base.unshift({ key: "date", label: `Open decision for ${q.trim()}`, go: () => navigate(`/desk/curve?${new URLSearchParams({ ...Object.fromEntries(params), date: q.trim() })}`) });
    return base.filter((i) => i.label.toLowerCase().includes(q.toLowerCase()) || i.key === "date");
  }, [q, navigate, params]);
  useEffect(() => { if (open) setQ(""); }, [open]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-ink/10 pt-[12vh]" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label="Command palette" className="card w-full max-w-[520px] overflow-hidden" style={{ boxShadow: "var(--shadow-drawer)" }} onClick={(e) => e.stopPropagation()}>
        <input autoFocus className="w-full border-b border-rule bg-surface px-4 py-3 text-[15px] outline-none" placeholder="Jump to a section, or type a stay date (2026-10-12)…"
          value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Escape") onClose(); if (e.key === "Enter" && items[0]) { items[0].go(); onClose(); } }} />
        <ul className="ledger max-h-[320px] overflow-y-auto">
          {items.map((i) => (
            <li key={i.key}><button className="flex w-full items-center justify-between px-4 py-2.5 text-left text-[14px] hover:bg-paper-deep" onClick={() => { i.go(); onClose(); }}>
              {i.label}<ArrowRight size={14} strokeWidth={1.5} className="text-ink-faint" /></button></li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function DeskShell() {
  const [params, setParams] = useSearchParams();
  const [palette, setPalette] = useState(false);
  const entities = useQuery({ queryKey: ["entities"], queryFn: () => api.admin.get<{ entities: Entity[] }>("/v1/entities") });
  const room = params.get("room") ?? HERO;
  const setRoom = (r: string) => { const p = new URLSearchParams(params); p.set("room", r); p.delete("date"); setParams(p); };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette((p) => !p); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const qs = params.toString() ? `?${params}` : "";
  return (
    <Ctx.Provider value={{ room, setRoom, entities: entities.data?.entities ?? [] }}>
      <div className="flex min-h-screen">
        <nav aria-label="Desk" className="sticky top-0 flex h-screen w-[248px] shrink-0 flex-col gap-4 border-r border-rule bg-paper py-4">
          <div className="px-5"><Wordmark compact /></div>
          <LedgerPage />
          <ol className="flex flex-col gap-0.5 px-3">
            {SECTIONS.map((s) => (
              <li key={s.path}><NavLink to={`/desk/${s.path}${qs}`} className="rail-link">
                <span className="num w-6 text-[11px] text-ink-faint">§{s.n}</span><span className="text-[13px]">{s.label}</span></NavLink></li>
            ))}
          </ol>
          <div className="mt-auto space-y-1 px-3">
            <button onClick={() => setPalette(true)} className="rail-link w-full text-[12px]"><Command size={13} strokeWidth={1.5} /> Command palette <span className="num ml-auto text-ink-faint">Ctrl K</span></button>
            <button onClick={() => setAdminToken(null)} className="rail-link w-full text-[12px]"><LogOut size={13} strokeWidth={1.5} /> Sign out</button>
          </div>
        </nav>
        <main className="min-w-0 flex-1 px-8 py-6">
          <Suspense fallback={<Skeleton lines={8} />}>
            <Routes>
              <Route index element={<Navigate to={`curve${qs}`} replace />} />
              <Route path="curve" element={<ClampReport />} />
              <Route path="approvals" element={<Approvals />} />
              <Route path="controls" element={<Controls />} />
              <Route path="signals" element={<Signals />} />
              <Route path="simulator" element={<Simulator />} />
              <Route path="metrics" element={<Metrics />} />
              <Route path="audit" element={<Audit />} />
              <Route path="proof" element={<ProofPanel />} />
              <Route path="*" element={<Navigate to="curve" replace />} />
            </Routes>
          </Suspense>
        </main>
      </div>
      <Palette open={palette} onClose={() => setPalette(false)} />
    </Ctx.Provider>
  );
}

export default function Desk() {
  const [signedIn, setSignedIn] = useState(isSignedIn());
  useEffect(() => { onAuthChange(setSignedIn); }, []);
  return signedIn ? <DeskShell /> : <Login />;
}

export function RoomPicker() {
  const { room, setRoom, entities } = useDesk();
  return (
    <label className="field min-w-[280px]">
      <span>Room</span>
      <select className="input" value={room} onChange={(e) => setRoom(e.target.value)}>
        {entities.map((e) => <option key={e.entity_id} value={e.entity_id}>{e.city_name} · {e.hotel_name} · {e.room_name}</option>)}
      </select>
    </label>
  );
}
