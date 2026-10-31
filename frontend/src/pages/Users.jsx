import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Copy, UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, errMsg, fmtDate, fmtDateTime } from "@/lib/api";
import { Loading, NativeSelect, PageHeader, Panel } from "@/components/Common";
import { StatusBadge } from "@/components/StatusBadge";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { FormDialog } from "@/pages/Pipeline";
import { useAuth } from "@/context/AuthContext";

export default function UsersPage() {
  const { isAdmin, user: me } = useAuth();
  const [users, setUsers] = useState(null);
  const [invites, setInvites] = useState([]);
  const [groups, setGroups] = useState([]);
  const [invite, setInvite] = useState(false);
  const [link, setLink] = useState(null);
  const [deact, setDeact] = useState(null);
  const load = () => { api.get("/users").then((r) => setUsers(r.data)); api.get("/invitations").then((r) => setInvites(r.data)); };
  useEffect(() => { load(); api.get("/groups").then((r) => setGroups(r.data)); }, []);
  const patch = async (u, body, msg) => { try { await api.patch(`/users/${u.id}`, body); toast.success(msg); load(); } catch (e) { toast.error(errMsg(e)); } };
  if (!users) return <Loading />;
  return (
    <div data-testid="users-page">
      <PageHeader title="Users & invitations" subtitle="Access is invitation-only. Employees activate with Google or a password.">
        <Button size="sm" onClick={() => setInvite(true)} data-testid="invite-user-button"><UserPlus className="mr-1 h-4 w-4" />Invite employee</Button>
      </PageHeader>
      <Tabs defaultValue="users">
        <TabsList className="border bg-white"><TabsTrigger value="users" data-testid="tab-users">Users ({users.length})</TabsTrigger><TabsTrigger value="invites" data-testid="tab-invitations">Invitations ({invites.length})</TabsTrigger></TabsList>
        <TabsContent value="users"><Panel>
          <table className="dense-table w-full" data-testid="users-table"><thead><tr><th>Name</th><th>Role</th><th>Status</th><th>Groups</th><th>MFA</th><th>Last login</th><th></th></tr></thead>
            <tbody>{users.map((u) => (
              <tr key={u.id} data-testid="user-row"><td><div className="font-medium">{u.name}</div><div className="text-[11px] text-slate-500">{u.email}</div></td>
                <td>{isAdmin && u.id !== me.id ? <NativeSelect testId={`user-role-${u.id}`} value={u.role} onChange={(v) => patch(u, { role: v }, "Role updated — user sessions revoked")} options={["ADMIN", "OPERATIONS", "EMPLOYEE", "AUDITOR"]} /> : <span className="text-xs font-semibold">{u.role}</span>}</td>
                <td><StatusBadge status={u.status} /></td>
                <td className="text-xs">{u.groups.map((g) => `${g.group_name} (${g.role})`).join(", ") || "—"}</td>
                <td className="text-xs">{u.mfa_enabled ? "Enabled" : u.role === "ADMIN" ? "Enroll at login" : "—"}</td>
                <td className="text-xs">{fmtDateTime(u.last_login_at)}</td>
                <td className="whitespace-nowrap">{isAdmin && u.id !== me.id && u.role === "AUDITOR" && <Button size="sm" variant="ghost" onClick={() => patch(u, { can_view_ops_only: !u.can_view_ops_only }, "Updated")} data-testid={`grant-ops-${u.id}`}>{u.can_view_ops_only ? "Revoke ops-notes" : "Grant ops-notes"}</Button>}
                  {isAdmin && u.id !== me.id && u.status === "ACTIVE" && <Button size="sm" variant="ghost" className="text-rose-700" onClick={() => setDeact(u)} data-testid={`deactivate-user-${u.id}`}>Deactivate</Button>}
                  {isAdmin && u.status === "DEACTIVATED" && <Button size="sm" variant="ghost" onClick={() => patch(u, { status: "ACTIVE" }, "User reactivated")} data-testid={`reactivate-user-${u.id}`}>Reactivate</Button>}</td></tr>))}</tbody></table>
        </Panel></TabsContent>
        <TabsContent value="invites"><Panel>
          <table className="dense-table w-full" data-testid="invitations-table"><thead><tr><th>Email</th><th>Role</th><th>Status</th><th>Invited by</th><th>Expires</th><th></th></tr></thead>
            <tbody>{invites.map((i) => (
              <tr key={i.id} data-testid="invitation-row"><td>{i.email}</td><td className="text-xs">{i.role}</td><td><StatusBadge status={i.status} /></td><td className="text-xs">{i.invited_by_name}</td><td className="text-xs">{fmtDate(i.expires_at)}</td>
                <td className="whitespace-nowrap">{i.status === "PENDING" && <><Button size="sm" variant="ghost" onClick={() => setLink(`${window.location.origin}/activate?token=${i.token}`)} data-testid={`copy-invite-${i.id}`}><Copy className="h-4 w-4" /></Button>
                  <Button size="sm" variant="ghost" className="text-rose-700" onClick={async () => { await api.post(`/invitations/${i.id}/revoke`); toast.success("Invitation revoked"); load(); }} data-testid={`revoke-invite-${i.id}`}>Revoke</Button></>}</td></tr>))}</tbody></table>
        </Panel></TabsContent>
      </Tabs>
      <FormDialog open={invite} onOpenChange={setInvite} title="Invite employee" testId="invite-dialog"
        fields={[{ key: "name", label: "Full name", required: true }, { key: "email", label: "Work email", type: "email", required: true },
          { key: "role", label: "Organization role", required: true, default: "EMPLOYEE", options: isAdmin ? ["EMPLOYEE", "OPERATIONS", "AUDITOR", "ADMIN"] : ["EMPLOYEE", "AUDITOR"] },
          { key: "group_id", label: "Initial group (employees)", placeholder: "— none —", options: groups.map((g) => ({ value: g.id, label: g.name })) },
          { key: "group_role", label: "Group role", placeholder: "— none —", options: ["LEAD", "RECRUITER", "MARKETING", "VIEWER"] }]}
        onSubmit={async (f) => { const { data } = await api.post("/invitations", { ...f, group_id: f.group_id || null, group_role: f.group_role || null }); toast.success("Invitation created"); setLink(`${window.location.origin}${data.activation_path}`); load(); }} />
      <ConfirmDialog open={!!link} onOpenChange={() => setLink(null)} title="Activation link" testId="invite-link-dialog" confirmLabel="Copy link"
        description="Email delivery is MOCKED (logged to outbox). Share this link with the invitee."
        onConfirm={async () => { await navigator.clipboard?.writeText(link).catch(() => {}); toast.success("Link copied"); setLink(null); }}>
        <code data-testid="invite-activation-link" className="block break-all rounded bg-slate-100 p-2 text-xs">{link}</code>
      </ConfirmDialog>
      <ConfirmDialog open={!!deact} onOpenChange={() => setDeact(null)} title={`Deactivate ${deact?.name}?`} testId="deactivate-user-dialog" confirmWord="DEACTIVATE" destructive
        description="Sessions are revoked immediately, group memberships end, owned candidates have their owner cleared, and leads/operations are notified."
        onConfirm={async () => { await patch(deact, { status: "DEACTIVATED" }, "User deactivated"); setDeact(null); }} />
    </div>
  );
}
