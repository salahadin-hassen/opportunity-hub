/**
 * The hero's discovery tour: the globe travels between real upcoming
 * opportunities, a map pin lands on each, and an atlas card introduces the
 * listing. The visitor can take over at any time (drag, pins, regions, the
 * card's controls); the tour holds while they read or focus anything inside,
 * and picks up again after a quiet spell unless they paused it.
 *
 * Every stop is a published listing with a published, future deadline and a
 * country we can place on the map. Nothing is synthesised: a small catalogue
 * simply makes a short tour, and an empty one shows no tour at all.
 */
import { AnimatePresence, motion } from "motion/react";
import { geoDistance } from "d3-geo";
import { ArrowRight, ChevronLeft, ChevronRight, Pause, Play } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import type { Opportunity } from "../../api/types";
import { TYPE_LABELS, countryName, deadlineInfo, plural } from "../../lib/format";
import { deadlineWords } from "../opportunities/OpportunityRow";
import { GLOBE_SCENE } from "./Atlas";
import { regionOf } from "./geo-land";
import { COUNTRY_CENTRES } from "./geo-world";
import { LiveGlobe, type GlobeHandle } from "./LiveGlobe";
import { BleedGlobe, EASE, REGIONS, RegionChips, isCountry, type RegionKey } from "./shared";

/** Tour timing (ms): calm enough to read, never a screensaver. */
const TRAVEL = 1500;
const SHOW = 4200;
const LEAVE = 320;
/** After a visitor takes over, the tour waits this long before carrying on. */
const IDLE_RESUME = 12_000;
/** The first stop is reached as the entrance finishes. */
const FIRST_DELAY = 650;
const MAX_STOPS = 9;

export type Stop = { opportunity: Opportunity; code: string };

const placeOf = (item: Opportunity) => (item.countries ?? []).map(String).find((code) => isCountry(code) && COUNTRY_CENTRES[code]);
const centreOf = (code: string) => COUNTRY_CENTRES[code]! as [number, number];

/** One upcoming listing per country, as a route: start at the soonest deadline, then always travel to the nearest unvisited stop. */
function planTour(upcoming: Opportunity[]): Stop[] {
  const stops: Stop[] = [];
  for (const item of upcoming) {
    const code = placeOf(item);
    if (code && !stops.some((stop) => stop.code === code)) stops.push({ opportunity: item, code });
    if (stops.length === MAX_STOPS) break;
  }
  if (stops.length < 3) return stops;
  const route = [stops.shift()!];
  while (stops.length) {
    const here = centreOf(route[route.length - 1]!.code);
    let best = 0;
    stops.forEach((stop, index) => {
      if (geoDistance(here, centreOf(stop.code)) < geoDistance(here, centreOf(stops[best]!.code))) best = index;
    });
    route.push(stops.splice(best, 1)[0]!);
  }
  return route;
}

