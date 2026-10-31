import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { Loading, PageHeader } from "@/components/Common";
import { FormDialog } from "@/pages/Pipeline";
import { useAuth } from "@/context/AuthContext";

export default function Groups() {
  const { isOps } = useAuth();
  const [items, setItems] = useState(null);
  const [open, setOpen] = useState(false);
  const load = () => api.get("/groups").then((r) => setItems(r.data));
  useEffect(() => { load(); }, []);
  return (
    <div data-testid="groups-page">
      <PageHeader title="Groups" subtitle="Each candidate belongs to at most one active group. Standard users only see candidates of groups they belong to.">
        {isOps && <Button size="sm" onClick={() => setOpen(true)} data-testid="add-group-button"><Plus className="mr-1 h-4 w-4" />New group</Button>}
      </PageHeader>
      {!items ? <Loading /> : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {items.map((g) => (
            <Link key={g.id} to={`/groups/${g.id}`} data-testid={`group-card-${g.id}`} className="group rounded-md border bg-white p-4 transition-[border-color,transform] hover:-translate-y-0.5 hover:border-indigo-400">
              <div className="flex items-center justify-between"><h3 className="font-display text-lg font-semibold group-hover:text-indigo-700">{g.name}</h3>
                {!g.active && <span className="rounded bg-zinc-200 px-1.5 text-[10px] font-bold">INACTIVE</span>}{g.my_role && <span className="rounded bg-indigo-100 px-1.5 text-[10px] font-bold text-indigo-800">{g.my_role}</span>}</div>
              <p className="mt-1 text-sm text-slate-600">{g.description}</p>
              <div className="mt-3 flex gap-6 text-xs text-slate-500"><span><b className="font-display text-xl text-slate-900">{g.candidate_count}</b> candidates</span><span><b className="font-display text-xl text-slate-900">{g.member_count}</b> members</span></div>
            </Link>
          ))}
        </div>
      )}
      <FormDialog open={open} onOpenChange={setOpen} title="New group" testId="group-dialog" fields={[{ key: "name", label: "Name", required: true }, { key: "description", label: "Description" }]}
        onSubmit={async (f) => { await api.post("/groups", f); toast.success("Group created"); load(); }} />
    </div>
  );
}
