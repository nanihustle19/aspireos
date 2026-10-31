import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import { UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, errMsg, fmtDate } from "@/lib/api";
import { Field, InlineError, Loading, NativeSelect, PageHeader, Panel } from "@/components/Common";
import { StatusBadge } from "@/components/StatusBadge";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { FormDialog } from "@/pages/Pipeline";
import { CandidateTable } from "@/pages/Candidates";

const ROLES = ["LEAD", "RECRUITER", "MARKETING", "VIEWER"];

export default function GroupDetail() {
  const { id } = useParams();
  const [g, setG] = useState(null);
  const [cands, setCands] = useState([]);
  const [users, setUsers] = useState([]);
  const [add, setAdd] = useState(false);
  const [remove, setRemove] = useState(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const load = () => {
    api.get(`/groups/${id}`).then((r) => setG(r.data)).catch((e) => setError(errMsg(e)));
    api.get("/candidates", { params: { group_id: id, page_size: 200 } }).then((r) => setCands(r.data.items));
  };
  useEffect(() => { load(); api.get("/users").then((r) => setUsers(r.data)); }, [id]); // eslint-disable-line
  if (error && !g) return <InlineError error={error} />;
  if (!g) return <Loading />;
  const memberIds = new Set(g.members.map((m) => m.user_id));
  const eligible = users.filter((u) => u.role === "EMPLOYEE" && u.status === "ACTIVE" && !memberIds.has(u.id));
  const changeRole = async (m, role) => { try { await api.patch(`/groups/${id}/members/${m.id}`, { role }); toast.success("Role updated"); load(); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <div data-testid="group-detail-page">
      <PageHeader title={g.name} subtitle={g.description}>{g.can_manage && <Button size="sm" onClick={() => setAdd(true)} data-testid="add-member-button"><UserPlus className="mr-1 h-4 w-4" />Add member</Button>}</PageHeader>
      <div className="grid gap-4 xl:grid-cols-[380px_1fr]">
        <Panel title={`Members (${g.members.length})`} testId="group-members-panel">
          <table className="dense-table w-full"><thead><tr><th>Member</th><th>Role</th><th></th></tr></thead>
            <tbody>{g.members.map((m) => (
              <tr key={m.id} data-testid="member-row"><td><div className="font-medium">{m.user?.name}</div><div className="text-[11px] text-slate-500">{m.user?.email} · since {fmtDate(m.created_at)}</div></td>
                <td>{g.can_manage ? <NativeSelect testId={`member-role-${m.id}`} value={m.role} onChange={(v) => changeRole(m, v)} options={ROLES} /> : <StatusBadge status={m.role} />}</td>
                <td>{g.can_manage && <Button size="sm" variant="ghost" className="text-rose-700" onClick={() => { setReason(""); setRemove(m); }} data-testid={`remove-member-${m.id}`}>Remove</Button>}</td></tr>))}</tbody></table>
        </Panel>
        <Panel title={`Candidates (${cands.length})`}><CandidateTable items={cands} testId="group-candidates-table" /></Panel>
      </div>
      <FormDialog open={add} onOpenChange={setAdd} title="Add member" testId="add-member-dialog"
        fields={[{ key: "user_id", label: "Employee", required: true, options: eligible.map((u) => ({ value: u.id, label: `${u.name} (${u.email})` })) }, { key: "role", label: "Group role", required: true, options: ROLES, default: "RECRUITER" }]}
        onSubmit={async (f) => { await api.post(`/groups/${id}/members`, f); toast.success("Member added"); load(); }} />
      <ConfirmDialog open={!!remove} onOpenChange={() => setRemove(null)} testId="remove-member-dialog" title={`Remove ${remove?.user?.name}?`} confirmWord="REMOVE" destructive
        description="Access is revoked immediately. Candidates they own in this group will have their owner cleared, and leads/operations are notified."
        disabled={!reason.trim()} onConfirm={async () => { const { data } = await api.delete(`/groups/${id}/members/${remove.id}`, { params: { reason } }); toast.success(`Member removed · ${data.owners_cleared} owner(s) cleared`); setRemove(null); load(); }}>
        <Field label="Reason *"><Input data-testid="remove-member-reason" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      </ConfirmDialog>
    </div>
  );
}
