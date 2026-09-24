import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, X } from "lucide-react";
import { useState } from "react";
import { api } from "../../api/client";
import type { Pending } from "../../api/types";
import { Button, Empty, ErrorNote, SectionTitle, Skeleton, Tag } from "../../components/ui";
import { formatDate } from "../../lib/dates";
import { diff, formatMoney } from "../../lib/money";

export default function Approvals() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["approvals"], queryFn: () => api.admin.get<{ pending: Pending[] }>("/v1/approvals") });
  const [notes, setNotes] = useState<Record<string, string>>({});
  const decide = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "approve" | "reject" }) =>
      api.admin.post(`/v1/approvals/${id}`, { action, note: notes[id]?.trim() || (action === "approve" ? "Reviewed and approved" : "Reviewed and rejected") }),
    onSuccess: () => qc.invalidateQueries(),
  });
  const rows = q.data?.pending ?? [];
  return (
    <div>
      <SectionTitle n={2} title="Approval queue"><Tag tone={rows.length ? "vermilion" : "teal"}>{rows.length} waiting</Tag></SectionTitle>
      <p className="mb-4 max-w-[70ch] text-[13px] text-ink-muted">
        Moves inside the auto-apply band publish themselves. Larger moves, and anything the anomaly guardrail flags, wait here; the
        previous price stays live until a person decides. Every decision is written to the audit log.
      </p>
      {q.isLoading && <Skeleton lines={6} />}
      {q.isError && <ErrorNote error={q.error} />}
      {decide.isError && <ErrorNote error={decide.error} />}
      {q.data && rows.length === 0 && <Empty title="Nothing waiting">All proposed moves this cycle were inside the auto-apply band.</Empty>}
      <ul className="space-y-3">
        {rows.map((r) => (
          <li key={r.decision_id} className="card grid gap-3 p-4 md:grid-cols-[1fr_auto] md:items-center">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="num text-[13px] text-ink-muted">{formatDate(r.for_date, "en-IN", { weekday: "short", day: "numeric", month: "short" })}</span>
                <span className="text-[14px]">{r.hotel_name} · {r.room_name}</span>
                {r.anomaly_flag ? <Tag tone="vermilion">anomaly flagged</Tag> : <Tag tone="saffron">outside auto-band</Tag>}
              </div>
              <p className="num mt-1 text-[15px]">
                {formatMoney(r.live_price_before, r.currency)} → <strong>{formatMoney(r.published_price, r.currency)}</strong>
                <span className="ml-2 text-[12px] text-ink-muted">({diff(r.published_price, r.live_price_before)})</span>
              </p>
              <p className="mt-1 text-[12px] text-ink-muted">{r.summary}</p>
              <input className="input mt-2 w-full max-w-[520px]" placeholder="Note for the audit log (min 5 characters)" value={notes[r.decision_id] ?? ""}
                onChange={(e) => setNotes({ ...notes, [r.decision_id]: e.target.value })} aria-label="Decision note" />
            </div>
            <div className="flex gap-2">
              <Button variant="quiet" onClick={() => decide.mutate({ id: r.decision_id, action: "reject" })} disabled={decide.isPending}><X size={14} strokeWidth={1.5} />Reject</Button>
              <Button variant="primary" onClick={() => decide.mutate({ id: r.decision_id, action: "approve" })} disabled={decide.isPending}><Check size={14} strokeWidth={1.5} />Approve</Button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
