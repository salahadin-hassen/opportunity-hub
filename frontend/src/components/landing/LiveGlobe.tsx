/**
 * The globe you can turn. Loaded after first paint (with d3-geo and the world
 * outline), it shows every country with listings as a quiet pin, and one active
 * destination as an inked map pin that drops in when the globe arrives there.
 *
 * Rendering stays outside React: each frame projects the land once (no adaptive
 * resampling: the outline is already dense) and writes it to a single path that
 * the fill, the hatching and the coastline all reference. The animation loop runs
 * only while something moves (a journey, a drag's inertia, an arrow-key turn).
 */
import { geoDistance, geoOrthographic, geoPath } from "d3-geo";
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { ExplorerGlobe, GLOBE_SCENE, INK, rotatePoint } from "./Atlas";
import { GRATICULE, GRATICULE_MOTION, LAND_FULL, LAND_LIGHT, LAND_MOTION } from "./geo-land";
import { COUNTRY_CENTRES } from "./geo-world";
import { globeView } from "./shared";

export type GlobePin = { code: string; count: number; label: string };
export type GlobeHandle = {
  /** Turn so ``[lon, lat]`` sits in the viewing position, then call ``onArrive``. Duration 0 jumps there. */
  travelTo: (lon: number, lat: number, duration: number, onArrive?: () => void) => void;
};

/** A frame whose projection takes longer than this (ms) means a slow device: draw every other frame instead. */
const SLOW_FRAME = 18;
export const GLOBE_START: [number, number] = [-18, -14];
const easeInOut = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);

/** The active destination's map pin, its anchor (the geographic point) at 0,0. */
function MapPin() {
  return (
    <g>
      <ellipse cx={2.5} cy={1} rx={6} ry={2.2} fill="#1f2833" opacity="0.28" />
      <path d="M0 0 C -1.6 -5.2, -8.6 -10.4, -8.6 -18.2 A 8.6 8.6 0 1 1 8.6 -18.2 C 8.6 -10.4, 1.6 -5.2, 0 0 Z" fill="var(--atlas-terra)" stroke={INK} strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M -5.4 -21.5 A 6 6 0 0 1 -1.2 -25.6" fill="none" stroke="#fff3df" strokeWidth="1.4" strokeLinecap="round" opacity="0.7" />
      <circle cx={0} cy={-18.2} r={3.4} fill="var(--atlas-paper)" stroke={INK} strokeWidth="1.2" />
    </g>
  );
}

export const LiveGlobe = forwardRef<
  GlobeHandle,
  {
    pins: GlobePin[];
    /** The destination being shown: its pin drops in whenever ``landing`` changes. */
    active: string | null;
    landing: number;
    visited: ReadonlySet<string>;
    onSelect: (code: string) => void;
    /** The user grabbed or turned the globe themselves. */
    onUserTurn?: () => void;
    /** Each frame: where the active pin's point is, in scene units (after tilt), or null when it's out of view. */
    onActiveMove?: (point: [number, number] | null) => void;
    /** False while the hero is off screen: no frames are drawn. */
    running: boolean;
    reduced: boolean;
    compact?: boolean;
    className?: string;
  }
