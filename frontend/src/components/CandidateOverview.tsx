import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api, errMsg, fmtDate, fmtDateTime, money } from "@/lib/api";
import { Field, InlineError, Panel } from "@/components/Common";
import { CandidateFields } from "@/components/CandidateForm";
import type { Candidate, TimelineEvent } from "@/types";

const FULL = [
  "first_name", "last_name", "email", "phone", "location", "linkedin_url",
  "primary_skill", "skills", "experience_years", "visa_status", "work_authorization",
  "availability_date", "source", "pay_rate", "bill_rate", "target_rate",
];

const MKT = ["location", "skills", "availability_date", "target_rate"];

interface AssignmentHistoryItem {
  id: string;
  group_id: string;
  group_name: string;
  active: boolean;
  started_at: string;
  ended_at?: string | null;
  reason?: string | null;
  end_reason?: string | null;
}

interface CandidateDetailProps {
  candidate: Candidate;
  assignment_history: AssignmentHistoryItem[];
  permissions: {
    edit_level: "full" | "marketing" | null;
    can_edit: boolean;
    allowed_transitions: string[];
    can_assign: boolean;
    can_transfer: boolean;
    can_unassign: boolean;
    can_archive: boolean;
    can_restore: boolean;
    can_set_owner: boolean;
  };
}

interface OverviewTabProps {
  detail: CandidateDetailProps;
  reload: () => void;
  isOps: boolean;
}

