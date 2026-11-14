import { AnimatePresence, motion } from "motion/react";
import { Bookmark, ChevronDown, Compass, FileCheck, LogOut, Menu, ScanSearch, Shield, UserRound, X, type LucideIcon } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router";
import { useProfile, useUserAccount } from "../../api/queries";
import { useAuth } from "../../auth/AuthContext";
import { useEligibility } from "../../features/eligibility";
import { Logo } from "../ui/Logo";
import { MobileMenuSheet, useMobileMenu } from "../marketing/MarketingChrome";
import { ThemeToggle } from "../ui/ThemeToggle";

const BASE_NAV: { to: string; label: string; icon: LucideIcon }[] = [
  { to: "/discover", label: "Discover", icon: Compass },
  { to: "/eligibility", label: "Eligibility", icon: ScanSearch },
  { to: "/saved", label: "Saved", icon: Bookmark },
  { to: "/applications", label: "Applications", icon: FileCheck },
  { to: "/profile", label: "Profile", icon: UserRound },
];

/** Live status of a running eligibility check, visible from every page. */
function RunStatus() {
  const { running, progress } = useEligibility();
  const percent = progress.total ? Math.round((progress.done / progress.total) * 100) : 0;
  return (
    <AnimatePresence>
      {running && (
        <motion.div
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          className="flex items-center gap-2.5 text-[13px] text-ink-soft"
          role="status"
        >
          <span className="relative h-1.5 w-20 overflow-hidden rounded-full bg-cream">
            <motion.span className="absolute inset-y-0 left-0 rounded-full bg-cobalt" animate={{ width: `${percent}%` }} transition={{ duration: 0.25 }} />
          </span>
          <span className="num whitespace-nowrap">
            Checking {progress.done}/{progress.total}
          </span>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function initialsOf(name: string): string {
  return name
    .split(/[\s@.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]!.toUpperCase())
    .join("");
}

function AccountMenu() {
  const { email, logout } = useAuth();
  const profile = useProfile();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const name = profile.data?.full_name ?? email ?? "";

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !ref.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="flex items-center gap-2 rounded-full py-1 pl-1 pr-2.5 text-[14px] text-ink hover:bg-cream"
      >
        <span className="inline-flex size-8 items-center justify-center rounded-full bg-ink font-display text-[12px] font-bold text-paper">{initialsOf(name)}</span>
        <span className="hidden max-w-[140px] truncate font-medium sm:inline">{profile.data?.full_name ?? "Account"}</span>
        <ChevronDown size={14} className="text-muted" />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            role="menu"
            initial={{ opacity: 0, y: -6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.98 }}
            transition={{ duration: 0.16 }}
            className="absolute right-0 top-[calc(100%+8px)] z-50 w-64 origin-top-right rounded-panel border border-rule bg-paper p-2 shadow-float"
          >
            <div className="px-3 py-2">
              <p className="truncate text-[14px] font-semibold text-ink">{profile.data?.full_name ?? "Your account"}</p>
              <p className="truncate text-[13px] text-muted">{email}</p>
            </div>
            <div className="my-1 h-px bg-rule" />
            <Link role="menuitem" to="/profile" onClick={() => setOpen(false)} className="flex items-center gap-2.5 rounded-[8px] px-3 py-2 text-[14px] text-ink hover:bg-cream">
              <UserRound size={15} />
              Edit profile
            </Link>
            <button role="menuitem" type="button" onClick={logout} className="flex w-full items-center gap-2.5 rounded-[8px] px-3 py-2 text-left text-[14px] text-ink hover:bg-cream">
              <LogOut size={15} />
              Sign out
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/**
 * The application frame: an editorial masthead with tabs, not a dashboard
 * sidebar. On phones the tabs move to a bottom bar within thumb reach.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const location = useLocation();
  const account = useUserAccount();
  const isCuratorOrAdmin = account.data?.role === "curator" || account.data?.role === "admin";
  const navItems = isCuratorOrAdmin
    ? [...BASE_NAV, { to: "/curate", label: "Admin", icon: Shield }]
    : BASE_NAV;

  return (
    <div className="min-h-dvh bg-ivory pb-20 md:pb-0">
      <header className="sticky top-0 z-40 border-b border-rule bg-ivory/90 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-[1240px] items-center gap-8 px-4 sm:px-8">
          <Logo to="/discover" />
          <nav aria-label="Application" className="hidden h-full items-stretch gap-1 md:flex">
            {navItems.map(({ to, label }) => {
              const active = location.pathname.startsWith(to);
              return (
                <NavLink key={to} to={to} className={`relative flex items-center px-3 text-[14.5px] ${active ? "font-semibold text-ink" : "text-ink-soft hover:text-ink"}`}>
                  {label}
                  {active && <motion.span layoutId="masthead-tab" className="absolute inset-x-3 -bottom-px h-[3px] rounded-full bg-persimmon" transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }} />}
                </NavLink>
              );
            })}
          </nav>
          <div className="ml-auto flex items-center gap-4">
            <RunStatus />
            <ThemeToggle />
            <AccountMenu />
          </div>
        </div>
      </header>

      <main id="main">{children}</main>

      <nav aria-label="Application" className="fixed inset-x-0 bottom-0 z-40 border-t border-rule bg-paper/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md md:hidden">
        <ul className="flex items-center justify-around">
          {navItems.map(({ to, label, icon: Icon }) => {
            const active = location.pathname.startsWith(to);
            return (
              <li key={to} className="flex-1">
                <NavLink to={to} className={`flex h-16 flex-col items-center justify-center gap-1 text-[11px] ${active ? "font-semibold text-ink" : "text-muted"}`}>
                  <span className={`inline-flex h-7 w-12 items-center justify-center rounded-full transition-colors ${active ? "bg-lime text-night" : ""}`}>
                    <Icon size={18} strokeWidth={active ? 2.3 : 1.8} />
                  </span>
                  {label}
                </NavLink>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}

/** Masthead for public application pages (listing, detail). */
export function GuestShell({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const [menuOpen, setMenuOpen] = useMobileMenu();
  return (
    <div className="min-h-dvh bg-ivory">
      <header className="sticky top-0 z-40 border-b border-rule bg-ivory/90 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-[1240px] items-center gap-6 px-4 sm:px-8">
          <Logo />
          <nav aria-label="Main" className="hidden items-center gap-1 text-[14.5px] md:flex">
            <NavLink to="/opportunities" className={({ isActive }) => `px-3 py-2 ${isActive ? "font-semibold text-ink" : "text-ink-soft hover:text-ink"}`}>
              Opportunities
            </NavLink>
            <Link to="/#how-it-works" className="px-3 py-2 text-ink-soft hover:text-ink">
              How it works
            </Link>
            <Link to="/#engine" className="px-3 py-2 text-ink-soft hover:text-ink">
              The engine
            </Link>
          </nav>
          {/* Phones: the landing page's pattern, theme toggle plus the shared menu sheet, so nothing overflows. */}
          <div className="ml-auto flex items-center gap-1 sm:hidden">
            <ThemeToggle className="size-11" />
            <button
              type="button"
              className="btn btn-ghost size-11 px-0"
              aria-label={menuOpen ? "Close menu" : "Open menu"}
              aria-expanded={menuOpen}
              aria-controls="mobile-menu"
              onClick={() => setMenuOpen((value) => !value)}
            >
              {menuOpen ? <X size={22} /> : <Menu size={22} />}
            </button>
          </div>
          <div className="ml-auto hidden items-center gap-2 sm:flex">
            <ThemeToggle />
            {isAuthenticated ? (
              <Link to="/discover" className="btn btn-ink btn-sm">
                Open the app
              </Link>
            ) : (
              <>
                <Link to="/login" className="btn btn-ghost btn-sm">
                  Sign in
                </Link>
                <Link to="/register" className="btn btn-ink btn-sm">
                  Check my eligibility
                </Link>
              </>
            )}
          </div>
        </div>
      </header>
      <MobileMenuSheet open={menuOpen} onClose={() => setMenuOpen(false)} className="z-30 pt-[88px]" />
      <main id="main">{children}</main>
    </div>
  );
}

export function PageHeader({ kicker, title, description, actions }: { kicker?: string; title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
      <div className="min-w-0">
        {kicker && <p className="kicker mb-3">{kicker}</p>}
        <h1 className="display text-[44px] text-ink sm:text-[60px]">{title}</h1>
        {description && <p className="mt-4 max-w-[60ch] text-[16px] text-ink-soft">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
