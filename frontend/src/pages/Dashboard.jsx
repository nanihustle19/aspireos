import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, Area, AreaChart } from "recharts";
import { api, fmtDateTime } from "@/lib/api";
import { PageHeader, Panel, Loading } from "@/components/Common";
import { StatusBadge } from "@/components/StatusBadge";
import { useAuth } from "@/context/AuthContext";

const Kpi = ({ label, value, tone = "text-slate-900", testId, hint }) => (
  <div data-testid={testId} className="rounded-md border bg-white px-4 py-3">
    <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</div>
    <div className={`mt-1 font-display text-3xl font-bold ${tone}`}>{value}</div>
    {hint && <div className="text-[11px] text-slate-500">{hint}</div>}
  </div>
);

export default function Dashboard() {
  const { user } = useAuth();
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/dashboard").then((r) => setD(r.data)); }, []);
  if (!d) return <Loading />;
  const s = d.by_status;
  const statusData = Object.entries(s).filter(([k]) => k !== "ARCHIVED").map(([k, v]) => ({ status: k.replace("_", " "), count: v }));
  const aging = Object.entries(d.bench_aging).map(([k, v]) => ({ bucket: `${k} days`, count: v }));
  return (
    <div data-testid="dashboard-page">
      <PageHeader title={`Good day, ${user?.name?.split(" ")[0]}`} subtitle="Pipeline health across the candidates you can access." />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8 fade-up">
        <Kpi testId="kpi-bench" label="On bench" value={(s.BENCH || 0) + (s.ON_HOLD || 0)} tone="text-amber-700" hint={`${d.bench_critical} over ${d.settings.bench_aging_critical_days}d`} />
        <Kpi testId="kpi-marketing" label="Marketing" value={s.MARKETING || 0} tone="text-indigo-700" />
        <Kpi testId="kpi-submitted" label="Submitted" value={s.SUBMITTED || 0} />
        <Kpi testId="kpi-interviewing" label="Interviewing" value={s.INTERVIEWING || 0} tone="text-sky-700" />
        <Kpi testId="kpi-offers" label="Open offers" value={d.offers_open} tone="text-lime-700" />
        <Kpi testId="kpi-placed" label="Active placements" value={d.placements_active} tone="text-emerald-700" />
        <Kpi testId="kpi-subs-7d" label="Subs · 7 days" value={d.submissions_7d} hint={`Target ${d.settings.weekly_submission_target}/wk per recruiter`} />
        <Kpi testId="kpi-my-tasks" label="My open tasks" value={d.my_open_tasks} />
      </div>
      <div className="mt-5 grid gap-4 xl:grid-cols-3">
        <Panel title="Candidates by status" className="xl:col-span-2" testId="chart-status">
          <div className="h-64 p-3"><ResponsiveContainer><BarChart data={statusData}><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" />
            <XAxis dataKey="status" tick={{ fontSize: 11 }} /><YAxis allowDecimals={false} tick={{ fontSize: 11 }} /><Tooltip /><Bar isAnimationActive={false} dataKey="count" fill="#4F46E5" radius={[3, 3, 0, 0]} /></BarChart></ResponsiveContainer></div>
        </Panel>
        <Panel title="Bench aging" testId="chart-bench-aging">
          <div className="h-64 p-3"><ResponsiveContainer><BarChart data={aging} layout="vertical"><CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#E2E8F0" />
            <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} /><YAxis type="category" dataKey="bucket" width={80} tick={{ fontSize: 11 }} /><Tooltip /><Bar isAnimationActive={false} dataKey="count" fill="#D97706" radius={[0, 3, 3, 0]} /></BarChart></ResponsiveContainer></div>
        </Panel>
        <Panel title="Submissions · last 14 days" className="xl:col-span-2" testId="chart-submissions">
          <div className="h-56 p-3"><ResponsiveContainer><AreaChart data={d.submissions_daily}><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} /><YAxis allowDecimals={false} tick={{ fontSize: 11 }} /><Tooltip /><Area isAnimationActive={false} dataKey="submissions" stroke="#059669" fill="#05966922" /></AreaChart></ResponsiveContainer></div>
        </Panel>
        <Panel title="Upcoming interviews" actions={<Link to="/interviews" className="text-xs text-indigo-700 hover:underline">View all</Link>} testId="upcoming-interviews">
          <ul className="divide-y">
            {d.upcoming_interviews.length === 0 && <li className="p-4 text-sm text-slate-500">None scheduled</li>}
            {d.upcoming_interviews.map((i) => (
              <li key={i.id} className="flex items-center justify-between px-4 py-2.5 text-sm">
                <div><Link to={`/candidates/${i.candidate_id}`} className="font-medium hover:underline">{i.candidate_name}</Link><div className="text-xs text-slate-500">{i.round} · {i.mode}</div></div>
                <div className="text-right text-xs"><div className="font-mono">{fmtDateTime(i.scheduled_at, i.timezone)}</div><StatusBadge status={i.status} /></div>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
