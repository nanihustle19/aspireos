import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, errMsg } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export default function AuthCallback() {
  const done = useRef(false);
  const nav = useNavigate();
  const { complete } = useAuth();
  const [error, setError] = useState("");
  useEffect(() => {
    if (done.current) return;
    done.current = true;
    const sid = new URLSearchParams(window.location.hash.slice(1)).get("session_id");
    window.history.replaceState(null, "", window.location.pathname);
    api.post("/auth/google/session", { session_id: sid }).then(async ({ data }) => {
      if (data.mfa_required || data.mfa_setup_required) {
        sessionStorage.setItem("mfa_pending", JSON.stringify(data));
        nav("/login", { replace: true });
      } else {
        await complete(data);
        nav("/dashboard", { replace: true });
      }
    }).catch((e) => setError(errMsg(e)));
  }, [complete, nav]);
  if (!error) return null;
  return (
    <div className="grid min-h-screen place-items-center bg-slate-50 p-6">
      <div data-testid="google-auth-error" className="max-w-md rounded-md border border-rose-300 bg-white p-6 text-sm">
        <div className="mb-2 font-display text-lg font-bold">Sign-in failed</div>
        <p className="text-rose-800">{error}</p>
        <a href="/login" className="mt-4 inline-block text-indigo-700 hover:underline">Back to sign in</a>
      </div>
    </div>
  );
}
