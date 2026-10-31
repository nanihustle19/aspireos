import { useEffect, useState } from "react";
import { api, daysSince } from "@/lib/api";
import { PageHeader, Panel, Loading, Empty, NativeSelect } from "@/components/Common";
import { CandidateTable } from "@/pages/Candidates";

export default function Bench() {
  const [items, setItems] = useState(null);
  const [settings, setSettings] = useState({ bench_aging_warning_days: 14, bench_aging_critical_days: 30 });
  const [status, setStatus] = useState("BENCH,ON_HOLD");
  const [groups, setGroups] = useState([]);
  const [group, setGroup] = useState("");
  useEffect(() => { api.get("/settings").then((r) => setSettings(r.data)); api.get("/groups").then((r) => setGroups(r.data)); }, []);
  useEffect(() => {
    api.get("/candidates", { params: { status, group_id: group, page_size: 200, sort: "bench_since" } }).then((r) => setItems(r.data.items));
  }, [status, group]);
  const aging = (c) => {
    const d = daysSince(c.bench_since);
    if (d === null) return "—";
    const tone = d > settings.bench_aging_critical_days ? "bg-rose-100 text-rose-800 border-rose-300" : d > settings.bench_aging_warning_days ? "bg-amber-100 text-amber-800 border-amber-300" : "bg-slate-100 text-slate-700 border-slate-300";
    return <span data-testid="bench-aging-badge" className={`rounded border px-1.5 py-0.5 font-mono text-[11px] font-semibold ${tone}`}>{d}d</span>;
  };
  return (
    <div data-testid="bench-page">
      <PageHeader title="Bench workspace" subtitle={`Aging thresholds: warning > ${settings.bench_aging_warning_days}d · critical > ${settings.bench_aging_critical_days}d (Settings)`}>
        <NativeSelect testId="bench-status-filter" value={status} onChange={setStatus} options={[{ value: "BENCH,ON_HOLD", label: "Bench + On hold" }, { value: "BENCH", label: "Bench" }, { value: "ON_HOLD", label: "On hold" }, { value: "NEW", label: "New (unassigned intake)" }]} />
        <NativeSelect testId="bench-group-filter" value={group} onChange={setGroup} placeholder="All groups" options={groups.map((g) => ({ value: g.id, label: g.name }))} />
      </PageHeader>
      <Panel>
        {!items ? <Loading /> : items.length === 0 ? <Empty text="Bench is empty." /> :
          <CandidateTable testId="bench-workspace-table" items={items} extraCols={[{ label: "On bench", render: aging }, { label: "Target", render: (c) => <span className="font-mono text-xs">{c.target_rate != null ? `$${c.target_rate}` : "•••"}</span> }]} />}
      </Panel>
    </div>
  );
}