export const OverviewTab: React.FC<OverviewTabProps> = ({ detail, reload, isOps }) => {
  const c = detail.candidate;
  const lvl = detail.permissions.edit_level;
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<Record<string, any>>({});
  const [error, setError] = useState("");

  const fields = lvl === "full" ? FULL : MKT;

  const start = () => {
    setForm({
      ...c,
      skills: (c.skills || []).join(", "),
      summary: c.summary || "",
    });
    setError("");
    setEditing(true);
  };

  const save = async () => {
    const body: Record<string, any> = { version: c.version };
    [...fields, "summary"].filter((k) => isOps || k !== "pay_rate").forEach((k) => {
      let v = form[k];
      if (k === "skills") {
        v = String(v || "").split(",").map((s) => s.trim()).filter(Boolean);
      } else if (["experience_years", "pay_rate", "bill_rate", "target_rate"].includes(k)) {
        v = v === "" || v === null ? null : Number(v);
      }
      const orig = k === "skills" ? c.skills || [] : (c as any)[k];
      if (JSON.stringify(v ?? null) !== JSON.stringify(orig ?? null)) {
        body[k] = v;
      }
    });

    if (Object.keys(body).length === 1) return setEditing(false);

    try {
      await api.patch(`/candidates/${c.id}`, body);
      toast.success("Candidate updated");
      setEditing(false);
      reload();
    } catch (e) {
      setError(errMsg(e));
    }
  };

  const rows: [string, any][] = [
    ["Email", c.email],
    ["Phone", c.phone],
    ["Location", c.location],
    ["Primary skill", c.primary_skill],
    ["Skills", (c.skills || []).join(", ")],
    ["Experience", c.experience_years != null ? `${c.experience_years} yrs` : null],
    ["Visa", c.visa_status],
    ["Work auth", c.work_authorization],
    ["Available", fmtDate(c.availability_date)],
    ["Source", c.source],
    ["Bench since", c.bench_since ? fmtDate(c.bench_since) : null],
    ["Created", fmtDateTime(c.created_at)],
  ];

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Panel
        title="Profile"
        className="lg:col-span-2"
        testId="candidate-profile-panel"
        actions={
          detail.permissions.can_edit && !editing && (
            <Button size="sm" variant="outline" onClick={start} data-testid="edit-candidate-button">
              {lvl === "marketing" ? "Edit (marketing fields)" : "Edit"}
            </Button>
          )
        }
      >
        {editing ? (
          <form className="space-y-3 p-4" onSubmit={(e) => { e.preventDefault(); save(); }}>
            <CandidateFields form={form} set={setForm} fields={fields} showPay={isOps} />
            <Field label="Summary">
              <Textarea
                data-testid="candidate-field-summary"
                value={form.summary || ""}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setForm({ ...form, summary: e.target.value })}
              />
            </Field>
            <InlineError error={error} testId="candidate-edit-error" />
            <div className="flex gap-2">
              <Button type="submit" data-testid="save-candidate-button">Save changes</Button>
              <Button type="button" variant="outline" onClick={() => setEditing(false)}>Cancel</Button>
              <span className="ml-auto self-center font-mono text-[11px] text-slate-400">v{c.version}</span>
            </div>
          </form>
        ) : (
          <dl className="grid gap-x-6 gap-y-2 p-4 text-sm sm:grid-cols-2">
            {rows.map(([k, v]) => (
              <div key={k} className="flex gap-3">
                <dt className="w-28 shrink-0 text-slate-500">{k}</dt>
                <dd className="font-medium text-slate-900">{v || "—"}</dd>
              </div>
            ))}
            {c.summary && (
              <div className="sm:col-span-2">
                <dt className="text-slate-500">Summary</dt>
                <dd className="mt-1 text-slate-800">{c.summary}</dd>
              </div>
            )}
          </dl>
        )}
      </Panel>

      <div className="space-y-4">
        <Panel title="Rates" testId="candidate-rates-panel">
          <dl className="space-y-2 p-4 text-sm">
            {[
              ["Pay rate", "pay_rate"],
              ["Bill rate", "bill_rate"],
              ["Target rate", "target_rate"],
            ].map(([l, k]) => (
              <div key={k} className="flex items-center justify-between">
                <dt className="text-slate-500">{l}</dt>
                <dd data-testid={`rate-${k}`} className="font-mono font-semibold">
                  {(c._redacted || []).includes(k) ? (
                    <span className="inline-flex items-center gap-1 text-slate-400">
                      <Lock className="h-3 w-3" />Restricted
                    </span>
                  ) : (
                    money((c as any)[k])
                  )}
                </dd>
              </div>
            ))}
          </dl>
        </Panel>

        <Panel title="Group assignment history" testId="assignment-history-panel">
          <ul className="divide-y text-sm">
            {detail.assignment_history.length === 0 && (
              <li className="p-4 text-slate-500">Never assigned</li>
            )}
            {detail.assignment_history.map((h) => (
              <li key={h.id} className="px-4 py-2">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{h.group_name}</span>
                  {h.active && (
                    <span className="rounded bg-emerald-100 px-1.5 text-[10px] font-bold text-emerald-800">ACTIVE</span>
                  )}
                </div>
                <div className="text-[11px] text-slate-500">
                  {fmtDate(h.started_at)} → {h.ended_at ? fmtDate(h.ended_at) : "now"}
                  {h.end_reason ? ` · ${h.end_reason}` : ""}
                </div>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
};

export const TimelineTab: React.FC<{ cid: string }> = ({ cid }) => {
  const [items, setItems] = useState<TimelineEvent[]>([]);

  useEffect(() => {
    api.get<TimelineEvent[]>(`/candidates/${cid}/timeline`).then((r) => setItems(r.data));
  }, [cid]);

  return (
    <Panel testId="timeline-panel">
      <ol className="relative ml-6 border-l py-3">
        {items.map((t) => (
          <li key={t.id} className="mb-3 ml-4" data-testid="timeline-item">
            <span className="absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full border-2 border-white bg-indigo-500" />
            <div className="flex flex-wrap items-baseline gap-2">
              <span className="font-mono text-[11px] font-semibold text-indigo-700">{t.event}</span>
              <span className="text-sm text-slate-800">{t.detail}</span>
            </div>
            <div className="text-[11px] text-slate-500">{t.actor_name} · {fmtDateTime(t.created_at)}</div>
          </li>
        ))}
      </ol>
    </Panel>
  );
};