export default function GlobeExplorer({
  all,
  upcoming,
  compact,
  heroActive,
  reduced,
  entering,
  loading,
  beside,
}: {
  all: Opportunity[];
  upcoming: Opportunity[];
  compact: boolean;
  heroActive: boolean;
  reduced: boolean;
  /** The page's entrance is still playing: the first stop waits for it. */
  entering: boolean;
  /** The catalogue hasn't arrived yet (so an empty tour means "not yet", not "nothing"). */
  loading: boolean;
  /** Wide screens: the card sits beside the globe with a leader line to the pin; otherwise below it. */
  beside: boolean;
}) {
  const globe = useRef<GlobeHandle>(null);
  const leader = useRef<SVGPathElement>(null);
  const card = useRef<HTMLDivElement>(null);
  const area = useRef<HTMLDivElement>(null);

  const pins = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of all) for (const code of new Set((item.countries ?? []).map(String))) if (isCountry(code)) counts.set(code, (counts.get(code) ?? 0) + 1);
    return [...counts.entries()].map(([code, count]) => ({ code, count, label: countryName(code) }));
  }, [all]);
  const countIn = useMemo(() => new Map(pins.map((pin) => [pin.code, pin.count])), [pins]);
  const stops = useMemo(() => planTour(upcoming), [upcoming]);
  const regionCounts = useMemo(() => {
    const out = new Map<RegionKey, number>();
    for (const item of all) {
      const regions = new Set((item.countries ?? []).map(String).filter(isCountry).map(regionOf).filter(Boolean) as RegionKey[]);
      for (const key of regions) out.set(key, (out.get(key) ?? 0) + 1);
    }
    return out;
  }, [all]);

  // Where we are on the tour, or a visitor's own choice outside it.
  const [cursor, setCursor] = useState(0);
  const [detour, setDetour] = useState<Stop | null>(null);
  const [trip, setTrip] = useState(0);
  const [phase, setPhase] = useState<"travel" | "show" | "leave">("travel");
  const [landing, setLanding] = useState(0);
  const [visited, setVisited] = useState<Set<string>>(new Set());
  const [paused, setPaused] = useState(reduced); // explicit, sticky
  const [idle, setIdle] = useState(false); // a visitor just took over; clears itself
  const [focusInside, setFocusInside] = useState(false);
  const [pointerOnCard, setPointerOnCard] = useState(false);
  const [region, setRegion] = useState<RegionKey | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const idleTimer = useRef(0);
  const current = detour ?? stops[cursor] ?? null;
  const currentRef = useRef(current);
  currentRef.current = current;
  const holding = paused || idle || focusInside || pointerOnCard || !heroActive;
  const hasStops = stops.length > 0;

  /** A visitor did something: hold the tour, and let it carry on after a quiet spell. */
  const takeOver = useCallback(() => {
    setIdle(true);
    window.clearTimeout(idleTimer.current);
    idleTimer.current = window.setTimeout(() => setIdle(false), IDLE_RESUME);
  }, []);
  useEffect(() => () => window.clearTimeout(idleTimer.current), []);

  // Travel to the current stop whenever a new trip starts (or the tour first becomes available).
  const entranceRef = useRef(entering);
  useEffect(() => {
    const stop = currentRef.current;
    if (!stop) return;
    setPhase("travel");
    const [lon, lat] = centreOf(stop.code);
    const first = trip === 0;
    const timer = window.setTimeout(
      () =>
        globe.current?.travelTo(lon, lat, reduced ? 0 : TRAVEL, () => {
          setPhase("show");
          setLanding((n) => n + 1);
          setVisited((old) => (old.has(stop.code) ? old : new Set(old).add(stop.code)));
        }),
      first && entranceRef.current && !reduced ? FIRST_DELAY : 0,
    );
    return () => window.clearTimeout(timer);
  }, [trip, hasStops, reduced]);

  // Show, then leave, then on to the next stop: only while nobody is holding the tour.
  useEffect(() => {
    if (phase !== "show" || holding || stops.length < 2) return;
    const timer = window.setTimeout(() => setPhase("leave"), SHOW);
    return () => window.clearTimeout(timer);
  }, [phase, holding, stops.length, trip]);
  useEffect(() => {
    if (phase !== "leave") return;
    const timer = window.setTimeout(() => {
      setCursor((old) => (detour ? old : (old + 1) % stops.length));
      setDetour(null);
      setTrip((old) => old + 1);
    }, LEAVE);
    return () => window.clearTimeout(timer);
  }, [phase, detour, stops.length]);

  function announce(stop: Stop) {
    const deadline = deadlineInfo(stop.opportunity);
    setAnnouncement(`${stop.opportunity.title}, ${stop.opportunity.host_name ?? ""}, ${countryName(stop.code)}. Deadline ${deadline.label}.`);
  }
  function goToStop(index: number) {
    if (!stops.length) return;
    const next = (index + stops.length) % stops.length;
    setDetour(null);
    setCursor(next);
    setTrip((old) => old + 1);
    announce(stops[next]!);
  }
  function goToCountry(code: string) {
    takeOver();
    const index = stops.findIndex((stop) => stop.code === code);
    if (index >= 0) return goToStop(index);
    // Not on the tour: show this country's soonest open listing, or any open one.
    const inCountry = all.filter((item) => (item.countries ?? []).map(String).includes(code) && deadlineInfo(item).state !== "closed");
    const listing = upcoming.find((item) => inCountry.includes(item)) ?? inCountry[0];
    if (!listing) return;
    const stop = { opportunity: listing, code };
    setDetour(stop);
    setTrip((old) => old + 1);
    announce(stop);
  }
  function pickRegion(key: RegionKey) {
    setRegion(key);
    takeOver();
    const index = stops.findIndex((stop) => regionOf(stop.code) === key);
    if (index >= 0) return goToStop(index);
    const busiest = [...pins].filter((pin) => regionOf(pin.code) === key).sort((a, b) => b.count - a.count)[0];
    if (busiest) goToCountry(busiest.code);
    else {
      const target = REGIONS.find((entry) => entry.key === key)!;
      globe.current?.travelTo(target.lon, target.lat, reduced ? 0 : TRAVEL);
    }
  }

  /** Keep the leader line from the card's corner to the active pin. */
  const onActiveMove = useCallback((point: [number, number] | null) => {
    const line = leader.current;
    if (!line) return;
    const box = area.current?.getBoundingClientRect();
    const cardBox = card.current?.getBoundingClientRect();
    if (!point || !box || !cardBox || !box.width) return line.setAttribute("d", "");
    const k = GLOBE_SCENE.width / box.width;
    const ax = (cardBox.right - box.left) * k;
    const ay = (cardBox.top - box.top) * k + 18;
    const midX = (ax + point[0]) / 2;
    line.setAttribute("d", `M ${ax.toFixed(1)} ${ay.toFixed(1)} C ${midX.toFixed(1)} ${ay.toFixed(1)}, ${midX.toFixed(1)} ${point[1].toFixed(1)}, ${point[0].toFixed(1)} ${(point[1] - 9).toFixed(1)}`);
  }, []);
  useEffect(() => {
    if (phase !== "show") leader.current?.setAttribute("d", "");
  }, [phase]);

  const showing = phase === "show" && current !== null;
  const panel = (
    <DiscoveryCard
      loading={loading}
      stop={current}
      showing={showing}
      count={current ? (countIn.get(current.code) ?? 0) : 0}
      position={detour ? null : { index: cursor, total: stops.length }}
      paused={paused}
      holding={holding}
      trip={trip}
      reduced={reduced}
      compact={compact}
      onPrev={() => {
        takeOver();
        goToStop(cursor - 1);
      }}
      onNext={() => {
        takeOver();
        goToStop(detour ? cursor : cursor + 1);
      }}
      onToggle={() => {
        setPaused((old) => !old);
        setIdle(false);
        setFocusInside(false); // resuming is explicit: it overrides the focus hold
      }}
      cardRef={card}
      onPointerEnter={() => setPointerOnCard(true)}
      onPointerLeave={() => setPointerOnCard(false)}
    />
  );

  return (
    <div
      // Keyboard focus holds the tour (a pointer click leaves focus behind too, but that shouldn't freeze it).
      onFocus={(event) => setFocusInside((event.target as Element).matches(":focus-visible"))}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setFocusInside(false);
      }}
    >
      <div ref={area} className="relative">
        <BleedGlobe compact={compact}>
          <LiveGlobe
            ref={globe}
            pins={pins}
            active={showing ? current!.code : null}
            landing={landing}
            visited={visited}
            onSelect={goToCountry}
            onUserTurn={takeOver}
            onActiveMove={beside ? onActiveMove : undefined}
            running={heroActive}
            reduced={reduced}
            compact={compact}
          />
        </BleedGlobe>
        {beside && (
          <>
            <svg viewBox={`0 0 ${GLOBE_SCENE.width} ${GLOBE_SCENE.height}`} className="pointer-events-none absolute inset-0 h-full w-full overflow-visible" aria-hidden="true">
              <path ref={leader} className="leader-line" fill="none" stroke="var(--atlas-ink)" strokeWidth="1.1" strokeDasharray="1 3.5" strokeLinecap="round" />
            </svg>
            {/* A stable place for the card: over the stand at the globe's lower left, never over the destination (which lands right of centre) or the headline. */}
            <div className="enter-card absolute bottom-[6%] left-[-5%] z-10 w-[286px]">{panel}</div>
          </>
        )}
      </div>
      {/* Below the globe: the card first (it's what the tour is showing), then the regions. */}
      {!beside && <div className={`enter-card mx-auto mt-3 ${compact ? "px-5" : "max-w-[420px]"}`}>{panel}</div>}
      <RegionChips current={region} onPick={pickRegion} counts={regionCounts} compact={compact} />
      <p className="sr-only" aria-live="polite">
        {announcement}
      </p>
    </div>
  );
}

