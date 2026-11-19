import { motion, useMotionValueEvent, useReducedMotion, useScroll, useTransform } from "motion/react";
import { ArrowRight } from "lucide-react";
import { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { Page } from "../components/layout/Page";
import { AtlasDefs, ExplorerGlobe, MapCloud, PortolanBackdrop } from "../components/landing/Atlas";
import { BleedGlobe, RegionChips, Stamp, useAtlas, useSceneActive, useVoyagePinned, voyageGlobe } from "../components/landing/shared";
import { MarketingFooter, MarketingNav } from "../components/marketing/MarketingChrome";
import { useMediaQuery } from "../hooks/useMediaQuery";

// Loaded after first paint: the turnable globe (with d3-geo and the world outline), then the scenes below the fold.
const loadExplorer = () => import("../components/landing/GlobeExplorer");
const GlobeExplorer = lazy(loadExplorer);
const LandingStory = lazy(() => import("./LandingStory"));

/** The opening plays once per visit: navigating back to the page shows it settled. */
const ENTRANCE_MS = 2400;
let atlasOpened = false;
/** How long to wait for the live globe before showing the (identical) static one. */
const STATIC_AFTER_MS = 700;

const glideEase = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);

/** A headline line that rises out of its own mask. */
function Line({ children, delay }: { children: React.ReactNode; delay: number }) {
  const reduced = useReducedMotion();
  return (
    <span className="block overflow-hidden pb-[0.04em]">
      <motion.span className="block" initial={reduced ? false : { y: "105%" }} animate={{ y: "0%" }} transition={{ duration: 1, delay, ease: [0.65, 0, 0.35, 1] }}>
        {children}
      </motion.span>
    </span>
  );
}

/** The static globe and its (disabled) controls, laid out exactly like the live explorer so the hand-over doesn't shift anything. */
function StaticGlobe({ compact, beside }: { compact: boolean; beside: boolean }) {
  return (
    <div>
      <BleedGlobe compact={compact}>
        <ExplorerGlobe compact={compact} className="block h-auto w-full" />
      </BleedGlobe>
      {/* The card's space, held where the live explorer puts it. */}
      {!beside && <div className={compact ? "mt-3 min-h-[196px]" : "mx-auto mt-3 min-h-[258px] max-w-[420px]"} />}
      <RegionChips compact={compact} />
    </div>
  );
}

