/**
 * The Cartographer's Atlas: hand-inked illustrations for the landing page.
 *
 * One visual universe: antique cartography drawn with a fixed deep-ink contour
 * (var(--atlas-ink)) over muted watercolour fills, on parchment. Geography is
 * real (see ./geo); only the objects around it are drawn. Free-standing
 * background linework uses currentColor so it redraws itself in dark mode.
 */
import type { ReactNode } from "react";
import { GLOBE, GLOBE_GRATICULE, GLOBE_LAND } from "./geo-globe";

export const INK = "var(--atlas-ink)";

/* ------------------------------------------------------------------------ */
/* Shared drawing helpers                                                    */
/* ------------------------------------------------------------------------ */

/** Point on a circle, angle in degrees clockwise from 12 o'clock. */
export function polar(cx: number, cy: number, r: number, deg: number): [number, number] {
  const a = ((deg - 90) * Math.PI) / 180;
  return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
}

/** Rotate a point around a centre, degrees clockwise (SVG convention). */
export function rotatePoint([x, y]: readonly [number, number], [cx, cy]: readonly [number, number], deg: number): [number, number] {
  const a = (deg * Math.PI) / 180;
  const dx = x - cx;
  const dy = y - cy;
  return [cx + dx * Math.cos(a) - dy * Math.sin(a), cy + dx * Math.sin(a) + dy * Math.cos(a)];
}

/** Gradients and engraving patterns shared by every illustration (render once per page). */
export function AtlasDefs() {
  return (
    <svg width="0" height="0" className="absolute" aria-hidden="true" focusable="false">
      <defs>
        <radialGradient id="atlas-sea" cx="34%" cy="30%" r="80%">
          <stop offset="0" stopColor="#d6e4df" />
          <stop offset="0.5" stopColor="var(--atlas-sea)" />
          <stop offset="1" stopColor="var(--atlas-sea-deep)" />
        </radialGradient>
        <radialGradient id="atlas-shade" cx="32%" cy="28%" r="78%">
          <stop offset="0.52" stopColor="#1f2833" stopOpacity="0" />
          <stop offset="1" stopColor="#1f2833" stopOpacity="0.42" />
        </radialGradient>
        <radialGradient id="atlas-shine" cx="50%" cy="50%" r="50%">
          <stop offset="0" stopColor="#fffaf0" stopOpacity="0.75" />
          <stop offset="1" stopColor="#fffaf0" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="atlas-brass" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="var(--atlas-brass-hi)" />
          <stop offset="0.5" stopColor="var(--atlas-brass)" />
          <stop offset="1" stopColor="var(--atlas-brass-deep)" />
        </linearGradient>
        <linearGradient id="atlas-brass-h" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="var(--atlas-brass-deep)" />
          <stop offset="0.35" stopColor="var(--atlas-brass-hi)" />
          <stop offset="0.7" stopColor="var(--atlas-brass)" />
          <stop offset="1" stopColor="var(--atlas-brass-deep)" />
        </linearGradient>
        <linearGradient id="atlas-wood" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="var(--atlas-wood-deep)" />
          <stop offset="0.4" stopColor="var(--atlas-wood)" />
          <stop offset="0.62" stopColor="#9a6a47" />
          <stop offset="1" stopColor="var(--atlas-wood-deep)" />
        </linearGradient>
        <linearGradient id="atlas-paper" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="var(--atlas-paper)" />
          <stop offset="1" stopColor="var(--atlas-paper-deep)" />
        </linearGradient>
        {/* Engraver's hatching for land, and fine horizontal lines for water. */}
        <pattern id="atlas-hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(38)">
          <line x1="0" y1="0" x2="0" y2="5" stroke="#1f2833" strokeOpacity="0.22" strokeWidth="0.8" />
        </pattern>
        <pattern id="atlas-water" width="9" height="5" patternUnits="userSpaceOnUse">
          <line x1="0" y1="2.5" x2="5" y2="2.5" stroke="#1f2833" strokeOpacity="0.1" strokeWidth="0.7" />
        </pattern>
        <filter id="atlas-soft" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="6" />
        </filter>
      </defs>
    </svg>
  );
}

