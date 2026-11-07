import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api, tokens } from "@/lib/api";
import type { User, Organization, UserGroup, OrgRole } from "@/types";

interface AuthState {
  user: User;
  organization: Organization;
  groups: UserGroup[];
  access_token: string;
  refresh_token: string;
}

interface AuthContextValue {
  /** null = loading, false = unauthenticated, AuthState = authenticated */
  session: AuthState | false | null;
  user: User | undefined;
  org: Organization | undefined;
  groups: UserGroup[];
  role: OrgRole | undefined;
  isOps: boolean;
  isAdmin: boolean;
  isAuditor: boolean;
  groupRoles: string[];
  refresh: () => Promise<AuthState | false>;
  complete: (data: { access_token: string; refresh_token: string }) => Promise<AuthState | false>;
  logout: () => Promise<void>;
  setState: React.Dispatch<React.SetStateAction<AuthState | false | null>>;
}

const AuthCtx = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState | false | null>(null);

  const refresh = useCallback(async (): Promise<AuthState | false> => {
    try {
      const { data } = await api.get<AuthState>("/auth/me");
      setState(data);
      return data;
    } catch {
      setState(false);
      return false;
    }
  }, []);

  useEffect(() => {
    if (window.location.hash?.includes("session_id=")) return;
    refresh();
  }, [refresh]);

  const complete = async (data: {
    access_token: string;
    refresh_token: string;
  }): Promise<AuthState | false> => {
    tokens.set(data.access_token, data.refresh_token);
    return refresh();
  };

  const logout = async (): Promise<void> => {
    try {
      await api.post("/auth/logout");
    } catch {
      /* ignore */
    }
    tokens.clear();
    setState(false);
  };

  const s = (state || {}) as Partial<AuthState>;
  const role = s.user?.role;
  const isOps = role === "ADMIN" || role === "OPERATIONS";
  const groupRoles = (s.groups || []).map((g) => g.role);

  return (
    <AuthCtx.Provider
      value={{
        session: state,
        user: s.user,
        org: s.organization,
        groups: s.groups || [],
        role,
        isOps,
        isAdmin: role === "ADMIN",
        isAuditor: role === "AUDITOR",
        groupRoles,
        refresh,
        complete,
        logout,
        setState,
      }}
    >
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = (): AuthContextValue => {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
};

