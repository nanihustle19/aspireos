import React from "react";
import { Loader2 } from "lucide-react";
import { Label } from "@/components/ui/label";

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  children?: React.ReactNode;
  testId?: string;
}

export const PageHeader: React.FC<PageHeaderProps> = ({ title, subtitle, children, testId }) => (
  <div className="mb-5 flex flex-wrap items-end justify-between gap-3 fade-up">
    <div>
      <h1 data-testid={testId || "page-title"} className="text-2xl lg:text-3xl font-bold tracking-tight text-slate-900">{title}</h1>
      {subtitle && <p className="mt-1 text-sm text-slate-600">{subtitle}</p>}
    </div>
    <div className="flex flex-wrap items-center gap-2">{children}</div>
  </div>
);

interface PanelProps {
  title?: string;
  actions?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
  testId?: string;
}

export const Panel: React.FC<PanelProps> = ({ title, actions, children, className = "", testId }) => (
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

export const Loading: React.FC = () => (
  <div data-testid="loading-indicator" className="flex items-center gap-2 p-6 text-sm text-slate-500"><Loader2 className="h-4 w-4 animate-spin" />Loading…</div>
);

interface EmptyProps {
  text?: string;
  testId?: string;
}

export const Empty: React.FC<EmptyProps> = ({ text = "Nothing here yet.", testId = "empty-state" }) => (
  <div data-testid={testId} className="p-8 text-center text-sm text-slate-500">{text}</div>
);

interface FieldProps {
  label: string;
  error?: string;
  children?: React.ReactNode;
  hint?: string;
  id?: string;
}

export const Field: React.FC<FieldProps> = ({ id, label, error, children, hint }) => (
  <div className="space-y-1">
    <Label htmlFor={id} className="text-sm font-medium text-slate-700">{label}</Label>
    {children}
    {hint && !error && <p id={id && `${id}-feedback`} className="text-xs text-slate-600">{hint}</p>}
    {error && <p id={id && `${id}-feedback`} className="text-xs font-medium text-rose-700" role="alert">{error}</p>}
  </div>
);

interface InlineErrorProps {
  error?: string;
  testId?: string;
}

export const InlineError: React.FC<InlineErrorProps> = ({ error, testId = "inline-error" }) =>
  error ? <div data-testid={testId} role="alert" className="rounded border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-800">{error}</div> : null;

interface SelectOption {
  value: string;
  label: string;
}

interface NativeSelectProps {
  value: string | null | undefined;
  onChange: (value: string) => void;
  options: (string | SelectOption)[];
  placeholder?: string;
  testId?: string;
  className?: string;
}

export const NativeSelect: React.FC<NativeSelectProps> = ({ value, onChange, options, placeholder, testId, className = "" }) => (
  <select data-testid={testId} value={value ?? ""} onChange={(e: React.ChangeEvent<HTMLSelectElement>) => onChange(e.target.value)}
    className={`h-9 rounded-md border border-input bg-white px-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 ${className}`}>
    {placeholder !== undefined && <option value="">{placeholder}</option>}
    {options.map((o) => typeof o === "string" ? <option key={o} value={o}>{o.replace(/_/g, " ")}</option> : <option key={o.value} value={o.value}>{o.label}</option>)}
  </select>
);

