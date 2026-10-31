import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Download, Upload, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, errMsg, fmtDateTime } from "@/lib/api";
import { Empty, PageHeader, Panel } from "@/components/Common";
import { StatusBadge } from "@/components/StatusBadge";
import { useAuth } from "@/context/AuthContext";

export default function DataJobs() {
  const { isOps, isAuditor } = useAuth();
  const [jobs, setJobs] = useState([]);
  const ref = useRef();
  const load = () => api.get("/bg-jobs").then((r) => setJobs(r.data));
  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (!jobs.some((j) => ["PENDING", "RUNNING"].includes(j.status))) return;
    const t = setTimeout(load, 2000); return () => clearTimeout(t);
  }, [jobs]);
  const exportAll = async () => { try { await api.post("/exports/candidates", {}); toast.success("Export queued"); load(); } catch (e) { toast.error(errMsg(e)); } };
  const importCsv = async (file) => {
    if (!file) return;
    const fd = new FormData(); fd.append("file", file);
    try { const { data } = await api.post("/imports/candidates", fd); toast.success(`Import queued (${data.rows} rows)`); load(); } catch (e) { toast.error(errMsg(e)); }
    ref.current.value = "";
  };
  const download = async (j) => {
    const r = await api.get(`/bg-jobs/${j.id}/download`, { responseType: "blob" });
    const url = URL.createObjectURL(r.data); const a = document.createElement("a"); a.href = url; a.download = `candidates-${j.id.slice(0, 8)}.csv`; a.click(); URL.revokeObjectURL(url);
  };
  return (
    <div data-testid="data-jobs-page">
      <PageHeader title="Imports & exports" subtitle="Run as background jobs. Candidate exports are limited to Admin, Operations and Auditors; rates are redacted per your role.">
        <Button size="sm" variant="outline" onClick={load} data-testid="refresh-jobs-button"><RefreshCw className="h-4 w-4" /></Button>
        {(isOps || isAuditor) && <Button size="sm" variant="outline" onClick={exportAll} data-testid="export-all-button"><Download className="mr-1 h-4 w-4" />Export candidates</Button>}
        {isOps && <><input ref={ref} type="file" accept=".csv" className="hidden" data-testid="import-file-input" onChange={(e) => importCsv(e.target.files[0])} />
          <Button size="sm" onClick={() => ref.current.click()} data-testid="import-csv-button"><Upload className="mr-1 h-4 w-4" />Import CSV</Button></>}
      </PageHeader>
      {isOps && <p className="mb-3 text-xs text-slate-500">CSV columns: <code>first_name,last_name,email,phone,primary_skill,skills (semicolon separated),experience_years,location,visa_status</code>. Exact duplicates are skipped.</p>}
      {!isOps && !isAuditor && <div className="mb-3 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900" data-testid="export-restricted-notice">Your role cannot export candidate data.</div>}
      <Panel>{jobs.length === 0 ? <Empty text="No jobs yet" /> : (
        <table className="dense-table w-full" data-testid="bg-jobs-table"><thead><tr><th>Type</th><th>Status</th><th>Requested by</th><th>Created</th><th>Result</th><th></th></tr></thead>
          <tbody>{jobs.map((j) => (
            <tr key={j.id} data-testid="bg-job-row"><td className="font-mono text-xs">{j.type}</td><td><StatusBadge status={j.status} /></td><td className="text-xs">{j.created_by_name}</td><td className="text-xs">{fmtDateTime(j.created_at)}</td>
              <td className="max-w-[360px] text-xs">{j.result ? (j.result.rows != null ? `${j.result.rows} rows` : `${j.result.created} created, ${j.result.skipped} skipped`) : j.error}
                {j.result?.errors?.length > 0 && <details className="text-[11px] text-rose-700"><summary>{j.result.errors.length} issues</summary>{j.result.errors.map((e) => <div key={e}>{e}</div>)}</details>}</td>
              <td>{j.type === "EXPORT_CANDIDATES" && j.status === "COMPLETED" && <Button size="sm" variant="ghost" onClick={() => download(j)} data-testid={`download-export-${j.id}`}><Download className="h-4 w-4" /></Button>}</td></tr>))}</tbody></table>
      )}</Panel>
    </div>
  );
}
