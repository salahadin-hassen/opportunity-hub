import { AnimatePresence, motion } from "motion/react";
import { ArrowUpRight, Menu, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router";
import { useAuth } from "../../auth/AuthContext";
import { Logo } from "../ui/Logo";
import { ThemeToggle } from "../ui/ThemeToggle";

const LINKS = [
  { href: "/opportunities", label: "Opportunities" },
  { href: "/#how-it-works", label: "How it works" },
  { href: "/#engine", label: "The engine" },
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

/** The phone menu sheet shared by the landing page and the public listing pages. */
export function MobileMenuSheet({ open, onClose, className = "z-40 pt-[96px]" }: { open: boolean; onClose: () => void; className?: string }) {
  const { isAuthenticated } = useAuth();
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          id="mobile-menu"
          initial={{ clipPath: "inset(0 0 100% 0)" }}
          animate={{ clipPath: "inset(0 0 0% 0)" }}
          exit={{ clipPath: "inset(0 0 100% 0)" }}
          transition={{ duration: 0.45, ease: [0.65, 0, 0.35, 1] }}
          className={`fixed inset-0 flex flex-col bg-ivory px-5 pb-8 lg:hidden ${className}`}
        >
          <nav aria-label="Mobile" className="flex flex-col">
            {LINKS.map((link, index) => (
              <motion.div
                key={link.href}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.15 + index * 0.06, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
              >
                <Link to={link.href} onClick={onClose} className="flex items-center justify-between border-b border-rule py-4 font-display text-[34px] font-bold tracking-[-0.04em] text-ink">
                  {link.label}
                  <ArrowUpRight size={24} className="text-persimmon" />
                </Link>
              </motion.div>
            ))}
          </nav>
          <div className="mt-auto grid grid-cols-2 gap-3">
            {isAuthenticated ? (
              <Link to="/discover" className="btn btn-ink btn-lg col-span-2">
                Open the app
              </Link>
            ) : (
              <>
                <Link to="/login" className="btn btn-quiet btn-lg">
                  Sign in
                </Link>
                <Link to="/register" className="btn btn-ink btn-lg">
                  Get started
                </Link>
              </>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function MarketingNav() {
  const { isAuthenticated } = useAuth();
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useMobileMenu();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

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
              <Link key={link.href} to={link.href} className="text-ink-soft transition-colors hover:text-ink">
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

export function MarketingFooter() {
  return (
    <footer className="overflow-hidden bg-ivory">
      <div className="mx-auto max-w-[1320px] px-5 pt-20 sm:px-8">
        <div className="grid grid-cols-1 gap-10 border-t border-ink pt-10 md:grid-cols-[minmax(0,2fr)_repeat(3,minmax(0,1fr))]">
          <p className="max-w-[34ch] text-[15px] text-ink-soft">
            Scholarships, internships and research programs, checked against the rules their organizers publish.
          </p>
          <div>
            <p className="text-[13px] font-semibold text-ink">Explore</p>
            <ul className="mt-3 flex flex-col gap-2 text-[14.5px] text-ink-soft">
              <li><Link to="/opportunities" className="hover:text-ink">Opportunities</Link></li>
              <li><Link to="/#how-it-works" className="hover:text-ink">How it works</Link></li>
              <li><Link to="/#engine" className="hover:text-ink">The engine</Link></li>
            </ul>
          </div>
          <div>
            <p className="text-[13px] font-semibold text-ink">Account</p>
            <ul className="mt-3 flex flex-col gap-2 text-[14.5px] text-ink-soft">
              <li><Link to="/register" className="hover:text-ink">Create an account</Link></li>
              <li><Link to="/login" className="hover:text-ink">Sign in</Link></li>
            </ul>
          </div>
          <div>
            <p className="text-[13px] font-semibold text-ink">About</p>
            <ul className="mt-3 flex flex-col gap-2 text-[14.5px] text-ink-soft">
              <li><Link to="/privacy" className="hover:text-ink">Privacy</Link></li>
              <li><Link to="/credits" className="hover:text-ink">Photography credits</Link></li>
            </ul>
          </div>
        </div>
        <p className="mt-12 max-w-[70ch] text-[13px] text-muted">
          Verdicts compare your profile with published rules. They aren’t admissions, awards or approvals, and they’re only as current as the
          official pages. Confirm there before you apply.
        </p>
      </div>
      <div className="mx-auto mt-10 max-w-[1320px] px-3 sm:px-6" aria-hidden="true">
        <p className="display translate-y-[18%] select-none whitespace-nowrap text-[15.2vw] leading-none text-ink xl:text-[200px]">Opportunity Hub</p>
      </div>
    </footer>
  );
}
