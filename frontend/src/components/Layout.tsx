import React, { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { LayoutDashboard, Users, Armchair, Megaphone, Send, CalendarClock, FileSignature, BadgeCheck, Building2, Briefcase, Store,
  BarChart3, ScrollText, Settings, UsersRound, UserCog, ListTodo, Database, LogOut, Search, PanelLeftClose, PanelLeft, Menu, Building, type LucideIcon } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { NotificationBell } from "@/components/NotificationBell";

type NavFlag = "ops" | "audit" | "platform" | undefined;
type NavItem = [string, string, LucideIcon, string, NavFlag?];
type NavSection = [string, NavItem[]];

const NAV: NavSection[] = [
  ["Work", [["/dashboard", "Dashboard", LayoutDashboard, "dashboard"], ["/candidates", "Candidates", Users, "candidates"], ["/bench", "Bench", Armchair, "bench"],
    ["/marketing", "Marketing Pool", Megaphone, "marketing"], ["/tasks", "Tasks", ListTodo, "tasks"]]],
  ["Pipeline", [["/submissions", "Submissions", Send, "submissions"], ["/interviews", "Interviews", CalendarClock, "interviews"],
    ["/offers", "Offers", FileSignature, "offers"], ["/placements", "Placements", BadgeCheck, "placements"]]],
  ["Directory", [["/jobs", "Jobs", Briefcase, "jobs"], ["/clients", "Clients", Building2, "clients"], ["/vendors", "Vendors", Store, "vendors"]]],
  ["Organization", [["/groups", "Groups", UsersRound, "groups"], ["/users", "Users & Invites", UserCog, "users", "ops"], ["/reports", "Reports", BarChart3, "reports"],
    ["/data", "Imports & Exports", Database, "data"], ["/audit", "Audit Log", ScrollText, "audit-log", "audit"], ["/settings", "Settings", Settings, "settings"]]],
  ["Platform", [["/organizations", "Organizations", Building, "organizations", "platform"]]],
];

export default function Layout() {
  const { user, org, groups, isOps, isAuditor, logout } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [q, setQ] = useState("");
  const nav = useNavigate();
  const allowed = (flag?: NavFlag): boolean => !flag || (flag === "ops" && isOps) || (flag === "audit" && (isOps || isAuditor)) || (flag === "platform" && !!user?.is_platform_admin);
  return (
    <div className="flex h-screen overflow-hidden bg-[#F8FAFC]">
      {mobileOpen && <div className="fixed inset-0 z-30 bg-slate-900/40 backdrop-blur-sm md:hidden" onClick={() => setMobileOpen(false)} data-testid="mobile-nav-scrim" />}
      <aside data-testid="app-sidebar" onClick={(e: React.MouseEvent<HTMLElement>) => (e.target as HTMLElement).closest("a") && setMobileOpen(false)}
        className={`${collapsed ? "md:w-16" : "md:w-60"} w-64 ${mobileOpen ? "fixed inset-y-0 left-0 z-40 flex" : "hidden"} md:static md:flex shrink-0 flex-col border-r bg-white transition-[width] duration-200`}>
        <div className="flex h-14 items-center gap-2 border-b px-4">
          <div className="grid h-8 w-8 shrink-0 place-items-center rounded bg-indigo-600 font-display text-sm font-bold text-white">B</div>
          {!collapsed && <div className="min-w-0"><div className="font-display text-sm font-bold leading-tight">BenchOS</div>
            <div data-testid="consultancy-tenant-select" className="truncate text-[11px] text-slate-500">{org?.name}</div></div>}
        </div>
        <nav className="flex-1 overflow-y-auto px-2 py-3">
          {NAV.filter(([, items]) => items.some((i) => allowed(i[4]))).map(([section, items]) => (
            <div key={section} className="mb-4">
              {!collapsed && <div className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-widest text-slate-400">{section}</div>}
              {items.filter((i) => allowed(i[4])).map(([to, label, Icon, id]) => (
                <NavLink key={to} to={to} data-testid={`nav-${id}-link`} title={label}
                  className={({ isActive }: { isActive: boolean }) => `flex items-center gap-2.5 rounded px-2 py-1.5 text-sm transition-colors ${isActive ? "bg-indigo-50 font-semibold text-indigo-700" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"}`}>
                  <Icon className="h-4 w-4 shrink-0" />{!collapsed && label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <button data-testid="sidebar-collapse-toggle" onClick={() => setCollapsed(!collapsed)} className="flex items-center gap-2 border-t px-4 py-3 text-xs text-slate-500 hover:text-slate-900">
          {collapsed ? <PanelLeft className="h-4 w-4" /> : <><PanelLeftClose className="h-4 w-4" />Collapse</>}
        </button>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b bg-white px-3 md:px-5">
          <button data-testid="mobile-nav-toggle" onClick={() => setMobileOpen(true)} className="rounded p-2 text-slate-600 hover:bg-slate-100 md:hidden" aria-label="Open navigation"><Menu className="h-5 w-5" /></button>
          <form onSubmit={(e: React.FormEvent) => { e.preventDefault(); nav(`/candidates?q=${encodeURIComponent(q)}`); }} className="relative w-full max-w-md">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
            <input data-testid="global-search-input" value={q} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setQ(e.target.value)} placeholder="Search candidates by name, email, skill…"
              className="h-9 w-full rounded-md border bg-slate-50 pl-8 pr-3 text-sm focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          </form>
          <div className="ml-auto flex items-center gap-3">
            {groups.length > 0 && <div data-testid="active-group-badge" className="hidden items-center gap-1 lg:flex">
              {groups.map((g) => <span key={g.id} className="rounded border bg-slate-50 px-2 py-0.5 text-[11px] text-slate-700">{g.name} · <b>{g.role}</b></span>)}
            </div>}
            <NotificationBell />
            <div className="hidden text-right leading-tight sm:block">
              <div data-testid="current-user-name" className="text-sm font-semibold">{user?.name}</div>
              <div data-testid="current-user-role" className="text-[11px] uppercase tracking-wide text-slate-500">{user?.role}</div>
            </div>
            <button data-testid="logout-button" onClick={async () => { await logout(); nav("/login"); }} title="Sign out" className="rounded p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900">
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto p-3 md:p-5 lg:p-7"><Outlet /></main>
      </div>
    </div>
  );
}

