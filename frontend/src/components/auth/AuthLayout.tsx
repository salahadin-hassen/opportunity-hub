/**
 * The entrance to the atlas: the shared frame of every authentication screen
 * (sign in, create account, forgot and reset password, the Google return).
 *
 * Wide screens: a framed atlas plate (the landing page's engraved globe, its
 * rhumb lines and compass rose: static drawings already in the main bundle, no
 * interactive globe) beside a calm form column. Phones: no illustration block,
 * just a slim cartographic band above the heading, so the form starts high.
 *
 * The plate's entrance plays once per visit, and the form is usable at once.
 */
import { AlertCircle, CheckCircle2, Info } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { AtlasDefs, CompassRose, ExplorerGlobe, PortolanBackdrop } from "../landing/Atlas";
import { Logo } from "../ui/Logo";
import { ThemeToggle } from "../ui/ThemeToggle";

/** The plate's entrance plays on the first authentication screen of a visit only. */
let entered = false;

/** A route drawn across the plate to a pin on the globe (scene units of the 680 × 720 globe drawing). */
function PlateRoute() {
  return (
    <svg viewBox="0 0 680 720" className="pointer-events-none absolute inset-0 h-full w-full overflow-visible" aria-hidden="true">
      <defs>
        <mask id="auth-route-reveal" maskUnits="userSpaceOnUse" x="-100" y="0" width="900" height="900">
          <path className="auth-route" d="M 34 640 C 96 600, 112 528, 170 474 S 250 420, 268 352" pathLength={1} fill="none" stroke="#fff" strokeWidth="8" />
        </mask>
      </defs>
      <path d="M 34 640 C 96 600, 112 528, 170 474 S 250 420, 268 352" fill="none" stroke="var(--atlas-terra)" strokeWidth="2.2" strokeDasharray="8 7" strokeLinecap="round" mask="url(#auth-route-reveal)" />
      <g className="auth-pin" transform="translate(268 352)">
        <circle r="13" fill="none" stroke="var(--atlas-terra)" strokeWidth="1.6" opacity="0.5" />
        <path d="M0 0 C -1.6 -5.2, -8.6 -10.4, -8.6 -18.2 A 8.6 8.6 0 1 1 8.6 -18.2 C 8.6 -10.4, 1.6 -5.2, 0 0 Z" fill="var(--atlas-terra)" stroke="var(--atlas-ink)" strokeWidth="1.6" strokeLinejoin="round" />
        <circle cx="0" cy="-18.2" r="3.4" fill="var(--atlas-paper)" stroke="var(--atlas-ink)" strokeWidth="1.2" />
      </g>
      <g transform="translate(34 640)">
        <g className="auth-rose text-[var(--atlas-ink)]">
          <circle r="34" fill="var(--atlas-paper)" opacity="0.85" />
          <CompassRose cx={0} cy={0} r={30} />
        </g>
      </g>
    </svg>
  );
}