/** The atlas card: a page torn from the index, introducing the listing at the active pin. */
function DiscoveryCard({
  loading,
  stop,
  showing,
  count,
  position,
  paused,
  holding,
  trip,
  reduced,
  compact,
  onPrev,
  onNext,
  onToggle,
  cardRef,
  onPointerEnter,
  onPointerLeave,
}: {
  loading: boolean;
  stop: Stop | null;
  showing: boolean;
  count: number;
  position: { index: number; total: number } | null;
  paused: boolean;
  holding: boolean;
  trip: number;
  reduced: boolean;
  compact: boolean;
  onPrev: () => void;
  onNext: () => void;
  onToggle: () => void;
  cardRef: React.RefObject<HTMLDivElement | null>;
  onPointerEnter: () => void;
  onPointerLeave: () => void;
}) {
  const multiple = (position?.total ?? 0) > 1 || position === null;
  return (
    <div
      ref={cardRef}
      onPointerEnter={onPointerEnter}
      onPointerLeave={onPointerLeave}
      className="atlas-card relative border-[1.5px] border-[var(--atlas-ink)] bg-[var(--atlas-paper)] text-[var(--atlas-ink)] shadow-[4px_5px_0_rgb(31_40_51/0.16)]"
    >
      <div className={`relative overflow-hidden ${compact ? "min-h-[150px] px-4 pb-3 pt-3.5" : "min-h-[212px] px-5 pb-4 pt-4"}`}>
        <AnimatePresence mode="wait" initial={false}>
          {!stop && loading ? (
            <motion.div key="loading" initial={false} className="flex flex-col gap-2 pt-1" aria-hidden="true">
              <span className="skeleton h-2.5 w-24" />
              <span className="skeleton h-4 w-full" />
              <span className="skeleton h-4 w-3/4" />
            </motion.div>
          ) : !stop ? (
            <motion.div key="empty" initial={false} className="text-[13.5px] leading-relaxed text-[#5c5a52]">
              No dated opportunities to introduce right now.{" "}
              <Link to="/opportunities" className="font-semibold text-[var(--atlas-ink)] underline underline-offset-2">
                Browse the index
              </Link>
              .
            </motion.div>
          ) : showing ? (
            <motion.div
              key={`${stop.opportunity.id}-${trip}`}
              initial={reduced ? false : { opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0, transition: { duration: 0.45, ease: EASE } }}
              exit={reduced ? undefined : { opacity: 0, y: -6, transition: { duration: 0.28 } }}
            >
              <CardBody stop={stop} count={count} compact={compact} />
            </motion.div>
          ) : (
            <motion.p
              key={`route-${trip}`}
              initial={reduced ? false : { opacity: 0 }}
              animate={{ opacity: 1, transition: { duration: 0.25 } }}
              exit={{ opacity: 0 }}
              className="small-caps pt-1 text-[10.5px] text-[#5c5a52]"
            >
              En route to {countryName(stop.code)}…
            </motion.p>
          )}
        </AnimatePresence>
      </div>

      {stop && multiple && (
        <div className="flex items-center gap-1 border-t border-[var(--atlas-ink)]/30 px-2 py-1">
          <button type="button" onClick={onPrev} className="atlas-ctl" aria-label="Previous opportunity">
            <ChevronLeft size={16} />
          </button>
          <button type="button" onClick={onToggle} className="atlas-ctl" aria-label={paused ? "Resume the tour" : "Pause the tour"} aria-pressed={paused}>
            {paused ? <Play size={14} /> : <Pause size={14} />}
          </button>
          <button type="button" onClick={onNext} className="atlas-ctl" aria-label="Next opportunity">
            <ChevronRight size={16} />
          </button>
          {/* How long until the tour moves on; it stands still while held. */}
          <span className="relative mx-2 h-[2px] flex-1 overflow-hidden bg-[var(--atlas-ink)]/15" aria-hidden="true">
            {showing && position && <span key={trip} className="tour-progress absolute inset-y-0 left-0 bg-[var(--atlas-terra)]" style={{ animationPlayState: holding ? "paused" : "running" }} />}
          </span>
          <span className="num pr-2 text-[11.5px] text-[#5c5a52]">{position ? `${position.index + 1} / ${position.total}` : "Your pick"}</span>
        </div>
      )}
    </div>
  );
}

