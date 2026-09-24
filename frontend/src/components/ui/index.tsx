/** UI primitives, hand-built on the Rate Ledger tokens (no default component-library look). */
import { X } from "lucide-react";
import { useEffect, useId, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import type { Bound } from "../../api/types";
import { sectionByNumber } from "../../pages/admin/sections";
import { formatMoney, type Locale } from "../../lib/money";

type Variant = "primary" | "quiet" | "danger" | "ghost";
const VARIANTS: Record<Variant, string> = {
  primary: "bg-ink text-paper border border-ink hover:bg-ink-soft active:translate-y-px",
  quiet: "bg-surface text-ink border border-rule-strong hover:border-ink active:translate-y-px",
  danger: "bg-vermilion text-white border border-vermilion hover:brightness-95 active:translate-y-px",
  ghost: "bg-transparent text-ink-muted border border-transparent hover:text-ink hover:bg-paper-deep",
};

export function Button({ variant = "quiet", className = "", ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      {...rest}
      className={`inline-flex h-9 items-center justify-center gap-2 rounded-[3px] px-4 text-[13px] font-medium tracking-[0.01em] transition-all duration-150 disabled:opacity-45 ${VARIANTS[variant]} ${className}`}
    />
  );
}

export const BOUND_META: Record<Bound, { label: string; glyph: string; cls: string; color: string }> = {
  ceiling: { label: "Ceiling", glyph: "▲", cls: "stamp-ceiling", color: "var(--saffron)" },
  floor: { label: "Floor", glyph: "▼", cls: "stamp-floor", color: "var(--teal)" },
  max_daily_movement: { label: "Daily move", glyph: "◆", cls: "stamp-daily", color: "var(--plum)" },
  max_weekly_movement: { label: "Weekly move", glyph: "■", cls: "stamp-weekly", color: "var(--slate)" },
};

export function Stamp({ bound, value, currency, locale = "en-IN" }: { bound: Bound; value?: string | null; currency?: string; locale?: Locale }) {
  const m = BOUND_META[bound];
  return (
    <span className={`stamp ${m.cls}`}>
      <span aria-hidden>{m.glyph}</span>
      {m.label}
      {value && currency ? <span className="num">{formatMoney(value, currency, locale, false)}</span> : null}
    </span>
  );
}

export function Tag({ tone = "slate", children }: { tone?: "indigo" | "teal" | "saffron" | "plum" | "slate" | "vermilion"; children: ReactNode }) {
  const tones = {
    indigo: "bg-indigo-wash text-indigo-ink", teal: "bg-teal-wash text-teal", saffron: "bg-saffron-wash text-saffron-text",
    plum: "bg-plum-wash text-plum", slate: "bg-slate-wash text-slate", vermilion: "bg-vermilion-wash text-vermilion",
  };
  return <span className={`inline-flex items-center gap-1 rounded-[2px] px-1.5 py-0.5 font-mono text-[10.5px] font-medium uppercase tracking-[0.06em] ${tones[tone]}`}>{children}</span>;
}

export function Skeleton({ lines = 4 }: { lines?: number }) {
  return (
    <div className="space-y-3 py-2" aria-busy="true" aria-label="Loading">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="skeleton-line" style={{ width: `${88 - ((i * 17) % 40)}%` }} />
      ))}
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  const e = error as { message?: string; error_code?: string; request_id?: string } | null;
  return (
    <div role="alert" className="rounded-[3px] border border-vermilion/30 bg-vermilion-wash px-3 py-2 text-[13px] text-vermilion">
      {e?.message ?? "Something went wrong."}
      {e?.request_id ? <span className="num ml-2 text-[11px] opacity-70">ref {e.request_id}</span> : null}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-[3px] border border-dashed border-rule-strong bg-surface/60 px-6 py-10 text-center">
      <p className="font-display text-[19px] text-ink">{title}</p>
      {children ? <div className="mt-1 text-[13px] text-ink-muted">{children}</div> : null}
    </div>
  );
}

export function SectionTitle({ n, title, kicker, children }: { n: number; title: string; kicker?: ReactNode; children?: ReactNode }) {
  const sec = sectionByNumber(n);
  const Icon = sec.icon;
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4 border-b border-ink pb-4">
      <div className="min-w-0">
        <p className="eyebrow flex items-center gap-2"><Icon size={13} strokeWidth={1.7} className="text-brass" aria-hidden /><span className="text-brass">{sec.group}</span><span className="h-px w-6 bg-rule-strong" />Revenue desk</p>
        <h1 className="mt-1.5 text-[30px] leading-[1.1]">{title}</h1>
        {kicker ? <p className="mt-1.5 max-w-[72ch] text-[13.5px] text-ink-muted">{kicker}</p> : null}
      </div>
      {children ? <div className="flex flex-wrap items-center gap-2">{children}</div> : null}
    </header>
  );
}

export function Drawer({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("keydown", onKey); prev?.focus(); };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="presentation">
      <div className="fade-in absolute inset-0 bg-ink/25 backdrop-blur-[1px]" onClick={onClose} aria-hidden />
      <aside
        ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby={id}
        className="drawer-in relative z-10 flex h-full w-full max-w-[600px] flex-col border-l border-rule bg-surface outline-none"
        style={{ boxShadow: "var(--shadow-drawer)" }}
      >
        <div className="flex items-start justify-between gap-4 border-b border-rule px-6 py-4">
          <div id={id} className="min-w-0">{title}</div>
          <Button variant="ghost" onClick={onClose} aria-label="Close"><X size={16} strokeWidth={1.5} /></Button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>
      </aside>
    </div>
  );
}

/** Every chart has an accessible table alternative. */
export function ChartOrTable({ chart, table, label }: { chart: ReactNode; table: ReactNode; label: string }) {
  const [mode, setMode] = useState<"chart" | "table">("chart");
  return (
    <div>
      <div className="mb-2 flex justify-end" role="group" aria-label={`${label} view`}>
        {(["chart", "table"] as const).map((m) => (
          <button key={m} onClick={() => setMode(m)} aria-pressed={mode === m}
            className={`px-2.5 py-1 font-mono text-[10.5px] uppercase tracking-wider transition-colors ${mode === m ? "border-b-[1.5px] border-ink text-ink" : "text-ink-faint hover:text-ink-muted"}`}>
            {m}
          </button>
        ))}
      </div>
      {mode === "chart" ? chart : <div className="max-h-[420px] overflow-auto">{table}</div>}
    </div>
  );
}

export function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: "alert" | "ok" }) {
  return (
    <div className="border-t border-ink pt-3">
      <p className="eyebrow">{label}</p>
      <p className={`display-price mt-1 text-[30px] leading-none ${tone === "alert" ? "text-vermilion" : tone === "ok" ? "text-teal" : "text-ink"}`}>{value}</p>
      {sub ? <p className="mt-1.5 text-[12px] text-ink-muted">{sub}</p> : null}
    </div>
  );
}
