import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Plus, History } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { api, errMsg, fmtDate, fmtDateTime, rate } from "@/lib/api";
import { Empty, Field, InlineError, Loading, NativeSelect, PageHeader, Panel } from "@/components/Common";
import { StatusBadge } from "@/components/StatusBadge";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { useAuth } from "@/context/AuthContext";

const TZS = ["America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "Europe/London", "Asia/Kolkata", "UTC"];

export const FormDialog = ({ open, onOpenChange, title, fields, onSubmit, testId, confirmWord }) => {
  const [form, setForm] = useState({});
  const [error, setError] = useState("");
  useEffect(() => { if (open) { setForm(Object.fromEntries(fields.map((f) => [f.key, f.default ?? ""]))); setError(""); } }, [open]); // eslint-disable-line
  const submit = async () => {
    const missing = fields.filter((f) => f.required && !form[f.key]);
    if (missing.length) return setError(`Required: ${missing.map((m) => m.label).join(", ")}`);
    try { await onSubmit(form); onOpenChange(false); } catch (e) { setError(errMsg(e)); }
  };
  if (confirmWord) {
    return <ConfirmDialog open={open} onOpenChange={onOpenChange} title={title} testId={testId} confirmWord={confirmWord} error={error} onConfirm={submit}>
      <Fields fields={fields} form={form} setForm={setForm} testId={testId} /></ConfirmDialog>;
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={testId}>
        <DialogHeader><DialogTitle className="font-display">{title}</DialogTitle></DialogHeader>
        <form onSubmit={(e) => { e.preventDefault(); submit(); }} className="space-y-3">
          <Fields fields={fields} form={form} setForm={setForm} testId={testId} />
          <InlineError error={error} testId={`${testId}-error`} />
          <DialogFooter><Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button type="submit" data-testid={`${testId}-submit`}>Save</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

const Fields = ({ fields, form, setForm, testId }) => fields.map((f) => (
  <Field key={f.key} label={f.label + (f.required ? " *" : "")} hint={f.hint}>
    {f.options ? <NativeSelect testId={`${testId}-${f.key}`} value={form[f.key]} onChange={(v) => setForm({ ...form, [f.key]: v })} placeholder={f.placeholder ?? "Select…"} options={f.options} className="w-full" />
      : <Input data-testid={`${testId}-${f.key}`} type={f.type || "text"} value={form[f.key] ?? ""} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} />}
  </Field>
));

const num = (v) => (v === "" || v == null ? null : Number(v));

const StatusMenu = ({ item, statuses, path, reload, testId }) => {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const save = async () => {
    try { await api.patch(`/pipeline/${path}/${item.id}/status`, { status, note, version: item.version }); toast.success(`Status → ${status}`); setOpen(false); reload(); }
    catch (e) { setError(errMsg(e)); }
  };
  return (<>
    <Button size="sm" variant="ghost" data-testid={`${testId}-${item.id}`} onClick={() => { setStatus(""); setNote(""); setError(""); setOpen(true); }}>Update</Button>
    <ConfirmDialog open={open} onOpenChange={setOpen} title="Update status" testId="status-update-dialog" disabled={!status} error={error} onConfirm={save}>
      <Field label="New status"><NativeSelect testId="status-update-select" value={status} onChange={setStatus} placeholder="Select…" options={statuses.filter((s) => s !== item.status)} className="w-full" /></Field>
      <Field label="Note"><Input data-testid="status-update-note" value={note} onChange={(e) => setNote(e.target.value)} /></Field>
    </ConfirmDialog>
  </>);
};

function usePipeline(path, params) {
  const [items, setItems] = useState(null);
  const load = () => api.get(`/pipeline/${path}`, { params }).then((r) => setItems(r.data));
  useEffect(() => { load(); }, [JSON.stringify(params)]); // eslint-disable-line
  return [items, load];
}

const CandCell = ({ i }) => <Link className="font-medium hover:underline" to={`/candidates/${i.candidate_id}`}>{i.candidate_name}</Link>;

export const SubmissionsTable = ({ items, reload }) => {
  const [hist, setHist] = useState(null);
  return (<>
    <table className="dense-table w-full" data-testid="submissions-table"><thead><tr><th>Candidate</th><th>Job</th><th>Client</th><th>Group</th><th>Rate</th><th>Status</th><th>Submitted</th><th></th></tr></thead>
      <tbody>{items.map((s) => (
        <tr key={s.id} data-testid="submission-row"><td><CandCell i={s} /></td><td>{s.job_title}</td><td>{s.client_name}</td><td className="text-xs">{s.group_name}</td>
          <td className="font-mono text-xs">{rate(s, "submission_rate")}</td><td><StatusBadge status={s.status} /></td><td className="text-xs">{s.submitted_by_name} · {fmtDate(s.created_at)}</td>
          <td className="whitespace-nowrap"><Button size="sm" variant="ghost" onClick={() => setHist(s)} data-testid={`submission-history-${s.id}`}><History className="h-4 w-4" /></Button>
            <StatusMenu item={s} statuses={["SUBMITTED", "CLIENT_REVIEW", "INTERVIEW", "OFFER", "REJECTED", "WITHDRAWN"]} path="submissions" reload={reload} testId="submission-status" /></td></tr>))}</tbody></table>
    <Dialog open={!!hist} onOpenChange={() => setHist(null)}><DialogContent data-testid="submission-history-dialog"><DialogHeader><DialogTitle>Status history</DialogTitle></DialogHeader>
      <ol className="space-y-2 text-sm">{hist?.status_history?.map((h, i) => <li key={i} className="flex items-center gap-3"><StatusBadge status={h.status} /><span className="text-xs text-slate-500">{fmtDateTime(h.at)} · {h.by}</span><span className="text-xs">{h.note}</span></li>)}</ol>
    </DialogContent></Dialog>
  </>);
};

export const InterviewsTable = ({ items, reload }) => {
  const [res, setRes] = useState(null);
  const [hist, setHist] = useState(null);
  return (<>
    <table className="dense-table w-full" data-testid="interviews-table"><thead><tr><th>Candidate</th><th>Job</th><th>Round</th><th>When (interview TZ)</th><th>Your time</th><th>Mode</th><th>Status</th><th></th></tr></thead>
      <tbody>{items.map((i) => (
        <tr key={i.id} data-testid="interview-row"><td><CandCell i={i} /></td><td>{i.job_title}</td><td>{i.round}</td><td className="font-mono text-xs">{fmtDateTime(i.scheduled_at, i.timezone)}</td>
          <td className="font-mono text-xs text-slate-500">{fmtDateTime(i.scheduled_at)}</td><td className="text-xs">{i.mode}</td><td><StatusBadge status={i.status} />{i.reschedule_history?.length > 0 && <button onClick={() => setHist(i)} className="ml-1 text-[10px] text-indigo-700 underline" data-testid={`reschedule-history-${i.id}`}>{i.reschedule_history.length}× rescheduled</button>}</td>
          <td className="whitespace-nowrap">{i.status === "SCHEDULED" && <Button size="sm" variant="ghost" onClick={() => setRes(i)} data-testid={`reschedule-button-${i.id}`}>Reschedule</Button>}
            <StatusMenu item={i} statuses={["SCHEDULED", "COMPLETED", "CANCELLED", "NO_SHOW"]} path="interviews" reload={reload} testId="interview-status" /></td></tr>))}</tbody></table>
    <FormDialog open={!!res} onOpenChange={() => setRes(null)} title="Reschedule interview" testId="reschedule-dialog"
      fields={[{ key: "scheduled_at", label: "New date & time (in selected timezone)", type: "datetime-local", required: true }, { key: "timezone", label: "Timezone", options: TZS, default: res?.timezone, required: true }, { key: "reason", label: "Reason", required: true }]}
      onSubmit={async (f) => { await api.post(`/pipeline/interviews/${res.id}/reschedule`, { scheduled_at: localToUtc(f.scheduled_at, f.timezone), timezone: f.timezone, reason: f.reason, version: res.version }); toast.success("Interview rescheduled"); reload(); }} />
    <Dialog open={!!hist} onOpenChange={() => setHist(null)}><DialogContent data-testid="reschedule-history-dialog"><DialogHeader><DialogTitle>Reschedule history</DialogTitle></DialogHeader>
      <ul className="space-y-2 text-sm">{hist?.reschedule_history?.map((h, k) => <li key={k} className="rounded border p-2 text-xs"><div className="font-mono">{fmtDateTime(h.from, h.from_tz)} → {fmtDateTime(h.to, h.to_tz)}</div><div>{h.reason} · {h.by} · {fmtDateTime(h.at)}</div></li>)}</ul>
    </DialogContent></Dialog>
  </>);
};

export function localToUtc(local, tz) {
  const asUtc = new Date(local + ":00Z");
  const inTz = new Date(asUtc.toLocaleString("en-US", { timeZone: tz }));
  const inUtc = new Date(asUtc.toLocaleString("en-US", { timeZone: "UTC" }));
  return new Date(asUtc.getTime() - (inTz - inUtc)).toISOString();
}

export const OffersTable = ({ items, reload }) => {
  const { isOps } = useAuth();
  const [place, setPlace] = useState(null);
  return (<>
    <table className="dense-table w-full" data-testid="offers-table"><thead><tr><th>Candidate</th><th>Job</th><th>Client</th><th>Bill</th><th>Pay</th><th>Start</th><th>Status</th><th></th></tr></thead>
      <tbody>{items.map((o) => (
        <tr key={o.id} data-testid="offer-row"><td><CandCell i={o} /></td><td>{o.job_title}</td><td>{o.client_name}</td><td className="font-mono text-xs">{rate(o, "bill_rate")}</td><td className="font-mono text-xs">{rate(o, "pay_rate")}</td>
          <td className="text-xs">{fmtDate(o.start_date)}</td><td><StatusBadge status={o.status} /></td>
          <td className="whitespace-nowrap"><StatusMenu item={o} statuses={["EXTENDED", "ACCEPTED", "DECLINED", "WITHDRAWN"]} path="offers" reload={reload} testId="offer-status" />
            {isOps && o.status === "ACCEPTED" && o.candidate_status === "OFFERED" && <Button size="sm" onClick={() => setPlace(o)} data-testid={`create-placement-${o.id}`}>Place</Button>}</td></tr>))}</tbody></table>
    <FormDialog open={!!place} onOpenChange={() => setPlace(null)} title={`Create placement for ${place?.candidate_name}`} testId="placement-confirm-dialog" confirmWord="PLACE"
      fields={[{ key: "start_date", label: "Start date", type: "date", required: true, default: place?.start_date }, { key: "end_date", label: "End date", type: "date" }]}
      onSubmit={async (f) => { await api.post("/pipeline/placements", { offer_id: place.id, start_date: f.start_date, end_date: f.end_date || null, confirm: true }); toast.success("Candidate placed"); reload(); }} />
  </>);
};

export const PlacementsTable = ({ items, reload }) => {
  const { isOps } = useAuth();
  const [end, setEnd] = useState(null);
  return (<>
    <table className="dense-table w-full" data-testid="placements-table"><thead><tr><th>Candidate</th><th>Job</th><th>Client</th><th>Group</th><th>Bill</th><th>Pay</th><th>Start</th><th>End</th><th>Status</th><th></th></tr></thead>
      <tbody>{items.map((p) => (
        <tr key={p.id} data-testid="placement-row"><td><CandCell i={p} /></td><td>{p.job_title}</td><td>{p.client_name}</td><td className="text-xs">{p.group_name}</td><td className="font-mono text-xs">{rate(p, "bill_rate")}</td><td className="font-mono text-xs">{rate(p, "pay_rate")}</td>
          <td className="text-xs">{fmtDate(p.start_date)}</td><td className="text-xs">{fmtDate(p.end_date)}</td><td><StatusBadge status={p.status} /></td>
          <td>{isOps && p.status === "ACTIVE" && <Button size="sm" variant="ghost" onClick={() => setEnd(p)} data-testid={`end-placement-${p.id}`}>End</Button>}</td></tr>))}</tbody></table>
    <FormDialog open={!!end} onOpenChange={() => setEnd(null)} title="End placement — candidate returns to BENCH" testId="end-placement-dialog" confirmWord="END"
      fields={[{ key: "note", label: "Reason", required: true }]}
      onSubmit={async (f) => { await api.post(`/pipeline/placements/${end.id}/end`, { status: "ENDED", note: f.note, version: end.version }); toast.success("Placement ended"); reload(); }} />
  </>);
};

const Page = ({ title, path, Table, subtitle, params = {} }) => {
  const [items, load] = usePipeline(path, params);
  return (<div data-testid={`${path}-page`}><PageHeader title={title} subtitle={subtitle} />
    <Panel>{!items ? <Loading /> : items.length === 0 ? <Empty /> : <div className="overflow-x-auto"><Table items={items} reload={load} /></div>}</Panel></div>);
};

export const Submissions = () => <Page title="Submissions" path="submissions" Table={SubmissionsTable} subtitle="Create submissions from a candidate's Pipeline tab." />;
export const Interviews = () => <Page title="Interviews" path="interviews" Table={InterviewsTable} subtitle="Times shown in the interview's timezone and your local time." />;
export const Offers = () => <Page title="Offers" path="offers" Table={OffersTable} />;
export const Placements = () => <Page title="Placements" path="placements" Table={PlacementsTable} />;

export const PipelineTab = ({ detail, reload }) => {
  const c = detail.candidate;
  const canWork = detail.permissions.can_edit;
  const [subs, loadSubs] = usePipeline("submissions", { candidate_id: c.id });
  const [ints, loadInts] = usePipeline("interviews", { candidate_id: c.id });
  const [offs, loadOffs] = usePipeline("offers", { candidate_id: c.id });
  const [pls, loadPls] = usePipeline("placements", { candidate_id: c.id });
  const [jobs, setJobs] = useState([]);
  const [dlg, setDlg] = useState(null);
  useEffect(() => { api.get("/jobs", { params: { status: "OPEN" } }).then((r) => setJobs(r.data)); }, []);
  const all = () => { loadSubs(); loadInts(); loadOffs(); loadPls(); reload(); };
  const activeSubs = (subs || []).filter((s) => !["REJECTED", "WITHDRAWN", "PLACED"].includes(s.status)).map((s) => ({ value: s.id, label: `${s.job_title} (${s.status})` }));
  return (
    <div className="space-y-4">
      {canWork && <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={() => setDlg("sub")} disabled={!["MARKETING", "SUBMITTED", "INTERVIEWING"].includes(c.status)} data-testid="new-submission-button"><Plus className="mr-1 h-4 w-4" />Submission</Button>
        <Button size="sm" variant="outline" onClick={() => setDlg("int")} disabled={!activeSubs.length} data-testid="new-interview-button"><Plus className="mr-1 h-4 w-4" />Interview</Button>
        <Button size="sm" variant="outline" onClick={() => setDlg("off")} disabled={!activeSubs.length} data-testid="new-offer-button"><Plus className="mr-1 h-4 w-4" />Offer</Button>
        {c.status === "BENCH" && <span className="self-center text-xs text-slate-500">Move candidate to MARKETING to submit.</span>}
      </div>}
      <Panel title="Submissions">{subs?.length ? <SubmissionsTable items={subs} reload={all} /> : <Empty text="No submissions" />}</Panel>
      <Panel title="Interviews">{ints?.length ? <InterviewsTable items={ints} reload={all} /> : <Empty text="No interviews" />}</Panel>
      <Panel title="Offers">{offs?.length ? <OffersTable items={offs} reload={all} /> : <Empty text="No offers" />}</Panel>
      <Panel title="Placements">{pls?.length ? <PlacementsTable items={pls} reload={all} /> : <Empty text="No placements" />}</Panel>
      <FormDialog open={dlg === "sub"} onOpenChange={() => setDlg(null)} title="New submission" testId="submission-dialog"
        fields={[{ key: "job_id", label: "Job", required: true, options: jobs.map((j) => ({ value: j.id, label: `${j.title} — ${j.client_name || ""}` })) }, { key: "submission_rate", label: "Submission rate ($/hr)", type: "number", default: c.target_rate ?? "" }, { key: "notes", label: "Notes" }]}
        onSubmit={async (f) => { await api.post("/pipeline/submissions", { candidate_id: c.id, job_id: f.job_id, submission_rate: num(f.submission_rate), notes: f.notes }); toast.success("Submission created"); all(); }} />
      <FormDialog open={dlg === "int"} onOpenChange={() => setDlg(null)} title="Schedule interview" testId="interview-dialog"
        fields={[{ key: "submission_id", label: "Submission", required: true, options: activeSubs }, { key: "scheduled_at", label: "Date & time (in selected timezone)", type: "datetime-local", required: true },
          { key: "timezone", label: "Timezone", options: TZS, default: "America/New_York", required: true }, { key: "round", label: "Round", default: "Round 1" }, { key: "mode", label: "Mode", options: ["VIDEO", "PHONE", "ONSITE"], default: "VIDEO" }, { key: "interviewer", label: "Interviewer" }]}
        onSubmit={async (f) => { await api.post("/pipeline/interviews", { ...f, scheduled_at: localToUtc(f.scheduled_at, f.timezone) }); toast.success("Interview scheduled"); all(); }} />
      <FormDialog open={dlg === "off"} onOpenChange={() => setDlg(null)} title="Record offer" testId="offer-dialog"
        fields={[{ key: "submission_id", label: "Submission", required: true, options: activeSubs }, { key: "bill_rate", label: "Bill rate", type: "number" }, { key: "pay_rate", label: "Pay rate (Admin/Ops only)", type: "number" }, { key: "start_date", label: "Start date", type: "date" }]}
        onSubmit={async (f) => { await api.post("/pipeline/offers", { ...f, bill_rate: num(f.bill_rate), pay_rate: num(f.pay_rate), start_date: f.start_date || null }); toast.success("Offer recorded"); all(); }} />
    </div>
  );
};
