import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router";
import { UNAUTHORIZED_EVENT, api, getSession, setSession, unwrap } from "../api/client";

type AuthState = {
  isAuthenticated: boolean;
  email: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void | Promise<void>;
  /** Present only in development builds whose env defines a demo account. */
  demo: { email: string; password: string } | null;
};

const AuthContext = createContext<AuthState | null>(null);

const DEMO =
  import.meta.env.DEV && import.meta.env.VITE_DEMO_EMAIL && import.meta.env.VITE_DEMO_PASSWORD
    ? { email: String(import.meta.env.VITE_DEMO_EMAIL), password: String(import.meta.env.VITE_DEMO_PASSWORD) }
    : null;

export function AuthProvider({ children }: { children: ReactNode }) {
  const [current, setCurrent] = useState(() => getSession());
  const client = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();

  const clear = useCallback(async () => {
    try {
      await api.POST("/auth/logout", {});
    } catch {
      /* ignore if server unavailable or already logged out */
    }
    setSession(null);
    setCurrent(null);
    client.removeQueries({ queryKey: ["me"] });
  }, [client]);

  // A rejected token or a reached expiry both send the person to sign-in,
  // remembering where they were.
  useEffect(() => {
    const expire = () => {
      clear();
      const next = `${location.pathname}${location.search}`;
      navigate(`/login?expired=1&next=${encodeURIComponent(next)}`, { replace: true });
    };
    window.addEventListener(UNAUTHORIZED_EVENT, expire);
    const timer = current ? window.setTimeout(expire, Math.max(0, current.expiresAt - Date.now())) : undefined;
    return () => {
      window.removeEventListener(UNAUTHORIZED_EVENT, expire);
      window.clearTimeout(timer);
    };
  }, [current, clear, location.pathname, location.search, navigate]);

  const login = useCallback(
    async (email: string, password: string) => {
      const { access_token } = await unwrap(api.POST("/auth/login", { body: { email, password } }));
      client.removeQueries({ queryKey: ["me"] });
      setCurrent(setSession({ token: access_token, email }));
    },
    [client],
  );

  const register = useCallback(
    async (email: string, password: string) => {
      await unwrap(api.POST("/auth/register", { body: { email, password } }));
      await login(email, password);
    },
    [login],
  );

  const value = useMemo<AuthState>(
    () => ({
      isAuthenticated: current !== null,
      email: current?.email ?? null,
      login,
      register,
      logout: clear,
      demo: DEMO,
    }),
    [current, login, register, clear],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
