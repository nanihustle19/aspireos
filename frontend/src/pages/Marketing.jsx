import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { LayoutGrid, Table2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { PageHeader, Loading, Panel, Empty } from "@/components/Common";
import { CandidateTable } from "@/pages/Candidates";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

const COLS = ["BENCH", "MARKETING", "SUBMITTED", "INTERVIEWING", "OFFERED"];
const DRAGGABLE = { BENCH: ["MARKETING"], MARKETING: ["BENCH"], SUBMITTED: ["MARKETING"], INTERVIEWING: ["MARKETING"], OFFERED: ["MARKETING"] };

const Card = ({ c, onDrag }) => (
  <div draggable onDragStart={(e) => { e.dataTransfer.setData("text/plain", c.id); onDrag(c); }} data-testid="marketing-candidate-card"
    className="cursor-grab rounded-md border bg-white p-3 shadow-sm transition-[transform,box-shadow] hover:-translate-y-0.5 hover:shadow active:cursor-grabbing">
    <Link to={`/candidates/${c.id}`} className="text-sm font-semibold hover:text-indigo-700">{c.full_name}</Link>
    <div className="text-xs text-slate-600">{c.primary_skill} · {c.experience_years ?? "?"} yrs · {c.visa_status}</div>
    <div className="mt-2 flex flex-wrap gap-1">{(c.skills || []).slice(0, 3).map((s) => <span key={s} className="rounded bg-slate-100 px-1.5 text-[10px] text-slate-700">{s}</span>)}</div>
    <div className="mt-2 flex items-center justify-between text-[11px] text-slate-500"><span>{c.group_name}</span><span className="font-mono font-semibold text-slate-800">{c.target_rate != null ? `$${c.target_rate}/hr` : "•••"}</span></div>
  </div>
);

export default function Marketing() {
  const [items, setItems] = useState(null);
  const [view, setView] = useState("kanban");
  const [drag, setDrag] = useState(null);
  const load = () => api.get("/candidates", { params: { status: COLS.join(","), page_size: 200 } }).then((r) => setItems(r.data.items));
  useEffect(() => { load(); }, []);
  const drop = async (col) => {
    const c = drag; setDrag(null);
    if (!c || c.status === col) return;
    if (!(DRAGGABLE[c.status] || []).includes(col)) return toast.error(`${c.status} → ${col} must happen through the pipeline workflow (submission/interview/offer)`);
    try { await api.post(`/candidates/${c.id}/transition`, { to_status: col, version: c.version, reason: "Kanban move" }); toast.success(`${c.full_name} → ${col}`); load(); }
    catch (e) { toast.error(errMsg(e)); load(); }
  };
  const pool = (items || []).filter((c) => c.status !== "BENCH");
  return (
    <div data-testid="marketing-page">
      <PageHeader title="Marketing pool" subtitle="Drag Bench ↔ Marketing. Later stages are driven by submissions, interviews and offers.">
        <ToggleGroup type="single" value={view} onValueChange={(v) => v && setView(v)} className="rounded border bg-white">
          <ToggleGroupItem value="kanban" data-testid="marketing-view-kanban" aria-label="Kanban"><LayoutGrid className="h-4 w-4" /></ToggleGroupItem>
          <ToggleGroupItem value="table" data-testid="marketing-view-table" aria-label="Table"><Table2 className="h-4 w-4" /></ToggleGroupItem>
        </ToggleGroup>
      </PageHeader>
      {!items ? <Loading /> : view === "table" ? (
        <Panel>{pool.length ? <CandidateTable items={pool} testId="marketing-pool-table" /> : <Empty />}</Panel>
      ) : (
        <div className="grid gap-3 overflow-x-auto pb-2 lg:grid-cols-5" data-testid="marketing-kanban-board">
          {COLS.map((col) => {
            const list = items.filter((c) => c.status === col);
            return (
              <div key={col} data-testid="marketing-kanban-column" data-column={col} onDragOver={(e) => e.preventDefault()} onDrop={() => drop(col)}
                className={`min-h-[300px] min-w-[220px] rounded-md border bg-slate-100/70 p-2 transition-colors ${drag && (DRAGGABLE[drag.status] || []).includes(col) ? "ring-2 ring-indigo-400" : ""}`}>
                <div className="mb-2 flex items-center justify-between px-1 text-[11px] font-bold uppercase tracking-wide text-slate-600"><span>{col}</span><span className="rounded bg-white px-1.5">{list.length}</span></div>
                <div className="space-y-2">{list.map((c) => <Card key={c.id} c={c} onDrag={setDrag} />)}</div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
