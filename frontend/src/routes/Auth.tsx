import { ArrowLeft, CheckCircle2, Clock3, Eye, EyeOff } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router";
import { ApiError, api, unwrap } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Page } from "../components/layout/Page";
import { Logo } from "../components/ui/Logo";
import { FieldError, Spinner } from "../components/ui/States";
import { Credit } from "../components/ui/Plate";
import { PHOTOS } from "../lib/photos";
import { ThemeToggle } from "../components/ui/ThemeToggle";
import { GoogleSignIn, googleErrorMessage } from "../auth/google";

/** Only same-site relative paths are honoured as a post-login destination. */
function safeNext(value: string | null): string | null {
  return value && value.startsWith("/") && !value.startsWith("//") ? value : null;
}

function AuthFrame({ title, subtitle, children }: { title: string; subtitle: ReactNode; children: ReactNode }) {
  const photo = PHOTOS.radioTelescope;
  return (
    <div className="grid min-h-dvh grid-cols-1 bg-ivory lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <div className="flex flex-col px-5 py-6 sm:px-10">
        <div className="flex items-center justify-between">
          <Logo />
          <ThemeToggle className="-my-2" />
        </div>
        <main id="main" className="flex flex-1 items-center py-12">
          <div className="mx-auto w-full max-w-[400px]">
            <h1 className="display text-[48px] text-ink sm:text-[56px]">{title}</h1>
            <p className="mt-4 text-[15.5px] text-ink-soft">{subtitle}</p>
            <div className="mt-10">{children}</div>
          </div>
        </main>
      </div>
      <div className="relative hidden overflow-hidden bg-night lg:block">
        <img
          src={photo.small}
          srcSet={`${photo.small} 800w, ${photo.large} 1600w`}
          sizes="55vw"
          alt={photo.alt}
          className="absolute inset-0 h-full w-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-night/85 via-night/10 to-transparent" aria-hidden="true" />
        <div className="absolute inset-x-0 bottom-0 p-12 xl:p-16">
          <p className="display max-w-[14ch] text-[52px] text-snow xl:text-[64px]">Every verdict shows its work.</p>
          <p className="mt-4 max-w-[44ch] text-[16px] text-snow/80">
            Rules are copied from official pages and checked against your profile one at a time. Anything a machine can’t decide is left for you.
          </p>
          <p className="mt-8 text-[12px] text-snow/70">
            {photo.caption}. <Credit photo="radioTelescope" tone="paper" />
          </p>
        </div>
      </div>
    </div>
  );
}

/** A password input with a show/hide control; the value is never revealed unless asked. */
export function PasswordField({
  id,
  label,
  value,
  onChange,
  autoComplete,
  error,
  hint,
  aside,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: "current-password" | "new-password";
  error?: string;
  hint?: string;
  aside?: ReactNode;
}) {
  const [visible, setVisible] = useState(false);
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor={id} className="field-label">
          {label}
        </label>
        {aside}
      </div>
      <div className="relative">
        <input
          id={id}
          type={visible ? "text" : "password"}
          autoComplete={autoComplete}
          required
          className="input pr-12"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          aria-invalid={Boolean(error)}
          aria-describedby={describedBy}
        />
        <button
          type="button"
          className="icon-btn absolute right-1 top-1/2 size-9 -translate-y-1/2"
          onClick={() => setVisible((shown) => !shown)}
          aria-pressed={visible}
          aria-controls={id}
          aria-label={visible ? "Hide password" : "Show password"}
        >
          {visible ? <EyeOff size={17} /> : <Eye size={17} />}
        </button>
      </div>
      {hint && !error && (
        <p id={`${id}-hint`} className="mt-1.5 text-[12.5px] text-muted">
          {hint}
        </p>
      )}
      <FieldError id={`${id}-error`} message={error} />
    </div>
  );
}

function useCredentials() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  return { email, setEmail, password, setPassword, errors, setErrors, busy, setBusy };
}

function CredentialFields({
  state,
  passwordHint,
  autoCompletePassword,
}: {
  state: ReturnType<typeof useCredentials>;
  passwordHint?: string;
  autoCompletePassword: "current-password" | "new-password";
}) {
  return (
    <div className="flex flex-col gap-4">
      <div>
        <label htmlFor="email" className="field-label">
          Email
        </label>
        <input
          id="email"
          type="email"
          autoComplete="email"
          required
          className="input"
          value={state.email}
          onChange={(event) => state.setEmail(event.target.value)}
          aria-invalid={Boolean(state.errors.email)}
          aria-describedby={state.errors.email ? "email-error" : undefined}
        />
        <FieldError id="email-error" message={state.errors.email} />
      </div>
      <PasswordField
        id="password"
        label="Password"
        value={state.password}
        onChange={state.setPassword}
        autoComplete={autoCompletePassword}
        error={state.errors.password}
        hint={passwordHint}
        aside={
          autoCompletePassword === "current-password" && (
            <Link to="/forgot-password" className="text-[13px] font-medium text-cobalt-deep hover:underline">
              Forgot password?
            </Link>
          )
        }
      />
    </div>
  );
}

