import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { toast } from "sonner";
import { Building, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, fmtDate } from "@/lib/api";
import { Loading, PageHeader, Panel } from "@/components/Common";
import { StatusBadge } from "@/components/StatusBadge";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { FormDialog } from "@/pages/Pipeline";
import { useAuth } from "@/context/AuthContext";

const slugify = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40);

export default function Organizations() {
  const { user } = useAuth();
  const [items, setItems] = useState(null);
  const [open, setOpen] = useState(false);
  const [created, setCreated] = useState(null);
  const load = () => api.get("/platform/organizations").then((r) => setItems(r.data));
  useEffect(() => { if (user?.is_platform_admin) load(); }, [user]);
  if (!user?.is_platform_admin) return <Navigate to="/dashboard" replace />;
  return (
    <div data-testid="organizations-page">
      <PageHeader title="Client organizations" subtitle="Each consultancy is a fully isolated tenant with its own admin, groups, candidates and settings.">
        <Button size="sm" onClick={() => setOpen(true)} data-testid="create-organization-button"><Plus className="mr-1 h-4 w-4" />New organization</Button>
      </PageHeader>
      <Panel>{!items ? <Loading /> : (
        <table className="dense-table w-full" data-testid="organizations-table"><thead><tr><th>Organization</th><th>Slug</th><th>Plan</th><th>Primary admin</th><th>Users</th><th>Candidates</th><th>Created</th></tr></thead>
          <tbody>{items.map((o) => (
            <tr key={o.id} data-testid="organization-row"><td className="font-medium"><Building className="mr-1.5 inline h-4 w-4 text-slate-400" />{o.name}</td><td className="font-mono text-xs">{o.slug}</td><td className="text-xs">{o.plan}</td>
              <td className="text-xs">{o.primary_admin ? <span className="inline-flex items-center gap-2">{o.primary_admin.email}<StatusBadge status={o.primary_admin.status} /></span> : "—"}</td>
              <td className="font-mono">{o.user_count}</td><td className="font-mono">{o.candidate_count}</td><td className="text-xs">{fmtDate(o.created_at)}</td></tr>))}</tbody></table>
      )}</Panel>
      <FormDialog open={open} onOpenChange={setOpen} title="New client organization" testId="create-org-dialog"
        fields={[{ key: "name", label: "Consultancy name", required: true }, { key: "slug", label: "Slug (unique, lowercase)", hint: "Leave empty to derive from name" },
          { key: "plan", label: "Plan", options: ["Starter", "Professional", "Enterprise"], default: "Professional" },
          { key: "admin_name", label: "Admin full name", required: true }, { key: "admin_email", label: "Admin email", type: "email", required: true },
          { key: "default_groups", label: "Starter groups (comma separated)", default: "Core Bench" }]}
        onSubmit={async (f) => {
          const { data } = await api.post("/platform/organizations", { ...f, slug: f.slug || slugify(f.name), default_groups: String(f.default_groups || "").split(",").map((s) => s.trim()).filter(Boolean) });
          toast.success(`${data.name} created`); setCreated(data); load();
        }} />
      <ConfirmDialog open={!!created} onOpenChange={() => setCreated(null)} title="Organization ready" testId="org-created-dialog" confirmLabel="Copy activation link"
        description={`Send this link to ${created?.admin_email}. They set a password (or use Google) and enroll MFA. Email delivery is MOCKED.`}
        onConfirm={async () => { await navigator.clipboard?.writeText(`${window.location.origin}${created.activation_path}`).catch(() => {}); toast.success("Link copied"); setCreated(null); }}>
        <code data-testid="org-admin-activation-link" className="block break-all rounded bg-slate-100 p-2 text-xs">{created && `${window.location.origin}${created.activation_path}`}</code>
      </ConfirmDialog>
    </div>
  );
}
