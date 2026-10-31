import axios from "axios";

export const BACKEND = process.env.REACT_APP_BACKEND_URL;
export const api = axios.create({ baseURL: `${BACKEND}/api`, withCredentials: true });

export const tokens = {
  get: () => localStorage.getItem("access_token"),
  set: (a, r) => { localStorage.setItem("access_token", a); if (r) localStorage.setItem("refresh_token", r); },
  clear: () => { localStorage.removeItem("access_token"); localStorage.removeItem("refresh_token"); },
};

api.interceptors.request.use((cfg) => {
  const t = tokens.get();
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});

let refreshing = null;
api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const cfg = err.config;
    if (err.response?.status === 401 && !cfg._retry && !cfg.url.includes("/auth/")) {
      cfg._retry = true;
      try {
        refreshing = refreshing || api.post("/auth/refresh", {}, { headers: { "X-Refresh-Token": localStorage.getItem("refresh_token") || "" } });
        const { data } = await refreshing;
        refreshing = null;
        tokens.set(data.access_token, data.refresh_token);
        return api(cfg);
      } catch (e) {
        refreshing = null;
        tokens.clear();
        if (!window.location.pathname.startsWith("/login")) window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);

export function errMsg(e) {
  const d = e?.response?.data?.detail;
  if (d == null) return e?.message || "Something went wrong. Please try again.";
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x?.msg || JSON.stringify(x)).join(" ");
  if (d.message) return d.message;
  if (d.msg) return d.msg;
  return String(d);
}

export const errCode = (e) => e?.response?.data?.detail?.code;

export const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "—");
export const fmtDateTime = (iso, tz) =>
  iso ? new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: tz || undefined, timeZoneName: tz ? "short" : undefined }) : "—";
export const money = (v, redacted) => (redacted ? "•••" : v === null || v === undefined ? "—" : `$${Number(v).toFixed(0)}/hr`);
export const rate = (o, k) => money(o[k], (o._redacted || []).includes(k));
export const daysSince = (iso) => (iso ? Math.floor((Date.now() - new Date(iso).getTime()) / 86400000) : null);