export function Login() {
  const { login, isAuthenticated, demo } = useAuth();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const state = useCredentials();
  const next = safeNext(params.get("next"));
  const expired = params.get("expired") === "1";
  const googleError = googleErrorMessage(params.get("google_error"));

  if (isAuthenticated && !state.busy) return <Navigate to={next ?? "/discover"} replace />;

  async function submit(event: FormEvent, credentials?: { email: string; password: string }) {
    event.preventDefault();
    state.setErrors({});
    state.setBusy(true);
    try {
      await login(credentials?.email ?? state.email, credentials?.password ?? state.password);
      navigate(next ?? "/discover", { replace: true });
    } catch (error) {
      state.setErrors({
        form:
          error instanceof ApiError && error.status === 401
            ? "That email and password don’t match an account."
            : error instanceof ApiError
              ? error.message
              : "Sign-in failed. Try again.",
      });
    } finally {
      state.setBusy(false);
    }
  }

  return (
    <Page title="Sign in">
      <AuthFrame
        title="Sign in"
        subtitle={
          <>
            New here?{" "}
            <Link to="/register" className="font-medium text-cobalt-deep hover:underline">
              Create an account
            </Link>
          </>
        }
      >
        {expired && (
          <div className="mb-5 flex items-start gap-2.5 rounded-[10px] border border-potential/40 bg-potential-wash px-3.5 py-3 text-[13.5px] text-potential-ink" role="status">
            <Clock3 size={15} className="mt-0.5 shrink-0" />
            Your session expired after 30 minutes. Sign in again to pick up where you left off.
          </div>
        )}
        {googleError && (
          <p role="alert" className="mb-5 rounded-[10px] border border-ineligible/30 bg-ineligible-wash px-3.5 py-3 text-[13.5px] text-ineligible-ink">
            {googleError}
          </p>
        )}
        <GoogleSignIn next={next} />
        <form onSubmit={submit} noValidate>
          <CredentialFields state={state} autoCompletePassword="current-password" />
          {state.errors.form && (
            <p role="alert" key={state.errors.form + state.busy} className="nudge mt-4 text-[13.5px] text-ineligible-ink">
              {state.errors.form}
            </p>
          )}
          <button type="submit" className="btn btn-primary btn-lg mt-6 w-full" disabled={state.busy}>
            {state.busy && <Spinner size={15} />}
            Sign in
          </button>
        </form>
        {demo && (
          <div className="mt-6 border-t border-rule pt-5">
            <button type="button" className="btn btn-quiet w-full" disabled={state.busy} onClick={(event) => submit(event, demo)}>
              Use the local demo account
            </button>
            <p className="mt-2 text-center text-[12px] text-muted">Development builds only. Signs in as {demo.email}.</p>
          </div>
        )}
      </AuthFrame>
    </Page>
  );
}

export function Register() {
  const { register, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const state = useCredentials();

  if (isAuthenticated && !state.busy) return <Navigate to="/discover" replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    const errors: Record<string, string> = {};
    if (!/^\S+@\S+\.\S+$/.test(state.email)) errors.email = "Enter a valid email address.";
    if (state.password.length < 8) errors.password = "Use at least 8 characters.";
    if (state.password.length > 128) errors.password = "Use at most 128 characters.";
    state.setErrors(errors);
    if (Object.keys(errors).length) return;
    state.setBusy(true);
    try {
      await register(state.email, state.password);
      navigate("/onboarding", { replace: true });
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        state.setErrors({ email: "An account with this email already exists. Sign in instead." });
      } else if (error instanceof ApiError && Object.keys(error.fields).length) {
        state.setErrors(error.fields);
      } else {
        state.setErrors({ form: error instanceof ApiError ? error.message : "Registration failed. Try again." });
      }
    } finally {
      state.setBusy(false);
    }
  }

  return (
    <Page title="Create account">
      <AuthFrame
        title="Create your account"
        subtitle={
          <>
            Already have one?{" "}
            <Link to="/login" className="font-medium text-cobalt-deep hover:underline">
              Sign in
            </Link>
          </>
        }
      >
        <GoogleSignIn label="Sign up with Google" />
        <form onSubmit={submit} noValidate>
          <CredentialFields state={state} passwordHint="At least 8 characters." autoCompletePassword="new-password" />
          {state.errors.form && (
            <p role="alert" key={state.errors.form + state.busy} className="nudge mt-4 text-[13.5px] text-ineligible-ink">
              {state.errors.form}
            </p>
          )}
          <button type="submit" className="btn btn-primary btn-lg mt-6 w-full" disabled={state.busy}>
            {state.busy && <Spinner size={15} />}
            Create account
          </button>
          <p className="mt-4 text-[12.5px] text-muted">
            Next you’ll build a short profile. It takes about two minutes.{" "}
            <Link to="/privacy" className="link">
              What we store
            </Link>
          </p>
        </form>
      </AuthFrame>
    </Page>
  );
}

