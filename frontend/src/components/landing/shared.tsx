import { motion, useReducedMotion } from "motion/react";
import { useEffect, useMemo, useState, type RefObject } from "react";
import { Link } from "react-router";
import { useOpportunities } from "../../api/queries";
import type { OpportunityType } from "../../api/types";
import { deadlineInfo } from "../../lib/format";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { Ticks } from "./Ink";

export const EASE = [0.22, 1, 0.36, 1] as const;
/** Codes in the catalogue that aren't countries ("GLOBAL", "EU"): never pinned or counted as places. */
export const isCountry = (code: string) => /^[A-Z]{2}$/.test(code) && code !== "EU";
/** The listing whose real rule illustrates "Find your direction" (any cycle of it). */
export const SPECIMEN_SLUG = "kaust-visiting-student-research-program";

/** Everything the page shows, derived once from the real catalogue. */
export function useAtlas() {
  const query = useOpportunities();
  const { data, isPending, isError, refetch } = query;
  return useMemo(() => {
    const all = data ?? [];
    const upcoming = all
      .map((item) => ({ item, info: deadlineInfo(item) }))
      .filter(({ info }) => info.state === "open" || info.state === "soon")
      .sort((a, b) => a.info.sortKey - b.info.sortKey)
      .map(({ item }) => item);
    const byCountry = new Map<string, number>();
    for (const item of all) for (const code of new Set((item.countries ?? []).map(String))) if (isCountry(code)) byCountry.set(code, (byCountry.get(code) ?? 0) + 1);
    const byType = new Map<OpportunityType, number>();
    for (const item of all) byType.set(item.opportunity_type, (byType.get(item.opportunity_type) ?? 0) + 1);
    const types = [...byType.entries()].sort((a, b) => b[1] - a[1]);
    const specimenId = all.find((item) => item.slug.startsWith(SPECIMEN_SLUG))?.id;
    return { all, upcoming, byCountry, types, specimenId, isPending, isError, refetch: () => void refetch() };
  }, [data, isPending, isError, refetch]);
}

export function Stamp({ to, children, solid = false, className = "" }: { to: string; children: React.ReactNode; solid?: boolean; className?: string }) {
  return (
    <Link to={to} className={`btn-stamp ${solid ? "btn-stamp-solid" : ""} ${className}`}>
      <Ticks />
      {children}
    </Link>
  );
}

/** A heading that arrives grainy and sharpens, as the reference's second headline does. */
export function Sharpen({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  const reduced = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduced ? false : { opacity: 0, filter: "blur(10px)", x: 24 }}
      whileInView={{ opacity: 1, filter: "blur(0px)", x: 0 }}
      viewport={{ once: true, margin: "-120px" }}
      transition={{ duration: 1.1, ease: EASE }}
    >
      {children}
    </motion.div>
  );
}


/** Regions the globe can turn to: a label and the point to centre on. Classification lives with the world data. */
export const REGIONS = [
  { key: "europe", label: "Europe", lon: 12, lat: 50 },
  { key: "africa", label: "Africa", lon: 20, lat: 4 },
  { key: "asia", label: "Middle East & Asia", lon: 80, lat: 28 },
  { key: "americas", label: "Americas", lon: -78, lat: 18 },
  { key: "oceania", label: "Oceania", lon: 140, lat: -26 },
] as const;
export type RegionKey = (typeof REGIONS)[number]["key"];

/**
 * Buttons that turn the globe toward a part of the world. Rendered disabled by
 * the static globe (same size, so nothing shifts) and live by the explorer.
 */
export function RegionChips({
  current,
  onPick,
  counts,
  compact = false,
}: {
  current?: RegionKey | null;
  onPick?: (key: RegionKey) => void;
  counts?: Map<RegionKey, number>;
  compact?: boolean;
}) {
  return (
    <div className={`handoff-fade relative mt-4 ${compact ? "" : "flex justify-center"}`}>
      <div
        role="group"
        aria-label="Turn the globe to a region"
        className={`flex gap-2 overflow-x-auto py-1 [scrollbar-width:none] ${compact ? "snap-x px-5" : "flex-wrap justify-center"}`}
      >
        {REGIONS.map((region) => {
          const active = current === region.key;
          const count = counts?.get(region.key);
          return (
            <button
              key={region.key}
              type="button"
              disabled={!onPick}
              aria-pressed={active}
              onClick={() => onPick?.(region.key)}
              className={`region-chip snap-start ${active ? "is-active" : ""}`}
            >
              {region.label}
              {count !== undefined && <span className="num text-[11px] opacity-70">{count}</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Whether a scene is on screen. Scenes put this on data-active, which pauses
 * their ambient CSS motion while they're out of view (see app.css).
 */
export function useSceneActive(ref: RefObject<Element | null>, margin = "0px"): boolean {
  const [active, setActive] = useState(true);
  useEffect(() => {
    const node = ref.current;
    if (!node || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(([entry]) => setActive(Boolean(entry?.isIntersecting)), { rootMargin: margin });
    observer.observe(node);
    return () => observer.disconnect();
  }, [ref, margin]);
  return active;
}

/**
 * A one-shot entrance for a scene: "pre" while waiting (parts hidden), "in" once
 * it scrolls into view. Nothing is hidden with reduced motion or before JS runs.
 */
export function useEntrance(ref: RefObject<Element | null>, reduced: boolean): string {
  const [state, setState] = useState<"" | "pre" | "in">("");
  useEffect(() => {
    const node = ref.current;
    if (reduced || !node || typeof IntersectionObserver === "undefined") return;
    // Already on screen (e.g. arriving by an anchor link): show at once, no hiding.
    const box = node.getBoundingClientRect();
    if (box.top < window.innerHeight * 0.85 && box.bottom > 0) return setState("in");
    setState("pre");
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          setState("in");
          observer.disconnect();
        }
      },
      { rootMargin: "0px 0px -8% 0px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [ref, reduced]);
  return state;
}

/** On phones the globe bleeds past both edges (it reads larger), while the controls below stay inside the page. */
export function BleedGlobe({ compact, children }: { compact: boolean; children: React.ReactNode }) {
  if (!compact) return <>{children}</>;
  // Phones show the globe's upper part: still the largest thing on screen, with the tour's card close below.
  return (
    <div className="max-h-[min(92vw,380px)] overflow-hidden">
      <div className="relative left-1/2 w-[114%] -translate-x-1/2">{children}</div>
    </div>
  );
}

/*
 * The hand-off between the hero globe and the unfolding atlas below it.
 * The hero's globe publishes where it is pointing; on wide screens it glides to
 * the atlas stage's globe position as the hero scrolls away, and the stage takes
 * over from the same rotation, size and tilt, so it reads as one globe.
 */
export const globeView: { rotation: [number, number] } = { rotation: [-18, -14] };

/** Where the atlas stage draws its globe (viewport px): the hero globe lands exactly here. */
export function voyageGlobe(width: number, height: number) {
  return { x: width * 0.56, y: height * 0.56, r: Math.min(height * 0.3, width * 0.19) };
}

/** The pinned, scroll-driven atlas (and the hero's glide into it): wide, tall-enough screens without reduced motion. */
export function useVoyagePinned(): boolean {
  const reduced = useReducedMotion();
  const wide = useMediaQuery("(min-width: 1024px) and (min-height: 600px)");
  return wide && !reduced;
}
