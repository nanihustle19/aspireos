import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, InlineError, Loading } from "@/components/Common";
import { api, errMsg } from "@/lib/api";

const Shell = ({ title, children, testId }) => (
  <div className="grid min-h-screen place-items-center bg-slate-50 p-6">
    <div className="w-full max-w-md rounded-md border bg-white p-8 fade-up" data-testid={testId}>
      <div className="mb-1 font-display text-2xl font-bold">{title}</div>
      {children}
      <Link to="/login" data-testid="back-to-login-link" className="mt-5 inline-block text-sm text-indigo-700 hover:underline">Back to sign in</Link>
    </div>
  </div>
);

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError("");
    try { const { data } = await api.post("/auth/forgot-password", { email }); setSent(data.message); }
    catch (err) { setError(errMsg(err)); } finally { setBusy(false); }
  };
  return (
    <Shell title="Forgot password" testId="forgot-password-page">
      {sent ? (
        <div data-testid="forgot-password-sent" className="mt-4 flex gap-2 rounded border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-900"><CheckCircle2 className="h-4 w-4 shrink-0" />{sent}</div>
      ) : (
        <form onSubmit={submit} className="mt-4 space-y-4">
          <p className="text-sm text-slate-600">Enter your work email and we’ll send a one-hour reset link.</p>
          <Field label="Work email"><Input data-testid="forgot-email-input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
          <InlineError error={error} testId="forgot-error" />
          <Button data-testid="forgot-submit-button" type="submit" className="w-full" disabled={busy}>{busy ? "Sending…" : "Send reset link"}</Button>
          <p className="text-xs text-slate-500">Lost your authenticator app? Ask another administrator to reset it from Users &amp; Invites.</p>
        </form>
      )}
    </Shell>
  );
}

export function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const [info, setInfo] = useState(null);
  const [error, setError] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [done, setDone] = useState(false);
  useEffect(() => { api.get(`/auth/reset-password/${token}`).then((r) => setInfo(r.data)).catch((e) => setError(errMsg(e))); }, [token]);
  const submit = async (e) => {
    e.preventDefault();
    try { await api.post("/auth/reset-password", { token, password: pw }); setDone(true); } catch (err) { setError(errMsg(err)); }
  };
  return (
    <Shell title="Choose a new password" testId="reset-password-page">
      {!info && !error && <Loading />}
      {error && !info && <div className="mt-4"><InlineError error={error} testId="reset-token-error" /><Link to="/forgot-password" className="mt-3 inline-block text-sm text-indigo-700 hover:underline">Request a new link</Link></div>}
      {info && (done ? (
        <div data-testid="reset-password-success" className="mt-4 rounded border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-900">Password updated. All existing sessions were signed out — sign in with your new password.</div>
      ) : (
        <form onSubmit={submit} className="mt-4 space-y-4">
          <p className="text-sm text-slate-600">Resetting password for <b>{info.email}</b>.</p>
          <Field label="New password" error={pw && pw.length < 8 ? "At least 8 characters" : ""}><Input data-testid="reset-password-input" type="password" value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
          <Field label="Confirm new password" error={pw2 && pw !== pw2 ? "Passwords do not match" : ""}><Input data-testid="reset-password-confirm-input" type="password" value={pw2} onChange={(e) => setPw2(e.target.value)} /></Field>
          <InlineError error={error} testId="reset-error" />
          <Button data-testid="reset-submit-button" type="submit" className="w-full" disabled={pw.length < 8 || pw !== pw2}>Update password</Button>
        </form>
      ))}
    </Shell>
  );
}
