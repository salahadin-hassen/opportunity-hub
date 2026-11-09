import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import { Compass } from "lucide-react";
import { Suspense, lazy, useEffect, type ReactNode } from "react";
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from "react-router";
import { ApiError, sessionExpired } from "../api/client";
import { useProfile } from "../api/queries";
import { AuthProvider, useAuth } from "../auth/AuthContext";
import { AppShell, GuestShell } from "../components/layout/AppShell";
import { Content, Page } from "../components/layout/Page";
import { EmptyState, ErrorState, Spinner } from "../components/ui/States";
import { ToastProvider } from "../components/ui/Toast";
import { EligibilityProvider } from "../features/eligibility";
import { ThemeProvider } from "./theme";
import { Landing } from "../routes/Landing";

// The landing page ships first; application routes load on demand.
const Login = lazy(() => import("../routes/Auth").then((module) => ({ default: module.Login })));
const Register = lazy(() => import("../routes/Auth").then((module) => ({ default: module.Register })));
const Discover = lazy(() => import("../routes/Discover").then((module) => ({ default: module.Discover })));
const Eligibility = lazy(() => import("../routes/Eligibility").then((module) => ({ default: module.Eligibility })));
const Onboarding = lazy(() => import("../routes/Onboarding").then((module) => ({ default: module.Onboarding })));
const OpportunityDetail = lazy(() => import("../routes/OpportunityDetail").then((module) => ({ default: module.OpportunityDetail })));
const Privacy = lazy(() => import("../routes/Privacy").then((module) => ({ default: module.Privacy })));
const Credits = lazy(() => import("../routes/Credits").then((module) => ({ default: module.Credits })));
const Profile = lazy(() => import("../routes/Profile").then((module) => ({ default: module.Profile })));
const Saved = lazy(() => import("../routes/Saved").then((module) => ({ default: module.Saved })));
const Applications = lazy(() => import("../routes/Applications").then((module) => ({ default: module.Applications })));
const Curate = lazy(() => import("../routes/Curate").then((module) => ({ default: module.Curate })));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: (count, error) => !(error instanceof ApiError && error.status < 500 && error.status > 0) && count < 2,
    },
  },
});

function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const location = useLocation();
  if (!isAuthenticated) {
    const reason = sessionExpired() ? "expired=1&" : "";
    return <Navigate to={`/login?${reason}next=${encodeURIComponent(location.pathname + location.search)}`} replace />;
  }
  return <>{children}</>;
}

/** A signed-in person without a profile is sent to onboarding (the API answers 404). */
function RequireProfile({ children }: { children: ReactNode }) {
  const profile = useProfile();
  if (profile.isPending) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center text-muted">
        <Spinner />
      </div>
    );
  }
  if (profile.isError) {
    return (
      <Content width="narrow">
        <ErrorState message="Your profile couldn’t load. Check that the API is running." onRetry={() => profile.refetch()} />
      </Content>
    );
  }
  if (!profile.data) return <Navigate to="/onboarding" replace />;
  return <>{children}</>;
}

/** Public application pages use the app frame once a profile exists, the guest frame otherwise. */
function Frame({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const profile = useProfile();
  return isAuthenticated && profile.data ? <AppShell>{children}</AppShell> : <GuestShell>{children}</GuestShell>;
}

function ScrollRestoration() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (hash) {
      const target = document.getElementById(hash.slice(1));
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }
    }
    window.scrollTo({ top: 0 });
  }, [pathname, hash]);
  return null;
}

function NotFound() {
  return (
    <GuestShell>
      <Page title="Not found">
        <EmptyState
          icon={Compass}
          title="There’s no page at this address"
          action={
            <Link to="/opportunities" className="btn btn-quiet">
              Browse opportunities
            </Link>
          }
        >
          The link may be out of date.
        </EmptyState>
      </Page>
    </GuestShell>
  );
}

function app(children: ReactNode) {
  return (
    <RequireAuth>
      <RequireProfile>
        <AppShell>{children}</AppShell>
      </RequireProfile>
    </RequireAuth>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <MotionConfig reducedMotion="user">
          <ThemeProvider>
          <ToastProvider>
            <AuthProvider>
              <EligibilityProvider>
                <a
                  href="#main"
                  className="fixed left-3 top-3 z-[70] -translate-y-16 rounded-md bg-ink px-3 py-2 text-sm text-on-ink focus:translate-y-0"
                >
                  Skip to content
                </a>
                <ScrollRestoration />
                <Suspense
                  fallback={
                    <div className="flex min-h-dvh items-center justify-center bg-ivory text-muted">
                      <Spinner />
                    </div>
                  }
                >
                <Routes>
                  <Route path="/" element={<Landing />} />
                  <Route path="/opportunities" element={<Frame><Discover /></Frame>} />
                  <Route path="/opportunities/:id" element={<Frame><OpportunityDetail /></Frame>} />
                  <Route path="/login" element={<Login />} />
                  <Route path="/register" element={<Register />} />
                  <Route path="/onboarding" element={<RequireAuth><Onboarding /></RequireAuth>} />
                  <Route path="/discover" element={app(<Discover />)} />
                  <Route path="/eligibility" element={app(<Eligibility />)} />
                  <Route path="/saved" element={app(<Saved />)} />
                  <Route path="/applications" element={app(<Applications />)} />
                  <Route path="/curate" element={app(<Curate />)} />
                  <Route path="/profile" element={app(<Profile />)} />
                  <Route path="/credits" element={<Credits />} />
                  <Route path="/privacy" element={<Privacy />} />
                  <Route path="*" element={<NotFound />} />
                </Routes>
                </Suspense>
              </EligibilityProvider>
            </AuthProvider>
          </ToastProvider>
          </ThemeProvider>
        </MotionConfig>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
