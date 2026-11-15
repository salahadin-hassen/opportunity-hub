import { Clock3 } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Page } from "../components/layout/Page";
import { Logo } from "../components/ui/Logo";
import { FieldError, Spinner } from "../components/ui/States";
import { Credit } from "../components/ui/Plate";
import { PHOTOS } from "../lib/photos";
import { ThemeToggle } from "../components/ui/ThemeToggle";

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
      <div>
        <label htmlFor="password" className="field-label">
          Password
        </label>
        <input
          id="password"
          type="password"
          autoComplete={autoCompletePassword}
          required
          className="input"
          value={state.password}
          onChange={(event) => state.setPassword(event.target.value)}
          aria-invalid={Boolean(state.errors.password)}
          aria-describedby={state.errors.password ? "password-error" : passwordHint ? "password-hint" : undefined}
        />
        {passwordHint && !state.errors.password && (
          <p id="password-hint" className="mt-1.5 text-[12.5px] text-muted">
            {passwordHint}
          </p>
        )}
        <FieldError id="password-error" message={state.errors.password} />
      </div>
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
        <form onSubmit={submit} noValidate>
          <CredentialFields state={state} autoCompletePassword="current-password" />
          {state.errors.form && (
            <p role="alert" className="mt-4 text-[13.5px] text-ineligible-ink">
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
        <form onSubmit={submit} noValidate>
          <CredentialFields state={state} passwordHint="At least 8 characters." autoCompletePassword="new-password" />
          {state.errors.form && (
            <p role="alert" className="mt-4 text-[13.5px] text-ineligible-ink">
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
