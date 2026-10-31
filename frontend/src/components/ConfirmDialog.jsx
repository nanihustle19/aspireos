import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AlertTriangle } from "lucide-react";

export const ConfirmDialog = ({ open, onOpenChange, title, description, confirmWord, confirmLabel = "Confirm", destructive, onConfirm, children, testId = "confirm-dialog", disabled, error }) => {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (!open) setTyped(""); }, [open]);
  const ok = (!confirmWord || typed.trim().toUpperCase() === confirmWord) && !disabled;
  const run = async () => { setBusy(true); try { await onConfirm(); } finally { setBusy(false); } };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={testId} className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-display">
            {destructive && <AlertTriangle className="h-5 w-5 text-rose-600" />}{title}
          </DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        <div className="space-y-3">
          {children}
          {confirmWord && (
            <div>
              <label className="text-xs font-medium text-slate-600">Type <span className="font-mono font-semibold text-slate-900">{confirmWord}</span> to confirm</label>
              <Input data-testid={`${testId}-typed-input`} value={typed} onChange={(e) => setTyped(e.target.value)} className="mt-1 font-mono" />
            </div>
          )}
          {error && <div data-testid={`${testId}-error`} className="rounded border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-800">{error}</div>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid={`${testId}-cancel`}>Cancel</Button>
          <Button data-testid={`${testId}-confirm`} disabled={!ok || busy} onClick={run}
            className={destructive ? "bg-rose-600 hover:bg-rose-700 text-white" : ""}>{busy ? "Working…" : confirmLabel}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
