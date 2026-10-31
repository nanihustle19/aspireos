import { useEffect, useState } from "react";
import { Bell } from "lucide-react";
import { Link } from "react-router-dom";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { api, fmtDateTime } from "@/lib/api";

export const NotificationBell = () => {
  const [data, setData] = useState({ items: [], unread: 0 });
  const load = () => api.get("/notifications").then((r) => setData(r.data)).catch(() => {});
  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t); }, []);
  const readAll = async () => { await api.post("/notifications/read-all"); load(); };
  return (
    <Popover onOpenChange={(o) => o && load()}>
      <PopoverTrigger asChild>
        <button data-testid="notifications-bell" className="relative rounded p-2 text-slate-600 hover:bg-slate-100">
          <Bell className="h-4 w-4" />
          {data.unread > 0 && <span data-testid="notifications-unread-count" className="absolute -right-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-rose-600 px-1 text-[10px] font-bold text-white">{data.unread}</span>}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-96 p-0" data-testid="notifications-panel">
        <div className="flex items-center justify-between border-b px-3 py-2">
          <span className="text-sm font-semibold">Notifications</span>
          <button data-testid="notifications-read-all" onClick={readAll} className="text-xs text-indigo-700 hover:underline">Mark all read</button>
        </div>
        <div className="max-h-96 overflow-y-auto">
          {data.items.length === 0 && <div className="p-4 text-sm text-slate-500">No notifications</div>}
          {data.items.map((n) => (
            <div key={n.id} className={`border-b px-3 py-2 text-sm ${n.read ? "" : "bg-indigo-50/60"}`}>
              <div className="font-medium">{n.link ? <Link to={n.link} className="hover:underline">{n.title}</Link> : n.title}</div>
              <div className="text-xs text-slate-600">{n.body}</div>
              <div className="mt-0.5 text-[11px] text-slate-400">{fmtDateTime(n.created_at)}</div>
            </div>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
};
