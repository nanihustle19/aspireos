import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Plus, Zap, Download, Bookmark, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, errMsg, fmtDate } from "@/lib/api";
import { PageHeader, Panel, Loading, Empty, NativeSelect } from "@/components/Common";
import { StatusBadge } from "@/components/StatusBadge";
import { QuickCreateDialog } from "@/components/QuickCreateDialog";
import { useAuth } from "@/context/AuthContext";

const STATUSES = ["NEW", "BENCH", "MARKETING", "SUBMITTED", "INTERVIEWING", "OFFERED", "PLACED", "ON_HOLD", "ARCHIVED"];

export const CandidateTable = ({ items, extraCols = [], testId = "candidate-table" }) => (
  <div className="overflow-x-auto">
    <table className="dense-table w-full" data-testid={testId}>
      <thead><tr><th>Name</th><th>Status</th><th>Skill</th><th>Group</th><th>Owner</th><th>Exp</th><th>Visa</th>{extraCols.map((c) => <th key={c.label}>{c.label}</th>)}<th>Updated</th></tr></thead>
      <tbody>
        {items.map((c) => (
          <tr key={c.id} data-testid="candidate-row-item">
            <td><Link to={`/candidates/${c.id}`} data-testid={`candidate-link-${c.id}`} className="font-medium text-slate-900 hover:text-indigo-700 hover:underline">{c.full_name}</Link>
              <div className="text-[11px] text-slate-500">{c.email}</div></td>
            <td><StatusBadge status={c.status} /></td>
            <td className="max-w-[180px] truncate">{c.primary_skill}</td>
            <td>{c.group_name || <span className="text-slate-400">Unassigned</span>}</td>
            <td>{c.owner_name || <span className="text-slate-400">—</span>}</td>
            <td className="font-mono text-xs">{c.experience_years ?? "—"}</td>
            <td className="text-xs">{c.visa_status}</td>
            {extraCols.map((col) => <td key={col.label}>{col.render(c)}</td>)}
            <td className="text-xs text-slate-500">{fmtDate(c.updated_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

export default function Candidates() {
  const { isOps, isAuditor } = useAuth();
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState(null);
  const [groups, setGroups] = useState([]);
  const [views, setViews] = useState([]);
  const [quick, setQuick] = useState(false);
  const nav = useNavigate();
  const f = { q: params.get("q") || "", status: params.get("status") || "", group_id: params.get("group_id") || "", page: Number(params.get("page") || 1) };
  const setF = (patch) => { const n = { ...f, page: 1, ...patch }; setParams(Object.fromEntries(Object.entries(n).filter(([, v]) => v))); };

  const load = useCallback(() => {
    api.get("/candidates", { params: { ...f, page_size: 25, include_archived: f.status === "ARCHIVED" } }).then((r) => setData(r.data));
  }, [params]); // eslint-disable-line
  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.get("/groups").then((r) => setGroups(r.data)); api.get("/saved-views").then((r) => setViews(r.data)); }, []);

  const saveView = async () => {
    const name = window.prompt("Name this view");
    if (!name) return;
    const { data: v } = await api.post("/saved-views", { name, page: "candidates", filters: { q: f.q, status: f.status, group_id: f.group_id } });
    setViews([...views, v]); toast.success("View saved");
  };
  const exportCsv = async () => {
    try { await api.post("/exports/candidates", { filters: { status: f.status } }); toast.success("Export queued — download from Imports & Exports"); nav("/data"); }
    catch (e) { toast.error(errMsg(e)); }
  };
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div data-testid="candidates-page">
      <PageHeader title="Candidates" subtitle={data ? `${data.total} candidates in your scope` : ""}>
        {(isOps || isAuditor) && <Button variant="outline" size="sm" onClick={exportCsv} data-testid="export-candidates-button"><Download className="mr-1 h-4 w-4" />Export CSV</Button>}
        {isOps && <Button variant="outline" size="sm" onClick={() => setQuick(true)} data-testid="quick-create-button"><Zap className="mr-1 h-4 w-4" />Quick create</Button>}
        {isOps && <Button size="sm" onClick={() => nav("/candidates/new")} data-testid="add-candidate-button"><Plus className="mr-1 h-4 w-4" />Add candidate</Button>}
      </PageHeader>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Input data-testid="candidate-search-input" placeholder="Search name, email, skill…" defaultValue={f.q} key={f.q} onKeyDown={(e) => e.key === "Enter" && setF({ q: e.target.value })} className="h-9 w-64 bg-white" />
        <NativeSelect testId="candidate-status-filter" value={f.status} onChange={(v) => setF({ status: v })} placeholder="All statuses (excl. archived)" options={STATUSES} />
        <NativeSelect testId="candidate-group-filter" value={f.group_id} onChange={(v) => setF({ group_id: v })} placeholder="All groups" options={groups.map((g) => ({ value: g.id, label: g.name }))} />
        <Button variant="ghost" size="sm" onClick={saveView} data-testid="save-view-button"><Bookmark className="mr-1 h-4 w-4" />Save view</Button>
        {views.map((v) => (
          <span key={v.id} className="inline-flex items-center rounded border bg-white text-xs">
            <button data-testid={`saved-view-${v.id}`} className="px-2 py-1 hover:text-indigo-700" onClick={() => setF(v.filters)}>{v.name}</button>
            <button onClick={async () => { await api.delete(`/saved-views/${v.id}`); setViews(views.filter((x) => x.id !== v.id)); }} className="border-l px-1 text-slate-400 hover:text-rose-600"><X className="h-3 w-3" /></button>
          </span>
        ))}
      </div>
      <Panel>
        {!data ? <Loading /> : data.items.length === 0 ? <Empty text="No candidates match your filters." /> : <CandidateTable items={data.items} />}
        {data && data.total > 0 && (
          <div className="flex items-center justify-between border-t px-4 py-2 text-xs text-slate-600" data-testid="candidate-pagination">
            <span>Page {f.page} of {pages}</span>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" disabled={f.page <= 1} onClick={() => setF({ page: f.page - 1 })} data-testid="pagination-prev">Prev</Button>
              <Button size="sm" variant="outline" disabled={f.page >= pages} onClick={() => setF({ page: f.page + 1 })} data-testid="pagination-next">Next</Button>
            </div>
          </div>
        )}
      </Panel>
      <QuickCreateDialog open={quick} onOpenChange={setQuick} />
    </div>
  );
}
