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

  useEffect(() => {
    api.get(`/auth/invitations/${token}`).then((r) => { setInv(r.data); setName(r.data.name || ""); }).catch((e) => setError(errMsg(e)));
  }, [token]);

  const finish = async (data) => { await complete(data); nav("/dashboard", { replace: true }); };
  const pwError = pw && pw.length < 8 ? "At least 8 characters" : pw2 && pw !== pw2 ? "Passwords do not match" : "";
  const submit = async (e) => {
    e.preventDefault();
    try {
      const { data } = await api.post("/auth/activate", { token, password: pw, name });
      if (data.mfa_required || data.mfa_setup_required) setPending(data); else await finish(data);
    } catch (err) { setError(errMsg(err)); }
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
              <Field label="Full name"><Input data-testid="activate-name-input" value={name} onChange={(e) => setName(e.target.value)} /></Field>
              <Field label="Password" error={pw && pw.length < 8 ? "At least 8 characters" : ""}><Input data-testid="activate-password-input" type="password" value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
              <Field label="Confirm password" error={pw2 && pw !== pw2 ? "Passwords do not match" : ""}><Input data-testid="activate-password-confirm-input" type="password" value={pw2} onChange={(e) => setPw2(e.target.value)} /></Field>
              <InlineError error={inv && error} testId="activate-submit-error" />
              <Button data-testid="activate-submit-button" type="submit" className="w-full" disabled={!pw || !!pwError || pw !== pw2}>Set password & activate</Button>
            </form>
            <div className="my-4 text-center text-xs text-slate-400">or</div>
            <Button data-testid="activate-google-button" variant="outline" className="w-full" onClick={googleLogin}>Activate with Google ({inv.email})</Button>
          </>
        ))}
      </div>
    </div>
  );
}
