import createClient, { type Middleware } from "openapi-fetch";
import type { paths } from "./schema";

/**
 * Same-origin prefix by default; Vite (dev/preview) proxies it to the FastAPI app.
 * A deployment that serves the API from another origin sets VITE_API_BASE at build time.
 */
export const API_BASE = import.meta.env.VITE_API_BASE?.replace(/\/+$/, "") || "/api";

const TOKEN_KEY = "oh.session";

type Session = { token: string; email: string; expiresAt: number };

/** True once a session has ended by expiry or rejection, until the next sign-in. */
let expired = false;

let session: Session | null = readStoredSession();

function readStoredSession(): Session | null {
  try {
    const raw = window.localStorage.getItem(TOKEN_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Session;
    if (parsed.expiresAt > Date.now()) return parsed;
    expired = true;
    return null;
  } catch {
    return null;
  }
}

/** Whether the person was signed out by expiry, so sign-in can explain why. */
export function sessionExpired(): boolean {
  return expired;
}

function tokenExpiry(token: string): number {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]!.replace(/-/g, "+").replace(/_/g, "/"))) as {
      exp?: number;
    };
    return payload.exp ? payload.exp * 1000 : Date.now() + 30 * 60_000;
  } catch {
    return Date.now() + 30 * 60_000;
  }
}

export function getSession(): Session | null {
  if (session && session.expiresAt <= Date.now()) {
    expired = true;
    setSession(null);
  }
  return session;
}

export function setSession(next: { token: string; email: string } | null): Session | null {
  session = next ? { ...next, expiresAt: tokenExpiry(next.token) } : null;
  if (next) expired = false;
  try {
    if (session) window.localStorage.setItem(TOKEN_KEY, JSON.stringify(session));
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: the session simply lasts for this tab */
  }
  return session;
}

/** Fired when an authenticated request is rejected, so the app can re-route to sign-in. */
export const UNAUTHORIZED_EVENT = "oh:unauthorized";

const auth: Middleware = {
  onRequest({ request }) {
    const current = getSession();
    if (current) request.headers.set("Authorization", `Bearer ${current.token}`);
    return request;
  },
  onResponse({ request, response }) {
    if (response.status === 401 && request.headers.has("Authorization")) {
      expired = true;
      setSession(null);
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
    return response;
  },
};

export const api = createClient<paths>({ baseUrl: API_BASE });
api.use(auth);

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly fields: Record<string, string> = {},
  ) {
    super(message);
  }
}

type ValidationItem = { loc?: (string | number)[]; msg?: string };

function errorFrom(status: number, body: unknown): ApiError {
  const detail = (body as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string") return new ApiError(status, detail);
  if (Array.isArray(detail)) {
    const fields: Record<string, string> = {};
    for (const item of detail as ValidationItem[]) {
      const field = item.loc?.filter((part) => part !== "body").join(".") || "form";
      fields[field] = (item.msg ?? "Invalid value").replace(/^Value error, /, "");
    }
    return new ApiError(status, Object.values(fields)[0] ?? "Please check the highlighted fields.", fields);
  }
  if (status >= 500) return new ApiError(status, "The server had a problem. Please try again.");
  return new ApiError(status, `Request failed (${status}).`);
}

/** Turn an openapi-fetch result into data or a thrown ``ApiError``. */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  let result;
  try {
    result = await call;
  } catch {
    throw new ApiError(0, "Can’t reach the server. Check that the API is running.");
  }
  if (result.error !== undefined || !result.response.ok) {
    throw errorFrom(result.response.status, result.error);
  }
  return result.data as T;
}