/** The illustrated plate: a framed page of the atlas. */
function AtlasPlate({ animate }: { animate: boolean }) {
  return (
    <div className={`relative hidden lg:block ${animate ? "atlas-enter auth-enter" : ""}`}>
      <div className="sticky top-0 h-dvh p-5">
        {/* A double-ruled plate frame, as on an engraved atlas page. */}
        <div className="auth-plate paper-grain relative flex h-full flex-col overflow-hidden border-[1.5px] border-ink">
          <div className="pointer-events-none absolute inset-[7px] border border-ink/40" aria-hidden="true" />
          <PortolanBackdrop className="absolute inset-0 h-full w-full text-ink" cx={720} cy={470} />
          <div className="relative flex items-center justify-between px-9 pt-8 text-ink-soft" aria-hidden="true">
            <span className="small-caps text-[10.5px]">Opportunity Hub · Plate I</span>
            <span className="small-caps hidden text-[10.5px] xl:inline">The world of opportunity</span>
          </div>
          <div className="relative flex min-h-0 flex-1 items-center justify-center px-10" aria-hidden="true">
            <div className="relative aspect-[680/720] h-full max-h-[min(62vh,600px)] max-w-full">
              <ExplorerGlobe className="block h-full w-full" />
              <PlateRoute />
            </div>
          </div>
          <div className="relative px-9 pb-9">
            <p className="serif-display max-w-[18ch] text-[clamp(30px,2.6vw,44px)] leading-[1.04] text-ink">Every verdict shows its work.</p>
            <p className="mt-3 max-w-[48ch] text-[15px] leading-relaxed text-ink-soft">
              Each program’s rules are quoted from its official page and checked against your profile one at a time. Anything a machine can’t decide is left for you.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

/** On phones: a slim band with the compass, a route and its pin, instead of an illustration block. */
function PhoneMotif({ animate }: { animate: boolean }) {
  return (
    <svg viewBox="0 0 320 40" className={`block h-10 w-full text-ink lg:hidden ${animate ? "auth-enter" : ""}`} aria-hidden="true">
      <defs>
        <mask id="auth-band-reveal" maskUnits="userSpaceOnUse" x="0" y="0" width="320" height="40">
          <path className="auth-route" d="M 34 24 C 90 6, 150 34, 210 18 S 280 14, 296 22" pathLength={1} fill="none" stroke="#fff" strokeWidth="6" />
        </mask>
      </defs>
      <line x1="0" y1="38.5" x2="320" y2="38.5" stroke="currentColor" strokeOpacity="0.25" />
      <path d="M 34 24 C 90 6, 150 34, 210 18 S 280 14, 296 22" fill="none" stroke="var(--atlas-terra)" strokeWidth="1.6" strokeDasharray="5 4" strokeLinecap="round" mask="url(#auth-band-reveal)" />
      <g transform="translate(18 21)">
        <g className="auth-rose">
          <CompassRose cx={0} cy={0} r={15} />
        </g>
      </g>
      <g className="auth-pin" transform="translate(300 24) scale(0.8)">
        <path d="M0 0 C -1.6 -5.2, -8.6 -10.4, -8.6 -18.2 A 8.6 8.6 0 1 1 8.6 -18.2 C 8.6 -10.4, 1.6 -5.2, 0 0 Z" fill="var(--atlas-terra)" stroke="var(--atlas-ink)" strokeWidth="1.6" strokeLinejoin="round" />
        <circle cx="0" cy="-18.2" r="3.4" fill="var(--atlas-paper)" stroke="var(--atlas-ink)" strokeWidth="1.2" />
      </g>
    </svg>
  );
}

export function AuthFrame({ kicker, title, subtitle, children, footer }: { kicker: string; title: ReactNode; subtitle?: ReactNode; children: ReactNode; footer?: ReactNode }) {
  const [animate] = useState(() => !entered);
  useEffect(() => {
    entered = true;
  }, []);
  return (
    <div className="atlas auth grid min-h-dvh grid-cols-1 lg:grid-cols-[minmax(0,1.04fr)_minmax(0,1fr)]">
      <AtlasDefs />
      <AtlasPlate animate={animate} />
      <div className="flex min-h-dvh flex-col px-5 sm:px-10">
        <header className="flex h-16 items-center justify-between sm:h-20">
          <Logo />
          <ThemeToggle className="-my-2" />
        </header>
        <main id="main" className="flex flex-1 flex-col pb-10 pt-2 sm:pt-6 lg:justify-center lg:pt-0">
          <div className="mx-auto w-full max-w-[420px]">
            <PhoneMotif animate={animate} />
            <p className={`small-caps mt-5 text-[11px] text-ink-soft lg:mt-0 ${animate ? "auth-rise" : ""}`}>{kicker}</p>
            <h1 className={`serif-display mt-3 text-[clamp(34px,8.6vw,52px)] leading-[1.02] text-ink ${animate ? "auth-rise" : ""}`}>{title}</h1>
            {subtitle && <p className="mt-4 text-[15.5px] leading-relaxed text-ink-soft">{subtitle}</p>}
            <div className="mt-8">{children}</div>
            {footer && <div className="mt-8 border-t border-ink/15 pt-6 text-[14px] text-ink-soft">{footer}</div>}
          </div>
        </main>
        <footer className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1 py-5 text-[12.5px] text-muted">
          <Link to="/" className="inline-flex min-h-10 items-center hover:text-ink">
            ← Back to the atlas
          </Link>
          <Link to="/privacy" className="inline-flex min-h-10 items-center hover:text-ink">
            What we store
          </Link>
        </footer>
      </div>
    </div>
  );
}

/** A notice on an authentication screen: an icon and words, never colour alone. */
export function AuthNotice({ tone, children, id }: { tone: "ok" | "error" | "info"; children: ReactNode; id?: string }) {
  const Icon = tone === "ok" ? CheckCircle2 : tone === "error" ? AlertCircle : Info;
  const style =
    tone === "ok"
      ? "border-eligible/40 bg-eligible-wash text-eligible-ink"
      : tone === "error"
        ? "border-ineligible/40 bg-ineligible-wash text-ineligible-ink"
        : "border-potential/45 bg-potential-wash text-potential-ink";
  return (
    <div id={id} role={tone === "error" ? "alert" : "status"} className={`auth-notice flex items-start gap-2.5 border-[1.5px] px-4 py-3 text-[14px] leading-snug ${style}`}>
      <Icon size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
      <div>{children}</div>
    </div>
  );
}

/** A field's error, with an icon so it doesn't rely on colour. */
export function AuthFieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <p id={id} className="auth-field-error mt-1.5 flex items-start gap-1.5 text-[13px] text-ineligible-ink">
      <AlertCircle size={14} className="mt-[2px] shrink-0" aria-hidden="true" />
      <span>{message}</span>
    </p>
  );
}
