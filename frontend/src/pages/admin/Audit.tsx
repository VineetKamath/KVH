import { useQuery } from "@tanstack/react-query";
import { ShieldCheck, ShieldX } from "lucide-react";
import { api } from "../../api/client";
import type { AuditEntry } from "../../api/types";
import { ErrorNote, SectionTitle, Skeleton, Tag } from "../../components/ui";

export default function Audit() {
  const log = useQuery({ queryKey: ["audit"], queryFn: () => api.admin.get<{ entries: AuditEntry[] }>("/v1/audit?limit=200") });
  const verify = useQuery({ queryKey: ["audit-verify"], queryFn: () => api.admin.get<{ ok: boolean; rows_checked: number; head?: string }>("/v1/audit/verify") });
  return (
    <div>
      <SectionTitle n={7} title="Audit log">
        {verify.data && (verify.data.ok
          ? <Tag tone="teal"><ShieldCheck size={12} /> hash chain verified · {verify.data.rows_checked} rows</Tag>
          : <Tag tone="vermilion"><ShieldX size={12} /> chain broken</Tag>)}
      </SectionTitle>
      <p className="mb-4 text-[13px] text-ink-muted">Append-only: the database rejects any edit or delete, and each row carries the hash of the one before it.</p>
      {log.isLoading && <Skeleton lines={10} />}
      {log.isError && <ErrorNote error={log.error} />}
      <ol className="card ledger text-[13px]">
        {log.data?.entries.map((e) => (
          <li key={e.audit_id} className="grid grid-cols-[56px_150px_1fr_auto] items-baseline gap-3 px-4 py-2">
            <span className="num text-ink-faint">#{e.seq}</span>
            <span className="num text-[12px] text-ink-muted">{e.created_at.replace("T", " ").slice(0, 19)}</span>
            <span className="min-w-0"><strong className="font-medium">{e.action.replaceAll("_", " ")}</strong> <span className="text-ink-muted">· {e.actor} · {e.target}</span>
              {e.reason ? <span className="block truncate text-[12px] text-ink-muted">“{e.reason}”</span> : null}</span>
            <span className="num text-[10px] text-ink-faint" title={e.row_hash}>{e.row_hash.slice(0, 10)}…</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
