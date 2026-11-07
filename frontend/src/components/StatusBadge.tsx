import React from "react";

const STYLES: Record<string, string> = {
  NEW: "bg-slate-100 text-slate-800 border-slate-300",
  BENCH: "bg-amber-100 text-amber-900 border-amber-300",
  ON_HOLD: "bg-orange-100 text-orange-900 border-orange-300",
  MARKETING: "bg-indigo-100 text-indigo-900 border-indigo-300",
  SUBMITTED: "bg-violet-100 text-violet-900 border-violet-300",
  INTERVIEWING: "bg-sky-100 text-sky-900 border-sky-300",
  OFFERED: "bg-lime-100 text-lime-900 border-lime-300",
  PLACED: "bg-emerald-100 text-emerald-900 border-emerald-300",
  ARCHIVED: "bg-zinc-200 text-zinc-700 border-zinc-300",
  PASSED: "bg-emerald-100 text-emerald-900 border-emerald-300",
  PENDING: "bg-amber-100 text-amber-900 border-amber-300",
  FAILED: "bg-rose-100 text-rose-900 border-rose-300",
  ACTIVE: "bg-emerald-100 text-emerald-900 border-emerald-300",
  INVITED: "bg-sky-100 text-sky-900 border-sky-300",
  DEACTIVATED: "bg-rose-100 text-rose-900 border-rose-300",
  EXTENDED: "bg-lime-100 text-lime-900 border-lime-300",
  ACCEPTED: "bg-emerald-100 text-emerald-900 border-emerald-300",
  DECLINED: "bg-rose-100 text-rose-900 border-rose-300",
  REJECTED: "bg-rose-100 text-rose-900 border-rose-300",
  WITHDRAWN: "bg-zinc-200 text-zinc-700 border-zinc-300",
  SCHEDULED: "bg-sky-100 text-sky-900 border-sky-300",
  COMPLETED: "bg-emerald-100 text-emerald-900 border-emerald-300",
  CANCELLED: "bg-zinc-200 text-zinc-700 border-zinc-300",
  RUNNING: "bg-sky-100 text-sky-900 border-sky-300",
  ENDED: "bg-zinc-200 text-zinc-700 border-zinc-300",
  OPEN: "bg-sky-100 text-sky-900 border-sky-300",
  DONE: "bg-emerald-100 text-emerald-900 border-emerald-300",
};

interface StatusBadgeProps {
  status: string;
  testId?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, testId }) => (
  <span data-testid={testId || `status-badge-${String(status).toLowerCase()}`}
    className={`inline-flex items-center gap-1.5 rounded border px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide whitespace-nowrap ${STYLES[status] || "bg-slate-100 text-slate-700 border-slate-300"}`}>
    <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />
    {String(status || "—").replace(/_/g, " ")}
  </span>
);

