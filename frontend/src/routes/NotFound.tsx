import { ArrowRight } from "lucide-react";
import { Link, useLocation } from "react-router";
import { Stamp } from "../components/landing/shared";
import { Page } from "../components/layout/Page";

/**
 * A cable come unplugged, drawn in the atlas's ink: the plug and the socket hang
 * apart with a spark between them. Outlines take the theme's ink and the fills
 * take the page's ground, so the drawing inverts cleanly in dark mode. The two
 * ends drift toward each other and back (still, with reduced motion).
 */
function Unplugged() {
  const tube = (d: string) => (
    <>
      <path d={d} fill="none" stroke="currentColor" strokeWidth="11" strokeLinecap="round" />
      <path d={d} fill="none" stroke="var(--atlas-bg, var(--color-ivory))" strokeWidth="6" strokeLinecap="round" />
    </>
  );
  return (
    <svg viewBox="0 70 880 170" className="block h-auto w-full text-ink" aria-hidden="true">
      <g className="unplug-left">
        {tube("M -30 214 C 70 206, 130 166, 222 160 S 296 150, 320 150")}
        <rect x="318" y="139" width="24" height="22" rx="4" fill="var(--atlas-bg, var(--color-ivory))" stroke="currentColor" strokeWidth="3" />
        <rect x="340" y="114" width="66" height="72" rx="11" fill="var(--atlas-bg, var(--color-ivory))" stroke="currentColor" strokeWidth="3.2" />
        <path d="M 356 138 H 382 M 356 150 H 382 M 356 162 H 382" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
        <rect x="406" y="129" width="32" height="10" rx="2.5" fill="var(--atlas-brass)" stroke="currentColor" strokeWidth="2.6" />
        <rect x="406" y="161" width="32" height="10" rx="2.5" fill="var(--atlas-brass)" stroke="currentColor" strokeWidth="2.6" />
      </g>
      <g className="unplug-sparks" stroke="var(--atlas-terra)" strokeWidth="3" strokeLinecap="round">
        <path d="M 458 112 V 92" />
        <path d="M 438 116 L 426 100" />
        <path d="M 478 116 L 490 100" />
        <path d="M 458 188 V 208" />
        <path d="M 438 184 L 426 200" />
        <path d="M 478 184 L 490 200" />
      </g>
      <g className="unplug-right">
        <rect x="478" y="114" width="66" height="72" rx="11" fill="var(--atlas-bg, var(--color-ivory))" stroke="currentColor" strokeWidth="3.2" />
        <rect x="488" y="131" width="16" height="7" rx="2" fill="currentColor" />
        <rect x="488" y="162" width="16" height="7" rx="2" fill="currentColor" />
        <path d="M 520 136 V 164" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
        <rect x="542" y="139" width="24" height="22" rx="4" fill="var(--atlas-bg, var(--color-ivory))" stroke="currentColor" strokeWidth="3" />
        {tube("M 566 150 C 600 150, 650 134, 726 132 S 840 152, 910 140")}
      </g>
    </svg>
  );
}

export function NotFound() {
  const { pathname } = useLocation();
  return (
    <Page title="Page not found">
      <div className="atlas flex min-h-dvh items-center">
        <main id="main" className="mx-auto flex w-full max-w-[960px] flex-col px-4 py-6 sm:px-8 sm:py-10">
          <div className="not-found paper-grain relative overflow-hidden border-[1.5px] border-ink px-5 pb-12 pt-8 text-center sm:px-12 sm:pb-14 sm:pt-10">
            <div className="pointer-events-none absolute inset-[7px] border border-ink/35" aria-hidden="true" />
            {/* On phones the cable runs off both edges, so the plug and socket stay large. */}
            <div className="-mx-5 overflow-hidden sm:-mx-12">
              <div className="relative left-1/2 w-[175%] -translate-x-1/2 sm:w-full">
                <Unplugged />
              </div>
            </div>
            <p className="serif-display relative -mt-2 text-[clamp(88px,17vw,168px)] leading-[0.9] text-ink" aria-hidden="true">
              404
            </p>
            <div className="mx-auto mt-1 h-3 w-[min(260px,50%)] rounded-[50%] bg-ink/10 blur-[3px]" aria-hidden="true" />
            <h1 className="serif-display mt-6 text-[clamp(26px,4.4vw,40px)] leading-[1.06] text-ink">
              <span className="sr-only">Page not found (error 404). </span>
              This page has come unplugged.
            </h1>
            <p className="mx-auto mt-4 max-w-[46ch] text-[15.5px] leading-relaxed text-ink-soft">
              There’s nothing at <code className="num break-all rounded bg-ink/[0.06] px-1.5 py-0.5 text-[14px] text-ink">{pathname}</code>. The link may be out of date, or the page has moved. Everything in the atlas is still where it was.
            </p>
            <div className="mt-9 flex flex-wrap items-center justify-center gap-x-6 gap-y-4">
              <Stamp to="/" solid>
                Go back home
                <ArrowRight size={16} />
              </Stamp>
              <Link to="/opportunities" className="auth-link inline-flex min-h-11 items-center text-[14.5px]">
                Browse opportunities
              </Link>
            </div>
          </div>
        </main>
      </div>
    </Page>
  );
}
