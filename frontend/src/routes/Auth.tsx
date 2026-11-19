import { ArrowRight, Check, Eye, EyeOff } from "lucide-react";
import { useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router";
import { ApiError, api, unwrap } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { GoogleSignIn, googleErrorMessage } from "../auth/google";
import { AuthFieldError, AuthFrame, AuthNotice } from "../components/auth/AuthLayout";
import { Ticks } from "../components/landing/Ink";
import { Page } from "../components/layout/Page";
import { Spinner } from "../components/ui/States";

/** Only same-site relative paths are honoured as a post-login destination. */
function safeNext(value: string | null): string | null {
  return value && value.startsWith("/") && !value.startsWith("//") ? value : null;
}

const EMAIL = /^\S+@\S+\.\S+$/;
const MIN_PASSWORD = 8;
const MAX_PASSWORD = 128;

/** Focus the first field that has an error, so keyboard and screen-reader users land on it. */
function focusFirst(errors: Record<string, string>, order: string[]) {
  const id = order.find((key) => errors[key]);
  if (id) requestAnimationFrame(() => document.getElementById(id)?.focus());
}

/** The submit action, stamped like the landing page's calls to action. Busy: a spinner and a present-tense label. */
function SubmitButton({ busy, children, busyLabel }: { busy: boolean; children: ReactNode; busyLabel: string }) {
  return (
    <button type="submit" className="btn-stamp btn-stamp-solid auth-submit mt-7 w-full" disabled={busy} aria-busy={busy}>
      <Ticks />
      {busy ? <Spinner size={15} /> : null}
      <span>{busy ? busyLabel : children}</span>
      {!busy && <ArrowRight size={16} aria-hidden="true" />}
    </button>
  );
}

function EmailField({ value, onChange, error, onBlur, autoFocus }: { value: string; onChange: (value: string) => void; error?: string; onBlur?: () => void; autoFocus?: boolean }) {
  return (
    <div>
      <label htmlFor="email" className="field-label">
        Email address
      </label>
      <input
        id="email"
        name="email"
        type="email"
        inputMode="email"
        autoComplete="email"
        autoCapitalize="none"
        spellCheck={false}
        placeholder="you@example.org"
        required
        autoFocus={autoFocus}
        className="input"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onBlur={onBlur}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? "email-error" : undefined}
      />
      <AuthFieldError id="email-error" message={error} />
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
  hint?: ReactNode;
  aside?: ReactNode;
}) {
  const [visible, setVisible] = useState(false);
  const describedBy = [error ? `${id}-error` : null, hint ? `${id}-hint` : null].filter(Boolean).join(" ") || undefined;
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
          name={id}
          type={visible ? "text" : "password"}
          autoComplete={autoComplete}
          autoCapitalize="none"
          spellCheck={false}
          required
          className="input pr-12"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          aria-invalid={Boolean(error)}
          aria-describedby={describedBy}
        />
        <button
          type="button"
          className="auth-eye absolute right-1 top-1/2 inline-flex size-10 -translate-y-1/2 items-center justify-center rounded-full text-ink-soft hover:text-ink"
          onClick={() => setVisible((shown) => !shown)}
          aria-pressed={visible}
          aria-controls={id}
          aria-label={visible ? "Hide password" : "Show password"}
        >
          <span key={visible ? "hide" : "show"} className="auth-eye-icon inline-flex">
            {visible ? <EyeOff size={18} /> : <Eye size={18} />}
          </span>
        </button>
      </div>
      {hint && (
        <div id={`${id}-hint`} className="mt-1.5 text-[12.5px] text-muted">
          {hint}
        </div>
      )}
      <AuthFieldError id={`${id}-error`} message={error} />
    </div>
  );
}

/** "At least 8 characters", ticked off as you type: a mark and words, not colour alone. */
function LengthHint({ length }: { length: number }) {
  const met = length >= MIN_PASSWORD;
  return (
    <span className={`inline-flex items-center gap-1.5 transition-colors ${met ? "text-eligible-ink" : ""}`}>
      <span className={`inline-flex size-4 items-center justify-center rounded-full border ${met ? "border-eligible bg-eligible text-white" : "border-current"}`} aria-hidden="true">
        {met && <Check size={11} strokeWidth={3} />}
      </span>
      At least {MIN_PASSWORD} characters{met ? " (done)" : ""}
    </span>
  );
}

function Divider() {
  return (
    <div className="my-6 flex items-center gap-3 text-ink-soft" aria-hidden="true">
      <span className="h-px flex-1 bg-ink/20" />
      <span className="small-caps text-[10.5px]">or with email</span>
      <span className="h-px flex-1 bg-ink/20" />
    </div>
  );
}

