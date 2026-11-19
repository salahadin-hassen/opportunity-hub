/**
 * The unfolding atlas: the chapter after the hero, where the globe opens into a
 * flat map and the visitor travels across it, region by region, meeting real
 * opportunities on the way, and leaves with somewhere to go in the catalogue.
 * (How the globe unfolds into the map: see atlas-geo.ts.)
 *
 * Performance (measured, see the PR notes): the map is painted by a worker that
 * owns its canvas (OffscreenCanvas), so painting never competes with scrolling,
 * React or input here; where that isn't supported the same renderer runs on the
 * page. Either way a frame is painted at most once per animation frame and only
 * when something changed. Labels and cards are DOM moved with compositor
 * transforms. Scrolling is read from one passive listener, batched to animation
 * frames, against geometry measured only when layout changes.
 *
 * Wide screens get a pinned stage driven by vertical scrolling (the hero's globe
 * glides into it, see Landing.tsx). Phones, tablets and reduced motion get the
 * same map in the page with a native, snapping strip of destinations under it.
 */
import { ArrowRight, ChevronLeft, ChevronRight } from "lucide-react";
import { useReducedMotion } from "motion/react";
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import type { Opportunity } from "../../api/types";
import { countryName, plural } from "../../lib/format";
import { INITIAL_LAYERS, INITIAL_MORPH, createRenderer, type Layers, type MapData, type Palette, type Scene } from "./atlas-draw";
import { MAP_H, MAP_W, SCALE, clamp01, ease, fine, flatPoint, lerpCam, morphAt, ramp, toScreen, warmFlat, type Cam, type Morph } from "./atlas-geo";
import { regionOf } from "./geo-land";
import { COUNTRY_CENTRES } from "./geo-world";
import { CardBody } from "./GlobeExplorer";
import { REGIONS, Stamp, globeView, isCountry, useAtlas, useVoyagePinned, voyageGlobe, type RegionKey } from "./shared";

/** DOM writes only when the value changes: repeated identical writes still invalidate style (and, for inert, the accessibility tree). */
const written = new WeakMap<HTMLElement, Map<string, string>>();
function setStyle(el: HTMLElement, prop: "opacity" | "transform" | "visibility", value: string) {
  let cache = written.get(el);
  if (!cache) written.set(el, (cache = new Map()));
  if (cache.get(prop) === value) return;
  cache.set(prop, value);
  el.style[prop] = value;
}
function setInert(el: HTMLElement, value: boolean) {
  if (el.inert !== value) el.inert = value;
}

/* ------------------------------------------------------------------------ */
/* Scrolling: one passive listener, one update per frame, no layout reads     */
/* ------------------------------------------------------------------------ */

/**
 * Calls ``onFrame`` at most once per animation frame while the page scrolls or resizes, and once on
 * mount. ``measure`` runs only when layout may have changed (mount, resize, the page growing as lazy
 * content arrives), so per-frame work reads nothing but ``scrollY``.
 */
function useScrollFrame(onFrame: () => void, measure: () => void) {
  const frame = useRef(onFrame);
  const remeasure = useRef(measure);
  frame.current = onFrame;
  remeasure.current = measure;
  useEffect(() => {
    let raf = 0;
    const run = () => {
      raf = 0;
      frame.current();
    };
    const schedule = () => {
      if (!raf) raf = requestAnimationFrame(run);
    };
    const relayout = () => {
      remeasure.current();
      schedule();
    };
    relayout();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", relayout);
    const observer = new ResizeObserver(relayout);
    observer.observe(document.body);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", relayout);
      observer.disconnect();
    };
  }, []);
}

/* ------------------------------------------------------------------------ */
/* Data: everything comes from the published catalogue                        */
/* ------------------------------------------------------------------------ */

/** West to east across the map, so the journey reads left to right. */
const ORDER: RegionKey[] = ["americas", "europe", "africa", "asia", "oceania"];

type VoyageStop = { key: RegionKey; label: string; listings: number; countries: number; opportunity: Opportunity; code: string; here: number; at: [number, number] };
type VoyageRegion = { key: RegionKey; label: string; listings: number; countries: number; busiest: [string, number] | null; at: [number, number]; stop: number };
type Voyage = ReturnType<typeof useVoyage>;

function useVoyage() {
  const { all, upcoming, byCountry, isPending } = useAtlas();
  return useMemo(() => {
    const placeIn = (item: Opportunity, key: RegionKey) => (item.countries ?? []).map(String).find((code) => isCountry(code) && regionOf(code) === key);
    const regions: VoyageRegion[] = [];
    const stops: VoyageStop[] = [];
    for (const key of ORDER) {
      const meta = REGIONS.find((region) => region.key === key)!;
      const listings = all.filter((item) => placeIn(item, key)).length;
      if (!listings) continue;
      const places = [...byCountry.entries()].filter(([code]) => regionOf(code) === key).sort((a, b) => b[1] - a[1]);
      // The region's soonest open deadline: a real, dated listing a visitor can still apply to.
      const pick = upcoming.find((item) => placeIn(item, key));
      let stop = -1;
      if (pick) {
        const code = placeIn(pick, key)!;
        stop = stops.length;
        stops.push({ key, label: meta.label, listings, countries: places.length, opportunity: pick, code, here: byCountry.get(code) ?? 1, at: flatPoint(COUNTRY_CENTRES[code] as [number, number]) });
      }
      regions.push({ key, label: meta.label, listings, countries: places.length, busiest: places[0] ?? null, at: flatPoint([meta.lon, meta.lat]), stop });
    }
    const maxCount = Math.max(1, ...byCountry.values());
    const dots = [...byCountry.entries()]
      .filter(([code]) => COUNTRY_CENTRES[code])
      .map(([code, count]) => ({ at: flatPoint(COUNTRY_CENTRES[code] as [number, number]), px: 1.8 + Math.sqrt(count / maxCount) * 3.4 }));
    // The route as points along great circles, so it can be drawn on progressively.
    const route: [number, number][] = [];
    if (stops.length > 1) {
      const stream = fine.stream({
        point: (x: number, y: number) => void route.push([x, y]),
        lineStart: () => {},
        lineEnd: () => {},
        polygonStart: () => {},
        polygonEnd: () => {},
        sphere: () => {},
      });
      stream.lineStart();
      for (const stop of stops) {
        const [lon, lat] = COUNTRY_CENTRES[stop.code] as [number, number];
        stream.point(lon, lat);
      }
      stream.lineEnd();
    }
    const routeLengths = [0];
    for (let i = 1; i < route.length; i += 1) routeLengths.push(routeLengths[i - 1]! + Math.hypot(route[i]![0] - route[i - 1]![0], route[i]![1] - route[i - 1]![1]));
    return { regions, stops, dots, route, routeLengths, total: all.length, countryCount: byCountry.size, isPending };
  }, [all, upcoming, byCountry, isPending]);
}