function Notice({ tone, children }: { tone: "ok" | "error"; children: ReactNode }) {
  return tone === "ok" ? (
    <div role="status" className="flex items-start gap-2.5 rounded-[10px] border border-eligible/35 bg-eligible-wash px-3.5 py-3 text-[14px] text-eligible-ink">
      <CheckCircle2 size={16} className="mt-0.5 shrink-0" />
      <div>{children}</div>
    </div>
  ) : (
    <p role="alert" className="rounded-[10px] border border-ineligible/30 bg-ineligible-wash px-3.5 py-3 text-[14px] text-ineligible-ink">
      {children}
    </p>
  );
}

function BackToSignIn() {
  return (
    <Link to="/login" className="inline-flex items-center gap-1.5 text-[14px] font-medium text-cobalt-deep hover:underline">
      <ArrowLeft size={15} />
      Back to sign in
    </Link>
  );
}

/** Ask for a reset link. The answer never reveals whether an account exists. */
export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!/^\S+@\S+\.\S+$/.test(email)) {
      setFieldError("Enter the email address you signed up with.");
      return;
    }
    setFieldError(undefined);
    setBusy(true);
    try {
      await unwrap(api.POST("/auth/forgot-password", { body: { email } }));
      setSent(true);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The request didn’t go through. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page title="Reset your password">
      <AuthFrame title="Reset your password" subtitle="Enter your account’s email and we’ll send a link to choose a new password.">
        {sent ? (
          <div className="flex flex-col gap-6">
            <Notice tone="ok">
              If <span className="font-semibold">{email}</span> has an account, a reset link is on its way. It works once and expires; check spam if it doesn’t arrive.
            </Notice>
            <BackToSignIn />
          </div>
        ) : (
          <form onSubmit={submit} noValidate className="flex flex-col gap-5">
            <div>
              <label htmlFor="email" className="field-label">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                className="input"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                aria-invalid={Boolean(fieldError)}
                aria-describedby={fieldError ? "email-error" : undefined}
              />
              <FieldError id="email-error" message={fieldError} />
            </div>
            {error && <Notice tone="error">{error}</Notice>}
            <button type="submit" className="btn btn-primary btn-lg w-full" disabled={busy}>
              {busy && <Spinner size={15} />}
              Send reset link
            </button>
            <BackToSignIn />
          </form>
        )}
      </AuthFrame>
    </Page>
  );
}

/** Choose a new password from an emailed link. The token arrives in the URL fragment, never in server logs. */
export function ResetPassword() {
  const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const next: Record<string, string> = {};
    if (password.length < 8) next.password = "Use at least 8 characters.";
    else if (password.length > 128) next.password = "Use at most 128 characters.";
    if (!next.password && confirm !== password) next.confirm = "The two passwords don’t match.";
    setErrors(next);
    if (Object.keys(next).length || !token) return;
    setBusy(true);
    try {
      await unwrap(api.POST("/auth/reset-password", { body: { token, new_password: password } }));
      // Drop the spent token from the address bar and history.
      window.history.replaceState(null, "", window.location.pathname);
      setDone(true);
    } catch (caught) {
      setErrors({ form: caught instanceof ApiError ? caught.message : "The reset didn’t go through. Try again." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page title="Choose a new password">
      <AuthFrame title="Choose a new password" subtitle="After this, every device signed in to your account is signed out.">
        {done ? (
          <div className="flex flex-col gap-6">
            <Notice tone="ok">Your password has been changed. Sign in with the new one.</Notice>
            <Link to="/login" className="btn btn-primary btn-lg w-full">
              Sign in
            </Link>
          </div>
        ) : !token ? (
          <div className="flex flex-col gap-6">
            <Notice tone="error">This page needs the link from your reset email. Open the link again, or request a new one.</Notice>
            <Link to="/forgot-password" className="btn btn-quiet w-full">
              Request a new link
            </Link>
          </div>
        ) : (
          <form onSubmit={submit} noValidate className="flex flex-col gap-5">
            <PasswordField id="new-password" label="New password" value={password} onChange={setPassword} autoComplete="new-password" error={errors.password} hint="At least 8 characters." />
            <PasswordField id="confirm-password" label="Repeat it" value={confirm} onChange={setConfirm} autoComplete="new-password" error={errors.confirm} />
            {errors.form && (
              <Notice tone="error">
                {errors.form}{" "}
                <Link to="/forgot-password" className="font-semibold underline underline-offset-2">
                  Request a new link
                </Link>
              </Notice>
            )}
            <button type="submit" className="btn btn-primary btn-lg w-full" disabled={busy}>
              {busy && <Spinner size={15} />}
              Save new password
            </button>
          </form>
        )}
      </AuthFrame>
    </Page>
  );
}
