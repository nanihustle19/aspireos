import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, InlineError } from "@/components/Common";
import { api, errMsg } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export const googleLogin = () => {
  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
  const redirectUrl = window.location.origin + "/dashboard";
  window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
};

export const MfaStep = ({ pending, onDone }) => {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    setError("");
    try { const { data } = await api.post("/auth/mfa/verify", { mfa_token: pending.mfa_token, code }); onDone(data); }
    catch (err) { setError(errMsg(err)); }
  };
  return (
    <form onSubmit={submit} className="space-y-4" data-testid="mfa-form">
      <div className="flex items-center gap-2 text-sm font-semibold text-slate-800"><ShieldCheck className="h-4 w-4 text-indigo-600" />Multi-factor authentication required</div>
      {pending.mfa_setup_required && (
        <div className="rounded border bg-slate-50 p-3 text-xs text-slate-700" data-testid="mfa-setup-info">
          Administrators must enroll an authenticator app. Add this secret to Google Authenticator, 1Password or Authy:
          <div data-testid="mfa-setup-secret" className="mt-1 break-all font-mono text-sm font-semibold text-slate-900">{pending.secret}</div>
        </div>
      )}
      <Field label="6-digit authenticator code">
        <Input data-testid="mfa-code-input" autoFocus inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} className="font-mono tracking-[0.3em]" />
      </Field>
      <InlineError error={error} testId="mfa-error" />
      <Button data-testid="mfa-submit-button" type="submit" className="w-full" disabled={code.length !== 6}>Verify & continue</Button>
    </form>
  );
};

export default function Login() {
  const { session, complete } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState(null);

  useEffect(() => {
    const p = sessionStorage.getItem("mfa_pending");
    if (p) { setPending(JSON.parse(p)); sessionStorage.removeItem("mfa_pending"); }
  }, []);

  if (session && !pending) return <Navigate to="/dashboard" replace />;

  const finish = async (data) => { await complete(data); nav("/dashboard", { replace: true }); };
  const submit = async (e) => {
    e.preventDefault();
    setError(""); setBusy(true);
    try {
      const { data } = await api.post("/auth/login", { email, password });
      if (data.mfa_required || data.mfa_setup_required) setPending(data); else await finish(data);
    } catch (err) { setError(errMsg(err)); } finally { setBusy(false); }
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <div className="relative hidden flex-col justify-between overflow-hidden bg-slate-900 p-12 text-white lg:flex">
        <div className="absolute inset-0 opacity-[0.08]" style={{ backgroundImage: "linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)", backgroundSize: "32px 32px" }} />
        <div className="relative flex items-center gap-2"><div className="grid h-9 w-9 place-items-center rounded bg-indigo-500 font-display font-bold">B</div><span className="font-display text-lg font-bold">BenchOS</span></div>
        <div className="relative max-w-lg">
          <h1 className="text-4xl font-extrabold leading-tight tracking-tight xl:text-5xl">Every consultant. Every group. Every move — on the record.</h1>
          <p className="mt-4 text-base text-slate-300">Intake, bench, marketing, submissions, interviews, offers and placements with transactional group control and a complete audit trail.</p>
        </div>
        <div className="relative grid grid-cols-3 gap-4 text-xs text-slate-400">
          {["Invitation-only access", "Role + group authorization", "Immutable audit history"].map((t) => <div key={t} className="border-t border-slate-700 pt-3">{t}</div>)}
        </div>
      </div>
      <div className="flex items-center justify-center bg-white p-6">
        <div className="w-full max-w-sm fade-up">
          <h2 className="text-2xl font-bold tracking-tight">Sign in</h2>
          <p className="mb-6 mt-1 text-sm text-slate-600">Access is by invitation only.</p>
          {pending ? <MfaStep pending={pending} onDone={finish} /> : (
            <>
              <form onSubmit={submit} className="space-y-4" data-testid="login-form">
                <Field label="Work email"><Input data-testid="login-email-input" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></Field>
                <Field label="Password"><Input data-testid="login-password-input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></Field>
                <InlineError error={error} testId="login-error" />
                <Button data-testid="login-submit-button" type="submit" className="w-full" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</Button>
              </form>
              <div className="my-5 flex items-center gap-3 text-xs text-slate-400"><div className="h-px flex-1 bg-slate-200" />or<div className="h-px flex-1 bg-slate-200" /></div>
              <Button data-testid="google-login-button" variant="outline" className="w-full" onClick={googleLogin}>Continue with Google</Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
