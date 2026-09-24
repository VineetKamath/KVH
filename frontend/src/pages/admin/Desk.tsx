import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, ArrowUpRight, Command, KeyRound, LogOut } from "lucide-react";
import { createContext, lazy, Suspense, useContext, useEffect, useMemo, useState } from "react";
import { Link, NavLink, Navigate, Route, Routes, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { api, isSignedIn, onAuthChange, setAdminToken, signIn } from "../../api/client";
import type { CycleSummary, Entity, Pending } from "../../api/types";
import { Button, ErrorNote, Skeleton } from "../../components/ui";
import { formatDate } from "../../lib/dates";
import { Mark, Wordmark } from "../traveller/TravellerLayout";
import { SECTIONS } from "./sections";

const ClampReport = lazy(() => import("./ClampReport"));
const Approvals = lazy(() => import("./Approvals"));
const Controls = lazy(() => import("./Controls"));
const Signals = lazy(() => import("./Signals"));
const Simulator = lazy(() => import("./Simulator"));
const Metrics = lazy(() => import("./Metrics"));
const Audit = lazy(() => import("./Audit"));
const ProofPanel = lazy(() => import("./ProofPanel"));

export const HERO = "rmt_039a87b5";
export { SECTIONS } from "./sections";

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
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <section className="relative hidden flex-col justify-between overflow-hidden bg-night p-12 text-night-text lg:flex">
        <Wordmark tone="light" />
        <div className="max-w-[46ch]">
          <p className="eyebrow !text-brass">Revenue desk</p>
          <h1 className="display mt-4 text-[52px] leading-[1.03] text-white">The control room for <span className="italic-serif">every published rate.</span></h1>
          <ul className="mt-8 space-y-3 text-[14px]">
            {["See why each price exists — factor by factor, to the paisa.", "Set floors, ceilings and daily-move limits; the engine never crosses them.",
              "Approve large moves, override, or stop the engine — every action is on the audit chain."].map((l) => (
              <li key={l} className="flex gap-3"><span className="mt-2 h-px w-4 shrink-0 bg-brass" />{l}</li>))}
          </ul>
        </div>
        <p className="num text-[11px] text-night-faint">APS-02 · PixelMinds</p>
        <svg className="pointer-events-none absolute -right-10 bottom-24 opacity-[0.08]" width="420" height="220" viewBox="0 0 420 220" aria-hidden>
          <line x1="0" y1="30" x2="420" y2="30" stroke="#fff" /><line x1="0" y1="190" x2="420" y2="190" stroke="#fff" />
          <path d="M0 150 L60 120 L110 135 L170 90 L230 105 L290 60 L350 75 L420 40" fill="none" stroke="#fff" strokeWidth="3" />
        </svg>
      </section>
      <div className="flex items-center justify-center px-5 py-12">
        <form onSubmit={submit} className="w-full max-w-[400px]">
          <div className="lg:hidden"><Wordmark compact /></div>
          <p className="eyebrow mt-8 lg:mt-0">Sign in</p>
          <h2 className="mt-1 text-[32px] leading-tight">Revenue desk</h2>
          <p className="mt-2 text-[13.5px] text-ink-muted">Enter the admin token from your <span className="num">.env</span>. It is kept in this tab's memory only and forgotten on reload.</p>
          <label className="field mt-7">
            <span>Admin token</span>
            <input className="input num" type="password" autoComplete="off" spellCheck={false} value={token}
              onChange={(e) => setToken(e.target.value)} required minLength={16} />
          </label>
          {error && <div className="mt-3"><ErrorNote error={{ message: "That token was not accepted." }} /></div>}
          <Button variant="primary" type="submit" className="mt-5 h-11 w-full" disabled={busy || token.length < 16}>
            <KeyRound size={15} strokeWidth={1.5} /> {busy ? "Checking…" : "Open the desk"}
          </Button>
          <Link to="/" className="mt-6 inline-flex items-center gap-1 text-[12.5px] text-ink-muted hover:text-ink">← Back to the traveller site</Link>
        </form>
      </div>
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
    <div className="mx-3 rounded-[3px] border border-night-rule bg-night-2 px-4 py-3.5">
      <p className="eyebrow !text-night-faint">Business date</p>
      <p className="display mt-1 text-[26px] leading-none text-white">{d ? formatDate(d, "en-IN", { day: "numeric", month: "short" }) : "—"}</p>
      <p className="num mt-1 text-[11px] text-night-faint">{d ? formatDate(d, "en-IN", { weekday: "long", year: "numeric" }) : ""}</p>
      <button onClick={() => advance.mutate()} disabled={advance.isPending}
        className="mt-3 inline-flex h-8 w-full items-center justify-center gap-2 rounded-[3px] border border-night-rule text-[12.5px] text-white transition-colors hover:border-brass hover:text-brass disabled:opacity-50">
        {advance.isPending ? "Pricing next day…" : "Advance day"} <ArrowRight size={13} strokeWidth={1.5} />
      </button>
      {advance.data && <p className="num mt-2 text-[10.5px] leading-snug text-night-text">{advance.data.decisions} prices · {advance.data.clamped_live} clamped · {advance.data.pending_approval} to approve</p>}
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
      SECTIONS.map((s) => ({ key: s.path as string, label: `${s.group} · ${s.label}`, go: () => navigate(`/desk/${s.path}?${params}`) }));
    if (/^\d{4}-\d{2}-\d{2}$/.test(q.trim())) base.unshift({ key: "date", label: `Open decision for ${q.trim()}`, go: () => navigate(`/desk/curve?${new URLSearchParams({ ...Object.fromEntries(params), date: q.trim() })}`) });
    return base.filter((i) => i.label.toLowerCase().includes(q.toLowerCase()) || i.key === "date");
  }, [q, navigate, params]);
  useEffect(() => { if (open) setQ(""); }, [open]);
  if (!open) return null;
  return (
    <div className="fade-in fixed inset-0 z-50 flex items-start justify-center bg-ink/30 px-4 pt-[12vh] backdrop-blur-[1px]" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label="Command palette" className="rise w-full max-w-[560px] overflow-hidden rounded-[4px] border border-rule bg-surface" style={{ boxShadow: "var(--shadow-drawer)" }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 border-b border-rule px-4">
          <Command size={15} strokeWidth={1.5} className="text-ink-faint" />
          <input autoFocus className="h-12 w-full bg-transparent text-[15px] outline-none" placeholder="Jump to a section, or type a stay date (2026-10-12)…"
            value={q} onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Escape") onClose(); if (e.key === "Enter" && items[0]) { items[0].go(); onClose(); } }} />
        </div>
        <ul className="ledger max-h-[340px] overflow-y-auto">
          {items.map((i) => (
            <li key={i.key}><button className="flex w-full items-center justify-between px-4 py-2.5 text-left text-[14px] hover:bg-paper-deep" onClick={() => { i.go(); onClose(); }}>
              {i.label}<ArrowRight size={14} strokeWidth={1.5} className="text-ink-faint" /></button></li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function ContextBar() {
  const { room, entities } = useDesk();
  const loc = useLocation();
  const sec = SECTIONS.find((s) => loc.pathname.includes(`/desk/${s.path}`)) ?? SECTIONS[0];
  const e = entities.find((x) => x.entity_id === room);
  return (
    <div className="sticky top-0 z-20 border-b border-rule bg-paper/90 backdrop-blur-sm">
      <div className="flex h-12 items-center justify-between gap-4 px-8">
        <p className="num flex min-w-0 items-center gap-2 truncate text-[12px] text-ink-muted">
          <span>Revenue desk</span><span className="text-ink-faint">/</span>
          <span className="text-ink">{sec.label}</span>
          {e && <><span className="text-ink-faint">/</span><span className="truncate">{e.city_name} · {e.hotel_name} · {e.room_name}</span></>}
        </p>
        <Link to="/" className="inline-flex shrink-0 items-center gap-1 text-[12px] text-ink-muted hover:text-ink">Traveller view <ArrowUpRight size={12} /></Link>
      </div>
    </div>
  );
}

function DeskShell() {
  const [params, setParams] = useSearchParams();
  const [palette, setPalette] = useState(false);
  const entities = useQuery({ queryKey: ["entities"], queryFn: () => api.admin.get<{ entities: Entity[] }>("/v1/entities") });
  const approvals = useQuery({ queryKey: ["approvals"], queryFn: () => api.admin.get<{ pending: Pending[] }>("/v1/approvals") });
  const waiting = approvals.data?.pending.length ?? 0;
  const room = params.get("room") ?? HERO;
  const setRoom = (r: string) => { const p = new URLSearchParams(params); p.set("room", r); p.delete("date"); setParams(p); };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette((p) => !p); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const qs = params.toString() ? `?${params}` : "";
  const groups = ["Pricing", "Analysis", "Record"] as const;
  return (
    <Ctx.Provider value={{ room, setRoom, entities: entities.data?.entities ?? [] }}>
      <div className="flex min-h-screen">
        <div className="w-[252px] shrink-0 bg-night">
        <nav aria-label="Desk" className="sticky top-0 flex h-screen flex-col gap-5 overflow-y-auto py-5">
          <Link to="/desk/curve" className="flex items-center gap-2.5 px-5">
            <Mark tone="light" />
            <span className="font-display text-[19px] text-white">Rate <span className="italic-serif">Ledger</span></span>
          </Link>
          <LedgerPage />
          <div className="flex flex-col gap-4 px-3">
            {groups.map((g) => (
              <div key={g}>
                <p className="eyebrow mb-1 px-3 !text-night-faint">{g}</p>
                <ol className="flex flex-col gap-0.5">
                  {SECTIONS.filter((s) => s.group === g).map((s) => (
                    <li key={s.path}><NavLink to={`/desk/${s.path}${qs}`} className="rail-link">
                      <s.icon size={15} strokeWidth={1.6} className="shrink-0 text-night-faint" aria-hidden /><span className="text-[13px]">{s.label}</span>
                      {s.path === "approvals" && waiting > 0 && <span className="num ml-auto rounded-[2px] bg-vermilion px-1.5 text-[10.5px] text-white">{waiting}</span>}
                    </NavLink></li>
                  ))}
                </ol>
              </div>
            ))}
          </div>
          <div className="mt-auto space-y-0.5 border-t border-night-rule px-3 pt-3">
            <button onClick={() => setPalette(true)} className="rail-link w-full text-[12px]"><Command size={13} strokeWidth={1.5} /> Command palette <span className="num ml-auto text-night-faint">Ctrl K</span></button>
            <button onClick={() => setAdminToken(null)} className="rail-link w-full text-[12px]"><LogOut size={13} strokeWidth={1.5} /> Sign out</button>
          </div>
        </nav>
        </div>
        <div className="min-w-0 flex-1">
          <ContextBar />
          <main className="mx-auto max-w-[1280px] px-8 py-7">
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
    <label className="field w-[320px] max-w-full">
      <span>Room</span>
      <select className="input w-full" value={room} onChange={(e) => setRoom(e.target.value)}>
        {entities.map((e) => <option key={e.entity_id} value={e.entity_id}>{e.city_name} · {e.hotel_name} · {e.room_name}</option>)}
      </select>
    </label>
  );
}
