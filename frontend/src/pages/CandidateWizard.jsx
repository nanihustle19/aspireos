import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api, errMsg } from "@/lib/api";
import { PageHeader, Panel, Field, InlineError, NativeSelect } from "@/components/Common";
import { CandidateFields, DuplicateBanner, emptyCandidate, toPayload, useDuplicateCheck, validateBasics } from "@/components/CandidateForm";

const STEPS = ["Identity", "Skills & availability", "Rates", "Group & review"];

export default function CandidateWizard() {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState(emptyCandidate);
  const [errors, setErrors] = useState({});
  const [override, setOverride] = useState("");
  const [error, setError] = useState("");
  const [groups, setGroups] = useState([]);
  const dups = useDuplicateCheck(form);
  const nav = useNavigate();
  useEffect(() => { api.get("/groups").then((r) => setGroups(r.data.filter((g) => g.active))); }, []);

  const next = () => {
    if (step === 0) {
      const e = validateBasics(form);
      setErrors(e);
      if (Object.keys(e).length) return;
      if (dups.exact?.length && !override.trim()) return setError("Resolve the exact duplicate (or provide an override reason) before continuing.");
    }
    setError("");
    setStep(step + 1);
  };
  const submit = async () => {
    try {
      const { data } = await api.post("/candidates", { ...toPayload(form), override_duplicate_reason: override || null });
      toast.success(`Candidate ${data.full_name} created`);
      nav(`/candidates/${data.id}`);
    } catch (err) { setError(errMsg(err)); }
  };

  return (
    <div data-testid="candidate-wizard">
      <PageHeader title="Add candidate" subtitle="Duplicate checks run as you type. Group assignment is transactional." />
      <ol className="mb-5 flex flex-wrap gap-2">
        {STEPS.map((s, i) => (
          <li key={s} data-testid={`wizard-step-${i}`} className={`flex items-center gap-2 rounded border px-3 py-1.5 text-xs font-medium ${i === step ? "border-indigo-500 bg-indigo-50 text-indigo-800" : i < step ? "bg-emerald-50 text-emerald-800 border-emerald-300" : "bg-white text-slate-500"}`}>
            <span className="grid h-5 w-5 place-items-center rounded-full border bg-white text-[10px]">{i < step ? <Check className="h-3 w-3" /> : i + 1}</span>{s}
          </li>
        ))}
      </ol>
      <Panel className="max-w-3xl p-5">
        <form onSubmit={(e) => { e.preventDefault(); step < 3 ? next() : submit(); }} className="space-y-4">
          {step === 0 && <><CandidateFields form={form} set={setForm} errors={errors} fields={["first_name", "last_name", "email", "phone", "location", "linkedin_url"]} />
            <DuplicateBanner dups={dups} override={override} setOverride={setOverride} /></>}
          {step === 1 && <><CandidateFields form={form} set={setForm} fields={["primary_skill", "skills", "experience_years", "visa_status", "work_authorization", "availability_date", "source"]} />
            <Field label="Summary"><Textarea data-testid="candidate-field-summary" value={form.summary} onChange={(e) => setForm({ ...form, summary: e.target.value })} /></Field></>}
          {step === 2 && <><CandidateFields form={form} set={setForm} fields={["pay_rate", "bill_rate", "target_rate"]} />
            <p className="text-xs text-slate-500">Pay rate is visible to Admin/Operations only. Bill and target rates are visible to Admin/Operations, group Leads and Marketing.</p></>}
          {step === 3 && (
            <div className="space-y-4">
              <Field label="Assign to group (optional)" hint="Leave empty to keep the candidate unassigned (NEW). Assignment moves the candidate to BENCH.">
                <NativeSelect testId="wizard-group-select" value={form.group_id} onChange={(v) => setForm({ ...form, group_id: v })} placeholder="— Unassigned —" options={groups.map((g) => ({ value: g.id, label: g.name }))} />
              </Field>
              <dl className="grid grid-cols-2 gap-x-6 gap-y-1 rounded border bg-slate-50 p-3 text-sm" data-testid="wizard-review">
                {[["Name", `${form.first_name} ${form.last_name}`], ["Email", form.email], ["Phone", form.phone], ["Skill", form.primary_skill], ["Skills", form.skills], ["Experience", form.experience_years], ["Pay", form.pay_rate], ["Bill", form.bill_rate], ["Target", form.target_rate]].map(([k, v]) => (
                  <div key={k} className="flex gap-2"><dt className="w-24 text-slate-500">{k}</dt><dd className="font-medium">{v || "—"}</dd></div>))}
              </dl>
              {override && <p className="text-xs text-rose-700">Duplicate override reason will be recorded in audit: “{override}”</p>}
            </div>
          )}
          <InlineError error={error} testId="wizard-error" />
          <div className="flex justify-between border-t pt-4">
            <Button type="button" variant="outline" disabled={step === 0} onClick={() => setStep(step - 1)} data-testid="candidate-wizard-back">Back</Button>
            {step < 3 ? <Button type="submit" data-testid="candidate-wizard-next-step">Next</Button> : <Button type="submit" data-testid="candidate-wizard-submit">Create candidate</Button>}
          </div>
        </form>
      </Panel>
    </div>
  );
}