/* ------------------------------------------------------------------------ */
/* The map: a canvas painted off the main thread, DOM for what you read/press */
/* ------------------------------------------------------------------------ */

type MapApi = { morph: (m: Morph) => void; camera: (c: Cam) => void; layers: (l: Partial<Layers>) => void; cam: () => Cam | null; flush: () => void };

/** Map colours come from the atlas tokens, read once per theme. */
function readPalette(node: Element): Palette {
  const css = getComputedStyle(node);
  const v = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback;
  return {
    seaHi: "#d6e4df",
    sea: v("--atlas-sea", "#a8c0bd"),
    seaDeep: v("--atlas-sea-deep", "#6f9094"),
    land: v("--atlas-land", "#dccb9b"),
    ink: v("--atlas-ink", "#1f2833"),
    terra: v("--atlas-terra", "#b2603f"),
    brass: v("--atlas-brass", "#c99845"),
    brassHi: v("--atlas-brass-hi", "#efd38d"),
    brassDeep: v("--atlas-brass-deep", "#84591f"),
    paper: v("--atlas-paper", "#f6efdf"),
  };
}

/**
 * The painter behind a canvas: a worker that owns it where OffscreenCanvas is supported, otherwise
 * the same renderer on this thread (with the same lite-then-full rhythm).
 */
type Painter = { size: (w: number, h: number, dpr: number) => void; data: (d: MapData) => void; palette: (p: Palette) => void; scene: (s: Scene) => void; dispose: () => void };
function createPainter(canvas: HTMLCanvasElement): Painter {
  if ("transferControlToOffscreen" in canvas && typeof Worker !== "undefined") {
    try {
      const offscreen = canvas.transferControlToOffscreen();
      const worker = new Worker(new URL("./atlas-map.worker.ts", import.meta.url), { type: "module" });
      worker.postMessage({ type: "init", canvas: offscreen }, [offscreen]);
      // Opt-in for performance tests (a test sets window.__ohMapPerf = true first): read the worker's paint timings.
      const perf = window as { __ohMapPerf?: boolean; __ohMapStats?: () => Promise<{ timings: [number, number][]; origin: number }> };
      if (perf.__ohMapPerf)
        perf.__ohMapStats = () =>
          new Promise((resolve) => {
            const onStats = (event: MessageEvent) => {
              if (event.data?.type !== "stats") return;
              worker.removeEventListener("message", onStats);
              resolve(event.data);
            };
            worker.addEventListener("message", onStats);
            worker.postMessage({ type: "stats" });
          });
      return {
        size: (width, height, dpr) => worker.postMessage({ type: "size", width, height, dpr }),
        data: (data) => worker.postMessage({ type: "data", data }),
        palette: (palette) => worker.postMessage({ type: "palette", palette }),
        scene: (scene) => worker.postMessage({ type: "scene", scene }),
        dispose: () => worker.terminate(),
      };
    } catch {
      /* fall through to painting here */
    }
  }
  const ctx = canvas.getContext("2d")!;
  const draw = createRenderer(ctx);
  let dpr = 1;
  let data: MapData | null = null;
  let palette: Palette | null = null;
  let scene: Scene | null = null;
  let rest = 0;
  let warmed = false;
  const paint = (lite: boolean) => data && palette && scene && draw({ ...scene, lite }, data, palette, dpr);
  return {
    size: (width, height, ratio) => {
      dpr = ratio;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      paint(false);
    },
    data: (next) => {
      data = next;
      if (!warmed) {
        warmed = true;
        warmFlat(next.light);
      }
      paint(false);
    },
    palette: (next) => {
      palette = next;
      paint(false);
    },
    scene: (next) => {
      scene = next;
      paint(next.lite);
      window.clearTimeout(rest);
      if (next.lite) rest = window.setTimeout(() => paint(false), 130);
    },
    dispose: () => window.clearTimeout(rest),
  };
}

const MapCanvas = forwardRef<
  MapApi,
  { width: number; height: number; voyage: Voyage; light: boolean; showRegions: boolean; onRegion?: (stop: number) => void; className?: string }
