import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertOctagon, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/Common";
import { StatusBadge } from "@/components/StatusBadge";

export const emptyCandidate = { first_name: "", last_name: "", email: "", phone: "", location: "", primary_skill: "", skills: "", experience_years: "",
  visa_status: "", work_authorization: "", availability_date: "", source: "", linkedin_url: "", pay_rate: "", bill_rate: "", target_rate: "", summary: "", group_id: "" };

export const toPayload = (f) => {
  const num = (v) => (v === "" || v === null || v === undefined ? null : Number(v));
  return { ...f, skills: String(f.skills || "").split(",").map((s) => s.trim()).filter(Boolean), experience_years: num(f.experience_years),
    pay_rate: num(f.pay_rate), bill_rate: num(f.bill_rate), target_rate: num(f.target_rate), group_id: f.group_id || null,
    email: f.email || null, phone: f.phone || null, availability_date: f.availability_date || null };
};

export function useDuplicateCheck(form, excludeId) {
  const [dups, setDups] = useState({ exact: [], possible: [], can_override: false });
  useEffect(() => {
    const t = setTimeout(() => {
      if (!form.email && !form.phone && !(form.first_name && form.last_name)) return setDups({ exact: [], possible: [] });
      api.post("/candidates/duplicate-check", { email: form.email, phone: form.phone, first_name: form.first_name, last_name: form.last_name, exclude_id: excludeId })
        .then((r) => setDups(r.data)).catch(() => {});
    }, 400);
    return () => clearTimeout(t);
  }, [form.email, form.phone, form.first_name, form.last_name, excludeId]);
  return dups;
}

export const DuplicateBanner = ({ dups, override, setOverride }) => {
  if (!dups.exact?.length && !dups.possible?.length) return null;
  const hard = dups.exact?.length > 0;
  return (
    <div data-testid="candidate-duplicate-warning-banner" role="alert" className={`rounded-md border px-3 py-2.5 text-sm ${hard ? "border-rose-300 bg-rose-50 text-rose-900" : "border-amber-300 bg-amber-50 text-amber-900"}`}>
      <div className="flex items-center gap-2 font-semibold">{hard ? <AlertOctagon className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
        {hard ? "Exact duplicate found — creation blocked" : "Possible duplicate (same name)"}</div>
      <ul className="mt-1 space-y-0.5">
        {[...(dups.exact || []), ...(dups.possible || [])].map((c) => (
          <li key={c.id} className="flex items-center gap-2 text-xs">
            <Link to={`/candidates/${c.id}`} className="font-medium underline" target="_blank">{c.first_name} {c.last_name}</Link>
            <span className="opacity-75">{c.email} · match on <b>{c.match}</b></span><StatusBadge status={c.status} />
          </li>
        ))}
      </ul>
      {hard && (dups.can_override ? (
        <div className="mt-2"><label className="text-xs font-semibold">Override reason (Admin/Operations only)</label>
          <Input data-testid="duplicate-override-reason-input" value={override} onChange={(e) => setOverride(e.target.value)} placeholder="e.g. Same family phone number, verified different person" className="mt-1 bg-white" /></div>
      ) : <div className="mt-1 text-xs">Contact Operations to override.</div>)}
    </div>
  );
};

export const CandidateFields = ({ form, set, fields, errors = {}, showPay = true }) => {
  const F = { first_name: "First name *", last_name: "Last name *", email: "Email", phone: "Phone", location: "Location", primary_skill: "Primary skill",
    skills: "Skills (comma separated)", experience_years: "Experience (years)", visa_status: "Visa status", work_authorization: "Work authorization",
    availability_date: "Available from", source: "Source", linkedin_url: "LinkedIn URL", pay_rate: "Pay rate ($/hr)", bill_rate: "Bill rate ($/hr)", target_rate: "Target marketing rate ($/hr)" };
  const types = { experience_years: "number", pay_rate: "number", bill_rate: "number", target_rate: "number", availability_date: "date", email: "email" };
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {fields.filter((k) => showPay || k !== "pay_rate").map((k) => (
        <Field key={k} label={F[k]} error={errors[k]}>
          <Input data-testid={`candidate-field-${k}`} type={types[k] || "text"} value={form[k] ?? ""} onChange={(e) => set({ ...form, [k]: e.target.value })} />
        </Field>
      ))}
    </div>
  );
};

export const validateBasics = (f) => {
  const e = {};
  if (!f.first_name.trim()) e.first_name = "Required";
  if (!f.last_name.trim()) e.last_name = "Required";
  if (f.email && !/^\S+@\S+\.\S+$/.test(f.email)) e.email = "Invalid email";
  if (f.phone && f.phone.replace(/\D/g, "").length < 7) e.phone = "Invalid phone";
  return e;
};
