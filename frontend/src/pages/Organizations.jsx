import { useCallback, useEffect, useRef, useState } from "react";
import { Navigate } from "react-router-dom";
import { toast } from "sonner";
import { Building2, Check, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api, errMsg, fmtDate } from "@/lib/api";
import { Field, InlineError, PageHeader, Panel } from "@/components/Common";
import { StatusBadge } from "@/components/StatusBadge";
import { useAuth } from "@/context/AuthContext";

const steps = ["Organization", "Administrator", "Review"];
const sizes = ["1–10", "11–50", "51–200", "201+"];
const initial = {
  name: "", slug: "", industry: "", size: "", logo_data: "", plan: "Professional",
  admin_name: "", admin_email: "", default_groups: "Core Bench", temporary_password: "",
};
const deliveryCopy = {
  PENDING: "The invitation email is queued.",
  SENT: "The invitation email was sent.",
  FAILED: "The organization is ready, but the invitation email failed. Retry or share the link directly.",
  NOT_CONFIGURED: "Email delivery is unavailable on this server. Share the activation link directly.",
};
const slugify = (name) => name.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 41).replace(/^-|-$/g, "");
const slugValid = (slug) => /^[a-z0-9][a-z0-9-]{1,40}$/.test(slug);
const emailValid = (email) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim());
const passwordValid = (value) => Array.from(value).length >= 12 && new TextEncoder().encode(value).length <= 72;
const selectClass = "h-9 w-full rounded-md border border-input bg-white px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