/** A compass rose: 32 points in alternating fills, inked. */
export function CompassRose({ cx, cy, r, fill = true }: { cx: number; cy: number; r: number; fill?: boolean }) {
  const points: { deg: number; len: number; w: number; dark: boolean }[] = [];
  for (let i = 0; i < 32; i += 1) {
    const deg = i * 11.25;
    const major = i % 8 === 0;
    const mid = i % 4 === 0 && !major;
    const len = major ? r : mid ? r * 0.72 : i % 2 === 0 ? r * 0.52 : r * 0.38;
    points.push({ deg, len, w: major ? r * 0.13 : mid ? r * 0.09 : r * 0.05, dark: i % 2 === 0 });
  }
  return (
    <g>
      <circle cx={cx} cy={cy} r={r * 0.58} fill="none" stroke="currentColor" strokeWidth="0.8" />
      <circle cx={cx} cy={cy} r={r * 0.62} fill="none" stroke="currentColor" strokeWidth="0.5" strokeDasharray="2 3" />
      {[...points].reverse().map(({ deg, len, w, dark }) => {
        const tip = polar(cx, cy, len, deg);
        const left = polar(cx, cy, w, deg - 90);
        const right = polar(cx, cy, w, deg + 90);
        return (
          <g key={deg}>
            <path d={`M${left[0]} ${left[1]} L${tip[0]} ${tip[1]} L${cx} ${cy} Z`} fill={fill ? (dark ? "currentColor" : "transparent") : "transparent"} stroke="currentColor" strokeWidth="0.7" strokeLinejoin="round" />
            <path d={`M${right[0]} ${right[1]} L${tip[0]} ${tip[1]} L${cx} ${cy} Z`} fill={fill ? (dark ? "transparent" : "currentColor") : "transparent"} fillOpacity={0.55} stroke="currentColor" strokeWidth="0.7" strokeLinejoin="round" />
          </g>
        );
      })}
      <circle cx={cx} cy={cy} r={r * 0.06} fill="var(--atlas-bg)" stroke="currentColor" strokeWidth="0.8" />
    </g>
  );
}

/**
 * The portolan backdrop: rhumb lines radiating from a faint rose, as on
 * fifteenth-century sea charts. It fills its container behind the scene.
 */
export function PortolanBackdrop({ className = "", cx = 1060, cy = 470 }: { className?: string; cx?: number; cy?: number }) {
  const lines = Array.from({ length: 32 }, (_, i) => {
    const [x, y] = polar(cx, cy, 1800, i * 11.25);
    return { x, y, dashed: i % 2 === 1, strong: i % 8 === 0 };
  });
  return (
    <svg viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice" className={`pointer-events-none text-ink ${className}`} aria-hidden="true">
      <g opacity="0.16">
        {lines.map((line, i) =>
          line.dashed ? (
            <line key={i} x1={cx} y1={cy} x2={line.x} y2={line.y} stroke="currentColor" strokeWidth={0.6} strokeDasharray="3 6" />
          ) : (
            // Solid rhumbs draw outward from the rose on the hero's entrance (pathLength 1 makes the dash a percentage).
            <line key={i} className="rhumb" style={{ animationDelay: `${(i % 8) * 60}ms` }} pathLength={1} strokeDasharray="1" x1={cx} y1={cy} x2={line.x} y2={line.y} stroke="currentColor" strokeWidth={line.strong ? 1 : 0.6} />
          ),
        )}
        <circle cx={cx} cy={cy} r="420" fill="none" stroke="currentColor" strokeWidth="0.8" />
        <circle cx={cx} cy={cy} r="432" fill="none" stroke="currentColor" strokeWidth="0.5" />
      </g>
      <g opacity="0.22">
        <g className="rose">
          <CompassRose cx={cx} cy={cy} r={130} />
        </g>
      </g>
    </svg>
  );
}

