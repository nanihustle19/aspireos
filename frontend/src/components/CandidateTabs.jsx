import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ShieldCheck, ShieldAlert, Loader2, Upload, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api, BACKEND, errMsg, fmtDate, fmtDateTime } from "@/lib/api";
import { Empty, InlineError, NativeSelect, Panel } from "@/components/Common";
import { StatusBadge } from "@/components/StatusBadge";
import { useAuth } from "@/context/AuthContext";

export const NotesTab = ({ cid, canWrite }) => {
  const { isOps } = useAuth();
  const [items, setItems] = useState([]);
  const [body, setBody] = useState("");
  const [vis, setVis] = useState("STANDARD");
  const [error, setError] = useState("");
  const load = () => api.get(`/candidates/${cid}/notes`).then((r) => setItems(r.data));
  useEffect(() => { load(); }, [cid]); // eslint-disable-line
  const add = async () => {
    try { await api.post(`/candidates/${cid}/notes`, { body, visibility: vis }); setBody(""); setError(""); load(); }
    catch (e) { setError(errMsg(e)); }
  };
  return (
    <Panel testId="notes-panel">
      {canWrite && (
        <div className="space-y-2 border-b p-4">
          <Textarea data-testid="note-body-input" placeholder="Add a note…" value={body} onChange={(e) => setBody(e.target.value)} />
          <div className="flex items-center gap-2">
            {isOps && <NativeSelect testId="note-visibility-select" value={vis} onChange={setVis} options={["STANDARD", "OPERATIONS_ONLY"]} />}
            <Button size="sm" disabled={!body.trim()} onClick={add} data-testid="add-note-button">Add note</Button>
          </div>
          <InlineError error={error} />
        </div>
      )}
      {items.length === 0 ? <Empty text="No notes" /> : (
        <ul className="divide-y">{items.map((n) => (
          <li key={n.id} className="px-4 py-3" data-testid="note-item">
            <div className="flex items-center gap-2 text-xs text-slate-500"><b className="text-slate-800">{n.author_name}</b>{fmtDateTime(n.created_at)}
              {n.visibility === "OPERATIONS_ONLY" && <span data-testid="note-ops-only-badge" className="rounded bg-rose-100 px-1.5 text-[10px] font-bold text-rose-800">OPERATIONS ONLY</span>}</div>
            <p className="mt-1 whitespace-pre-wrap text-sm">{n.body}</p>
          </li>))}
        </ul>
      )}
    </Panel>
  );
};