function OrganizationWizard({ onClose, onOpenOrganization, items, reload, trigger }) {
  const [form, setForm] = useState(initial);
  const [step, setStep] = useState(0);
  const [manualSlug, setManualSlug] = useState(false);
  const [availability, setAvailability] = useState(null);
  const [checkAgain, setCheckAgain] = useState(0);
  const [method, setMethod] = useState("email");
  const [logoBusy, setLogoBusy] = useState(false);
  const [logoError, setLogoError] = useState("");
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState("");
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState(null);
  const [retrying, setRetrying] = useState(false);
  const heading = useRef(null);
  const currentAvailability = availability?.slug === form.slug ? availability.status : "";
  const delivery = items?.find((row) => row.id === created?.id)?.invite_status ?? created?.invite_status;
  const groups = form.default_groups.split(",").map((group) => group.trim()).filter(Boolean);
  const groupsInvalid = groups.length > 10 || groups.some((group) => group.length > 255);
  const orgValid = !!form.name.trim() && !!form.industry.trim() && !!form.size && currentAvailability === "available" && !logoBusy && !logoError && !groupsInvalid;
  const adminValid = !!form.admin_name.trim() && emailValid(form.admin_email) && conflict !== "admin_email" && (method === "email" || passwordValid(form.temporary_password));

  useEffect(() => {
    const slug = form.slug;
    if (!slugValid(slug)) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api.get("/platform/organizations/slug-availability", { params: { slug }, signal: controller.signal })
        .then(({ data }) => setAvailability({ slug, status: data.available ? "available" : "taken" }))
        .catch(() => { if (!controller.signal.aborted) setAvailability({ slug, status: "error" }); });
    }, 300);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [form.slug, checkAgain]);

  useEffect(() => {
    heading.current?.focus();
  }, [step, created]);
  useEffect(() => {
    if (conflict) document.getElementById("organization-" + conflict)?.focus();
  }, [conflict]);

  useEffect(() => {
    if (!created || delivery !== "PENDING") return;
    const timer = setInterval(reload, 4000);
    return () => clearInterval(timer);
  }, [created, delivery, reload]);

  const set = (key, value) => {
    setForm((current) => ({
      ...current, [key]: value,
      ...(key === "name" && !manualSlug ? { slug: slugify(value) } : {}),
    }));
    if (key === conflict) setConflict("");
  };

  const input = (key, label, { hint, invalid, ...props } = {}) => {
    const id = "organization-" + key;
    return <Field id={id} label={label} hint={hint} error={invalid}>
      <Input {...props} id={id} aria-invalid={!!invalid} aria-describedby={hint || invalid ? id + "-feedback" : undefined}
        value={form[key]} onChange={(e) => set(key, e.target.value)} />
    </Field>;
  };

  const uploadLogo = (event) => {
    const file = event.target.files?.[0];
    set("logo_data", "");
    setLogoError("");
    if (!file) return;
    if (!["image/png", "image/jpeg"].includes(file.type) || file.size > 131072) {
      setLogoError("Choose a PNG or JPEG up to 128 KB.");
      return;
    }
    setLogoBusy(true);
    const reader = new FileReader();
    reader.onload = () => { set("logo_data", String(reader.result)); setLogoBusy(false); };
    reader.onerror = () => { setLogoError("Couldn’t read this file. Choose it again."); setLogoBusy(false); };
    reader.readAsDataURL(file);
  };

  const submit = async (event) => {
    event.preventDefault();
    if (busy || created || (step === 0 && !orgValid) || (step === 1 && !adminValid)) return;
    setError("");
    if (step < 2) { setStep(step + 1); return; }
    if (!orgValid || !adminValid) return;
    setBusy(true);
    try {
      const { data } = await api.post("/platform/organizations", {
        ...form, logo_data: form.logo_data || null,
        temporary_password: method === "temporary" ? form.temporary_password : null,
        default_groups: groups,
      });
      setCreated(data);
      set("temporary_password", "");
      reload();
      toast.success(data.name + " created");
    } catch (err) {
      const message = errMsg(err);
      if (err.response?.status === 409 && /slug|email/i.test(message)) {
        const slugTaken = /slug/i.test(message);
        setConflict(slugTaken ? "slug" : "admin_email");
        if (slugTaken) setAvailability({ slug: form.slug, status: "taken" });
        setStep(slugTaken ? 0 : 1);
      }
      setError(message);
    } finally { setBusy(false); }
  };

  const copyLink = async () => {
    try { await navigator.clipboard.writeText(window.location.origin + created.activation_path); toast.success("Activation link copied"); }
    catch { setError("Select and copy the activation link below."); }
  };
  const retryInvite = async () => {
    setRetrying(true);
    setError("");
    try {
      const { data } = await api.post("/platform/organizations/" + created.id + "/retry-invite");
      setCreated({ ...created, invite_status: data.invite_status });
      await reload();
    } catch (err) { setError(errMsg(err)); }
    finally { setRetrying(false); }
  };

  const startOver = () => {
    setForm(initial);
    setManualSlug(false);
    setAvailability(null);
    setMethod("email");
    setLogoError("");
    setError("");
    setConflict("");
    setCreated(null);
    setStep(0);
  };

  return <Dialog open onOpenChange={(open) => { if (!open && !busy) onClose(); }}>
    <DialogContent data-testid={created ? "org-created-dialog" : "create-org-dialog"} onCloseAutoFocus={(event) => { event.preventDefault(); trigger.current?.focus(); }} className="max-h-[90dvh] w-[calc(100%-1.5rem)] max-w-xl overflow-y-auto rounded-xl p-5 sm:p-7">
      <DialogHeader className="pr-6 text-left">
        <DialogTitle ref={heading} tabIndex={-1} className="text-xl">{created ? "Organization ready" : "New client organization"}</DialogTitle>
        <DialogDescription>{created ? created.name + " is ready for its administrator." : "Set up a workspace and choose how its first administrator will get access."}</DialogDescription>
      </DialogHeader>
      {created ? <div className="space-y-4">
        <p role="status" className={"rounded-lg p-3 text-sm " + (delivery === "FAILED" || delivery === "NOT_CONFIGURED" ? "feedback-warning" : "feedback-success")}>{method === "temporary"
          ? "Share the activation link and temporary password separately. The administrator will choose a new password and set up their authenticator."
          : deliveryCopy[delivery]}</p>
        <Field id="organization-activation-link" label="Activation link"><Input id="organization-activation-link" data-testid="org-admin-activation-link" readOnly value={window.location.origin + created.activation_path} onFocus={(e) => e.target.select()} /></Field>
        <InlineError error={error} />
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={copyLink}>Copy link</Button>
          {delivery === "FAILED" && <Button variant="outline" disabled={retrying} onClick={retryInvite}>{retrying ? "Retrying…" : "Retry email"}</Button>}
          <Button variant="outline" onClick={startOver}>Create another</Button>
          <Button onClick={() => onOpenOrganization(created.slug)}>Open organization</Button>
        </div>
      </div> : <>
        <ol aria-label="Setup progress" className="grid grid-cols-3 gap-2">
          {steps.map((label, index) => <li key={label} aria-current={step === index ? "step" : undefined}
            className={"flex flex-col gap-1 rounded-lg px-2 py-2 text-xs font-semibold sm:flex-row sm:items-center sm:gap-2 " + (step === index ? "bg-accent text-accent-foreground" : "bg-muted text-slate-700")}>
            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-white" aria-hidden="true">{index < step ? <Check className="h-3.5 w-3.5" /> : index + 1}</span>{label}
          </li>)}
        </ol>
        <form onSubmit={submit} className="space-y-4">
          {step === 0 && <>
            {input("name", "Consultancy name", { required: true, maxLength: 255, autoComplete: "organization" })}
            <Field id="organization-slug" label="Workspace slug" hint="2–41 lowercase letters, numbers, or hyphens."
              error={currentAvailability === "taken" ? "This slug is already in use." : ""}>
              <Input id="organization-slug" required maxLength={41} aria-describedby="organization-slug-feedback slug-status"
                aria-invalid={currentAvailability === "taken" || (!!form.slug && !slugValid(form.slug))}
                value={form.slug} onChange={(e) => { setManualSlug(true); set("slug", e.target.value.toLowerCase()); }} />
            </Field>
            <div id="slug-status" role="status" className="text-xs text-slate-700">{slugValid(form.slug) && (
              currentAvailability === "available" ? "Slug available." : currentAvailability === "taken" ? "" :
              currentAvailability === "error" ? <Button variant="link" type="button" className="h-auto p-0" onClick={() => { setAvailability(null); setCheckAgain(checkAgain + 1); }}>Couldn’t check availability. Try again.</Button> : "Checking availability…"
            )}</div>
            <div className="grid gap-4 sm:grid-cols-2">
              {input("industry", "Industry", { required: true, maxLength: 100 })}
              <Field id="organization-size" label="Company size"><select id="organization-size" required className={selectClass} value={form.size} onChange={(e) => set("size", e.target.value)}><option value="">Select size</option>{sizes.map((size) => <option key={size}>{size}</option>)}</select></Field>
            </div>
            <details className="rounded-lg border px-3 py-2 text-sm">
              <summary className="cursor-pointer rounded font-medium text-slate-700 focus-visible:outline focus-visible:outline-ring">Plan and starter groups</summary>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <Field id="organization-plan" label="Plan"><select id="organization-plan" className={selectClass} value={form.plan} onChange={(e) => set("plan", e.target.value)}>{["Starter", "Professional", "Enterprise"].map((plan) => <option key={plan}>{plan}</option>)}</select></Field>
                {input("default_groups", "Starter groups", { hint: "Separate group names with commas.", invalid: groupsInvalid ? "Enter up to 10 groups, each with at most 255 characters." : "" })}
              </div>
            </details>
            <Field id="organization-logo" label="Logo (optional)" hint="PNG or JPEG, up to 128 KB." error={logoError}>
              <Input id="organization-logo" type="file" accept="image/png,image/jpeg" aria-describedby="organization-logo-feedback" disabled={logoBusy} onChange={uploadLogo} />
            </Field>
            {(form.logo_data || logoError) && <div className="flex items-center gap-2">
              {form.logo_data && <img src={form.logo_data} alt="Logo preview" className="h-10 w-10 rounded border object-contain" />}
              <Button type="button" variant="ghost" size="sm" onClick={() => { set("logo_data", ""); setLogoError(""); document.getElementById("organization-logo").value = ""; }}>Remove logo</Button>
            </div>}
          </>}
          {step === 1 && <>
            {input("admin_name", "Administrator full name", { required: true, maxLength: 255, autoComplete: "name" })}
            {input("admin_email", "Administrator work email", { type: "email", required: true, maxLength: 320, autoComplete: "email", invalid: conflict === "admin_email" ? "This email already belongs to a user." : "" })}
            <fieldset className="space-y-2">
              <legend className="mb-1 text-sm font-medium text-slate-700">How should the administrator get access?</legend>
              {[["email", "Send an invitation email"], ["temporary", "Set a temporary password"]].map(([value, label]) => <label key={value} className="flex items-center gap-2 rounded-lg border p-3 text-sm">
                <input name="access-method" type="radio" value={value} checked={method === value} onChange={() => setMethod(value)} className="accent-indigo-700 focus-visible:outline focus-visible:outline-ring" />{label}
              </label>)}
            </fieldset>
            {method === "temporary" && input("temporary_password", "Temporary password", { type: "password", autoComplete: "new-password", required: true, hint: "Use at least 12 characters. Share it separately from the activation link." })}
          </>}
          {step === 2 && <div className="divide-y rounded-lg border">
            <div className="space-y-2 p-4">
              <div className="flex items-center justify-between"><h3 className="font-semibold">Organization</h3><Button type="button" variant="ghost" size="sm" onClick={() => setStep(0)}>Edit organization</Button></div>
              <p className="break-words text-sm">{form.name} · {form.slug}</p><p className="break-words text-sm text-slate-700">{form.industry} · {form.size} employees · {form.plan}</p>
              {form.default_groups && <p className="break-words text-sm text-slate-700">Starter groups: {form.default_groups}</p>}
              {form.logo_data && <img src={form.logo_data} alt="Organization logo preview" className="h-10 w-10 rounded border object-contain" />}
            </div>
            <div className="space-y-2 p-4">
              <div className="flex items-center justify-between"><h3 className="font-semibold">Administrator</h3><Button type="button" variant="ghost" size="sm" onClick={() => setStep(1)}>Edit administrator</Button></div>
              <p className="break-words text-sm">{form.admin_name} · {form.admin_email}</p><p className="text-sm text-slate-700">{method === "email" ? "Email invitation" : "Temporary password"}</p>
            </div>
          </div>}
          <InlineError error={error} />
          <div className="flex justify-between gap-2 border-t pt-4">
            <Button variant="outline" type="button" disabled={busy} onClick={() => { setError(""); if (step) setStep(step - 1); else onClose(); }}>{step ? "Back" : "Cancel"}</Button>
            <Button type="submit" disabled={busy || (step !== 1 && !orgValid) || (step !== 0 && !adminValid)}>{busy ? "Creating…" : step === 2 ? "Create organization" : "Continue"}</Button>
          </div>
        </form>
      </>}
    </DialogContent>
  </Dialog>;
}