>(function LiveGlobe({ pins, active, landing, visited, onSelect, onUserTurn, onActiveMove, running, reduced, compact = false, className = "" }, ref) {
  const { cx, cy, tilt } = GLOBE_SCENE;
  const rotation = useRef<[number, number]>([...GLOBE_START]);
  const velocity = useRef(0);
  const tween = useRef<{ from: [number, number]; to: [number, number]; start: number; duration: number; done?: () => void } | null>(null);
  const frame = useRef(0);
  const drag = useRef<{ id: number; x: number; y: number; lastX: number; lastT: number; spinning: boolean; mouse: boolean } | null>(null);
  const land = useRef<SVGPathElement>(null);
  const graticule = useRef<SVGPathElement>(null);
  const pinNodes = useRef(new Map<string, SVGGElement>());
  const activeNode = useRef<SVGGElement>(null);
  const scale = useRef(1);
  const box = useRef<HTMLDivElement>(null);
  const [visibleCodes, setVisibleCodes] = useState<Set<string>>(new Set());
  const activeRef = useRef(active);
  activeRef.current = active;
  const moveRef = useRef(onActiveMove);
  moveRef.current = onActiveMove;
  const turnRef = useRef(onUserTurn);
  turnRef.current = onUserTurn;

  const projection = useMemo(() => geoOrthographic().scale(250).translate([cx, cy]).clipAngle(90).precision(0), [cx, cy]);
  const path = useMemo(() => geoPath(projection).digits(1), [projection]);
  const outline = compact ? LAND_LIGHT : LAND_FULL;
  const centres = useMemo(() => pins.filter((pin) => COUNTRY_CENTRES[pin.code]).map((pin) => ({ ...pin, at: COUNTRY_CENTRES[pin.code]! as [number, number] })), [pins]);

  const lastCost = useRef(0);
  const skip = useRef(false);
  const draw = useCallback((moving = false) => {
    // Opt-in timing for performance tests (a test sets window.__ohGlobePerf = []); nothing is recorded otherwise.
    const perf = (globalThis as { __ohGlobePerf?: number[] }).__ohGlobePerf;
    const started = perf ? performance.now() : 0;
    const [lon, lat] = rotation.current;
    globeView.rotation = [lon, lat];
    projection.rotate([lon, lat, 0]);
    const t0 = performance.now();
    land.current?.setAttribute("d", path(moving ? LAND_MOTION : outline) ?? "");
    graticule.current?.setAttribute("d", path(moving ? GRATICULE_MOTION : GRATICULE) ?? "");
    box.current?.classList.toggle("is-moving", moving);
    const centre: [number, number] = [-lon, -lat];
    const visible = new Set<string>();
    let activePoint: [number, number] | null = null;
    for (const pin of centres) {
      const node = pinNodes.current.get(pin.code);
      const shown = geoDistance(pin.at, centre) < Math.PI / 2 - 0.1;
      const xy = shown ? projection(pin.at) : null;
      if (xy) {
        visible.add(pin.code);
        const transform = `translate(${xy[0].toFixed(1)} ${xy[1].toFixed(1)})`;
        node?.setAttribute("transform", transform);
        if (node) node.style.visibility = "visible";
        if (pin.code === activeRef.current) {
          activeNode.current?.setAttribute("transform", transform);
          activePoint = rotatePoint([xy[0], xy[1]], [cx, cy], tilt);
        }
      } else if (node) {
        node.style.visibility = "hidden";
      }
    }
    if (activeNode.current) activeNode.current.style.visibility = activePoint ? "visible" : "hidden";
    moveRef.current?.(activePoint);
    lastCost.current = performance.now() - t0;
    if (perf) perf.push(performance.now() - started);
    // Visibility drives which pins are focusable; React hears about it only when the set changes.
    setVisibleCodes((old) => (old.size === visible.size && [...visible].every((code) => old.has(code)) ? old : visible));
  }, [centres, cx, cy, outline, path, projection, tilt]);

  /** One animation step; returns whether anything is still moving. Slow devices draw every other frame. */
  const step = useCallback(
    (now: number) => {
      const t = tween.current;
      const slow = lastCost.current > SLOW_FRAME;
      skip.current = slow ? !skip.current : false;
      if (t) {
        const k = t.duration <= 0 ? 1 : Math.min(1, (now - t.start) / t.duration);
        const e = easeInOut(k);
        let dLon = t.to[0] - t.from[0];
        dLon = ((dLon + 540) % 360) - 180; // the short way round
        rotation.current = [t.from[0] + dLon * e, t.from[1] + (t.to[1] - t.from[1]) * e];
        if (k >= 1) {
          tween.current = null;
          draw(false); // arrived: one full-detail drawing
          t.done?.();
          return false;
        }
        if (!skip.current) draw(true);
        return true;
      }
      if (!drag.current?.spinning && Math.abs(velocity.current) > 0.02) {
        rotation.current = [rotation.current[0] + velocity.current, rotation.current[1]];
        velocity.current *= 0.93;
        if (Math.abs(velocity.current) <= 0.02) {
          draw(false);
          return false;
        }
        if (!skip.current) draw(true);
        return true;
      }
      return false;
    },
    [draw],
  );

  const run = useCallback(() => {
    cancelAnimationFrame(frame.current);
    const loop = (now: number) => {
      if (document.hidden) return; // resumed by visibilitychange
      if (step(now)) frame.current = requestAnimationFrame(loop);
    };
    frame.current = requestAnimationFrame(loop);
  }, [step]);

  useEffect(() => {
    draw();
  }, [draw, active]);
  useEffect(() => {
    if (!running) {
      cancelAnimationFrame(frame.current);
      return;
    }
    run();
    const onVisible = () => !document.hidden && run();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelAnimationFrame(frame.current);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [run, running]);

  useImperativeHandle(
    ref,
    () => ({
      travelTo(lon, lat, duration, onArrive) {
        velocity.current = 0;
        // Sit the destination a little right of centre and away from the poles, so the card beside the globe can't cover it.
        const to: [number, number] = [-lon - (compact ? 0 : 16), Math.max(-48, Math.min(48, -lat + 6))];
        if (duration <= 0 || reduced) {
          tween.current = null;
          rotation.current = to;
          draw();
          onArrive?.();
          return;
        }
        tween.current = { from: [...rotation.current], to, start: performance.now(), duration, done: onArrive };
        run();
      },
    }),
    [compact, draw, reduced, run],
  );

  // Dragging turns the globe. On touch screens only a mostly horizontal drag turns it, so vertical swipes still scroll the page.
  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    const rect = box.current?.getBoundingClientRect();
    scale.current = rect ? 680 / rect.width : 1;
    // Nothing is captured yet: a press that doesn't move stays a click (on a pin, say).
    drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY, lastX: event.clientX, lastT: performance.now(), spinning: false, mouse: event.pointerType === "mouse" };
  }
  function onPointerMove(event: PointerEvent<HTMLDivElement>) {
    const d = drag.current;
    if (!d || d.id !== event.pointerId) return;
    if (!d.spinning) {
      const dx = event.clientX - d.x;
      const dy = event.clientY - d.y;
      if (Math.hypot(dx, dy) < (d.mouse ? 4 : 8)) return;
      // A mouse turns the globe in any direction; on touch, a mostly vertical drag is a scroll.
      if (!d.mouse && Math.abs(dx) < Math.abs(dy) * 1.2) {
        drag.current = null; // a scroll gesture: let the page have it
        return;
      }
      d.spinning = true;
      tween.current = null;
      turnRef.current?.();
      event.currentTarget.setPointerCapture(event.pointerId);
    }
    const now = performance.now();
    const delta = (event.clientX - d.lastX) * scale.current * 0.32;
    rotation.current = [rotation.current[0] + delta, rotation.current[1]];
    velocity.current = (delta / Math.max(8, now - d.lastT)) * 16;
    d.lastX = event.clientX;
    d.lastT = now;
    draw(true);
  }
  function onPointerUp(event: PointerEvent<HTMLDivElement>) {
    if (drag.current?.id !== event.pointerId) return;
    const spun = drag.current.spinning;
    drag.current = null;
    if (!spun) return;
    if (reduced || Math.abs(velocity.current) <= 0.02) draw(false);
    else run();
  }
  function onKeyDown(event: KeyboardEvent<SVGSVGElement>) {
    const turns: Record<string, [number, number]> = { ArrowLeft: [-12, 0], ArrowRight: [12, 0], ArrowUp: [0, 8], ArrowDown: [0, -8] };
    const turn = turns[event.key];
    if (!turn || event.target !== event.currentTarget) return;
    event.preventDefault();
    turnRef.current?.();
    const [lon, lat] = rotation.current;
    tween.current = { from: [lon, lat], to: [lon + turn[0], Math.max(-50, Math.min(50, lat + turn[1]))], start: performance.now(), duration: reduced ? 0 : 380 };
    run();
  }

  const maxCount = Math.max(1, ...pins.map((pin) => pin.count));
  const sphere = (
    <g transform={`rotate(${tilt} ${cx} ${cy})`}>
      <path ref={graticule} className="g-graticule" fill="none" stroke={INK} strokeOpacity="0.32" strokeWidth="0.6" />
      {/* One projected outline, drawn three ways. It carries no paint of its own, so each <use> supplies it. */}
      <defs>
        <path ref={land} id="atlas-live-land" pathLength={1} />
      </defs>
      <use href="#atlas-live-land" className="g-land-fill" fill="var(--atlas-land)" />
      <use href="#atlas-live-land" className="g-land-fill g-hatch" fill="url(#atlas-hatch)" />
      <use href="#atlas-live-land" className="g-coast" fill="none" stroke={INK} strokeWidth="1.25" strokeLinejoin="round" />
    </g>
  );

  return (
    // pan-y on the HTML wrapper: browsers ignore touch-action on SVG shapes. Vertical swipes scroll; horizontal ones turn the globe.
    <div
      ref={box}
      className={`relative cursor-grab touch-pan-y active:cursor-grabbing ${className}`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      <ExplorerGlobe sphere={sphere} compact={compact} className="block h-auto w-full">
        <g transform={`rotate(${tilt} ${cx} ${cy})`}>
          {centres.map((pin) => {
            const radius = 2.6 + Math.sqrt(pin.count / maxCount) * 3.6;
            const focusable = visibleCodes.has(pin.code);
            const isActive = pin.code === active;
            const seen = visited.has(pin.code) && !isActive;
            return (
              <g key={pin.code} ref={(node) => void (node ? pinNodes.current.set(pin.code, node) : pinNodes.current.delete(pin.code))} style={{ visibility: "hidden" }}>
                <g
                  className="globe-pin cursor-pointer outline-none"
                  role="button"
                  tabIndex={focusable ? 0 : -1}
                  aria-hidden={!focusable}
                  aria-pressed={isActive}
                  aria-label={`${pin.label}: ${pin.count} ${pin.count === 1 ? "listing" : "listings"}`}
                  onClick={() => onSelect(pin.code)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelect(pin.code);
                    }
                  }}
                >
                  {/* A generous invisible hit area for fingers. */}
                  <circle r={Math.max(radius + 9, 15)} fill="transparent" />
                  <circle className="pin-dot" r={radius} fill={seen ? "var(--atlas-terra)" : "var(--atlas-brass)"} fillOpacity={seen ? 0.55 : 0.9} stroke={INK} strokeWidth="1.1" opacity={isActive ? 0 : 1} />
                </g>
              </g>
            );
          })}
          {/* The active destination: an inked map pin that drops in, with one ripple where it lands. */}
          <g ref={activeNode} className="g-activepin" style={{ visibility: "hidden" }} pointerEvents="none" aria-hidden="true">
            {active && (
              <g key={`${active}-${landing}`}>
                <circle className="pin-ripple" r={7} fill="none" stroke="var(--atlas-terra)" strokeWidth="1.6" />
                <g className="pin-drop">
                  <MapPin />
                </g>
              </g>
            )}
          </g>
        </g>
      </ExplorerGlobe>
      <GlobeKeys onKeyDown={onKeyDown} />
    </div>
  );
});

/** A focusable stand-in for the globe that turns it with the arrow keys (the SVG itself stays decorative). */
function GlobeKeys({ onKeyDown }: { onKeyDown: (event: KeyboardEvent<SVGSVGElement>) => void }) {
  return (
    <svg
      tabIndex={0}
      role="application"
      aria-label="Globe. Use the arrow keys to turn it; the countries with listings are pins you can choose."
      aria-roledescription="globe"
      className="absolute inset-0 h-full w-full rounded-full opacity-0 focus-visible:opacity-100 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-cobalt"
      style={{ pointerEvents: "none" }}
      onKeyDown={onKeyDown}
    />
  );
}
