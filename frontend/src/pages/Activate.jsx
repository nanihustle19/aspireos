import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, InlineError, Loading } from "@/components/Common";
import { api, errMsg } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { googleLogin, MfaStep } from "@/pages/Login";

export default function Activate() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const nav = useNavigate();
  const { complete } = useAuth();
  const [inv, setInv] = useState(null);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [pending, setPending] = useState(null);
  const [temporary, setTemporary] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get(`/auth/invitations/${token}`).then((r) => { setInv(r.data); setName(r.data.name || ""); }).catch((e) => setError(errMsg(e)));
  }, [token]);

  const finish = async (data) => { await complete(data); nav("/dashboard", { replace: true }); };
  const pwError = pw && pw.length < 8 ? "At least 8 characters" : pw2 && pw !== pw2 ? "Passwords do not match" : "";
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { data } = await api.post("/auth/activate", { token, password: pw, name, temporary_password: temporary || null });
      if (data.mfa_required || data.mfa_setup_required) setPending(data); else await finish(data);
    } catch (err) { setError(errMsg(err)); } finally { setBusy(false); }
  };

  return (
    <div className="grid min-h-screen place-items-center bg-slate-50 p-6">
      <div className="w-full max-w-md rounded-md border bg-white p-8 fade-up" data-testid="activate-page">
        <div className="mb-1 font-display text-2xl font-bold">Activate your account</div>
        {!inv && !error && <Loading />}
        {error && !inv && <InlineError error={error} testId="activate-error" />}
        {inv && (pending ? <MfaStep pending={pending} onDone={finish} /> : (
          <>
            <p className="mb-5 text-sm text-slate-600">You were invited to <b>{inv.organization}</b> as <b>{inv.role}</b> ({inv.email}).</p>
            <form onSubmit={submit} className="space-y-4">
              <Field id="activate-name" label="Full name"><Input id="activate-name" data-testid="activate-name-input" value={name} onChange={(e) => setName(e.target.value)} /></Field>
              {inv.temporary_password_required && <Field id="activate-temporary" label="Temporary password"><Input id="activate-temporary" type="password" autoComplete="current-password" required value={temporary} onChange={(e) => setTemporary(e.target.value)} /></Field>}
              <Field id="activate-password" label="New password" error={pw && pw.length < 8 ? "At least 8 characters" : ""}><Input id="activate-password" data-testid="activate-password-input" type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
              <Field id="activate-confirm" label="Confirm password" error={pw2 && pw !== pw2 ? "Passwords do not match" : ""}><Input id="activate-confirm" data-testid="activate-password-confirm-input" type="password" autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} /></Field>
              <InlineError error={inv && error} testId="activate-submit-error" />
              <Button data-testid="activate-submit-button" type="submit" className="w-full" disabled={busy || !pw || !!pwError || pw !== pw2 || (inv.temporary_password_required && !temporary)}>{busy ? "Activating…" : "Set password & activate"}</Button>
            </form>
            {!inv.temporary_password_required && <><div className="my-4 text-center text-xs text-slate-500">or</div>
            <Button data-testid="activate-google-button" variant="outline" className="w-full" onClick={googleLogin}>Activate with Google</Button></>}
          </>
        ))}
      </div>
    </div>
  );
}
