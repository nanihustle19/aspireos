import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { api, errMsg } from "@/lib/api";
import { InlineError } from "@/components/Common";
import { CandidateFields, DuplicateBanner, emptyCandidate, toPayload, useDuplicateCheck, validateBasics } from "@/components/CandidateForm";

export const QuickCreateDialog = ({ open, onOpenChange, onCreated }) => {
  const [form, setForm] = useState(emptyCandidate);
  const [errors, setErrors] = useState({});
  const [override, setOverride] = useState("");
  const [error, setError] = useState("");
  const dups = useDuplicateCheck(form);
  const nav = useNavigate();
  const blocked = dups.exact?.length > 0 && !override.trim();
  const save = async () => {
    const e = validateBasics(form);
    setErrors(e);
    if (Object.keys(e).length) return;
    try {
      const { data } = await api.post("/candidates", { ...toPayload(form), override_duplicate_reason: override || null });
      toast.success(`Candidate ${data.full_name} created`);
      onOpenChange(false); setForm(emptyCandidate); setOverride("");
      onCreated ? onCreated(data) : nav(`/candidates/${data.id}`);
    } catch (err) { setError(errMsg(err)); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl" data-testid="quick-create-dialog">
        <DialogHeader><DialogTitle className="font-display">Quick create candidate</DialogTitle></DialogHeader>
        <form onSubmit={(e) => { e.preventDefault(); save(); }} className="space-y-3">
          <CandidateFields form={form} set={setForm} errors={errors} fields={["first_name", "last_name", "email", "phone", "primary_skill", "location"]} />
          <DuplicateBanner dups={dups} override={override} setOverride={setOverride} />
          <InlineError error={error} testId="quick-create-error" />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" data-testid="quick-create-submit" disabled={blocked}>Create</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};