export function Login() {
  const { login, isAuthenticated, demo } = useAuth();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const next = safeNext(params.get("next"));
  const expired = params.get("expired") === "1";
  const googleError = googleErrorMessage(params.get("google_error"));

  if (isAuthenticated && !busy) return <Navigate to={next ?? "/discover"} replace />;

  async function submit(event: FormEvent, credentials?: { email: string; password: string }) {
    event.preventDefault();
    if (inFlight.current) return; // one request at a time
    const values = credentials ?? { email: email.trim(), password };
    const found: Record<string, string> = {};
    if (!values.email) found.email = "Enter your email address.";
    else if (!EMAIL.test(values.email)) found.email = "That doesn’t look like an email address.";
    if (!values.password) found.password = "Enter your password.";
    setErrors(found);
    if (Object.keys(found).length) return focusFirst(found, ["email", "password"]);
    inFlight.current = true;
    setBusy(true);
    try {
      await login(values.email, values.password);
      navigate(next ?? "/discover", { replace: true });
    } catch (error) {
      // One message for any wrong combination: it never says which part, or whether the account exists.
      setErrors({
        form:
          error instanceof ApiError && error.status === 401
            ? "That email and password don’t match an account. Check both, or reset your password."
            : error instanceof ApiError && error.status === 429
              ? "Too many attempts. Wait a minute, then try again."
              : error instanceof ApiError
                ? error.message
                : "We couldn’t reach the server. Check your connection and try again.",
      });
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <Page title="Sign in">
      <AuthFrame
        kicker="Sign in"
        title="Welcome back."
        subtitle="Pick up where you left off: your saved opportunities, your applications, and where you stand on each."
        footer={
          <>
            New to Opportunity Hub?{" "}
            <Link to="/register" className="auth-link">
              Create an account
            </Link>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          {expired && <AuthNotice tone="info">Your session expired after 30 minutes. Sign in again to pick up where you left off.</AuthNotice>}
          {googleError && <AuthNotice tone="error">{googleError}</AuthNotice>}
        </div>
        <GoogleSignIn next={next} divider={<Divider />} />
        <form onSubmit={submit} noValidate className={expired || googleError ? "mt-6" : undefined} aria-describedby={errors.form ? "form-error" : undefined}>
          <div className="flex flex-col gap-5">
            <EmailField value={email} onChange={setEmail} error={errors.email} />
            <PasswordField
              id="password"
              label="Password"
              value={password}
              onChange={setPassword}
              autoComplete="current-password"
              error={errors.password}
              aside={
                <Link to="/forgot-password" className="auth-link text-[13px]">
                  Forgot password?
                </Link>
              }
            />
          </div>
          {errors.form && (
            <div key={errors.form + busy} className="nudge mt-5">
              <AuthNotice tone="error" id="form-error">
                {errors.form}
              </AuthNotice>
            </div>
          )}
          <SubmitButton busy={busy} busyLabel="Signing in…">
            Sign in
          </SubmitButton>
        </form>
        {demo && (
          <div className="mt-6 border-t border-ink/15 pt-5">
            <button type="button" className="btn btn-quiet w-full" disabled={busy} onClick={(event) => submit(event, demo)}>
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
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);

  if (isAuthenticated && !busy) return <Navigate to="/discover" replace />;

  function checkEmail(value: string) {
    return !value ? "Enter your email address." : !EMAIL.test(value) ? "That doesn’t look like an email address." : undefined;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current) return;
    const found: Record<string, string> = {};
    const emailError = checkEmail(email.trim());
    if (emailError) found.email = emailError;
    if (password.length < MIN_PASSWORD) found.password = `Use at least ${MIN_PASSWORD} characters.`;
    else if (password.length > MAX_PASSWORD) found.password = `Use at most ${MAX_PASSWORD} characters.`;
    setErrors(found);
    if (Object.keys(found).length) return focusFirst(found, ["email", "password"]);
    inFlight.current = true;
    setBusy(true);
    try {
      await register(email.trim(), password);
      navigate("/onboarding", { replace: true });
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setErrors({ email: "An account with this email already exists. Sign in instead, or reset your password." });
        focusFirst({ email: "x" }, ["email"]);
      } else if (error instanceof ApiError && Object.keys(error.fields).length) {
        setErrors(error.fields);
        focusFirst(error.fields, ["email", "password"]);
      } else {
        setErrors({ form: error instanceof ApiError ? error.message : "We couldn’t reach the server. Check your connection and try again." });
      }
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <Page title="Create account">
      <AuthFrame
        kicker="Create an account"
        title="Your next opportunity starts here."
        subtitle="One account to check your eligibility against each program’s published rules, keep a shortlist, and track your applications."
        footer={
          <>
            Already have an account?{" "}
            <Link to="/login" className="auth-link">
              Sign in
            </Link>
          </>
        }
      >
        <GoogleSignIn label="Sign up with Google" divider={<Divider />} />
        <form onSubmit={submit} noValidate>
          <div className="flex flex-col gap-5">
            <EmailField
              value={email}
              onChange={(value) => {
                setEmail(value);
                if (errors.email) setErrors(({ email: _drop, ...rest }) => rest);
              }}
              onBlur={() => {
                const message = email.trim() ? checkEmail(email.trim()) : undefined;
                setErrors((old) => (message ? { ...old, email: message } : (({ email: _drop, ...rest }) => rest)(old)));
              }}
              error={errors.email}
            />
            <PasswordField
              id="password"
              label="Choose a password"
              value={password}
              onChange={(value) => {
                setPassword(value);
                if (errors.password && value.length >= MIN_PASSWORD) setErrors(({ password: _drop, ...rest }) => rest);
              }}
              autoComplete="new-password"
              error={errors.password}
              hint={<LengthHint length={password.length} />}
            />
          </div>
          {errors.form && (
            <div key={errors.form + busy} className="nudge mt-5">
              <AuthNotice tone="error">{errors.form}</AuthNotice>
            </div>
          )}
          <SubmitButton busy={busy} busyLabel="Creating your account…">
            Create account
          </SubmitButton>
          <p className="mt-4 text-[12.5px] leading-relaxed text-muted">
            Next, a short profile so we can check your eligibility. It takes about two minutes, and you can skip parts of it.{" "}
            <Link to="/privacy" className="auth-link">
              What we store
            </Link>
          </p>
        </form>
      </AuthFrame>
    </Page>
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
    if (busy) return;
    setError(null);
    if (!EMAIL.test(email.trim())) {
      setFieldError("Enter the email address you signed up with.");
      return focusFirst({ email: "x" }, ["email"]);
    }
    setFieldError(undefined);
    setBusy(true);
    try {
      await unwrap(api.POST("/auth/forgot-password", { body: { email: email.trim() } }));
      setSent(true);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The request didn’t go through. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page title="Reset your password">
      <AuthFrame
        kicker="Password help"
        title={sent ? "Check your inbox." : "Find your way back."}
        subtitle={sent ? undefined : "Enter the email you signed up with and we’ll send a link to choose a new password."}
        footer={
          <Link to="/login" className="auth-link">
            ← Back to sign in
          </Link>
        }
      >
        {sent ? (
          <AuthNotice tone="ok">
            If <span className="font-semibold">{email.trim()}</span> has an account, a reset link is on its way. It works once and expires soon; check your spam folder if it doesn’t arrive.
          </AuthNotice>
        ) : (
          <form onSubmit={submit} noValidate className="flex flex-col">
            <EmailField value={email} onChange={setEmail} error={fieldError} />
            {error && (
              <div className="mt-5">
                <AuthNotice tone="error">{error}</AuthNotice>
              </div>
            )}
            <SubmitButton busy={busy} busyLabel="Sending…">
              Send reset link
            </SubmitButton>
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
    if (busy) return;
    const found: Record<string, string> = {};
    if (password.length < MIN_PASSWORD) found["new-password"] = `Use at least ${MIN_PASSWORD} characters.`;
    else if (password.length > MAX_PASSWORD) found["new-password"] = `Use at most ${MAX_PASSWORD} characters.`;
    if (!found["new-password"] && confirm !== password) found["confirm-password"] = "The two passwords don’t match.";
    setErrors(found);
    if (Object.keys(found).length) return focusFirst(found, ["new-password", "confirm-password"]);
    if (!token) return;
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
      <AuthFrame
        kicker="Password help"
        title={done ? "Password changed." : "Choose a new password."}
        subtitle={done ? undefined : "After this, every device signed in to your account is signed out."}
        footer={
          !done && (
            <Link to="/login" className="auth-link">
              ← Back to sign in
            </Link>
          )
        }
      >
        {done ? (
          <div className="flex flex-col">
            <AuthNotice tone="ok">Your password has been changed. Sign in with the new one.</AuthNotice>
            <Link to="/login" className="btn-stamp btn-stamp-solid mt-7 w-full">
              <Ticks />
              Sign in
              <ArrowRight size={16} aria-hidden="true" />
            </Link>
          </div>
        ) : !token ? (
          <div className="flex flex-col gap-6">
            <AuthNotice tone="error">This page needs the link from your reset email. Open the link again, or request a new one.</AuthNotice>
            <Link to="/forgot-password" className="btn btn-quiet w-full">
              Request a new link
            </Link>
          </div>
        ) : (
          <form onSubmit={submit} noValidate className="flex flex-col">
            <div className="flex flex-col gap-5">
              <PasswordField
                id="new-password"
                label="New password"
                value={password}
                onChange={setPassword}
                autoComplete="new-password"
                error={errors["new-password"]}
                hint={<LengthHint length={password.length} />}
              />
              <PasswordField id="confirm-password" label="Repeat it" value={confirm} onChange={setConfirm} autoComplete="new-password" error={errors["confirm-password"]} />
            </div>
            {errors.form && (
              <div className="mt-5">
                <AuthNotice tone="error">
                  {errors.form}{" "}
                  <Link to="/forgot-password" className="font-semibold underline underline-offset-2">
                    Request a new link
                  </Link>
                </AuthNotice>
              </div>
            )}
            <SubmitButton busy={busy} busyLabel="Saving…">
              Save new password
            </SubmitButton>
          </form>
        )}
      </AuthFrame>
    </Page>
  );
}
