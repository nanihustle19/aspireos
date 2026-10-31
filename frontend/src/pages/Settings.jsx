import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, errMsg, fmtDateTime } from "@/lib/api";
import { Field, InlineError, Loading, PageHeader, Panel } from "@/components/Common";
import { StatusBadge } from "@/components/StatusBadge";
import { useAuth } from "@/context/AuthContext";

const KEYS = [["bench_aging_warning_days", "Bench aging warning (days)"], ["bench_aging_critical_days", "Bench aging critical (days)"], ["weekly_submission_target", "Weekly submission target per recruiter"]];

export default function SettingsPage() {
  const { isAdmin, org, user, logout } = useAuth();
  const [s, setS] = useState(null);
  const [outbox, setOutbox] = useState([]);
  const [error, setError] = useState("");
  useEffect(() => { api.get("/settings").then((r) => setS((prev) => prev || r.data)); if (isAdmin) api.get("/outbox").then((r) => setOutbox(r.data)); }, [isAdmin]);
  if (!s) return <Loading />;
  const save = async () => {
    const body = Object.fromEntries(KEYS.map(([k]) => [k, Number(s[k])]));
    if (body.bench_aging_warning_days >= body.bench_aging_critical_days) return setError("Warning threshold must be lower than critical threshold");
    try { const { data } = await api.put("/settings", { ...body, interview_default_timezone: s.interview_default_timezone }); setS(data); setError(""); toast.success("Settings saved"); }
    catch (e) { setError(errMsg(e)); }
  };
  return (
    <div data-testid="settings-page">
      <PageHeader title="Settings" subtitle={`${org?.name} · plan ${org?.plan || "—"}`} />
      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Official thresholds" testId="settings-thresholds">
          <form className="space-y-3 p-4" onSubmit={(e) => { e.preventDefault(); save(); }}>
            {KEYS.map(([k, l]) => <Field key={k} label={l}><Input data-testid={`setting-${k}`} type="number" min={1} disabled={!isAdmin} value={s[k]} onChange={(e) => setS({ ...s, [k]: e.target.value })} /></Field>)}
            <Field label="Default interview timezone"><Input data-testid="setting-interview_default_timezone" disabled={!isAdmin} value={s.interview_default_timezone} onChange={(e) => setS({ ...s, interview_default_timezone: e.target.value })} /></Field>
            <InlineError error={error} testId="settings-error" />
            {isAdmin ? <Button type="submit" data-testid="save-settings-button">Save thresholds</Button> : <p className="text-xs text-slate-500">Only administrators can change official thresholds.</p>}
          </form>
        </Panel>
        <Panel title="Security" testId="settings-security">
          <div className="space-y-3 p-4 text-sm">
            <div className="flex justify-between"><span className="text-slate-600">MFA required for Admin</span><b>Enforced (TOTP)</b></div>
            <div className="flex justify-between"><span className="text-slate-600">Your MFA</span><b>{user?.mfa_enabled ? "Enabled" : user?.role === "ADMIN" ? "Pending" : "Not required"}</b></div>
            <div className="flex justify-between"><span className="text-slate-600">Sign-in methods</span><b>{(user?.auth_methods || []).join(", ") || "—"}</b></div>
            <Button variant="outline" size="sm" data-testid="logout-all-button" onClick={async () => { await api.post("/auth/logout-all"); await logout(); window.location.href = "/login"; }}>Sign out of all sessions</Button>
          </div>
        </Panel>
        {isAdmin && <Panel title="Email outbox (MOCKED — Resend not connected)" className="xl:col-span-2" testId="outbox-panel">
          <table className="dense-table w-full"><thead><tr><th>To</th><th>Subject</th><th>Status</th><th>Created</th></tr></thead>
            <tbody>{outbox.slice(0, 50).map((m) => <tr key={m.id}><td className="text-xs">{m.to}</td><td className="text-xs">{m.subject}</td><td><StatusBadge status={m.status === "SENT_MOCK" ? "COMPLETED" : m.status} /></td><td className="text-xs">{fmtDateTime(m.created_at)}</td></tr>)}</tbody></table>
        </Panel>}
      </div>
    </div>
  );
}
