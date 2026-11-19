import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { ApiError, api, unwrap } from "../api/client";
import { useAuth } from "./AuthContext";
import { Spinner } from "../components/ui/States";
import { AuthFrame, AuthNotice } from "../components/auth/AuthLayout";
import { Page } from "../components/layout/Page";
import type { ReactNode } from "react";

/** What the browser shows for each refusal code the API's Google callback can send back. */
export const GOOGLE_ERRORS: Record<string, string> = {
  link_required:
    "An account with this email already exists. Sign in with your password, then connect Google from your profile.",
  email_unverified: "Google hasn’t verified this account’s email address, so it can’t be used to sign in.",
  identity_in_use: "That Google account is already connected to another Opportunity Hub account.",
  already_linked: "Your account already has a Google account connected. Disconnect it first to connect a different one.",
  cancelled: "Google sign-in was cancelled.",
  state_invalid: "That sign-in attempt expired or was already used. Please try again.",
  token_invalid: "Google’s response couldn’t be verified. Please try again.",
  provider_error: "Google couldn’t be reached. Please try again in a moment.",
  account_inactive: "This account can’t be signed in to.",
};

export function googleErrorMessage(code: string | null): string | null {
  if (!code) return null;
  return GOOGLE_ERRORS[code] ?? "Google sign-in didn’t complete. Please try again.";
}

/** Whether this deployment offers Google sign-in (the API says so; nothing is assumed). */
export function useGoogleAvailable(): boolean {
  const { data } = useQuery({
    queryKey: ["auth-providers"],
    queryFn: () => unwrap(api.GET("/auth/providers")),
    staleTime: 5 * 60_000,
  });
  return Boolean(data?.google);
}

/** Google's standard multicolour "G", per its sign-in branding guidelines. */
function GoogleMark() {
  return (
    <svg aria-hidden="true" width="18" height="18" viewBox="0 0 48 48" className="shrink-0">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  );
}

/**
 * "Continue with Google": Google's own button spec (light: white, #747775 outline, #1F1F1F text;
 * dark: #131314, #8E918F outline, #E3E3E3 text), 40px tall, the standard mark on the left.
 */
export function GoogleButton({
  label = "Continue with Google",
  start,
  disabled,
}: {
  label?: string;
  start: () => Promise<string>;
  disabled?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function go() {
    setError(null);
    setBusy(true);
    try {
      window.location.assign(await start());
    } catch (err) {
      setBusy(false);
      setError(err instanceof ApiError ? err.message : "Google sign-in couldn’t start. Please try again.");
    }
  }
  return (
    <div>
      <button
        type="button"
        onClick={go}
        disabled={busy || disabled}
        aria-busy={busy}
        className="google-btn inline-flex h-11 w-full items-center justify-center gap-2.5 rounded-full border px-4 text-[14px] font-medium transition-colors disabled:opacity-60"
      >
        {busy ? <Spinner size={16} /> : <GoogleMark />}
        <span>{busy ? "Redirecting to Google…" : label}</span>
      </button>
      {error && (
        <p role="alert" className="mt-2 text-[13px] text-ineligible-ink">
          {error}
        </p>
      )}
    </div>
  );
}

/** Sign in (or create an account) with Google, then come back to ``next``. Renders nothing (not even the divider) if unavailable. */
export function GoogleSignIn({ next, label, divider }: { next?: string | null; label?: string; divider?: ReactNode }) {
  const available = useGoogleAvailable();
  if (!available) return null;
  return (
    <>
      <GoogleButton
        label={label}
        start={async () => {
          const { authorization_url } = await unwrap(api.POST("/auth/google/start", { body: { next: next ?? null } }));
          return authorization_url;
        }}
      />
      {divider ?? (
        <div className="my-5 flex items-center gap-3 text-[12px] uppercase tracking-wide text-muted" aria-hidden="true">
          <span className="h-px flex-1 bg-rule" />
          or
          <span className="h-px flex-1 bg-rule" />
        </div>
      )}
    </>
  );
}

/**
 * /auth/google/complete — Google sent the browser to the API, which sent it here with a single-use
 * code in the URL fragment. Trade it for a session, then continue. The fragment is cleared at once.
 */
export function GoogleComplete() {
  const { adopt } = useAuth();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [failed, setFailed] = useState(false);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return; // StrictMode runs effects twice; the code works only once
    started.current = true;
    const code = new URLSearchParams(window.location.hash.slice(1)).get("code");
    window.history.replaceState(null, "", window.location.pathname);
    if (!code) {
      setFailed(true);
      return;
    }
    (async () => {
      try {
        const result = await unwrap(api.POST("/auth/google/exchange", { body: { code } }));
        if (result.outcome === "linked") {
          await client.invalidateQueries({ queryKey: ["auth-identities"] });
          navigate(`${result.next ?? "/profile"}?google=linked`, { replace: true });
          return;
        }
        adopt(result.access_token!, result.email!);
        navigate(result.is_new_user ? "/onboarding" : (result.next ?? "/discover"), { replace: true });
      } catch {
        setFailed(true);
      }
    })();
  }, [adopt, client, navigate]);

  return (
    <Page title={failed ? "Google sign-in didn’t finish" : "Signing you in"}>
      <AuthFrame kicker="Sign in with Google" title={failed ? "That link has expired." : "Signing you in…"}>
        {failed ? (
          <div className="flex flex-col gap-6">
            <AuthNotice tone="error">That Google sign-in link has expired or was already used. Start again from the sign-in page.</AuthNotice>
            <a href="/login" className="btn btn-quiet w-full">
              Back to sign in
            </a>
          </div>
        ) : (
          <p role="status" className="flex items-center gap-2.5 text-[15px] text-ink-soft">
            <Spinner size={16} /> Confirming your Google account with the server.
          </p>
        )}
      </AuthFrame>
    </Page>
  );
}

