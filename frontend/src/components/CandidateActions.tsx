import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { ArrowRightLeft, UserMinus, UserPlus, Archive, RotateCcw, ChevronRight, UserCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { api, errMsg, errCode } from "@/lib/api";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Field, NativeSelect } from "@/components/Common";
import type { Candidate, Group, Offer, User } from "@/types";

const MARKETING = ["MARKETING", "SUBMITTED", "INTERVIEWING", "OFFERED"];

interface CandidateActionPermissions {
  allowed_transitions: string[];
  can_assign: boolean;
  can_transfer: boolean;
  can_set_owner: boolean;
  can_unassign: boolean;
  can_archive: boolean;
  can_restore: boolean;
}

interface CandidateDetailData {
  candidate: Candidate;
  permissions: CandidateActionPermissions;
  active_offer?: { id: string; status: string } | null;
}

interface CandidateActionsProps {
  detail: CandidateDetailData;
  reload: () => void;
}

export const CandidateActions: React.FC<CandidateActionsProps> = ({ detail, reload }) => {
  const { candidate: c, permissions: p, active_offer } = detail;
  const [open, setOpen] = useState<string | null>(null);
  const [groups, setGroups] = useState<Group[]>([]);
  const [members, setMembers] = useState<{ id: string; user_id: string; role: string; user: User }[]>([]);
  const [form, setForm] = useState<Record<string, any>>({});
  const [error, setError] = useState("");

  useEffect(() => {
    api.get<Group[]>("/groups").then((r) => setGroups(r.data.filter((g) => g.active)));
  }, []);

  useEffect(() => {
    if (open === "owner" && c.current_group_id) {
      api.get<{ members: any[] }>(`/groups/${c.current_group_id}`).then((r) => setMembers(r.data.members));
    }
  }, [open, c.current_group_id]);

  const show = (k: string) => { setForm({}); setError(""); setOpen(k); };

  const run = async (path: string, body: Record<string, any>, msg: string) => {
    setError("");
    try {
      await api.post(`/candidates/${c.id}/${path}`, { version: c.version, ...body });
      toast.success(msg);
      setOpen(null);
      reload();
    } catch (e: any) {
      if (e.response?.status === 409 && errCode(e) !== "ACTIVE_OFFER") {
        setError(errMsg(e) + " (version conflict)");
      } else {
        setError(errMsg(e));
      }
    }
  };

  const needsTarget = MARKETING.includes(c.status);
  const otherGroups = groups.filter((g) => g.id !== c.current_group_id).map((g) => ({ value: g.id, label: g.name }));

  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="candidate-actions">
      {p.allowed_transitions.map((t) => (
        <Button
          key={t}
          size="sm"
          variant="outline"
          data-testid={`transition-${t.toLowerCase()}-button`}
          onClick={() => { setForm({ to: t }); setError(""); setOpen("transition"); }}
        >
          <ChevronRight className="mr-0.5 h-3.5 w-3.5" />{t.replace(/_/g, " ")}
        </Button>
      ))}
      {p.can_assign && (
        <Button size="sm" data-testid="assign-group-button" onClick={() => show("assign")}>
          <UserPlus className="mr-1 h-4 w-4" />Assign group
        </Button>
      )}
      {p.can_transfer && (
        <Button size="sm" variant="outline" data-testid="transfer-group-button" onClick={() => show("transfer")}>
          <ArrowRightLeft className="mr-1 h-4 w-4" />Transfer
        </Button>
      )}
      {p.can_set_owner && (
        <Button size="sm" variant="outline" data-testid="set-owner-button" onClick={() => show("owner")}>
          <UserCheck className="mr-1 h-4 w-4" />Owner
        </Button>
      )}
      {p.can_unassign && (
        <Button size="sm" variant="outline" className="border-orange-300 text-orange-800" data-testid="unassign-group-button" onClick={() => show("unassign")}>
          <UserMinus className="mr-1 h-4 w-4" />Unassign
        </Button>
      )}
      {p.can_archive && (
        <Button size="sm" variant="outline" className="border-rose-300 text-rose-700" data-testid="archive-candidate-button" onClick={() => show("archive")}>
          <Archive className="mr-1 h-4 w-4" />Archive
        </Button>
      )}
      {p.can_restore && (
        <Button size="sm" data-testid="restore-candidate-button" onClick={() => show("restore")}>
          <RotateCcw className="mr-1 h-4 w-4" />Restore
        </Button>
      )}

      {/* Transition Dialog */}
      <ConfirmDialog
        open={open === "transition"}
        onOpenChange={() => setOpen(null)}
        testId="transition-confirm-dialog"
        title={`Move to ${form.to}?`}
        error={error}
        description={`${c.status} → ${form.to}. Guarded transitions are validated by the server.`}
        onConfirm={() => run("transition", { to_status: form.to, reason: form.reason }, `Status changed to ${form.to}`)}
      >
        <Field label="Reason (optional)">
          <Textarea data-testid="transition-reason-input" value={form.reason || ""} onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setForm({ ...form, reason: e.target.value })} />
        </Field>
      </ConfirmDialog>

      {/* Assign Dialog */}
      <ConfirmDialog
        open={open === "assign"}
        onOpenChange={() => setOpen(null)}
        testId="assign-confirm-dialog"
        title="Assign to group"
        error={error}
        disabled={!form.group_id}
        description="Creates the single active group assignment for this candidate."
        onConfirm={() => run("assign", { group_id: form.group_id, reason: form.reason }, "Candidate assigned")}
      >
        <Field label="Group">
          <NativeSelect testId="assign-group-select" value={form.group_id} onChange={(v) => setForm({ ...form, group_id: v })} placeholder="Select group" options={groups.map((g) => ({ value: g.id, label: g.name }))} />
        </Field>
      </ConfirmDialog>

      {/* Transfer Dialog */}
      <ConfirmDialog
        open={open === "transfer"}
        onOpenChange={() => setOpen(null)}
        testId="transfer-group-confirm-dialog"
        title="Transfer candidate"
        confirmWord="TRANSFER"
        destructive
        error={error}
        disabled={Boolean(!form.to_group_id || !form.reason?.trim() || (active_offer && !form.ack))}
        confirmLabel="Transfer"
        description="Ends the current group assignment and creates a new one. The current group loses access immediately; owner is cleared."
        onConfirm={() => run("transfer", { to_group_id: form.to_group_id, reason: form.reason, acknowledge_active_offer: !!form.ack }, "Candidate transferred")}
      >
        <Field label="Destination group">
          <NativeSelect testId="transfer-group-select" value={form.to_group_id} onChange={(v) => setForm({ ...form, to_group_id: v })} placeholder="Select group" options={otherGroups} />
        </Field>
        <Field label="Reason *">
          <Textarea data-testid="transfer-reason-input" value={form.reason || ""} onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setForm({ ...form, reason: e.target.value })} />
        </Field>
        {(active_offer || c.status === "OFFERED") && (
          <label className="flex items-start gap-2 rounded border border-rose-300 bg-rose-50 p-2 text-xs text-rose-900" data-testid="active-offer-warning">
            <Checkbox data-testid="transfer-ack-offer-checkbox" checked={Boolean(form.ack)} onCheckedChange={(v: boolean | "indeterminate") => setForm({ ...form, ack: !!v })} />
            This candidate has an active offer ({active_offer?.status || "OFFERED"}). I acknowledge transferring may disrupt the offer. (Admin/Operations only)
          </label>
        )}
      </ConfirmDialog>

      {/* Unassign Dialog */}
      <ConfirmDialog
        open={open === "unassign"}
        onOpenChange={() => setOpen(null)}
        testId="unassign-confirm-dialog"
        title="Unassign from group"
        confirmWord="UNASSIGN"
        destructive
        error={error}
        disabled={!form.reason?.trim() || (needsTarget && !form.target)}
        confirmLabel="Unassign"
        description="The candidate will have no active group. Group members lose access immediately."
        onConfirm={() => run("unassign", { reason: form.reason, target_status: form.target || null }, "Candidate unassigned")}
      >
        {needsTarget && (
          <Field label="Candidate is in marketing — choose resulting status *">
            <div className="flex gap-2" role="radiogroup">
              {["BENCH", "ON_HOLD"].map((s) => (
                <button
                  type="button"
                  key={s}
                  data-testid={`unassign-target-${s.toLowerCase()}`}
                  onClick={() => setForm({ ...form, target: s })}
                  className={`flex-1 rounded border px-3 py-2 text-sm font-medium ${form.target === s ? "border-indigo-600 bg-indigo-50 text-indigo-800" : "bg-white"}`}
                >
                  {s.replace(/_/g, " ")}
                </button>
              ))}
            </div>
          </Field>
        )}
        <Field label="Reason *">
          <Textarea data-testid="unassign-reason-input" value={form.reason || ""} onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setForm({ ...form, reason: e.target.value })} />
        </Field>
      </ConfirmDialog>

      {/* Set Owner Dialog */}
      <ConfirmDialog
        open={open === "owner"}
        onOpenChange={() => setOpen(null)}
        testId="owner-dialog"
        title="Set candidate owner"
        error={error}
        onConfirm={() => run("owner", { owner_id: form.owner_id || null }, "Owner updated")}
      >
        <Field label="Owner (current group members)">
          <NativeSelect
            testId="owner-select"
            value={form.owner_id}
            onChange={(v) => setForm({ ...form, owner_id: v })}
            placeholder="— No owner —"
            options={members.map((m) => ({ value: m.user_id, label: `${m.user?.name || m.user_id} (${m.role})` }))}
          />
        </Field>
      </ConfirmDialog>

      {/* Archive Dialog */}
      <ConfirmDialog
        open={open === "archive"}
        onOpenChange={() => setOpen(null)}
        testId="archive-confirm-dialog"
        title="Archive candidate"
        confirmWord="ARCHIVE"
        destructive
        error={error}
        disabled={!form.reason?.trim()}
        confirmLabel="Archive"
        description="Ends any active group assignment. Restoring later will NOT restore group access."
        onConfirm={() => run("archive", { reason: form.reason }, "Candidate archived")}
      >
        <Field label="Reason *">
          <Textarea data-testid="archive-reason-input" value={form.reason || ""} onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setForm({ ...form, reason: e.target.value })} />
        </Field>
      </ConfirmDialog>

      {/* Restore Dialog */}
      <ConfirmDialog
        open={open === "restore"}
        onOpenChange={() => setOpen(null)}
        testId="restore-confirm-dialog"
        title="Restore candidate"
        error={error}
        description="Candidate returns to BENCH with no group. Previous group access is not restored — assign a group explicitly."
        onConfirm={() => run("restore", { reason: "Restored" }, "Candidate restored")}
      />
    </div>
  );
};

