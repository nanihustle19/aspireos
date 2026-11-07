import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Check, KeyRound, Mail } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, InlineError, Loading } from "@/components/Common";
import { useAuth } from "@/context/AuthContext";
import { api, errMsg } from "@/lib/api";

const Shell = ({ title, children, testId, icon: Icon = KeyRound, hideBack = false }) => (
  <main className="grid min-h-screen place-items-center bg-background p-4 sm:p-8">
    <section className="w-full max-w-md rounded-xl border bg-card p-6 shadow-sm sm:p-8" data-testid={testId}>
      <div className="mb-5 grid h-11 w-11 place-items-center rounded-lg bg-accent text-accent-foreground"><Icon aria-hidden="true" className="h-5 w-5" /></div>
      <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
      {children}
      {!hideBack && <Button variant="link" asChild className="mt-5 px-0"><Link to="/login" data-testid="back-to-login-link">Back to sign in</Link></Button>}
    </section>
  </main>
);

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [until, setUntil] = useState(0);
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!until) return;
    const tick = () => {
      const remaining = Math.max(0, Math.ceil((until - Date.now()) / 1000));
      setSeconds(remaining);
      if (!remaining) setUntil(0);
    };
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [until]);

  const submit = async (e) => {
    e.preventDefault();
    if (busy || until) return;
    setBusy(true);
    setError("");
    try {
      await api.post("/auth/forgot-password", { email: email.trim() });
      setSent(true);
      setSeconds(60);
      setUntil(Date.now() + 60000);
    } catch (err) { setError(errMsg(err)); }
    finally { setBusy(false); }
  };

  return (
    <Shell title={sent ? "Check your email" : "Forgot password"} testId="forgot-password-page" icon={Mail}>
      <form onSubmit={submit} className="mt-3 space-y-4">
        {sent ? (
          <div data-testid="forgot-password-sent" role="status" className="space-y-2 text-sm text-slate-700">
            <p>If an account exists for that email, we’ve sent a password reset link.</p>
            <p>Check your spam folder if it doesn’t arrive. The link is valid for one hour.</p>
          </div>
        ) : (
          <>
            <p className="text-sm text-slate-700">Enter your work email to request a secure reset link.</p>
            <Field id="forgot-email" label="Work email"><Input id="forgot-email" data-testid="forgot-email-input" type="email" autoComplete="email" required maxLength={320} value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
          </>
        )}
        <InlineError error={error} testId="forgot-error" />
        <Button data-testid="forgot-submit-button" type="submit" variant={sent ? "outline" : "default"} className="w-full" disabled={busy || !!until}>
          {busy ? "Sending…" : sent ? seconds ? "Resend in " + seconds + "s" : "Resend link" : "Send reset link"}
        </Button>
      </form>
    </Shell>
  );
}

export function ResetPassword() {
  const [params] = useSearchParams();
  return <ResetForm key={params.get("token")} token={params.get("token")} />;
}

function ResetForm({ token }) {
  const { logout } = useAuth();
  const [info, setInfo] = useState(null);
  const [error, setError] = useState("");
  const [checkError, setCheckError] = useState(null);
  const [retry, setRetry] = useState(0);
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [visible, setVisible] = useState(false);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const lengthOk = Array.from(pw).length >= 8;
  const sizeOk = new TextEncoder().encode(pw).length <= 72;
  const matches = !!pw && pw === pw2;
  const strength = !pw ? 0 : !lengthOk || !sizeOk ? 1 : pw.length >= 14 && new Set(pw).size >= 8 ? 3 : 2;

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    api.post("/auth/reset-password/check", { token }, { signal: controller.signal })
      .then((r) => setInfo(r.data))
      .catch((e) => { if (!controller.signal.aborted) setCheckError({ expired: e.response?.status === 422, message: errMsg(e) }); });
    return () => controller.abort();
  }, [token, retry]);

  const submit = async (e) => {
    e.preventDefault();
    if (!lengthOk || !sizeOk || !matches || busy) return;
    setBusy(true);
    setError("");
    try {
      await api.post("/auth/reset-password", { token, password: pw });
      await logout();
      setDone(true);
    } catch (err) {
      if (err.response?.status === 422 && /link/i.test(errMsg(err))) {
        setInfo(null);
        setCheckError({ expired: true });
      } else {
        setError(errMsg(err));
      }
    } finally { setBusy(false); }
  };

  return (
    <Shell title={done ? "Password updated" : "Set a new password"} testId="reset-password-page" hideBack={done}>
      {token && !info && !checkError && <Loading />}
      {(!token || checkError) && <div className="mt-4 space-y-3">
        <InlineError error={!token || checkError.expired ? "This link is missing, expired, or already used. Request a new one to continue." : checkError.message} testId="reset-token-error" />
        {!token || checkError.expired
          ? <Button asChild><Link to="/forgot-password">Request a new link</Link></Button>
          : <Button onClick={() => { setCheckError(null); setRetry(retry + 1); }}>Try again</Button>}
      </div>}
      {info && (done ? (
        <div data-testid="reset-password-success" role="status" className="mt-4 space-y-4">
          <p className="feedback-success rounded-lg p-3 text-sm">Your other sessions were signed out. You can now sign in with your new password.</p>
          <Button asChild className="w-full"><Link to="/login">Go to sign in</Link></Button>
        </div>
      ) : (
        <form onSubmit={submit} className="mt-4 space-y-4">
          <p className="break-words text-sm text-slate-700">Updating the password for <strong>{info.email}</strong>.</p>
          <Field id="new-password" label="New password">
            <Input id="new-password" data-testid="reset-password-input" type={visible ? "text" : "password"} autoComplete="new-password" aria-describedby="password-requirements" value={pw} onChange={(e) => setPw(e.target.value)} />
          </Field>
          <Field id="confirm-password" label="Confirm new password" error={pw2 && !matches ? "Passwords don’t match." : ""}>
            <Input id="confirm-password" data-testid="reset-password-confirm-input" type={visible ? "text" : "password"} autoComplete="new-password" aria-invalid={!!pw2 && !matches} aria-describedby={pw2 && !matches ? "confirm-password-feedback" : undefined} value={pw2} onChange={(e) => setPw2(e.target.value)} />
          </Field>
          <Button type="button" variant="outline" size="sm" aria-pressed={visible} onClick={() => setVisible(!visible)}>{visible ? "Hide passwords" : "Show passwords"}</Button>
          <div id="password-requirements" className="space-y-2 rounded-lg bg-muted p-3 text-xs text-slate-700">
            <div className="flex justify-between"><span>Password strength</span><span>{["Not entered", "Weak", "Fair", "Strong"][strength]}</span></div>
            <meter className="h-2 w-full" min={0} max={3} value={strength} aria-label="Password strength" />
            <ul className="space-y-1">
              {[[lengthOk, "At least 8 characters"], [!!pw && sizeOk, "At most 72 bytes"], [matches, "Both passwords match"]].map(([met, label]) => <li key={label} className="flex items-center gap-2"><span className="sr-only">{met ? "Met" : "Not met"}</span>{met ? <Check aria-hidden="true" className="h-3.5 w-3.5 text-emerald-700" /> : <span aria-hidden="true" className="w-3.5 text-center">○</span>}{label}</li>)}
            </ul>
          </div>
          <InlineError error={error} testId="reset-error" />
          <Button data-testid="reset-submit-button" type="submit" className="w-full" disabled={busy || !lengthOk || !sizeOk || !matches}>{busy ? "Updating…" : "Update password"}</Button>
        </form>
      ))}
    </Shell>
  );
}
