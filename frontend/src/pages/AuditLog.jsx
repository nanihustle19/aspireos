import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, errMsg } from "@/lib/api";
import { InlineError, Loading, NativeSelect, PageHeader, Panel } from "@/components/Common";
import { AuditRows } from "@/components/CandidateTabs";

export default function AuditLog() {
  const [data, setData] = useState(null);
  const [type, setType] = useState("");
  const [action, setAction] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  useEffect(() => {
    api.get("/audit", { params: { entity_type: type, action, page, page_size: 50 } }).then((r) => setData(r.data)).catch((e) => setError(errMsg(e)));
  }, [type, action, page]);
  if (error) return <InlineError error={error} />;
  const pages = data ? Math.max(1, Math.ceil(data.total / 50)) : 1;
  return (
    <div data-testid="audit-page">
      <PageHeader title="Audit log" subtitle="Retained indefinitely. Rate fields are redacted in snapshots for non-Operations viewers.">
        <NativeSelect testId="audit-log-filter-select" value={type} onChange={(v) => { setType(v); setPage(1); }} placeholder="All entities"
          options={["candidate", "user", "group", "submission", "interview", "offer", "placement", "document", "settings", "export", "import", "job", "client", "vendor"]} />
        <Input data-testid="audit-action-filter" placeholder="Action contains…" className="h-9 w-48 bg-white" onKeyDown={(e) => e.key === "Enter" && (setAction(e.target.value), setPage(1))} />
      </PageHeader>
      <Panel>{!data ? <Loading /> : <div className="overflow-x-auto"><AuditRows items={data.items} /></div>}
        {data && <div className="flex items-center justify-between border-t px-4 py-2 text-xs"><span>{data.total} events · page {page}/{pages}</span>
          <div className="flex gap-2"><Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>Prev</Button><Button size="sm" variant="outline" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button></div></div>}
      </Panel>
    </div>
  );
}
