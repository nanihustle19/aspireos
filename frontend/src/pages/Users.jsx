import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Copy, UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, errMsg, fmtDate, fmtDateTime } from "@/lib/api";
import { Empty, Field, InlineError, Loading, NativeSelect, PageHeader, Panel } from "@/components/Common";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/StatusBadge";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { FormDialog } from "@/pages/Pipeline";
import { useAuth } from "@/context/AuthContext";

export default function UsersPage() {
  const { isAdmin, user: me, org } = useAuth();
  const [users, setUsers] = useState(null);
  const [invites, setInvites] = useState([]);
  const [groups, setGroups] = useState([]);
  const [invite, setInvite] = useState(false);
  const [link, setLink] = useState(null);
  const [deact, setDeact] = useState(null);
  const [mfa, setMfa] = useState(null);
  const [mfaReason, setMfaReason] = useState("");
  const [mfaError, setMfaError] = useState("");
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const load = () => {
    setError("");
    return Promise.all([api.get("/users"), api.get("/invitations"), api.get("/groups")])
      .then(([u, i, g]) => { setUsers(u.data); setInvites(i.data); setGroups(g.data); })
      .catch((e) => setError(errMsg(e)));
  };
  useEffect(() => { load(); }, []);
  const patch = async (u, body, msg) => { try { await api.patch(`/users/${u.id}`, body); toast.success(msg); load(); } catch (e) { toast.error(errMsg(e)); } };
  if (!users) return error ? <div className="space-y-3"><InlineError error={error} /><Button onClick={load}>Try again</Button></div> : <Loading />;
  const matches = users.filter((u) => `${u.name} ${u.email}`.toLowerCase().includes(query.trim().toLowerCase()));
  return (
    <div data-testid="users-page">
      <PageHeader title="Users & invitations" subtitle="Access is invitation-only. Employees activate with Google or a password.">
        <Button size="sm" onClick={() => setInvite(true)} data-testid="invite-user-button"><UserPlus className="mr-1 h-4 w-4" />Invite employee</Button>
      </PageHeader>
      <Tabs defaultValue="users">
        <TabsList className="border bg-white"><TabsTrigger value="users" data-testid="tab-users">Users ({users.length})</TabsTrigger><TabsTrigger value="invites" data-testid="tab-invitations">Invitations ({invites.length})</TabsTrigger></TabsList>
        <TabsContent value="users"><Panel>
          <div className="border-b p-4"><div className="max-w-sm"><Field id="user-search" label="Find a user"><Input id="user-search" type="search" placeholder="Name or work email" value={query} onChange={(e) => setQuery(e.target.value)} /></Field></div></div>
          <div className="overflow-x-auto">
          <table className="dense-table min-w-[760px] w-full" data-testid="users-table"><thead><tr><th>Name</th><th>Organization</th><th>Role</th><th>Status</th><th>Groups</th><th>Authenticator</th><th>Last login</th><th>Actions</th></tr></thead>
            <tbody>{matches.map((u) => (
              <tr key={u.id} data-testid="user-row"><td><div className="font-medium">{u.name}</div><div className="text-[11px] text-slate-500">{u.email}</div></td>
                <td className="text-xs">{org?.name || "—"}</td>
                <td>{isAdmin && u.id !== me.id ? <NativeSelect testId={`user-role-${u.id}`} value={u.role} onChange={(v) => patch(u, { role: v }, "Role updated — user sessions revoked")} options={["ADMIN", "OPERATIONS", "EMPLOYEE", "AUDITOR"]} /> : <span className="text-xs font-semibold">{u.role}</span>}</td>
                <td><StatusBadge status={u.status} /></td>
                <td className="text-xs">{u.groups.map((g) => `${g.group_name} (${g.role})`).join(", ") || "—"}</td>
                <td className="text-xs">{u.mfa_enabled ? "Enabled" : u.role === "ADMIN" ? "Enroll at login" : "—"}</td>
                <td className="text-xs">{fmtDateTime(u.last_login_at)}</td>
                <td className="whitespace-nowrap">{isAdmin && u.id !== me.id && u.role === "AUDITOR" && <Button size="sm" variant="ghost" onClick={() => patch(u, { can_view_ops_only: !u.can_view_ops_only }, "Updated")} data-testid={`grant-ops-${u.id}`}>{u.can_view_ops_only ? "Revoke ops-notes" : "Grant ops-notes"}</Button>}
                  {isAdmin && u.id !== me.id && u.mfa_enabled && <Button size="sm" variant="ghost" onClick={() => { setMfaReason(""); setMfaError(""); setMfa(u); }} data-testid={`reset-mfa-${u.id}`}>Reset authenticator</Button>}
                  {isAdmin && u.id !== me.id && u.status === "ACTIVE" && <Button size="sm" variant="ghost" className="text-rose-700" onClick={() => setDeact(u)} data-testid={`deactivate-user-${u.id}`}>Deactivate</Button>}
                  {isAdmin && u.status === "DEACTIVATED" && <Button size="sm" variant="ghost" onClick={() => patch(u, { status: "ACTIVE" }, "User reactivated")} data-testid={`reactivate-user-${u.id}`}>Reactivate</Button>}</td></tr>))}</tbody></table>
          </div>{!matches.length && <Empty text="No users match this search." />}
        </Panel></TabsContent>
        <TabsContent value="invites"><Panel className="overflow-x-auto">
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
        description="You can also share this activation link with the invitee."
        onConfirm={async () => { await navigator.clipboard?.writeText(link).catch(() => {}); toast.success("Link copied"); setLink(null); }}>
        <code data-testid="invite-activation-link" className="block break-all rounded bg-slate-100 p-2 text-xs">{link}</code>
      </ConfirmDialog>
      <ConfirmDialog open={isAdmin && !!mfa} onOpenChange={() => setMfa(null)} title={`Reset authenticator for ${mfa?.name}?`} testId="reset-mfa-dialog" confirmWord="RESET" destructive
        disabled={!mfaReason.trim()} confirmLabel="Reset authenticator" error={mfaError}
        description="Removes their enrolled authenticator and signs them out everywhere. On next sign-in they must enroll a new authenticator app."
        onConfirm={async () => { setMfaError(""); try { await api.post(`/users/${mfa.id}/reset-mfa`, { reason: mfaReason }); toast.success("Authenticator reset"); setMfa(null); load(); } catch (e) { setMfaError(errMsg(e)); } }}>
        <Field id="mfa-reset-reason" label="Reason" hint="This reason is recorded in the audit log."><Input id="mfa-reset-reason" aria-describedby="mfa-reset-reason-feedback" data-testid="reset-mfa-reason-input" required maxLength={1000} value={mfaReason} onChange={(e) => setMfaReason(e.target.value)} /></Field>
      </ConfirmDialog>
      <ConfirmDialog open={!!deact} onOpenChange={() => setDeact(null)} title={`Deactivate ${deact?.name}?`} testId="deactivate-user-dialog" confirmWord="DEACTIVATE" destructive
        description="Sessions are revoked immediately, group memberships end, owned candidates have their owner cleared, and leads/operations are notified."
        onConfirm={async () => { await patch(deact, { status: "DEACTIVATED" }, "User deactivated"); setDeact(null); }} />
    </div>
  );
}
