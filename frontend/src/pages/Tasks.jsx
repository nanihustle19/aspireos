import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api, errMsg, fmtDate } from "@/lib/api";
import { Empty, Loading, NativeSelect, PageHeader, Panel } from "@/components/Common";
import { StatusBadge } from "@/components/StatusBadge";

export default function Tasks() {
  const [items, setItems] = useState(null);
  const [status, setStatus] = useState("OPEN");
  const load = () => api.get("/tasks", { params: { mine: true, status } }).then((r) => setItems(r.data));
  useEffect(() => { load(); }, [status]); // eslint-disable-line
  const toggle = async (t) => { try { await api.patch(`/tasks/${t.id}`, { status: t.status === "DONE" ? "OPEN" : "DONE" }); toast.success("Task updated"); load(); } catch (e) { toast.error(errMsg(e)); } };
  const overdue = (t) => t.status === "OPEN" && t.due_date && t.due_date < new Date().toISOString().slice(0, 10);
  return (
    <div data-testid="tasks-page">
      <PageHeader title="My tasks"><NativeSelect testId="tasks-status-filter" value={status} onChange={setStatus} placeholder="All" options={["OPEN", "DONE"]} /></PageHeader>
      <Panel>{!items ? <Loading /> : items.length === 0 ? <Empty text="No tasks" /> : (
        <table className="dense-table w-full" data-testid="my-tasks-table"><thead><tr><th></th><th>Task</th><th>Candidate</th><th>Priority</th><th>Due</th><th>Status</th></tr></thead>
          <tbody>{items.map((t) => (
            <tr key={t.id} data-testid="my-task-row"><td className="w-8"><input type="checkbox" aria-label="Done" checked={t.status === "DONE"} onChange={() => toggle(t)} data-testid={`my-task-toggle-${t.id}`} /></td>
              <td className="font-medium">{t.title}</td><td>{t.candidate_id ? <Link className="text-indigo-700 hover:underline" to={`/candidates/${t.candidate_id}`}>Open</Link> : "—"}</td>
              <td className="text-xs font-semibold">{t.priority}</td><td className={`text-xs ${overdue(t) ? "font-bold text-rose-700" : ""}`}>{fmtDate(t.due_date)}{overdue(t) && " · overdue"}</td><td><StatusBadge status={t.status} /></td></tr>))}</tbody></table>
      )}</Panel>
    </div>
  );
}
