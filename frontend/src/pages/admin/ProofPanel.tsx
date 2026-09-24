import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, RefreshCw, XCircle } from "lucide-react";
import { api } from "../../api/client";
import type { Proof } from "../../api/types";
import { Button, ErrorNote, SectionTitle, Skeleton, Tag } from "../../components/ui";

export default function ProofPanel() {
  const q = useQuery({ queryKey: ["proof"], queryFn: () => api.admin.get<Proof>("/v1/proof"), staleTime: 0 });
  return (
    <div>
      <SectionTitle n={8} title="Proof">
        {q.data && <Tag tone={q.data.ok ? "teal" : "vermilion"}>{q.data.ok ? "all checks green" : "a check failed"}</Tag>}
        <Button onClick={() => q.refetch()} disabled={q.isFetching}><RefreshCw size={14} strokeWidth={1.5} className={q.isFetching ? "animate-spin" : ""} />Run again</Button>
      </SectionTitle>
      <p className="mb-4 max-w-[75ch] text-[13px] text-ink-muted">These checks run live against the database the app is serving right now, including the organisers' own conformance validator.</p>
      {q.isLoading && <Skeleton lines={9} />}
      {q.isError && <ErrorNote error={q.error} />}
      <ol className="card ledger">
        {q.data?.checks.map((c) => (
          <li key={c.check} className="grid grid-cols-[24px_1fr_auto] items-start gap-3 px-4 py-3">
            {c.ok ? <CheckCircle2 size={18} className="mt-0.5 text-teal" /> : <XCircle size={18} className="mt-0.5 text-vermilion" />}
            <div><p className="text-[14px] font-medium">{c.check}</p><p className="text-[13px] text-ink-muted">{c.detail}</p></div>
            <span className="num text-[11px] text-ink-faint">{c.ms} ms</span>
          </li>
        ))}
      </ol>
      {q.data && <p className="mt-3 text-[12px] text-ink-muted">{q.data.note}</p>}
    </div>
  );
}
