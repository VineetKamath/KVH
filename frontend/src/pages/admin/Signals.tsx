import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Sparkles } from "lucide-react";
import { api } from "../../api/client";
import type { Signal } from "../../api/types";
import { Button, Empty, ErrorNote, SectionTitle, Skeleton, Tag } from "../../components/ui";
import { formatDate } from "../../lib/dates";

const impactTone = { major: "vermilion", moderate: "saffron", minor: "slate" } as const;

export default function Signals() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["signals"], queryFn: () => api.admin.get<{ signals: Signal[] }>("/v1/event-signals") });
  const extract = useMutation({ mutationFn: () => api.admin.post<{ count: number }>("/v1/event-signals/extract"), onSuccess: () => qc.invalidateQueries({ queryKey: ["signals"] }) });
  const approve = useMutation({ mutationFn: (id: string) => api.admin.post(`/v1/event-signals/${id}/approve`, { reason: "Checked against the source" }),
    onSuccess: () => qc.invalidateQueries() });
  const rows = q.data?.signals ?? [];
  const pending = rows.filter((r) => !r.approved_at);
  return (
    <div>
      <SectionTitle n={4} title="Event signals">
        <Button onClick={() => extract.mutate()} disabled={extract.isPending}><Sparkles size={14} strokeWidth={1.5} />{extract.isPending ? "Reading the feed…" : "Extract from feed (AI)"}</Button>
      </SectionTitle>
      <p className="mb-4 max-w-[72ch] text-[13px] text-ink-muted">
        The extractor reads a curated feed where every row carries a source reference, and classifies impact, radius and confidence.
        A new signal is <strong>inert</strong>: only signals a person approves ever reach a price. Approving reprices the city's rooms immediately.
      </p>
      {extract.data && <p className="mb-3 text-[13px] text-teal">{extract.data.count} new signals extracted, all waiting for review.</p>}
      {extract.isError && <ErrorNote error={extract.error} />}
      {q.isLoading && <Skeleton lines={6} />}
      {q.isError && <ErrorNote error={q.error} />}
      {q.data && rows.length === 0 && <Empty title="No signals yet">Run the extractor to read the curated feed.</Empty>}
      {pending.length > 0 && <h2 className="mb-2 text-[18px]">Waiting for review · {pending.length}</h2>}
      <ul className="space-y-2">
        {rows.map((s) => (
          <li key={s.signal_id} className={`card grid gap-2 p-4 md:grid-cols-[1fr_auto] md:items-center ${s.approved_at ? "opacity-80" : ""}`}>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[15px] font-medium">{s.title}</span>
                <span className="text-[13px] text-ink-muted">{s.city_name}</span>
                <Tag tone={impactTone[s.impact_tag as keyof typeof impactTone] ?? "slate"}>{s.impact_tag}</Tag>
                <Tag tone={s.confidence_band === "high" ? "teal" : s.confidence_band === "medium" ? "indigo" : "slate"}>{s.confidence_band} confidence</Tag>
                <span className="num text-[12px] text-ink-muted">{formatDate(s.start_date)} → {formatDate(s.end_date)} · {Number(s.radius_km)} km</span>
              </div>
              <p className="mt-1 text-[13px]">{s.justification}</p>
              <p className="mt-0.5 text-[11px] text-ink-faint">Source: {s.source_ref} · extracted by {s.extracted_by}</p>
            </div>
            <div>{s.approved_at ? <Tag tone="teal"><Check size={12} /> approved</Tag> :
              <Button variant="primary" onClick={() => approve.mutate(s.signal_id)} disabled={approve.isPending}>Approve</Button>}</div>
          </li>
        ))}
      </ul>
      {approve.isError && <ErrorNote error={approve.error} />}
    </div>
  );
}
