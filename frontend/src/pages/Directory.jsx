import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, fmtDate, money } from "@/lib/api";
import { Empty, Loading, PageHeader, Panel } from "@/components/Common";
import { StatusBadge } from "@/components/StatusBadge";
import { FormDialog } from "@/pages/Pipeline";
import { useAuth } from "@/context/AuthContext";

const CONF = {
  vendors: { title: "Vendors", cols: [["name", "Name"], ["tier", "Tier"], ["contact_name", "Contact"], ["contact_email", "Email"]],
    fields: [{ key: "name", label: "Name", required: true }, { key: "tier", label: "Tier", options: ["Tier 1", "Tier 2", "Tier 3"] }, { key: "contact_name", label: "Contact name" }, { key: "contact_email", label: "Contact email", type: "email" }, { key: "phone", label: "Phone" }] },
  clients: { title: "Clients", cols: [["name", "Name"], ["industry", "Industry"], ["location", "Location"], ["contact_name", "Contact"]],
    fields: [{ key: "name", label: "Name", required: true }, { key: "industry", label: "Industry" }, { key: "location", label: "Location" }, { key: "contact_name", label: "Contact name" }, { key: "contact_email", label: "Contact email", type: "email" }] },
  jobs: { title: "Jobs", cols: [["title", "Title"], ["client_name", "Client"], ["vendor_name", "Vendor"], ["location", "Location"], ["work_mode", "Mode"], ["rate", "Bill rate", (v) => money(v)], ["skills", "Skills", (v) => (v || []).join(", ")]] },
};

export default function Directory({ entity }) {
  const { isAuditor } = useAuth();
  const [items, setItems] = useState(null);
  const [open, setOpen] = useState(false);
  const [lookups, setLookups] = useState({ clients: [], vendors: [] });
  const conf = CONF[entity];
  const load = () => api.get(`/${entity}`).then((r) => setItems(r.data));
  useEffect(() => {
    setItems(null); load();
    if (entity === "jobs") Promise.all([api.get("/clients"), api.get("/vendors")]).then(([c, v]) => setLookups({ clients: c.data, vendors: v.data }));
  }, [entity]); // eslint-disable-line
  const fields = entity === "jobs" ? [{ key: "title", label: "Title", required: true },
    { key: "client_id", label: "Client", options: lookups.clients.map((c) => ({ value: c.id, label: c.name })) },
    { key: "vendor_id", label: "Vendor", options: lookups.vendors.map((c) => ({ value: c.id, label: c.name })) },
    { key: "location", label: "Location" }, { key: "work_mode", label: "Work mode", options: ["Remote", "Hybrid", "Onsite"] }, { key: "rate", label: "Bill rate ($/hr)", type: "number" }, { key: "skills", label: "Skills (comma separated)" }] : conf.fields;
  const save = async (f) => {
    const body = { ...f };
    if (entity === "jobs") { body.skills = String(f.skills || "").split(",").map((s) => s.trim()).filter(Boolean); body.rate = f.rate ? Number(f.rate) : null; }
    await api.post(`/${entity}`, body); toast.success(`${conf.title.slice(0, -1)} created`); load();
  };
  const toggle = async (it) => {
    const next = entity === "jobs" ? (it.status === "OPEN" ? "CLOSED" : "OPEN") : (it.status === "ACTIVE" ? "INACTIVE" : "ACTIVE");
    await api.patch(`/${entity}/${it.id}`, { status: next, version: it.version }); load();
  };
  return (
    <div data-testid={`${entity}-page`}>
      <PageHeader title={conf.title}>{!isAuditor && <Button size="sm" onClick={() => setOpen(true)} data-testid={`add-${entity}-button`}><Plus className="mr-1 h-4 w-4" />Add</Button>}</PageHeader>
      <Panel>
        {!items ? <Loading /> : items.length === 0 ? <Empty /> : (
          <table className="dense-table w-full" data-testid={`${entity}-table`}>
            <thead><tr>{conf.cols.map(([, l]) => <th key={l}>{l}</th>)}<th>Status</th><th>Created</th><th></th></tr></thead>
            <tbody>{items.map((it) => (
              <tr key={it.id} data-testid={`${entity}-row`}>{conf.cols.map(([k, , fmt]) => <td key={k} className={k === "name" || k === "title" ? "font-medium" : "text-sm"}>{fmt ? fmt(it[k]) : it[k] || "—"}</td>)}
                <td><StatusBadge status={it.status} /></td><td className="text-xs">{fmtDate(it.created_at)}</td>
                <td>{!isAuditor && <Button size="sm" variant="ghost" onClick={() => toggle(it)} data-testid={`toggle-status-${it.id}`}>{["OPEN", "ACTIVE"].includes(it.status) ? (entity === "jobs" ? "Close" : "Deactivate") : "Reopen"}</Button>}</td></tr>))}</tbody>
          </table>
        )}
      </Panel>
      <FormDialog open={open} onOpenChange={setOpen} title={`New ${conf.title.slice(0, -1).toLowerCase()}`} testId={`${entity}-dialog`} fields={fields} onSubmit={save} />
    </div>
  );
}