function Hero() {
  const { all, upcoming, byCountry, isPending } = useAtlas();
  const reduced = Boolean(useReducedMotion());
  const compact = !useMediaQuery("(min-width: 640px)");
  const wide = useMediaQuery("(min-width: 1024px)");
  const ref = useRef<HTMLElement>(null);
  const active = useSceneActive(ref);
  const [entering, setEntering] = useState(!reduced && !atlasOpened);
  const [explorerReady, setExplorerReady] = useState(false);
  const [staticFallback, setStaticFallback] = useState(false);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const backdropY = useTransform(scrollYProgress, (v) => `${v * 14}%`);
  const globeY = useTransform(scrollYProgress, (v) => `${v * -5}%`);
  // Wide screens: as the hero scrolls away its globe stays in view and glides to where the atlas below
  // draws its own, shedding the stand, ring, pins and card; the atlas takes over at the same size and turn.
  const pinned = useVoyagePinned();
  const slot = useRef<HTMLDivElement>(null);
  const glide = useRef<HTMLDivElement>(null);
  const [handing, setHanding] = useState(false);
  const handingRef = useRef(false);
  // The slot never moves during the glide (it has no parallax when pinned), so its page position is
  // measured once and on resize: the per-frame work below reads only scrollY, never layout.
  const glideGeo = useRef<{ left: number; top: number; width: number; heroTop: number } | null>(null);
  const measureGlide = useCallback(() => {
    const box = slot.current;
    const hero = ref.current;
    if (!box || !hero) return null;
    const rect = box.getBoundingClientRect();
    glideGeo.current = { left: rect.left, top: rect.top + window.scrollY, width: rect.width, heroTop: hero.getBoundingClientRect().top + window.scrollY };
    return glideGeo.current;
  }, []);
  const glideTo = useCallback(
    (k: number) => {
      const el = glide.current;
      if (!el) return;
      const leaving = pinned && k > 0.01;
      if (leaving !== handingRef.current) {
        handingRef.current = leaving;
        setHanding(leaving);
      }
      el.classList.toggle("is-handing", leaving);
      if (!pinned || k <= 0) {
        el.style.transform = "";
        el.style.visibility = "";
        return;
      }
      const geo = glideGeo.current ?? measureGlide();
      if (!geo) return;
      const e = glideEase(Math.min(1, k));
      const w = geo.width;
      const scrolled = window.scrollY;
      // The sphere inside the explorer's 680 × 720 scene: centre (340, 300), radius 250.
      const ox = w * 0.5;
      const oy = w * (300 / 680);
      const nowX = geo.left + ox;
      const nowY = geo.top - scrolled + oy;
      const restY = nowY + (scrolled - geo.heroTop);
      const target = voyageGlobe(window.innerWidth, window.innerHeight);
      const dx = e * (target.x - nowX);
      const dy = restY + e * (target.y - restY) - nowY;
      const scale = 1 + e * (target.r / (w * (250 / 680)) - 1);
      el.style.transformOrigin = `${ox}px ${oy}px`;
      el.style.transform = `translate3d(${dx.toFixed(1)}px, ${dy.toFixed(1)}px, 0) scale(${scale.toFixed(4)})`;
      // Handed over: the atlas stage now draws this globe.
      el.style.visibility = k >= 0.999 ? "hidden" : "";
    },
    [pinned, measureGlide],
  );
  useMotionValueEvent(scrollYProgress, "change", glideTo);
  useEffect(() => {
    measureGlide();
    glideTo(scrollYProgress.get());
    const onResize = () => {
      measureGlide();
      glideTo(scrollYProgress.get());
    };
    window.addEventListener("resize", onResize);
    const observer = new ResizeObserver(onResize);
    observer.observe(document.body);
    return () => {
      window.removeEventListener("resize", onResize);
      observer.disconnect();
    };
  }, [glideTo, measureGlide, scrollYProgress]);

  useEffect(() => {
    let alive = true;
    // The live globe usually arrives while the headline is still rising; until then its space is held.
    void loadExplorer().then(() => alive && setExplorerReady(true));
    const fallback = window.setTimeout(() => alive && setStaticFallback(true), STATIC_AFTER_MS);
    const opened = window.setTimeout(() => {
      atlasOpened = true;
      if (alive) setEntering(false);
    }, reduced ? 0 : ENTRANCE_MS);
    return () => {
      alive = false;
      window.clearTimeout(fallback);
      window.clearTimeout(opened);
    };
  }, [reduced]);
  const delay = (seconds: number) => ({ animationDelay: `${seconds}s` });

  return (
    <section ref={ref} data-active={active} className={`paper-grain relative pt-[64px] sm:pt-[72px] ${pinned ? "z-[2] overflow-x-clip" : "overflow-hidden"} ${entering ? "atlas-enter" : ""}`}>
      <div className="absolute inset-0 overflow-hidden">
        <motion.div style={reduced ? undefined : { y: backdropY }} className="absolute inset-0">
          <PortolanBackdrop className="h-full w-full" />
        </motion.div>
      </div>
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        <div className="cloud-drift absolute right-[30%] top-[13%] hidden lg:block" style={{ ["--drift-time" as string]: "34s", ["--drift" as string]: "40px" }}>
          <MapCloud width={170} />
        </div>
        <div className="cloud-drift absolute right-[4%] top-[58%] hidden lg:block" style={{ ["--drift-time" as string]: "27s", ["--drift" as string]: "-30px" }}>
          <MapCloud width={120} />
        </div>
      </div>

      <div className="relative mx-auto grid max-w-[1440px] grid-cols-1 items-center gap-6 px-5 pb-10 pt-6 sm:gap-10 sm:px-8 sm:pb-16 sm:pt-10 lg:min-h-[calc(100dvh-72px)] lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:gap-6 lg:pb-8 lg:pt-0">
        <div className="relative z-10 max-w-[680px]">
          <p className="small-caps enter-fade text-[11px] text-ink-soft sm:text-[12px]" style={delay(0.05)}>
            <span className="sm:hidden">Scholarships · Fellowships · Research</span>
            <span className="hidden sm:inline">An atlas of scholarships, fellowships &amp; research</span>
          </p>
          <h1 className="serif-display mt-4 text-[clamp(40px,11.2vw,72px)] text-ink sm:mt-6 lg:text-[clamp(48px,4.6vw,78px)]">
            <Line delay={0.12}>Discover a</Line>{" "}
            <Line delay={0.22}>world of</Line>{" "}
            <Line delay={0.32}>opportunity.</Line>
          </h1>
          <p className="enter-fade mt-4 max-w-[42ch] text-[16px] leading-relaxed text-ink-soft sm:mt-7 sm:text-[18px]" style={delay(0.6)}>
            Programs from around the world, their eligibility rules quoted from the official pages, and where you stand before you apply.
          </p>
          <div className="enter-fade mt-6 flex flex-wrap items-center gap-x-5 gap-y-4 sm:mt-10 sm:gap-y-6" style={delay(0.75)}>
            <Stamp to="/opportunities" solid>
              Explore opportunities
              <ArrowRight size={16} />
            </Stamp>
            <Stamp to="/register" className="hidden sm:inline-flex">
              Check my eligibility
            </Stamp>
            <Link to="/register" className="inline-flex min-h-11 items-center gap-1.5 text-[14px] font-semibold text-ink underline decoration-1 underline-offset-4 sm:hidden">
              Check my eligibility
              <ArrowRight size={15} />
            </Link>
          </div>
          <p className="num enter-fade mt-6 text-[12.5px] text-muted sm:mt-10 sm:text-[13px]" style={delay(0.9)}>
            {isPending ? "Reading the index…" : `${all.length} listings · ${byCountry.size} countries · every rule quoted from its source`}
          </p>
        </div>

        <motion.div
          ref={slot}
          style={reduced || pinned ? undefined : { y: globeY }}
          className={compact ? "relative -mx-5 w-[calc(100%+40px)]" : "relative mx-auto w-full max-w-[min(100%,calc((100dvh-200px)*0.944))] lg:-mr-4"}
        >
          <div ref={glide} className="globe-handoff relative">
            {/* Lamplight: invisible by day, a warm pool behind the globe at night. */}
            <div className="handoff-fade pointer-events-none absolute inset-[6%_6%_18%] rounded-full bg-[radial-gradient(closest-side,var(--atlas-glow),transparent)]" aria-hidden="true" />
            <div className="relative">
              {explorerReady ? (
                <Suspense fallback={<StaticGlobe compact={compact} beside={wide} />}>
                  <GlobeExplorer all={all} upcoming={upcoming} compact={compact} heroActive={active && !handing} reduced={reduced} entering={entering} loading={isPending} beside={wide} />
                </Suspense>
              ) : staticFallback ? (
                <StaticGlobe compact={compact} beside={wide} />
              ) : (
                <div className={compact ? "aspect-[652/612]" : "aspect-[680/720]"} aria-hidden="true" />
              )}
            </div>
            {!compact && (
              <p className="enter-fade handoff-fade mt-2 text-center text-[12px] text-muted" style={delay(1.6)}>
                Drag to turn the globe, choose a pin, or let it take you on a tour.
              </p>
            )}
          </div>
        </motion.div>
      </div>
    </section>
  );
}

export function Landing() {
  return (
    <Page title="Opportunity Hub">
      <div className="atlas nav-enter">
        <AtlasDefs />
        <MarketingNav />
        <main id="main">
          <Hero />
          <Suspense fallback={<div className="min-h-[100dvh]" aria-busy="true" />}>
            <LandingStory />
          </Suspense>
        </main>
        <MarketingFooter />
      </div>
    </Page>
  );
}