export default function Organizations() {
  const { user } = useAuth();
  const isPlatformAdmin = !!user?.is_platform_admin;
  const [items, setItems] = useState(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("newest");
  const [retrying, setRetrying] = useState(null);
  const [selectedSlug, setSelectedSlug] = useState(null);
  const trigger = useRef(null);

  const reload = useCallback(async () => {
    setError("");
    try { setItems((await api.get("/platform/organizations")).data); }
    catch (err) { setError(errMsg(err)); }
  }, []);
  useEffect(() => { if (isPlatformAdmin) reload(); }, [isPlatformAdmin, reload]);
  if (!isPlatformAdmin) return <Navigate to="/dashboard" replace />;

  const rows = (items || []).filter((row) => [row.name, row.slug, row.primary_admin?.email].some((value) => value?.toLowerCase().includes(query.trim().toLowerCase())))
    .sort((a, b) => sort === "name" ? a.name.localeCompare(b.name) : b.created_at.localeCompare(a.created_at));
  const selected = items?.find((row) => row.slug === selectedSlug);

  const retryInvite = async (row) => {
    setRetrying(row.id);
    try {
      await api.post("/platform/organizations/" + row.id + "/retry-invite");
      toast.success("Invitation queued for retry");
      await reload();
    } catch (err) { toast.error(errMsg(err)); }
    finally { setRetrying(null); }
  };

  return <div data-testid="organizations-page">
    <PageHeader title="Client organizations" subtitle="Manage consultancy workspaces and track administrator access.">
      <Button ref={trigger} onClick={() => setOpen(true)} data-testid="create-organization-button"><Plus />New organization</Button>
    </PageHeader>
    <Panel>
      <div className="grid gap-3 border-b p-4 sm:grid-cols-[minmax(0,1fr)_12rem]">
        <Field id="organizations-search" label="Find an organization"><Input id="organizations-search" type="search" placeholder="Name, slug, or admin email" value={query} onChange={(e) => setQuery(e.target.value)} /></Field>
        <Field id="organizations-sort" label="Sort by"><select id="organizations-sort" className={selectClass} value={sort} onChange={(e) => setSort(e.target.value)}><option value="newest">Newest first</option><option value="name">Organization name</option></select></Field>
      </div>
      {error && <div className="space-y-2 p-4"><InlineError error={error} /><Button variant="outline" onClick={reload}>Try again</Button></div>}
      {!items && !error && <div role="status" aria-label="Loading organizations" className="space-y-3 p-4">{[1, 2, 3].map((row) => <div key={row} className="h-11 animate-pulse rounded bg-muted" />)}</div>}
      {items && !rows.length && <div className="space-y-3 px-4 py-10 text-center">
        <Building2 aria-hidden="true" className="mx-auto h-7 w-7 text-slate-500" />
        <p className="font-semibold">{query ? "No matching organizations" : "No organizations yet"}</p>
        <Button variant="outline" onClick={() => query ? setQuery("") : setOpen(true)}>{query ? "Clear search" : "New organization"}</Button>
      </div>}
      {rows.length > 0 && <div className="overflow-x-auto"><table className="dense-table w-full" data-testid="organizations-table">
        <thead><tr><th>Organization</th><th className="hidden md:table-cell">Plan</th><th className="hidden md:table-cell">Primary administrator</th><th>Status</th><th className="hidden lg:table-cell">Users</th><th className="hidden lg:table-cell">Candidates</th><th className="hidden lg:table-cell">Created</th></tr></thead>
        <tbody>{rows.map((row) => <tr key={row.id} data-testid="organization-row">
          <td><div className="flex items-center gap-2">
            {row.logo_data ? <img src={row.logo_data} alt="" className="h-8 w-8 rounded border object-contain" /> : <Building2 aria-hidden="true" className="h-5 w-5 text-slate-500" />}
            <div className="min-w-0"><Button type="button" variant="link" className="h-auto whitespace-normal break-words p-0 text-left font-semibold" onClick={() => setSelectedSlug(row.slug)}>{row.name}</Button><div className="break-all text-xs text-slate-600">{row.slug}{row.industry && " · " + row.industry}</div></div>
          </div></td>
          <td className="hidden md:table-cell">{row.plan}</td><td className="hidden break-all md:table-cell">{row.primary_admin?.email || "—"}</td>
          <td>{row.primary_admin ? <StatusBadge status={row.primary_admin.status} /> : "No administrator"}
            {row.invite_status === "FAILED" && <div><Button size="sm" variant="link" className="px-0" disabled={retrying === row.id} onClick={() => retryInvite(row)}>{retrying === row.id ? "Retrying…" : "Retry email"}</Button></div>}
            {row.invite_status === "NOT_CONFIGURED" && <p className="text-xs text-slate-600">Email unavailable</p>}
            {row.invite_status === "PENDING" && <p className="text-xs text-slate-600">Email queued</p>}
          </td>
          <td className="hidden lg:table-cell">{row.user_count}</td><td className="hidden lg:table-cell">{row.candidate_count}</td><td className="hidden lg:table-cell">{fmtDate(row.created_at)}</td>
        </tr>)}</tbody>
      </table></div>}
    </Panel>
    {open && <OrganizationWizard items={items} reload={reload} trigger={trigger} onClose={() => setOpen(false)}
      onOpenOrganization={(slug) => { setQuery(slug); setOpen(false); setSelectedSlug(slug); }} />}
    <Dialog open={!!selected} onOpenChange={(isOpen) => { if (!isOpen) setSelectedSlug(null); }}>
      {selected && <DialogContent className="max-h-[90dvh] w-[calc(100%-1.5rem)] overflow-y-auto rounded-xl">
        <DialogHeader className="pr-6 text-left">
          <DialogTitle className="break-words">{selected.name}</DialogTitle>
          <DialogDescription>{selected.slug}</DialogDescription>
        </DialogHeader>
        <dl className="grid gap-x-4 gap-y-3 text-sm sm:grid-cols-2">
          {[
            ["Primary administrator", selected.primary_admin?.email],
            ["Administrator status", selected.primary_admin?.status],
            ["Industry", selected.industry], ["Company size", selected.size],
            ["Plan", selected.plan], ["Created", fmtDate(selected.created_at)],
            ["Users", selected.user_count], ["Candidates", selected.candidate_count],
          ].map(([label, value]) => <div key={label}><dt className="font-medium text-slate-700">{label}</dt><dd className="break-words">{value ?? "—"}</dd></div>)}
        </dl>
        {selected.invite_status && <p role="status" className="text-sm text-slate-700">{deliveryCopy[selected.invite_status]}</p>}
        {selected.invite_status === "FAILED" && <Button variant="outline" disabled={retrying === selected.id} onClick={() => retryInvite(selected)}>Retry email</Button>}
      </DialogContent>}
    </Dialog>
  </div>;
}
