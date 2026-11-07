import React, { useEffect, useId, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AlertTriangle } from "lucide-react";

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  confirmWord?: string;
  confirmLabel?: string;
  destructive?: boolean;
  onConfirm: () => void | Promise<void>;
  children?: React.ReactNode;
  testId?: string;
  disabled?: boolean;
  error?: string;
}

export const ConfirmDialog: React.FC<ConfirmDialogProps> = ({ open, onOpenChange, title, description, confirmWord, confirmLabel = "Confirm", destructive, onConfirm, children, testId = "confirm-dialog", disabled, error }) => {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const confirmationId = useId();
  useEffect(() => { if (!open) setTyped(""); }, [open]);
  const ok = (!confirmWord || typed.trim().toUpperCase() === confirmWord) && !disabled;
  const run = async () => { setBusy(true); try { await onConfirm(); } finally { setBusy(false); } };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={testId} className="max-h-[90dvh] w-[calc(100%-1.5rem)] overflow-y-auto rounded-xl sm:max-w-lg">
        <DialogHeader className="pr-6 text-left">
          <DialogTitle className="flex items-center gap-2 font-display">
            {destructive && <AlertTriangle aria-hidden="true" className="h-5 w-5 shrink-0 text-rose-700" />}{title}
          </DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        <div className="space-y-3">
          {children}
          {confirmWord && (
            <div>
              <label htmlFor={confirmationId} className="text-xs font-medium text-slate-600">Type <span className="font-mono font-semibold text-slate-900">{confirmWord}</span> to confirm</label>
              <Input id={confirmationId} data-testid={`${testId}-typed-input`} value={typed} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTyped(e.target.value)} className="mt-1 font-mono" />
            </div>
          )}
          {error && <div role="alert" data-testid={`${testId}-error`} className="rounded border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-800">{error}</div>}
        </div>
        <DialogFooter className="gap-2 sm:space-x-0">
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid={`${testId}-cancel`}>Cancel</Button>
          <Button data-testid={`${testId}-confirm`} disabled={!ok || busy} onClick={run}
            variant={destructive ? "destructive" : "default"}>{busy ? "Working…" : confirmLabel}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