>(function MapCanvas({ width, height, voyage, light, showRegions, onRegion, className = "" }, ref) {
  const root = useRef<HTMLDivElement>(null);
  const host = useRef<HTMLDivElement>(null);
  const painter = useRef<Painter | null>(null);
  const marks = useRef<HTMLDivElement>(null);
  const markNodes = useRef(new Map<RegionKey, HTMLElement>());
  const state = useRef<{ morph: Morph; cam: Cam | null; layers: Layers; dirty: boolean }>({ morph: INITIAL_MORPH, cam: null, layers: { ...INITIAL_LAYERS }, dirty: true });
  const regionsRef = useRef(voyage.regions);
  regionsRef.current = voyage.regions;

  // The canvas is created here (not rendered by React) because control of it is handed to the worker,
  // which can happen only once per element; each mount gets a fresh one.
  useEffect(() => {
    const node = host.current;
    if (!node) return;
    const canvas = document.createElement("canvas");
    canvas.className = "atlas-art absolute inset-0 h-full w-full";
    canvas.setAttribute("aria-hidden", "true");
    node.appendChild(canvas);
    painter.current = createPainter(canvas);
    state.current.dirty = true;
    return () => {
      painter.current?.dispose();
      painter.current = null;
      canvas.remove();
    };
  }, []);

  useEffect(() => {
    if (width && height) painter.current?.size(width, height, Math.min(2, window.devicePixelRatio || 1));
  }, [width, height]);
  useEffect(() => {
    painter.current?.data({ dots: voyage.dots, route: voyage.route, routeLengths: voyage.routeLengths, light });
  }, [voyage.dots, voyage.route, voyage.routeLengths, light]);
  // Colours follow the theme.
  useEffect(() => {
    const send = () => root.current && painter.current?.palette(readPalette(root.current));
    send();
    const observer = new MutationObserver(send);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "class"] });
    return () => observer.disconnect();
  }, []);

  /** Region labels follow the camera with compositor transforms (only while they're shown). */
  const place = useCallback(() => {
    const { cam, layers } = state.current;
    if (!cam || !marks.current || layers.regions <= 0.01) return;
    for (const region of regionsRef.current) {
      const node = markNodes.current.get(region.key);
      if (!node) continue;
      const [x, y] = toScreen(cam, region.at);
      setStyle(node, "transform", `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0) translate(-50%, -50%)`);
    }
  }, []);

  useImperativeHandle(
    ref,
    () => ({
      morph(m) {
        const old = state.current.morph;
        if (old.alpha === m.alpha && old.lon === m.lon && old.lat === m.lat && old.tilt === m.tilt) return;
        state.current.morph = m;
        state.current.dirty = true;
      },
      camera(c) {
        const old = state.current.cam;
        if (old && old.ax === c.ax && old.ay === c.ay && old.z === c.z && old.cx === c.cx && old.cy === c.cy) return;
        state.current.cam = c;
        state.current.dirty = true;
      },
      layers(next) {
        const layers = state.current.layers;
        for (const key of Object.keys(next) as (keyof Layers)[]) {
          if (layers[key] !== next[key]) {
            Object.assign(layers, { [key]: next[key] });
            state.current.dirty = true;
          }
        }
        if (root.current) setStyle(root.current, "visibility", layers.globe > 0.001 ? "visible" : "hidden");
        if (marks.current) {
          setStyle(marks.current, "opacity", layers.regions.toFixed(3));
          setInert(marks.current, layers.regions < 0.5);
        }
      },
      cam: () => state.current.cam,
      flush() {
        const { cam, morph, layers, dirty } = state.current;
        if (dirty && cam && painter.current) {
          state.current.dirty = false;
          painter.current.scene({ morph, cam, layers: { ...layers }, lite: true });
        }
        place();
      },
    }),
    [place],
  );

  return (
    <div ref={root} className={className || "relative"}>
      <div ref={host} className="absolute inset-0" />
      {showRegions && (
        <div ref={marks} className="pointer-events-none absolute inset-0" style={{ opacity: 0 }} inert>
          {voyage.regions.map((region) => {
            const label = (
              <>
                <span className="small-caps text-[10.5px]">{region.label}</span>
                <span className="num text-[11px] opacity-75">{region.listings}</span>
              </>
            );
            return (
              <div key={region.key} ref={(node) => void (node ? markNodes.current.set(region.key, node) : markNodes.current.delete(region.key))} className="absolute left-0 top-0">
                {onRegion && region.stop >= 0 ? (
                  <button type="button" className="voyage-mark pointer-events-auto" onClick={() => onRegion(region.stop)} aria-label={`${region.label}: ${plural(region.listings, "listing")}. Travel there`}>
                    {label}
                  </button>
                ) : (
                  <span className="voyage-mark">{label}</span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
});

/* ------------------------------------------------------------------------ */
/* Shared pieces of copy                                                      */
/* ------------------------------------------------------------------------ */

function StopHeading({ stop, index, total }: { stop: VoyageStop; index: number; total: number }) {
  return (
    <>
      <p className="small-caps text-[11px] text-ink-soft">
        Destination {index + 1} of {total}
      </p>
      <h3 className="serif-display mt-2 text-[clamp(30px,3.4vw,52px)] leading-[1.02] text-ink">{stop.label}</h3>
      <p className="num mt-2 text-[14.5px] text-ink-soft">
        {plural(stop.listings, "listing")} in {plural(stop.countries, "country", "countries")}
      </p>
    </>
  );
}

function StopCard({ stop, compact }: { stop: VoyageStop; compact: boolean }) {
  return (
    <div className="atlas-card relative border-[1.5px] border-[var(--atlas-ink)] bg-[var(--atlas-paper)] text-[var(--atlas-ink)] shadow-[4px_5px_0_rgb(31_40_51/0.16)]">
      <div className={compact ? "px-4 pb-3 pt-3.5" : "px-5 pb-4 pt-4"}>
        <CardBody stop={{ opportunity: stop.opportunity, code: stop.code }} count={stop.here} compact={compact} />
      </div>
    </div>
  );
}

/** The way out of the story: the catalogue, the last opportunity seen, and the busiest place in each region. */
function NextDestination({ voyage, chosen }: { voyage: Voyage; chosen: VoyageStop | null }) {
  const places = voyage.regions.filter((region) => region.busiest);
  return (
    <div>
      <p className="small-caps text-[11px] text-ink-soft">Your next destination</p>
      <h3 className="serif-display mt-2 text-[clamp(30px,3.6vw,56px)] leading-[1.02] text-ink">Choose where to go next.</h3>
      <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-3">
        <Stamp to="/opportunities" solid>
          Explore all {voyage.total > 0 ? voyage.total : ""} opportunities
          <ArrowRight size={16} />
        </Stamp>
      </div>
      {chosen && (
        <Link to={`/opportunities/${chosen.opportunity.id}`} className="group mt-5 flex max-w-[44ch] items-start gap-2 text-[14px] font-semibold text-ink">
          <span className="decoration-1 underline-offset-4 group-hover:underline">Open {chosen.opportunity.title}</span>
          <ArrowRight size={15} className="mt-[3px] shrink-0 transition-transform duration-200 group-hover:translate-x-0.5" />
        </Link>
      )}
      {places.length > 0 && (
        <div className="mt-6">
          <p className="small-caps text-[10.5px] text-muted">Or start from a place</p>
          <ul className="mt-1 flex flex-wrap gap-x-4">
            {places.map((region) => (
              <li key={region.key}>
                <Link
                  to={`/opportunities?where=${region.busiest![0]}`}
                  className="inline-flex min-h-10 items-center gap-1.5 text-[13.5px] text-ink-soft underline decoration-ink/25 underline-offset-4 hover:text-ink hover:decoration-ink"
                >
                  {countryName(region.busiest![0])}
                  <span className="num text-[12px] text-muted">{region.busiest![1]}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------------ */
/* Wide screens: a pinned stage driven by vertical scrolling                  */
/* ------------------------------------------------------------------------ */

/** Story timing in viewport-heights of scrolling. */
function timeline(stops: number) {
  const morphEnd = 1.1;
  const overEnd = morphEnd + 0.65;
  const legs: { from: number; arrive: number; leave: number }[] = [];
  let u = overEnd;
  for (let i = 0; i < stops; i += 1) {
    const arrive = u + (i === 0 ? 0.4 : 0.3);
    legs.push({ from: u, arrive, leave: arrive + 0.34 });
    u = arrive + 0.34;
  }
  const endArrive = u + 0.4;
  const total = endArrive + 0.35;
  // Chapter boundaries: the world opens, every direction, what's possible, your next destination.
  const bounds = [0, morphEnd, overEnd + 0.15, (legs[legs.length - 1]?.leave ?? overEnd) + 0.1, total];
  return { morphEnd, overEnd, legs, endArrive, total, bounds };
}

const CHAPTERS = ["The world opens", "Every direction", "What’s possible", "Your next destination"];

function PinnedStory({ voyage }: { voyage: Voyage }) {
  const section = useRef<HTMLElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const map = useRef<MapApi>(null);
  const texts = useRef<(HTMLDivElement | null)[]>([]);
  const fills = useRef<(HTMLSpanElement | null)[]>([]);
  const card = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState(() => ({ w: window.innerWidth, h: window.innerHeight }));
  const [beat, setBeat] = useState({ chapter: 0, stop: 0 });
  const beatRef = useRef(beat);
  const startRot = useRef<[number, number]>([...globeView.rotation]);
  const geometry = useRef({ top: 0, height: 1, vh: 1 });
  const progress = useRef(0);
  const settled = useRef("");
  const { stops } = voyage;
  const n = Math.max(1, stops.length);
  const tl = useMemo(() => timeline(n), [n]);

  const cameras = useMemo(() => {
    const { w, h } = size;
    const g = voyageGlobe(w, h);
    const zF = Math.min((0.7 * w) / MAP_W, (0.6 * h) / MAP_H);
    const zT = Math.min((2.1 * h) / MAP_H, (3 * w) / MAP_W);
    return {
      globe: { ax: g.x, ay: g.y, z: g.r / SCALE, cx: 0, cy: 0 },
      overview: { ax: w * 0.62, ay: h * 0.58, z: zF, cx: 0, cy: 0 },
      stop: (at: [number, number]): Cam => ({ ax: w * 0.36, ay: h * 0.58, z: zT, cx: at[0], cy: at[1] }),
      end: { ax: w * 0.7, ay: h * 0.57, z: zF * 0.74, cx: 0, cy: 0 },
    };
  }, [size]);

  const measure = useCallback(() => {
    const node = section.current;
    if (!node) return;
    geometry.current = { top: node.getBoundingClientRect().top + window.scrollY, height: node.offsetHeight, vh: window.innerHeight };
    settled.current = "";
    setSize((old) => (old.w === window.innerWidth && old.h === window.innerHeight ? old : { w: window.innerWidth, h: window.innerHeight }));
  }, []);

  const apply = useCallback(
    () => {
      const api = map.current;
      if (!api) return;
      const { top, height, vh } = geometry.current;
      const y = window.scrollY;
      const pinned = y >= top - 1;
      // Before the pin (the hero still holds the globe) and after the story, the stage is static:
      // render that state once, then do nothing until it is pinned again.
      const idle = !pinned ? "before" : y > top + height + vh * 0.2 ? "after" : "";
      if (!pinned) startRot.current = [...globeView.rotation];
      if (idle && settled.current === idle) return;
      settled.current = idle;
      const p = clamp01((y - top) / Math.max(1, height - vh));
      progress.current = p;
      const u = p * tl.total;
      const m = clamp01(u / tl.morphEnd);
      const morph = morphAt(m, startRot.current);
      api.morph(morph);

      // The camera: follow the unfolding, hold on the whole map, travel stop to stop, then pull back.
      let cam: Cam = cameras.overview;
      let stopIndex = 0;
      let cardOpacity = 0;
      if (u <= tl.morphEnd) cam = lerpCam(cameras.globe, cameras.overview, morph.alpha);
      else if (u > tl.overEnd && stops.length) {
        const last = tl.legs[stops.length - 1]!;
        if (u >= last.leave) {
          stopIndex = stops.length - 1;
          cam = lerpCam(cameras.stop(stops[stopIndex]!.at), cameras.end, ease(ramp(u, last.leave, tl.endArrive)));
        } else {
          stopIndex = Math.max(0, tl.legs.findIndex((leg) => u < leg.leave));
          const leg = tl.legs[stopIndex]!;
          const target = cameras.stop(stops[stopIndex]!.at);
          const from = stopIndex === 0 ? cameras.overview : cameras.stop(stops[stopIndex - 1]!.at);
          cam = u < leg.arrive ? lerpCam(from, target, ease(ramp(u, leg.from, leg.arrive)), stopIndex === 0 ? 0 : 0.16) : target;
          cardOpacity = ramp(u, leg.arrive - 0.1, leg.arrive) * (1 - ramp(u, leg.leave - 0.05, leg.leave));
        }
      }
      api.camera(cam);
      const regionsIn = ramp(u, tl.morphEnd - 0.12, tl.morphEnd) * (1 - ramp(u, tl.overEnd + 0.02, tl.overEnd + 0.2)) + ramp(u, tl.endArrive - 0.25, tl.endArrive);
      api.layers({
        globe: pinned ? 1 : 0,
        dots: ramp(morph.alpha, 0.8, 1),
        route: ramp(u, tl.morphEnd - 0.05, tl.overEnd - 0.1),
        routeOpacity: u > tl.overEnd + 0.2 && u < tl.endArrive - 0.2 ? 0.55 : 1,
        regions: Math.min(1, regionsIn),
        pin: stops[stopIndex]?.at ?? null,
        pinOpacity: cardOpacity,
      });
      api.flush();

      // The card sits beside its pin and travels with the map as it leaves (compositor transform only).
      if (card.current) {
        const at = stops[stopIndex]?.at;
        if (at && cardOpacity > 0.01) {
          const [x, cy] = toScreen(cam, at);
          const left = Math.min(size.w - 316, x + 30);
          setStyle(card.current, "transform", `translate3d(${left.toFixed(1)}px, ${(cy - 150 + (1 - cardOpacity) * 10).toFixed(1)}px, 0)`);
          setStyle(card.current, "opacity", cardOpacity.toFixed(3));
          setStyle(card.current, "visibility", "visible");
        } else setStyle(card.current, "visibility", "hidden");
        setInert(card.current, cardOpacity < 0.5);
      }

      // Chapter copy and the progress line.
      const chapter = u < tl.bounds[1]! ? 0 : u < tl.bounds[2]! ? 1 : u < tl.bounds[3]! ? 2 : 3;
      const windows: [number, number][] = [
        [-1, tl.morphEnd * 0.56],
        [tl.morphEnd - 0.05, tl.overEnd + 0.12],
        [tl.overEnd + 0.18, (tl.legs[stops.length - 1]?.leave ?? tl.overEnd) + 0.04],
        [tl.endArrive - 0.22, 99],
      ];
      windows.forEach(([from, to], i) => {
        const el = texts.current[i];
        if (!el) return;
        const o = ramp(u, from, from + 0.12) * (1 - ramp(u, to, to + 0.12));
        setStyle(el, "opacity", o.toFixed(3));
        setStyle(el, "transform", `translate3d(0, ${((1 - o) * 14).toFixed(1)}px, 0)`);
        setInert(el, o < 0.5);
      });
      fills.current.forEach((el, i) => {
        if (el) setStyle(el, "transform", `scaleX(${ramp(u, tl.bounds[i]!, tl.bounds[i + 1]!).toFixed(3)})`);
      });
      if (beatRef.current.chapter !== chapter || beatRef.current.stop !== stopIndex) {
        beatRef.current = { chapter, stop: stopIndex };
        setBeat(beatRef.current);
      }
    },
    [cameras, size.w, stops, tl],
  );

  useScrollFrame(() => apply(), measure);
  useEffect(() => {
    measure();
    settled.current = "";
    apply();
  }, [apply, measure]);
  useEffect(() => {
    const node = stage.current;
    if (!node) return;
    // A sideways trackpad swipe over the stage moves the story too. Passive: it never blocks scrolling.
    const onWheel = (event: WheelEvent) => {
      if (Math.abs(event.deltaX) > Math.abs(event.deltaY) * 1.5 && Math.abs(event.deltaX) > 4) window.scrollBy({ top: event.deltaX });
    };
    node.addEventListener("wheel", onWheel, { passive: true });
    return () => node.removeEventListener("wheel", onWheel);
  }, []);

  const goTo = useCallback(
    (u: number) => {
      const { top, height, vh } = geometry.current;
      window.scrollTo({ top: top + (u / tl.total) * (height - vh), behavior: "smooth" });
    },
    [tl.total],
  );
  const beats = useMemo(() => [0, tl.overEnd - 0.12, ...tl.legs.slice(0, stops.length).map((leg) => leg.arrive + 0.04), tl.total], [stops.length, tl]);
  const chapterTarget = [0, tl.overEnd - 0.12, (tl.legs[0]?.arrive ?? tl.overEnd) + 0.04, tl.total];
  // Left and right arrows step through the story while it is on screen: from anywhere inside the
  // stage, or with nothing focused (after clicking plain text, say). Other widgets keep their arrows.
  const stepRef = useRef<(forward: boolean) => void>(() => {});
  stepRef.current = (forward) => {
    const u = progress.current * tl.total;
    const next = forward ? beats.find((b) => b > u + 0.03) : [...beats].reverse().find((b) => b < u - 0.03);
    if (next !== undefined) goTo(next);
  };
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.key !== "ArrowRight" && event.key !== "ArrowLeft") || event.altKey || event.metaKey || event.ctrlKey) return;
      const { top, height, vh } = geometry.current;
      const y = window.scrollY;
      if (y < top - 1 || y > top + height - vh + 1) return; // the story isn't pinned on screen
      const target = event.target as HTMLElement | null;
      const inStage = Boolean(target && stage.current?.contains(target));
      if (!inStage && target && target !== document.body) return;
      if (target?.closest("input, textarea, select, [contenteditable]")) return;
      event.preventDefault();
      stepRef.current(event.key === "ArrowRight");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const current = stops[beat.stop] ?? null;
  const announce =
    beat.chapter === 0
      ? `Chapter 1 of 4: ${CHAPTERS[0]}.`
      : beat.chapter === 1
        ? `Chapter 2 of 4: ${CHAPTERS[1]}. ${plural(voyage.total, "listing")} across ${plural(voyage.countryCount, "country", "countries")}.`
        : beat.chapter === 2 && current
          ? `Chapter 3 of 4, destination ${beat.stop + 1} of ${stops.length}: ${current.label}. ${current.opportunity.title}.`
          : `Chapter 4 of 4: ${CHAPTERS[3]}.`;

  return (
    <section ref={section} id="atlas" aria-labelledby="atlas-title" className="relative z-[1]" style={{ height: `${(tl.total + 1) * 100}vh` }}>
      <div ref={stage} className="voyage-stage paper-grain sticky top-0 h-screen overflow-hidden">
        <MapCanvas ref={map} width={size.w} height={size.h} voyage={voyage} light={false} showRegions onRegion={(i) => goTo(tl.legs[i]!.arrive + 0.04)} className="absolute inset-0" />

        {/* Chapter copy, one block per chapter, crossfading with the scroll. */}
        <div className="pointer-events-none absolute inset-x-0 top-0 mx-auto max-w-[1440px] px-8 pt-[max(96px,12vh)] xl:px-14">
          <div ref={(el) => void (texts.current[0] = el)} className="pointer-events-auto absolute max-w-[min(25vw,380px)]">
            <p className="small-caps text-[11px] text-ink-soft">Chapter one · {CHAPTERS[0]}</p>
            <h2 id="atlas-title" className="serif-display mt-3 text-[clamp(36px,3.6vw,60px)] leading-[1.02] text-ink">
              The world is full of opportunity.
            </h2>
            <p className="mt-4 text-[17px] leading-relaxed text-ink-soft">Let’s explore it. Keep scrolling and the globe opens into a map of where the listings are.</p>
          </div>
          <div ref={(el) => void (texts.current[1] = el)} className="pointer-events-auto absolute max-w-[min(30vw,400px)] opacity-0" inert>
            <p className="small-caps text-[11px] text-ink-soft">Chapter two · {CHAPTERS[1]}</p>
            <h3 className="serif-display mt-3 text-[clamp(28px,2.6vw,44px)] leading-[1.04] text-ink">Opportunities don’t sit in one place.</h3>
            <p className="num mt-4 text-[16px] leading-relaxed text-ink-soft">
              {voyage.isPending
                ? "Reading the index…"
                : `${plural(voyage.total, "listing")} across ${plural(voyage.countryCount, "country", "countries")}. The route links an open opportunity in each region; follow it, or choose a region on the map.`}
            </p>
          </div>
          <div ref={(el) => void (texts.current[2] = el)} className="pointer-events-auto absolute max-w-[360px] opacity-0" inert>
            <p className="small-caps text-[11px] text-ink-soft">Chapter three · {CHAPTERS[2]}</p>
            <div className="mt-4">{current && <StopHeading stop={current} index={beat.stop} total={stops.length} />}</div>
          </div>
          <div ref={(el) => void (texts.current[3] = el)} className="pointer-events-auto absolute max-w-[min(32vw,440px)] opacity-0" inert>
            <NextDestination voyage={voyage} chosen={current} />
          </div>
        </div>

        {/* The destination's card, beside its pin. */}
        <div ref={card} className="absolute left-0 top-0 w-[300px]" style={{ visibility: "hidden", willChange: "transform, opacity" }}>
          {current && <StopCard key={current.opportunity.id} stop={current} compact={false} />}
        </div>

        {/* Where you are in the story; each chapter (and destination) is a place to jump to. */}
        <nav aria-label="Atlas chapters" className="absolute inset-x-0 bottom-0 mx-auto flex max-w-[1440px] items-end gap-6 px-8 pb-5 xl:px-14">
          <ol className="grid flex-1 grid-cols-4 gap-4">
            {CHAPTERS.map((title, i) => (
              <li key={title}>
                <button type="button" onClick={() => goTo(chapterTarget[i]!)} aria-current={beat.chapter === i ? "step" : undefined} className={`voyage-step ${beat.chapter === i ? "is-current" : ""}`}>
                  <span className="relative block h-[2px] w-full overflow-hidden bg-ink/15">
                    <span ref={(el) => void (fills.current[i] = el)} className="absolute inset-0 origin-left scale-x-0 bg-ink" />
                  </span>
                  <span className="mt-2 flex items-center gap-2">
                    <span className="num text-[11px] opacity-70">{i + 1}</span>
                    <span className="small-caps text-[10.5px]">{title}</span>
                    {i === 2 && beat.chapter === 2 && stops.length > 0 && (
                      <span className="num text-[11px] opacity-70">
                        · {beat.stop + 1}/{stops.length}
                      </span>
                    )}
                  </span>
                </button>
                {i === 2 && stops.length > 1 && (
                  <span className="-mt-1 flex gap-0.5">
                    {stops.map((stop, s) => (
                      <button
                        key={stop.key}
                        type="button"
                        onClick={() => goTo(tl.legs[s]!.arrive + 0.04)}
                        aria-label={`Destination ${s + 1}: ${stop.label}`}
                        aria-current={beat.chapter === 2 && beat.stop === s ? "true" : undefined}
                        title={stop.label}
                        className={`voyage-dot ${beat.chapter === 2 && beat.stop === s ? "is-current" : ""}`}
                      />
                    ))}
                  </span>
                )}
              </li>
            ))}
          </ol>
          <div className="flex shrink-0 flex-col items-end gap-1 pb-1">
            <Link to="/opportunities" className="small-caps inline-flex min-h-8 items-center gap-1 text-[10.5px] text-ink underline decoration-ink/30 underline-offset-4 hover:decoration-ink">
              All opportunities
              <ArrowRight size={12} />
            </Link>
            <a href="#how-it-works" className="small-caps inline-flex min-h-8 items-center text-[10.5px] text-ink-soft underline decoration-ink/30 underline-offset-4 hover:text-ink">
              Skip the atlas
            </a>
          </div>
        </nav>
        <p className="sr-only" aria-live="polite">
          {announce}
        </p>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------------ */
/* Phones, tablets and reduced motion: the map in the page, a strip below     */
/* ------------------------------------------------------------------------ */

function StripStory({ voyage, reduced }: { voyage: Voyage; reduced: boolean }) {
  const frame = useRef<HTMLDivElement>(null);
  const strip = useRef<HTMLOListElement>(null);
  const map = useRef<MapApi>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [index, setIndex] = useState(0);
  const indexRef = useRef(0);
  const tween = useRef(0);
  const step = useRef(1);
  const geometry = useRef({ top: 0, vh: 1 });
  const startRot = useRef<[number, number]>([...globeView.rotation]);
  const unfolded = useRef(false);
  const { stops } = voyage;
  const cards = stops.length + 2; // the overview, each destination, the way out
  const wideEnough = size.w >= 560;

  const cameras = useMemo(() => {
    const { w, h } = size;
    const fit = Math.min((0.94 * w) / MAP_W, (0.88 * h) / MAP_H);
    return {
      globe: { ax: w / 2, ay: h / 2, z: (h * 0.42) / SCALE, cx: 0, cy: 0 },
      fit: { ax: w / 2, ay: h / 2, z: fit, cx: 0, cy: 0 },
      at: (i: number): Cam => {
        const stop = stops[i - 1];
        return stop ? { ax: w / 2, ay: h * 0.56, z: fit * 2.6, cx: stop.at[0], cy: stop.at[1] } : { ax: w / 2, ay: h / 2, z: fit, cx: 0, cy: 0 };
      },
    };
  }, [size, stops]);

  /** Glide the camera to the card's destination (or jump, with reduced motion). */
  const travel = useCallback(
    (i: number) => {
      const api = map.current;
      if (!api) return;
      const target = cameras.at(i);
      const stop = stops[i - 1];
      api.layers({ pin: stop?.at ?? null, pinOpacity: stop ? 1 : 0, regions: i === 0 || i === cards - 1 ? 1 : 0 });
      cancelAnimationFrame(tween.current);
      const from = api.cam();
      if (reduced || !from) {
        api.camera(target);
        return api.flush();
      }
      const start = performance.now();
      const frameStep = (now: number) => {
        const t = clamp01((now - start) / 650);
        api.camera(lerpCam(from, target, ease(t), 0.1));
        api.flush();
        if (t < 1) tween.current = requestAnimationFrame(frameStep);
      };
      tween.current = requestAnimationFrame(frameStep);
    },
    [cameras, cards, reduced, stops],
  );

  const measure = useCallback(() => {
    const node = frame.current;
    if (!node) return;
    geometry.current = { top: node.getBoundingClientRect().top + window.scrollY, vh: window.innerHeight };
    const first = strip.current?.firstElementChild as HTMLElement | null;
    step.current = first ? first.offsetWidth + 12 : 1;
  }, []);

  /** The map unfolds as it scrolls into view: from its top at 92% of the viewport to 22%. */
  const unfold = useCallback(
    () => {
      const api = map.current;
      if (!api || !size.w) return;
      const { top, vh } = geometry.current;
      const y = window.scrollY;
      if (top - y > vh * 1.5 || top - y < -vh * 2) return; // far away: nothing to do
      const m = reduced ? 1 : clamp01((vh * 0.92 - (top - y)) / (vh * 0.7));
      if (m <= 0) startRot.current = [...globeView.rotation];
      const morph = morphAt(m, startRot.current);
      api.morph(morph);
      api.layers({ dots: ramp(morph.alpha, 0.8, 1), route: ramp(m, 0.85, 1), routeOpacity: 1 });
      if (morph.alpha < 1) {
        unfolded.current = false;
        cancelAnimationFrame(tween.current);
        api.layers({ regions: 0, pinOpacity: 0 });
        api.camera(lerpCam(cameras.globe, cameras.fit, morph.alpha));
        api.flush();
      } else if (!unfolded.current) {
        unfolded.current = true;
        travel(indexRef.current);
      } else api.flush();
    },
    [cameras, reduced, size.w, travel],
  );

  useScrollFrame(() => unfold(), measure);
  useEffect(() => {
    unfolded.current = false;
    measure();
    unfold();
  }, [unfold, measure]);
  useEffect(() => {
    const node = frame.current;
    if (!node) return;
    const observer = new ResizeObserver(([entry]) => entry && setSize({ w: entry.contentRect.width, h: entry.contentRect.height }));
    observer.observe(node);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(tween.current);
    };
  }, []);

  // The strip is native scrolling; this only notices which card is in front (one read per frame).
  const stripFrame = useRef(0);
  function onStripScroll() {
    if (stripFrame.current) return;
    stripFrame.current = requestAnimationFrame(() => {
      stripFrame.current = 0;
      const node = strip.current;
      if (!node) return;
      // At the end of the strip the last card may not reach the start edge: count it as reached.
      const atEnd = node.scrollLeft >= node.scrollWidth - node.clientWidth - 4;
      const i = atEnd ? cards - 1 : Math.max(0, Math.min(cards - 1, Math.round(node.scrollLeft / step.current)));
      if (i !== indexRef.current) {
        indexRef.current = i;
        setIndex(i);
        if (unfolded.current) travel(i);
      }
    });
  }
  const show = (i: number) => strip.current?.scrollTo({ left: Math.max(0, Math.min(cards - 1, i)) * step.current, behavior: reduced ? "auto" : "smooth" });
  const chosen = stops[Math.max(0, Math.min(stops.length - 1, index - 1))] ?? null;

  return (
    <section id="atlas" aria-labelledby="atlas-title" className="voyage-stage paper-grain relative overflow-hidden py-16 sm:py-24">
      <div className="mx-auto max-w-[1100px] px-5 sm:px-8">
        <p className="small-caps text-[11px] text-ink-soft">The atlas opens</p>
        <h2 id="atlas-title" className="serif-display mt-3 max-w-[16ch] text-[clamp(36px,9vw,64px)] leading-[1.02] text-ink">
          The world is full of opportunity.
        </h2>
        <p className="mt-4 max-w-[46ch] text-[16px] leading-relaxed text-ink-soft sm:text-[17px]">
          Let’s explore it. {reduced ? "The map shows where the listings are;" : "Scroll on and the globe opens into a map;"} swipe through the destinations below it.
        </p>
      </div>

      <div ref={frame} className="relative mx-auto mt-8 h-[clamp(240px,66vw,520px)] max-w-[1100px]">
        <MapCanvas ref={map} width={size.w} height={size.h} voyage={voyage} light={!wideEnough} showRegions={wideEnough} className="absolute inset-0" />
      </div>

      <div className="mx-auto mt-6 max-w-[1100px]">
        <ol
          ref={strip}
          onScroll={onStripScroll}
          tabIndex={0}
          aria-label="Destinations. Scroll sideways for more."
          className="voyage-strip flex snap-x snap-mandatory gap-3 overflow-x-auto scroll-px-5 px-5 pb-4 [scrollbar-width:none] sm:scroll-px-8 sm:px-8"
        >
          <li aria-label={`1 of ${cards}: ${CHAPTERS[1]}`} className="voyage-slide">
            <div className="voyage-panel h-full border-[1.5px] border-ink p-5">
              <p className="small-caps text-[10.5px] text-ink-soft">{CHAPTERS[1]}</p>
              <h3 className="serif-display mt-2 text-[26px] leading-[1.05] text-ink">Opportunities don’t sit in one place.</h3>
              <p className="num mt-2 text-[14px] text-ink-soft">{voyage.isPending ? "Reading the index…" : `${plural(voyage.total, "listing")} across ${plural(voyage.countryCount, "country", "countries")}.`}</p>
              <ul className="mt-3 border-t border-dashed border-ink/40">
                {voyage.regions.map((region) => (
                  <li key={region.key}>
                    {region.stop >= 0 ? (
                      <button type="button" onClick={() => show(region.stop + 1)} className="flex min-h-10 w-full items-center justify-between gap-3 text-left text-[14px] text-ink">
                        <span className="underline decoration-ink/25 underline-offset-4">{region.label}</span>
                        <span className="num text-[12.5px] text-muted">{region.listings}</span>
                      </button>
                    ) : (
                      <span className="flex min-h-10 items-center justify-between gap-3 text-[14px] text-ink-soft">
                        {region.label}
                        <span className="num text-[12.5px] text-muted">{region.listings}</span>
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          </li>
          {stops.map((stop, i) => (
            <li key={stop.key} aria-label={`${i + 2} of ${cards}: ${stop.label}`} className="voyage-slide">
              <div className="flex h-full flex-col gap-3">
                <p className="small-caps px-1 text-[10.5px] text-ink-soft">
                  {stop.label} · {plural(stop.listings, "listing")}
                </p>
                <StopCard stop={stop} compact />
              </div>
            </li>
          ))}
          <li aria-label={`${cards} of ${cards}: ${CHAPTERS[3]}`} className="voyage-slide">
            <div className="voyage-panel h-full border-[1.5px] border-ink p-5">
              <NextDestination voyage={voyage} chosen={chosen} />
            </div>
          </li>
          <li aria-hidden="true" className="w-1 shrink-0" />
        </ol>
        <div className="flex items-center gap-3 px-5 sm:px-8">
          <button type="button" onClick={() => show(index - 1)} disabled={index === 0} className="atlas-ctl text-ink disabled:opacity-35" aria-label="Previous destination">
            <ChevronLeft size={17} />
          </button>
          <span className="relative h-[2px] flex-1 overflow-hidden bg-ink/15" aria-hidden="true">
            <span className="absolute inset-y-0 left-0 w-full origin-left bg-ink transition-transform duration-300" style={{ transform: `scaleX(${(index + 1) / cards})` }} />
          </span>
          <span className="num text-[12px] text-ink-soft" aria-live="polite">
            {index + 1} / {cards}
          </span>
          <button type="button" onClick={() => show(index + 1)} disabled={index === cards - 1} className="atlas-ctl text-ink disabled:opacity-35" aria-label="Next destination">
            <ChevronRight size={17} />
          </button>
        </div>
        <p className="mt-2 px-5 text-right sm:px-8">
          <Link to="/opportunities" className="small-caps inline-flex min-h-10 items-center gap-1 text-[10.5px] text-ink underline decoration-ink/30 underline-offset-4">
            Skip to all opportunities
            <ArrowRight size={12} />
          </Link>
        </p>
      </div>
    </section>
  );
}

export default function AtlasVoyage() {
  const voyage = useVoyage();
  const pinned = useVoyagePinned();
  const reduced = Boolean(useReducedMotion());
  return pinned ? <PinnedStory voyage={voyage} /> : <StripStory voyage={voyage} reduced={reduced} />;
}
