import { Loader2 } from "lucide-react";
import { Label } from "@/components/ui/label";

export const PageHeader = ({ title, subtitle, children, testId }) => (
  <div className="mb-5 flex flex-wrap items-end justify-between gap-3 fade-up">
    <div>
      <h1 data-testid={testId || "page-title"} className="text-2xl lg:text-3xl font-bold tracking-tight text-slate-900">{title}</h1>
      {subtitle && <p className="mt-1 text-sm text-slate-600">{subtitle}</p>}
    </div>
    <div className="flex flex-wrap items-center gap-2">{children}</div>
  </div>
);

export const Panel = ({ title, actions, children, className = "", testId }) => (
  <section data-testid={testId} className={`rounded-md border bg-white ${className}`}>
    {(title || actions) && (
      <div className="flex items-center justify-between border-b px-4 py-2.5">
        <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
        <div className="flex items-center gap-2">{actions}</div>
      </div>
    )}
    {children}
  </section>
);

export const Loading = () => (
  <div data-testid="loading-indicator" className="flex items-center gap-2 p-6 text-sm text-slate-500"><Loader2 className="h-4 w-4 animate-spin" />Loading…</div>
);

export const Empty = ({ text = "Nothing here yet.", testId = "empty-state" }) => (
  <div data-testid={testId} className="p-8 text-center text-sm text-slate-500">{text}</div>
);

export const Field = ({ label, error, children, hint }) => (
  <div className="space-y-1">
    <Label className="text-xs font-medium text-slate-700">{label}</Label>
    {children}
    {hint && !error && <p className="text-[11px] text-slate-500">{hint}</p>}
    {error && <p className="text-xs font-medium text-rose-700" role="alert">{error}</p>}
  </div>
);

export const InlineError = ({ error, testId = "inline-error" }) =>
  error ? <div data-testid={testId} role="alert" className="rounded border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-800">{error}</div> : null;

export const NativeSelect = ({ value, onChange, options, placeholder, testId, className = "" }) => (
  <select data-testid={testId} value={value ?? ""} onChange={(e) => onChange(e.target.value)}
    className={`h-9 rounded-md border border-input bg-white px-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 ${className}`}>
    {placeholder !== undefined && <option value="">{placeholder}</option>}
    {options.map((o) => typeof o === "string" ? <option key={o} value={o}>{o.replace(/_/g, " ")}</option> : <option key={o.value} value={o.value}>{o.label}</option>)}
  </select>
);