export function CardBody({ stop, count, compact }: { stop: Stop; count: number; compact: boolean }) {
  const { opportunity, code } = stop;
  const info = deadlineInfo(opportunity);
  const words = deadlineWords(opportunity);
  const date = opportunity.deadline_at && (info.state === "open" || info.state === "soon") ? new Date(opportunity.deadline_at) : null;
  // Funding is mentioned only when the record itself is tagged with it.
  const funding = (opportunity.tags ?? []).map(String).find((tag) => /fully funded|stipend|funded/i.test(tag));
  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <p className="small-caps truncate text-[10px] text-[#5c5a52]">{TYPE_LABELS[opportunity.opportunity_type]}</p>
        <span className="num shrink-0 border border-[var(--atlas-ink)] px-1 text-[10px] font-semibold tracking-[0.08em]" title={countryName(code)}>
          {code}
        </span>
      </div>
      <h3 className={`mt-1.5 font-semibold leading-[1.22] ${compact ? "line-clamp-2 text-[15.5px]" : "line-clamp-3 text-[17px]"}`}>{opportunity.title}</h3>
      <p className="mt-1 line-clamp-1 text-[12.5px] text-[#5c5a52]">
        {opportunity.host_name ? `${opportunity.host_name} · ` : ""}
        {countryName(code)}
      </p>
      <div className="mt-3 flex items-center gap-3 border-t border-dashed border-[var(--atlas-ink)]/40 pt-2.5">
        {date && (
          <span className="flex w-9 shrink-0 flex-col items-center leading-none" aria-hidden="true">
            <span className="font-[family-name:var(--font-serif)] text-[26px]">{date.getDate()}</span>
            <span className="small-caps mt-0.5 text-[9px] text-[#5c5a52]">{date.toLocaleDateString("en-GB", { month: "short" })}</span>
          </span>
        )}
        <span className="min-w-0 text-[12px] leading-snug">
          <span className="sr-only">Deadline {info.label}. </span>
          <span className={`block ${words.urgent ? "font-semibold text-[var(--atlas-terra)]" : "text-[#5c5a52]"}`}>{words.text}</span>
          {funding && <span className="block text-[#5c5a52]">Tagged: {funding}</span>}
        </span>
      </div>
      <div className="mt-3 flex items-center justify-between gap-3">
        <Link to={`/opportunities/${opportunity.id}`} className="group inline-flex items-center gap-1.5 text-[13px] font-semibold decoration-1 underline-offset-4 hover:underline">
          Explore opportunity
          <ArrowRight size={14} className="transition-transform duration-200 group-hover:translate-x-0.5" />
        </Link>
        {count > 1 && (
          <Link to={`/opportunities?where=${code}`} aria-label={`All ${plural(count, "listing")} in ${countryName(code)}`} className="shrink-0 text-[11.5px] text-[#5c5a52] underline decoration-[var(--atlas-ink)]/30 underline-offset-2 hover:text-[var(--atlas-ink)]">
            All {count} here
          </Link>
        )}
      </div>
    </div>
  );
}