/** A hand-drawn wavy rule between sections, so they meet like torn chart edges rather than boxes. */
export function InkEdge({ className = "", flip = false }: { className?: string; flip?: boolean }) {
  return (
    <svg viewBox="0 0 1440 40" preserveAspectRatio="none" className={`block h-6 w-full text-ink sm:h-9 ${flip ? "rotate-180" : ""} ${className}`} aria-hidden="true">
      <path
        d="M0 22 C 80 12, 140 30, 230 20 S 380 8, 470 22 S 640 34, 730 19 S 900 6, 1000 20 S 1170 33, 1260 18 S 1400 12, 1440 20"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        vectorEffect="non-scaling-stroke"
      />
      <path d="M0 29 C 120 22, 260 34, 420 27 S 760 20, 980 29 S 1300 34, 1440 27" fill="none" stroke="currentColor" strokeWidth="0.7" opacity="0.5" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/* ------------------------------------------------------------------------ */
/* Scene 1: the explorer's globe                                             */
/* ------------------------------------------------------------------------ */

/** The globe's frame: viewBox size, sphere centre and tilt, shared with the tag overlay. */
export const GLOBE_SCENE = { width: 680, height: 720, cx: 340, cy: 300, tilt: -18, offset: [90, 50] as const };

/** Where a globe point (from GLOBE_POINTS) lands in the scene, after the axial tilt. */
export function globeScenePoint(point: readonly [number, number]): [number, number] {
  const { cx, cy, tilt, offset } = GLOBE_SCENE;
  return rotatePoint([point[0] + offset[0], point[1] + offset[1]], [cx, cy], tilt);
}

/** An elliptical brass band (the horizon ring); ``half`` keeps the back or front arc only. */
function HorizonRing({ half }: { half: "back" | "front" }) {
  const { cx, cy } = GLOBE_SCENE;
  const rx = 312;
  const ry = 54;
  const y = cy + 18;
  const arc = half === "back" ? `M ${cx - rx} ${y} A ${rx} ${ry} 0 0 1 ${cx + rx} ${y}` : `M ${cx - rx} ${y} A ${rx} ${ry} 0 0 0 ${cx + rx} ${y}`;
  const ticks =
    half === "front"
      ? Array.from({ length: 35 }, (_, i) => {
          const t = Math.PI * (i / 34);
          const x = cx - rx * Math.cos(t);
          const yy = y + ry * Math.sin(t);
          return <line key={i} x1={x} y1={yy - 4} x2={x} y2={yy + (i % 5 === 0 ? 5 : 2)} stroke={INK} strokeWidth="0.8" />;
        })
      : null;
  return (
    <g>
      <path d={arc} fill="none" stroke={INK} strokeWidth="19" strokeLinecap="round" />
      <path d={arc} fill="none" stroke="url(#atlas-brass-h)" strokeWidth="15" strokeLinecap="round" />
      <path d={arc} fill="none" stroke="var(--atlas-brass-hi)" strokeWidth="1.2" strokeOpacity="0.8" transform="translate(0 -4)" />
      {ticks}
    </g>
  );
}

/** The static land layer: projected offline, for first paint and as the fallback. */
export function StaticSphere() {
  const { cx, cy, tilt, offset } = GLOBE_SCENE;
  return (
    <g transform={`rotate(${tilt} ${cx} ${cy}) translate(${offset[0]} ${offset[1]})`}>
      <path d={GLOBE_GRATICULE} className="g-graticule" fill="none" stroke={INK} strokeOpacity="0.32" strokeWidth="0.6" />
      <path d={GLOBE_LAND} className="g-land-fill" fill="var(--atlas-land)" />
      <path d={GLOBE_LAND} className="g-land-fill" fill="url(#atlas-hatch)" />
      <path d={GLOBE_LAND} className="g-coast" pathLength={1} fill="none" stroke={INK} strokeWidth="1.25" strokeLinejoin="round" />
    </g>
  );
}

/**
 * The explorer's globe, drawn as separate layers so each can move on its own:
 * ground shadow, back legs, back half of the horizon ring, the sphere (meridian
 * ring, sea, land, shading, pins), the front half of the ring, the turned stand,
 * and the props in front. ``sphere`` replaces the land layer (the live globe
 * passes its projected paths here); ``children`` draws above the sphere, inside
 * its sway. ``compact`` keeps only the sphere and its rings, for phones.
 */
export function ExplorerGlobe({
  sphere,
  children,
  compact = false,
  className = "",
}: {
  sphere?: ReactNode;
  children?: ReactNode;
  compact?: boolean;
  className?: string;
}) {
  const { width, height, cx, cy, tilt } = GLOBE_SCENE;
  const r = GLOBE.radius;
  const north = rotatePoint([cx, cy - 288], [cx, cy], tilt);
  const south = rotatePoint([cx, cy + 288], [cx, cy], tilt);
  const ringTicks = Array.from({ length: 36 }, (_, i) => {
    const deg = i * 10;
    const [x1, y1] = polar(cx, cy, 266, deg);
    const [x2, y2] = polar(cx, cy, i % 3 === 0 ? 276 : 271, deg);
    return <line key={deg} x1={x1} y1={y1} x2={x2} y2={y2} stroke={INK} strokeWidth="0.9" />;
  });
  const viewBox = compact ? `14 4 652 612` : `0 0 ${width} ${height}`;

  return (
    <svg viewBox={viewBox} className={`atlas-art globe-scene overflow-visible ${className}`} role="img" aria-label="An explorer's globe on a brass stand">
      {!compact && (
        <>
          <ellipse className="g-shadow" cx={cx} cy={688} rx={250} ry={18} fill="#1f2833" opacity="0.16" filter="url(#atlas-soft)" />
          <g className="g-stand">
            <path d="M 150 330 C 170 430, 230 560, 262 664" fill="none" stroke={INK} strokeWidth="9" strokeLinecap="round" />
            <path d="M 150 330 C 170 430, 230 560, 262 664" fill="none" stroke="url(#atlas-wood)" strokeWidth="6" strokeLinecap="round" />
            <path d="M 530 330 C 510 430, 450 560, 418 664" fill="none" stroke={INK} strokeWidth="9" strokeLinecap="round" />
            <path d="M 530 330 C 510 430, 450 560, 418 664" fill="none" stroke="url(#atlas-wood)" strokeWidth="6" strokeLinecap="round" />
          </g>
        </>
      )}

      <g className="g-ring">
        <HorizonRing half="back" />
      </g>

      {/* The sphere sways gently in its cradle, as the reference's ship rocks on the swell. */}
      <g className="g-sphere">
        <g className="atlas-sway" style={{ transformBox: "view-box", transformOrigin: `${cx}px ${height - 40}px` }}>
          <circle className="g-meridian" pathLength={1} cx={cx} cy={cy} r={271} fill="none" stroke={INK} strokeWidth="16" />
          <circle className="g-meridian" pathLength={1} cx={cx} cy={cy} r={271} fill="none" stroke="url(#atlas-brass)" strokeWidth="13" />
          <g className="g-ticks" transform={`rotate(${tilt} ${cx} ${cy})`}>{ringTicks}</g>

          <clipPath id="atlas-sphere-clip">
            <circle cx={cx} cy={cy} r={r} />
          </clipPath>
          <g clipPath="url(#atlas-sphere-clip)">
            <circle cx={cx} cy={cy} r={r} fill="url(#atlas-sea)" />
            <circle cx={cx} cy={cy} r={r} fill="url(#atlas-water)" />
            <g className="g-land">{sphere ?? <StaticSphere />}</g>
            {/* Light from the upper left, shadow toward the lower right. */}
            <circle cx={cx} cy={cy} r={r} fill="url(#atlas-shade)" pointerEvents="none" />
            <ellipse cx={cx - 95} cy={cy - 110} rx={70} ry={46} fill="url(#atlas-shine)" transform={`rotate(-35 ${cx - 95} ${cy - 110})`} pointerEvents="none" />
          </g>
          <circle cx={cx} cy={cy} r={r} fill="none" stroke={INK} strokeWidth="2.2" pointerEvents="none" />
          {children}
          {[north, south].map(([x, y], i) => (
            <g key={i} className="g-ticks">
              <circle cx={x} cy={y} r={9} fill="url(#atlas-brass)" stroke={INK} strokeWidth="1.6" />
              <circle cx={x} cy={y} r={3} fill={INK} />
            </g>
          ))}
        </g>
      </g>

      <g className="g-ring">
        <HorizonRing half="front" />
      </g>

      {!compact && (
        <>
          <g className="g-stand">
            <path d="M 44 330 C 70 470, 150 600, 196 668" fill="none" stroke={INK} strokeWidth="13" strokeLinecap="round" />
            <path d="M 44 330 C 70 470, 150 600, 196 668" fill="none" stroke="url(#atlas-wood)" strokeWidth="9.5" strokeLinecap="round" />
            <path d="M 636 330 C 610 470, 530 600, 484 668" fill="none" stroke={INK} strokeWidth="13" strokeLinecap="round" />
            <path d="M 636 330 C 610 470, 530 600, 484 668" fill="none" stroke="url(#atlas-wood)" strokeWidth="9.5" strokeLinecap="round" />
            <path
              d="M 324 572 L 356 572 L 360 590 C 384 600, 384 618, 366 626 C 392 636, 396 652, 372 660 L 308 660 C 284 652, 288 636, 314 626 C 296 618, 296 600, 320 590 Z"
              fill="url(#atlas-wood)"
              stroke={INK}
              strokeWidth="1.8"
              strokeLinejoin="round"
            />
            <rect x={316} y={566} width={48} height={10} rx={3} fill="url(#atlas-brass)" stroke={INK} strokeWidth="1.4" />
            <path d="M 150 668 L 530 668 L 548 686 L 132 686 Z" fill="url(#atlas-wood)" stroke={INK} strokeWidth="1.8" strokeLinejoin="round" />
            <ellipse cx={340} cy={668} rx={190} ry={14} fill="#9a6a47" stroke={INK} strokeWidth="1.8" />
            <g className="text-[var(--atlas-ink)]" opacity="0.55">
              <CompassRose cx={340} cy={668} r={11} fill={false} />
            </g>
          </g>
          <g className="g-scroll">
            <g transform="translate(18 650) rotate(-8)">
              <path d="M 0 34 L 196 10 L 204 40 L 8 66 Z" fill="url(#atlas-paper)" stroke={INK} strokeWidth="1.6" strokeLinejoin="round" />
              <path d="M 30 36 L 170 19 M 36 46 L 150 32 M 40 55 L 120 46" stroke={INK} strokeWidth="0.8" opacity="0.45" />
              <ellipse cx={200} cy={25} rx={9} ry={16} fill="var(--atlas-paper-deep)" stroke={INK} strokeWidth="1.6" transform="rotate(-8 200 25)" />
              <ellipse cx={200} cy={25} rx={3.5} ry={7} fill="none" stroke={INK} strokeWidth="1" transform="rotate(-8 200 25)" />
              <path d="M 2 34 C -8 40, -6 60, 8 66" fill="none" stroke={INK} strokeWidth="1.6" />
              <rect x={86} y={22} width={14} height={38} fill="var(--atlas-terra)" stroke={INK} strokeWidth="1.2" transform="rotate(-7 93 41)" />
            </g>
          </g>
          <g className="g-dividers">
            <g transform="translate(560 612) rotate(28)">
              <path d="M 0 0 L 6 92 M 0 0 L -26 88" stroke={INK} strokeWidth="5.5" strokeLinecap="round" />
              <path d="M 0 0 L 6 92 M 0 0 L -26 88" stroke="url(#atlas-brass)" strokeWidth="3.4" strokeLinecap="round" />
              <circle cx={0} cy={0} r={8} fill="url(#atlas-brass)" stroke={INK} strokeWidth="1.5" />
              <circle cx={0} cy={0} r={2.2} fill={INK} />
            </g>
          </g>
        </>
      )}
    </svg>
  );
}

/** A curling old-map cloud: one inked outline over a pale wash, for the hero's sky. */
export function MapCloud({ className = "", width = 150 }: { className?: string; width?: number }) {
  return (
    <svg viewBox="0 0 160 64" width={width} className={`text-ink ${className}`} aria-hidden="true">
      <path
        d="M10 52 C 2 52, 2 40, 12 40 C 10 28, 26 22, 34 30 C 38 16, 60 12, 66 26 C 74 12, 100 14, 100 30 C 112 22, 130 28, 126 40 C 140 38, 148 52, 136 54 Z"
        fill="var(--atlas-paper)"
        fillOpacity="0.85"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinejoin="round"
      />
      <path d="M 44 42 C 48 36, 56 36, 58 42 M 84 40 C 88 34, 96 34, 98 40 M 24 48 C 26 44, 32 44, 34 48" fill="none" stroke="currentColor" strokeWidth="0.9" strokeLinecap="round" opacity="0.6" />
    </svg>
  );
}

