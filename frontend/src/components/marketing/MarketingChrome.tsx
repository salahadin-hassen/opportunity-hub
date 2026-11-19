import { AnimatePresence, motion } from "motion/react";
import { ArrowUpRight, Menu, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router";
import { useOpportunities } from "../../api/queries";
import type { OpportunityType } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { TYPE_PLURALS } from "../../lib/format";
import { CompassRose, InkEdge } from "../landing/Atlas";
import { Logo, LogoMark } from "../ui/Logo";
import { ThemeToggle } from "../ui/ThemeToggle";

const LINKS = [
  { href: "/opportunities", label: "Opportunities" },
  { href: "/#how-it-works", label: "How it works" },
  { href: "/#open-now", label: "Open now" },
];

/** Open state for the phone menu sheet: closes on navigation and locks page scroll while open. */
export function useMobileMenu() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setOpen(false), [location.pathname, location.hash]);
  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);
  return [open, setOpen] as const;
}

const NUMERALS = ["I", "II", "III"];

/**
 * The phone menu sheet shared by the landing page and the public listing pages:
 * a modal panel in the atlas style. Escape closes it, focus moves in and stays
 * inside while it's open, and returns to the menu button afterwards.
 */
export function MobileMenuSheet({ open, onClose, className = "z-40 pt-[88px]" }: { open: boolean; onClose: () => void; className?: string }) {
  const { isAuthenticated } = useAuth();
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const opener = document.activeElement as HTMLElement | null;
    const focusables = () => [...(panel.current?.querySelectorAll<HTMLElement>("a[href], button:not([disabled])") ?? [])];
    window.setTimeout(() => focusables()[0]?.focus(), 80);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusables();
      if (items.length === 0) return;
      const first = items[0]!;
      const last = items[items.length - 1]!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      opener?.focus?.();
    };
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          ref={panel}
          id="mobile-menu"
          role="dialog"
          aria-modal="true"
          aria-label="Menu"
          initial={{ clipPath: "inset(0 0 100% 0)" }}
          animate={{ clipPath: "inset(0 0 0% 0)" }}
          exit={{ clipPath: "inset(0 0 100% 0)" }}
          transition={{ duration: 0.45, ease: [0.65, 0, 0.35, 1] }}
          className={`paper-grain fixed inset-0 flex flex-col overflow-hidden bg-[var(--atlas-bg,var(--color-ivory))] px-5 pb-[max(2rem,env(safe-area-inset-bottom))] lg:hidden ${className}`}
          style={{ ["--atlas-bg" as string]: "var(--color-ivory)" }}
        >
          <svg viewBox="0 0 200 200" className="pointer-events-none absolute -bottom-24 -right-24 size-[360px] text-ink opacity-[0.07]" aria-hidden="true">
            <g fill="none" stroke="currentColor" strokeWidth="0.8">
              <circle cx="100" cy="100" r="96" />
              <circle cx="100" cy="100" r="60" />
              {Array.from({ length: 16 }, (_, i) => {
                const a = (i * Math.PI) / 8;
                return <line key={i} x1={100} y1={100} x2={100 + Math.cos(a) * 96} y2={100 + Math.sin(a) * 96} />;
              })}
            </g>
            <path d="M100 8 L110 100 L100 192 L90 100 Z M8 100 L100 90 L192 100 L100 110 Z" fill="currentColor" />
          </svg>
          <nav aria-label="Mobile" className="relative flex flex-col">
            {LINKS.map((link, index) => (
              <motion.div
                key={link.href}
                initial={{ opacity: 0, x: -18 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.16 + index * 0.07, duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
              >
                <Link to={link.href} onClick={onClose} className="group flex items-baseline gap-4 border-b-[1.5px] border-ink py-5 text-ink active:translate-x-1">
                  <span className="w-8 font-[family-name:var(--font-serif)] text-[18px] text-muted">{NUMERALS[index]}</span>
                  <span className="serif-display min-w-0 flex-1 text-[clamp(26px,7.6vw,38px)]">{link.label}</span>
                  <ArrowUpRight size={22} className="transition-transform duration-300 group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
                </Link>
              </motion.div>
            ))}
          </nav>
          <motion.div
            className="relative mt-auto grid grid-cols-2 gap-3"
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.38, duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
          >
            {isAuthenticated ? (
              <Link to="/discover" className="btn-stamp btn-stamp-solid col-span-2">
                Open the app
              </Link>
            ) : (
              <>
                <Link to="/login" className="btn-stamp !px-3 !text-[12px]">
                  Sign in
                </Link>
                <Link to="/register" className="btn-stamp btn-stamp-solid !px-3 !text-[12px]">
                  Get started
                </Link>
              </>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function MarketingNav() {
  const { isAuthenticated } = useAuth();
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useMobileMenu();

  const location = useLocation();
  const [section, setSection] = useState<string | null>(null);
  useEffect(() => {
    const onScroll = () => {
      setScrolled(window.scrollY > 24);
      // On the landing page, mark the section in view (two lookups per scroll; no observers to manage).
      if (location.pathname !== "/") return setSection(null);
      const line = window.innerHeight * 0.4;
      let current: string | null = null;
      for (const id of ["how-it-works", "open-now"]) {
        const box = document.getElementById(id)?.getBoundingClientRect();
        if (box && box.top < line && box.bottom > line) current = id;
      }
      setSection(current);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [location.pathname]);

  return (
    <>
      <header
        className={`fixed inset-x-0 top-0 z-50 transition-[background-color,border-color] duration-300 ${
          scrolled || open ? "border-b border-rule bg-ivory/92 backdrop-blur-md" : "border-b border-transparent"
        }`}
      >
        <div className="mx-auto flex h-[72px] max-w-[1320px] items-center gap-10 px-5 sm:px-8">
          <Logo />
          <nav aria-label="Main" className="hidden items-center gap-7 text-[15px] lg:flex">
            {LINKS.map((link) => (
              <Link key={link.href} to={link.href} className="nav-ink" aria-current={section && link.href === `/#${section}` ? "location" : undefined}>
                {link.label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto hidden items-center gap-2 lg:flex">
            <ThemeToggle />
            {isAuthenticated ? (
              <Link to="/discover" className="btn btn-ink">
                Open the app
              </Link>
            ) : (
              <>
                <Link to="/login" className="btn btn-ghost">
                  Sign in
                </Link>
                <Link to="/register" className="btn btn-ink">
                  Check my eligibility
                </Link>
              </>
            )}
          </div>
          <div className="ml-auto flex items-center gap-1 lg:hidden">
          <ThemeToggle className="size-11" />
          <button
            type="button"
            className="btn btn-ghost size-11 px-0"
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            aria-controls="mobile-menu"
            onClick={() => setOpen((value) => !value)}
          >
            {open ? <X size={22} /> : <Menu size={22} />}
          </button>
          </div>
        </div>
      </header>

      <MobileMenuSheet open={open} onClose={() => setOpen(false)} />
    </>
  );
}

/** A footer link: a full-height touch target, with the masthead's ink underline drawn on hover. */
function FooterLink({ to, children, label }: { to: string; children: ReactNode; label?: string }) {
  return (
    <li>
      <Link to={to} aria-label={label} className="group inline-flex min-h-11 items-center gap-2 text-[15px] text-ink-soft transition-colors hover:text-ink lg:min-h-10">
        <span className="bg-[linear-gradient(currentColor,currentColor)] bg-[length:0%_1.5px] bg-left-bottom bg-no-repeat pb-0.5 transition-[background-size] duration-300 group-hover:bg-[length:100%_1.5px] motion-reduce:transition-none">
          {children}
        </span>
      </Link>
    </li>
  );
}

function FooterGroup({ title, children, className = "", listClassName = "" }: { title: string; children: ReactNode; className?: string; listClassName?: string }) {
  return (
    <div className={className}>
      <h2 className="small-caps text-[11px] text-muted">{title}</h2>
      <ul className={`mt-3 ${listClassName}`}>{children}</ul>
    </div>
  );
}

/**
 * The atlas's last page: the brand, the ways back into the index, and a
 * colophon line closed by the compass rose from the hero's chart.
 */
export function MarketingFooter() {
  const { isAuthenticated } = useAuth();
  // Published listings only (the public endpoint filters by status), so every count is one a visitor can open.
  const opportunities = useOpportunities();
  const all = opportunities.data ?? [];
  const counts = new Map<OpportunityType, number>();
  for (const item of all) counts.set(item.opportunity_type, (counts.get(item.opportunity_type) ?? 0) + 1);
  const kinds = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4);
  const count = (n: number) => <span className="num ml-1 text-[12.5px] text-muted">{n}</span>;

  return (
    <footer className="atlas paper-grain relative overflow-hidden">
      <InkEdge />

      <div className="mx-auto max-w-[1200px] px-5 pb-8 pt-12 sm:px-8 sm:pt-16 lg:pt-20">
        <div className="grid grid-cols-1 gap-y-11 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-x-16">
          <div>
            <Link to="/" className="inline-flex items-center gap-3 rounded-md font-display text-[24px] font-bold tracking-[-0.03em] text-ink sm:text-[26px]">
              <LogoMark size={34} />
              Opportunity Hub
            </Link>
            <p className="mt-5 max-w-[36ch] text-[16px] leading-[1.6] text-ink-soft">
              An atlas of scholarships, fellowships and research programs, each checked against the rules its organizers publish.
            </p>
          </div>

          <nav aria-label="Footer" className="grid grid-cols-2 gap-x-6 gap-y-9 sm:grid-cols-3 lg:pt-1">
            <FooterGroup title="Discover" className="col-span-2 sm:col-span-1" listClassName="grid grid-cols-2 gap-x-6 whitespace-nowrap sm:grid-cols-1">
              <FooterLink to="/opportunities" label={all.length ? `All opportunities: ${all.length}` : undefined}>
                All opportunities{all.length > 0 && count(all.length)}
              </FooterLink>
              {kinds.map(([type, n]) => (
                <FooterLink key={type} to={`/opportunities?type=${type}`} label={`${TYPE_PLURALS[type]}: ${n}`}>
                  {TYPE_PLURALS[type]}
                  {count(n)}
                </FooterLink>
              ))}
            </FooterGroup>
            <FooterGroup title="Explore">
              <FooterLink to="/#how-it-works">How it works</FooterLink>
              <FooterLink to="/#open-now">Open now</FooterLink>
              <FooterLink to={isAuthenticated ? "/eligibility" : "/register"}>Check eligibility</FooterLink>
            </FooterGroup>
            <FooterGroup title="Your account">
              {isAuthenticated ? (
                <>
                  <FooterLink to="/discover">Your matches</FooterLink>
                  <FooterLink to="/saved">Saved</FooterLink>
                  <FooterLink to="/applications">Applications</FooterLink>
                </>
              ) : (
                <>
                  <FooterLink to="/register">Create an account</FooterLink>
                  <FooterLink to="/login">Sign in</FooterLink>
                </>
              )}
            </FooterGroup>
          </nav>
        </div>

        {/* The colophon: a ruled line broken by the compass rose, then the fine print. */}
        <div className="mt-14 flex items-center gap-4 text-ink sm:mt-20" aria-hidden="true">
          <span className="h-px flex-1 bg-current opacity-80" />
          <svg viewBox="0 0 48 48" className="size-10 shrink-0">
            <CompassRose cx={24} cy={24} r={21} />
          </svg>
          <span className="h-px flex-1 bg-current opacity-80" />
        </div>
        <div className="mt-4 flex flex-col-reverse gap-1 text-[13px] text-muted sm:flex-row sm:items-center sm:justify-between">
          <p className="flex flex-col py-2 sm:flex-row sm:gap-1.5">
            <span>© {new Date().getFullYear()} Opportunity Hub</span>
            <span className="hidden sm:inline" aria-hidden="true">
              ·
            </span>
            <span>Every rule quoted from its official source</span>
          </p>
          <ul className="-mx-2 flex items-center">
            <li>
              <Link to="/privacy" className="inline-flex min-h-11 items-center px-2 text-ink-soft underline-offset-4 hover:text-ink hover:underline">
                Privacy
              </Link>
            </li>
            <li>
              <Link to="/credits" className="inline-flex min-h-11 items-center px-2 text-ink-soft underline-offset-4 hover:text-ink hover:underline">
                Credits
              </Link>
            </li>
          </ul>
        </div>
      </div>
    </footer>
  );
}
