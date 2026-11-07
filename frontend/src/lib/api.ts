import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";

export const BACKEND = process.env.REACT_APP_BACKEND_URL?.replace(/\/$/, "") ||
  (process.env.NODE_ENV === "development" ? "http://localhost:8000" : "");
export const api = axios.create({ baseURL: `${BACKEND}/api`, withCredentials: true });

export const tokens = {
  get: (): string | null => localStorage.getItem("access_token"),
  set: (a: string, r?: string): void => {
    localStorage.setItem("access_token", a);
    if (r) localStorage.setItem("refresh_token", r);
  },
  clear: (): void => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
  },
};

api.interceptors.request.use((cfg: InternalAxiosRequestConfig) => {
  const t = tokens.get();
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});

let refreshing: Promise<unknown> | null = null;
api.interceptors.response.use(
  (r) => r,
  async (err: AxiosError) => {
    const cfg = err.config as InternalAxiosRequestConfig & { _retry?: boolean };
    if (err.response?.status === 401 && !cfg._retry && !cfg.url?.includes("/auth/")) {
      cfg._retry = true;
      try {
        refreshing =
          refreshing ||
          api.post("/auth/refresh", {}, {
            headers: {
              "X-Refresh-Token": localStorage.getItem("refresh_token") || "",
            },
          });
        const { data } = (await refreshing) as { data: { access_token: string; refresh_token: string } };
        refreshing = null;
        tokens.set(data.access_token, data.refresh_token);
        return api(cfg);
      } catch {
        refreshing = null;
        tokens.clear();
        if (!window.location.pathname.startsWith("/login")) {
          window.location.href = "/login";
        }
      }
    }
    return Promise.reject(err);
  }
);

interface ErrorDetail {
  message?: string;
  msg?: string;
  code?: string;
}

export function errMsg(e: unknown): string {
  const ax = e as AxiosError<{ detail: string | ErrorDetail[] | ErrorDetail }>;
  if (ax?.code === "ERR_NETWORK") {
    return "Could not reach the BenchOS server. Please try again shortly.";
  }
  const d = ax?.response?.data?.detail;
  if (d == null) return (e as Error)?.message || "Something went wrong. Please try again.";
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x?.msg || JSON.stringify(x)).join(" ");
  if (d.message) return d.message;
  if (d.msg) return d.msg;
  return String(d);
}

export const errCode = (e: unknown): string | undefined => {
  const ax = e as AxiosError<{ detail: { code?: string } }>;
  return ax?.response?.data?.detail?.code;
};

export const fmtDate = (iso?: string | null): string =>
  iso
    ? new Date(iso).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : "—";

export const fmtDateTime = (iso?: string | null, tz?: string): string =>
  iso
    ? new Date(iso).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
        timeZone: tz || undefined,
        timeZoneName: tz ? "short" : undefined,
      })
    : "—";

export const money = (v?: number | null, redacted?: boolean): string =>
  redacted ? "•••" : v === null || v === undefined ? "—" : `$${Number(v).toFixed(0)}/hr`;

export const rate = (o: Record<string, unknown>, k: string): string =>
  money(
    o[k] as number | null | undefined,
    ((o._redacted as string[]) || []).includes(k)
  );

export const daysSince = (iso?: string | null): number | null =>
  iso ? Math.floor((Date.now() - new Date(iso).getTime()) / 86400000) : null;

