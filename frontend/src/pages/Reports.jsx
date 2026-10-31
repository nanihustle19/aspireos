import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "@/lib/api";
import { Loading, PageHeader, Panel } from "@/components/Common";
import { StatusBadge } from "@/components/StatusBadge";

export default function Reports() {
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/reports/summary").then((r) => setD(r.data)); }, []);
  if (!d) return <Loading />;
  return (
    <div data-testid="reports-page">
      <PageHeader title="Reports" subtitle="Scoped to the groups you can access." />
      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="By group" testId="report-by-group">
          <div className="h-72 p-3"><ResponsiveContainer><BarChart data={d.by_group}><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" /><XAxis dataKey="group" tick={{ fontSize: 11 }} /><YAxis allowDecimals={false} tick={{ fontSize: 11 }} /><Tooltip /><Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar isAnimationActive={false} dataKey="bench" fill="#D97706" /><Bar isAnimationActive={false} dataKey="marketing" fill="#4F46E5" /><Bar isAnimationActive={false} dataKey="submissions" fill="#0EA5E9" /><Bar isAnimationActive={false} dataKey="placements" fill="#059669" /></BarChart></ResponsiveContainer></div>
        </Panel>
        <Panel title="Pipeline funnel" testId="report-funnel">
          <div className="space-y-3 p-5">{d.funnel.map((f, i) => {
            const max = Math.max(...d.funnel.map((x) => x.count), 1);
            return <div key={f.stage}><div className="mb-1 flex justify-between text-xs"><span className="font-semibold">{f.stage}</span><span className="font-mono">{f.count}</span></div>
              <div className="h-6 rounded bg-slate-100"><div className="h-6 rounded bg-indigo-600 transition-[width] duration-700" style={{ width: `${(f.count / max) * 100}%`, opacity: 1 - i * 0.18 }} /></div></div>;
          })}</div>
        </Panel>
        <Panel title="Bench aging (longest first)" testId="report-bench-aging">
          <table className="dense-table w-full"><thead><tr><th>Candidate</th><th>Skill</th><th>Group</th><th>Status</th><th>Days</th></tr></thead>
            <tbody>{d.bench_aging.map((b) => <tr key={b.id}><td><Link to={`/candidates/${b.id}`} className="font-medium hover:underline">{b.first_name} {b.last_name}</Link></td><td>{b.primary_skill}</td><td className="text-xs">{b.group_name || "—"}</td><td><StatusBadge status={b.status} /></td><td className="font-mono">{b.days_on_bench ?? "—"}</td></tr>)}</tbody></table>
        </Panel>
        <Panel title="Recruiter activity (submissions)" testId="report-recruiters">
          <table className="dense-table w-full"><thead><tr><th>Recruiter</th><th>Submissions</th></tr></thead>
            <tbody>{d.recruiter_activity.map((r) => <tr key={r.name}><td>{r.name}</td><td className="font-mono">{r.submissions}</td></tr>)}</tbody></table>
          <table className="dense-table mt-2 w-full"><thead><tr><th>Group</th><th>Candidates</th><th>Interviews</th><th>Placements</th></tr></thead>
            <tbody>{d.by_group.map((g) => <tr key={g.group}><td>{g.group}</td><td className="font-mono">{g.candidates}</td><td className="font-mono">{g.interviews}</td><td className="font-mono">{g.placements}</td></tr>)}</tbody></table>
        </Panel>
      </div>
    </div>
  );
}