export const TasksTab = ({ cid, canWrite }) => {
  const [items, setItems] = useState([]);
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const load = () => api.get("/tasks", { params: { candidate_id: cid } }).then((r) => setItems(r.data));
  useEffect(() => { load(); }, [cid]); // eslint-disable-line
  const add = async () => { try { await api.post("/tasks", { title, candidate_id: cid, due_date: due || null }); setTitle(""); setDue(""); load(); } catch (e) { toast.error(errMsg(e)); } };
  const toggle = async (t) => { try { await api.patch(`/tasks/${t.id}`, { status: t.status === "DONE" ? "OPEN" : "DONE" }); load(); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <Panel testId="tasks-panel">
      {canWrite && <form className="flex gap-2 border-b p-4" onSubmit={(e) => { e.preventDefault(); add(); }}>
        <Input data-testid="task-title-input" placeholder="New task…" value={title} onChange={(e) => setTitle(e.target.value)} />
        <Input data-testid="task-due-input" type="date" value={due} onChange={(e) => setDue(e.target.value)} className="w-44" />
        <Button size="sm" type="submit" disabled={!title.trim()} data-testid="add-task-button">Add</Button></form>}
      {items.length === 0 ? <Empty text="No tasks" /> : (
        <table className="dense-table w-full"><thead><tr><th></th><th>Task</th><th>Assignee</th><th>Due</th><th>Status</th></tr></thead>
          <tbody>{items.map((t) => (
            <tr key={t.id} data-testid="task-row"><td className="w-8"><input type="checkbox" aria-label="Toggle done" data-testid={`task-toggle-${t.id}`} checked={t.status === "DONE"} onChange={() => toggle(t)} /></td>
              <td className={t.status === "DONE" ? "line-through text-slate-400" : ""}>{t.title}</td><td>{t.assignee_name}</td><td className="text-xs">{fmtDate(t.due_date)}</td><td><StatusBadge status={t.status} /></td></tr>))}</tbody></table>
      )}
    </Panel>
  );
};

const ScanBadge = ({ d }) => {
  const m = { PASSED: [ShieldCheck, "Clean"], FAILED: [ShieldAlert, "Quarantined"], PENDING: [Loader2, "Scanning"] }[d.scan_status] || [Loader2, d.scan_status];
  const Icon = m[0];
  const tone = { PASSED: "bg-emerald-100 text-emerald-900 border-emerald-300", FAILED: "bg-rose-100 text-rose-900 border-rose-300", PENDING: "bg-amber-100 text-amber-900 border-amber-300" }[d.scan_status];
  return <span data-testid="document-quarantine-status-badge" title={d.scan_reason || ""} className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] font-semibold ${tone}`}>
    <Icon className={`h-3 w-3 ${d.scan_status === "PENDING" ? "animate-spin" : ""}`} />{m[1]}</span>;
};

export const DocumentsTab = ({ cid, canUpload }) => {
  const [items, setItems] = useState([]);
  const [type, setType] = useState("RESUME");
  const [busy, setBusy] = useState(false);
  const ref = useRef();
  const load = () => api.get(`/candidates/${cid}/documents`).then((r) => setItems(r.data));
  useEffect(() => { load(); }, [cid]); // eslint-disable-line
  useEffect(() => {
    if (!items.some((d) => d.scan_status === "PENDING")) return;
    const t = setTimeout(load, 2500); return () => clearTimeout(t);
  }, [items]); // eslint-disable-line
  const upload = async (file) => {
    if (!file) return;
    const fd = new FormData(); fd.append("file", file); fd.append("doc_type", type);
    setBusy(true);
    try { await api.post(`/candidates/${cid}/documents`, fd); toast.success("Uploaded to quarantine — scanning"); load(); }
    catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); ref.current.value = ""; }
  };
  const download = async (d) => {
    try { const { data } = await api.get(`/documents/${d.id}/signed-url`); window.open(`${BACKEND}${data.url}`, "_blank"); }
    catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Panel testId="documents-panel" title="Versioned documents" actions={<span className="text-[11px] text-slate-500">Malware scanner: SIMULATED (signature + type checks)</span>}>
      {canUpload && <div className="flex items-center gap-2 border-b p-4">
        <NativeSelect testId="document-type-select" value={type} onChange={setType} options={["RESUME", "ID_PROOF", "WORK_AUTH", "CERTIFICATION", "OTHER"]} />
        <input ref={ref} type="file" className="hidden" data-testid="document-file-input" onChange={(e) => upload(e.target.files[0])} />
        <Button size="sm" disabled={busy} onClick={() => ref.current.click()} data-testid="document-upload-button"><Upload className="mr-1 h-4 w-4" />{busy ? "Uploading…" : "Upload"}</Button>
        <span className="text-xs text-slate-500">Files are quarantined until scan passes. Downloads use short-lived signed URLs.</span>
      </div>}
      {items.length === 0 ? <Empty text="No documents" /> : (
        <table className="dense-table w-full"><thead><tr><th>Type</th><th>Version</th><th>File</th><th>Scan</th><th>Uploaded</th><th></th></tr></thead>
          <tbody>{items.map((d) => (
            <tr key={d.id} data-testid="document-row"><td className="text-xs font-semibold">{d.doc_type}</td><td className="font-mono text-xs">v{d.version}</td><td className="max-w-[240px] truncate">{d.original_filename}</td>
              <td><ScanBadge d={d} />{d.scan_reason && <div className="text-[10px] text-rose-700">{d.scan_reason}</div>}</td><td className="text-xs">{d.uploaded_by_name} · {fmtDate(d.created_at)}</td>
              <td><Button size="sm" variant="ghost" disabled={d.scan_status !== "PASSED"} onClick={() => download(d)} data-testid={`document-download-${d.id}`}><Download className="h-4 w-4" /></Button></td></tr>))}</tbody></table>
      )}
    </Panel>
  );
};

export const AuditTab = ({ cid }) => {
  const [items, setItems] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => { api.get(`/candidates/${cid}/audit`).then((r) => setItems(r.data)).catch((e) => setError(errMsg(e))); }, [cid]);
  if (error) return <InlineError error={error} />;
  return <Panel testId="candidate-audit-panel"><AuditRows items={items || []} /></Panel>;
};

export const AuditRows = ({ items }) => (
  <table className="dense-table w-full" data-testid="audit-table"><thead><tr><th>When</th><th>Actor</th><th>Action</th><th>Entity</th><th>Change</th><th>Reason</th></tr></thead>
    <tbody>{items.map((a) => (
      <tr key={a.id} data-testid="audit-row"><td className="whitespace-nowrap text-xs">{fmtDateTime(a.created_at)}</td><td className="text-xs">{a.actor_name}</td>
        <td><span className="font-mono text-[11px] font-semibold">{a.action}</span></td><td className="text-xs">{a.entity_type}</td>
        <td className="max-w-[360px]"><code className="block truncate text-[11px] text-slate-600" title={JSON.stringify({ before: a.before, after: a.after })}>
          {a.before ? JSON.stringify(a.before) : "∅"} → {a.after ? JSON.stringify(a.after) : "∅"}</code></td><td className="text-xs">{a.reason}</td></tr>))}</tbody></table>
);