/** Profile: how this account signs in, and connecting or disconnecting Google. */
export function SignInMethods() {
  const client = useQueryClient();
  const { data, isPending } = useQuery({
    queryKey: ["auth-identities"],
    queryFn: () => unwrap(api.GET("/auth/identities")),
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(() =>
    googleErrorMessage(new URLSearchParams(window.location.search).get("google_error")),
  );
  const linked = new URLSearchParams(window.location.search).get("google") === "linked";

  if (isPending || !data) return <div className="skeleton h-24 w-full" />;

  async function disconnect() {
    setBusy(true);
    setError(null);
    try {
      await unwrap(api.DELETE("/auth/google/link"));
      await client.invalidateQueries({ queryKey: ["auth-identities"] });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn’t disconnect Google.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4 rounded-[12px] border border-rule bg-paper p-5">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-[14.5px] font-medium text-ink">Password</p>
          <p className="text-[13px] text-muted">
            {data.has_password ? "Set." : "Not set. Use “Forgot password” on the sign-in page to add one."}
          </p>
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-4 border-t border-rule pt-4">
        <div className="flex items-center gap-2.5">
          <GoogleMark />
          <div>
            <p className="text-[14.5px] font-medium text-ink">Google</p>
            <p className="text-[13px] text-muted">
              {data.google_linked ? `Connected${data.google_email ? ` as ${data.google_email}` : ""}.` : "Not connected."}
            </p>
          </div>
        </div>
        {data.google_linked ? (
          <button type="button" className="btn btn-quiet" onClick={disconnect} disabled={busy || !data.has_password}
            title={data.has_password ? undefined : "Set a password first: Google is this account’s only sign-in."}>
            {busy && <Spinner size={14} />} Disconnect
          </button>
        ) : data.google_available ? (
          <div className="w-full sm:w-64">
            <GoogleButton
              label="Connect Google"
              start={async () => {
                const { authorization_url } = await unwrap(api.POST("/auth/google/link/start", { body: { next: "/profile" } }));
                return authorization_url;
              }}
            />
          </div>
        ) : null}
      </div>
      {linked && !error && (
        <p role="status" className="text-[13px] text-eligible-ink">
          Google is connected. You can now sign in with it.
        </p>
      )}
      {error && (
        <p role="alert" className="text-[13px] text-ineligible-ink">
          {error}
        </p>
      )}
    </div>
  );
}
