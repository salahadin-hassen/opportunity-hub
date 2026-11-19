/**
 * The illustrations below the fold (the chart table and the crossroads), split from
 * ./Atlas so the page's first load carries only the globe. Same ink, same palette.
 */
import { motion, type MotionValue } from "motion/react";
import { CompassRose, INK, polar } from "./Atlas";
import { CHART, CHART_GRATICULE, CHART_LAND, CHART_SPHERE } from "./geo-chart";

/* ------------------------------------------------------------------------ */
/* Scene 2: the navigator's chart table                                      */
/* ------------------------------------------------------------------------ */

/** The chart's placement inside the table scene (shared with any overlay). */
export const CHART_SCENE = { width: 1000, height: 700, x: 70, y: 82, scale: 0.84, tilt: -3 };

export function ChartTable({
  dots = [],
  className = "",
  needleClass = "",
  onDot,
}: {
  dots?: { code: string; label: string; point: readonly [number, number]; count: number }[];
  className?: string;
  needleClass?: string;
  /** Choosing a country mark; it also works as a plain link to that country's listings. */
  onDot?: (code: string) => void;
}) {
  const { width, height, x, y, scale, tilt } = CHART_SCENE;
  const w = CHART.width * scale;
  const h = CHART.height * scale;
  const sheet = { x: x - 34, y: y - 40, w: w + 68, h: h + 80 };
  const rose = { x: 0.4 * CHART.width, y: 0.56 * CHART.height };
  const rhumbs = Array.from({ length: 16 }, (_, i) => polar(rose.x, rose.y, 900, i * 22.5));
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className={`atlas-art overflow-visible ${className}`} role="img" aria-label="A world chart on a navigator's table, with a brass compass, dividers and an inkwell">
      <ellipse cx={width / 2} cy={height - 34} rx={460} ry={26} fill="#1f2833" opacity="0.14" filter="url(#atlas-soft)" />

      <g className="c-sheet">
      <g transform={`rotate(${tilt} ${width / 2} ${height / 2})`}>
        {/* The sheet: parchment with a double ruled border and a curled corner. */}
        <rect x={sheet.x + 8} y={sheet.y + 10} width={sheet.w} height={sheet.h} fill="#1f2833" opacity="0.18" filter="url(#atlas-soft)" />
        <path
          d={`M ${sheet.x} ${sheet.y} H ${sheet.x + sheet.w} V ${sheet.y + sheet.h - 46} L ${sheet.x + sheet.w - 46} ${sheet.y + sheet.h} H ${sheet.x} Z`}
          fill="url(#atlas-paper)"
          stroke={INK}
          strokeWidth="1.8"
          strokeLinejoin="round"
        />
        <path
          d={`M ${sheet.x + sheet.w} ${sheet.y + sheet.h - 46} L ${sheet.x + sheet.w - 46} ${sheet.y + sheet.h} C ${sheet.x + sheet.w - 40} ${sheet.y + sheet.h - 22}, ${sheet.x + sheet.w - 22} ${sheet.y + sheet.h - 44}, ${sheet.x + sheet.w} ${sheet.y + sheet.h - 46} Z`}
          fill="var(--atlas-paper-deep)"
          stroke={INK}
          strokeWidth="1.6"
          strokeLinejoin="round"
        />
        <rect x={sheet.x + 14} y={sheet.y + 14} width={sheet.w - 28} height={sheet.h - 28} fill="none" stroke={INK} strokeWidth="1.2" />
        <rect x={sheet.x + 19} y={sheet.y + 19} width={sheet.w - 38} height={sheet.h - 38} fill="none" stroke={INK} strokeWidth="0.6" />

        <g transform={`translate(${x} ${y}) scale(${scale})`}>
          <clipPath id="atlas-chart-clip">
            <path d={CHART_SPHERE} />
          </clipPath>
          <path d={CHART_SPHERE} fill="var(--atlas-sea)" fillOpacity="0.38" />
          <path d={CHART_SPHERE} fill="url(#atlas-water)" />
          <g clipPath="url(#atlas-chart-clip)" className="text-[var(--atlas-ink)]">
            {rhumbs.map(([rx, ry], i) => (
              <line key={i} x1={rose.x} y1={rose.y} x2={rx} y2={ry} stroke={INK} strokeOpacity={i % 4 === 0 ? 0.35 : 0.2} strokeWidth={1 / scale} strokeDasharray={i % 2 ? "4 6" : undefined} />
            ))}
          </g>
          <path d={CHART_GRATICULE} fill="none" stroke={INK} strokeOpacity="0.25" strokeWidth={0.7 / scale} />
          <path d={CHART_LAND} fill="var(--atlas-land)" />
          <path d={CHART_LAND} fill="url(#atlas-hatch)" />
          <path d={CHART_LAND} fill="none" stroke={INK} strokeWidth={1.1 / scale} strokeLinejoin="round" />
          <path d={CHART_SPHERE} fill="none" stroke={INK} strokeWidth={1.6 / scale} />
          <g className="text-[var(--atlas-ink)]" opacity="0.7">
            <CompassRose cx={rose.x} cy={rose.y} r={46} />
          </g>
          {/* One mark per country with listings; the area grows with how many. Each is a link to them. */}
          {dots.map((dot, index) => (
            <a
              key={dot.code}
              href={`/opportunities?where=${dot.code}`}
              className="c-dot-link"
              aria-label={`${dot.label}: ${dot.count} ${dot.count === 1 ? "listing" : "listings"}`}
              onClick={(event) => {
                if (!onDot || event.metaKey || event.ctrlKey) return;
                event.preventDefault();
                onDot(dot.code);
              }}
            >
              <title>{`${dot.label}: ${dot.count} ${dot.count === 1 ? "listing" : "listings"}`}</title>
              <circle cx={dot.point[0]} cy={dot.point[1]} r={Math.max(9, Math.sqrt(dot.count) * 2.4 + 6)} fill="transparent" />
              <circle
                className="c-dot"
                style={{ ["--i" as string]: index }}
                cx={dot.point[0]}
                cy={dot.point[1]}
                r={Math.max(3.2, Math.sqrt(dot.count) * 2.4)}
                fill="var(--atlas-terra)"
                fillOpacity="0.82"
                stroke={INK}
                strokeWidth={1.1 / scale}
              />
            </a>
          ))}
        </g>
      </g>
      </g>

      {/* Dividers resting across the chart's upper left. */}
      <g className="c-dividers">
      <g transform="translate(150 70) rotate(-24)">
        <path d="M 0 0 L 32 210 M 0 0 L -40 204" stroke={INK} strokeWidth="7" strokeLinecap="round" />
        <path d="M 0 0 L 32 210 M 0 0 L -40 204" stroke="url(#atlas-brass)" strokeWidth="4.4" strokeLinecap="round" />
        <path d="M -12 80 L 14 82" stroke={INK} strokeWidth="2" />
        <circle cx={0} cy={0} r={11} fill="url(#atlas-brass)" stroke={INK} strokeWidth="1.8" />
        <circle cx={0} cy={0} r={3} fill={INK} />
      </g>
      </g>

      {/* The inkwell and quill, bottom left. */}
      <g className="c-ink">
      <g transform="translate(36 540)">
        <ellipse cx={58} cy={118} rx={62} ry={10} fill="#1f2833" opacity="0.2" filter="url(#atlas-soft)" />
        <path d="M 14 60 C 14 40, 30 34, 40 34 L 76 34 C 86 34, 102 40, 102 60 L 102 108 C 102 116, 96 120, 88 120 L 28 120 C 20 120, 14 116, 14 108 Z" fill="#2a3a4c" stroke={INK} strokeWidth="1.8" />
        <path d="M 24 50 C 26 44, 32 42, 38 42" fill="none" stroke="#e8f0f4" strokeWidth="2.4" strokeLinecap="round" opacity="0.55" />
        <rect x={36} y={18} width={44} height={18} rx={3} fill="url(#atlas-brass)" stroke={INK} strokeWidth="1.6" />
        <path d="M 60 22 C 70 -40, 120 -110, 190 -150 C 160 -100, 120 -50, 66 24 Z" fill="var(--atlas-paper)" stroke={INK} strokeWidth="1.5" strokeLinejoin="round" />
        <path d="M 66 20 C 100 -40, 140 -95, 186 -146" fill="none" stroke={INK} strokeWidth="1" />
        {Array.from({ length: 11 }, (_, i) => {
          const t = 0.15 + i * 0.07;
          const px = 66 + (186 - 66) * t;
          const py = 20 + (-146 - 20) * t;
          return <path key={i} d={`M ${px} ${py} l ${-14 + i * 0.4} ${-6 - i * 0.6}`} stroke={INK} strokeWidth="0.7" opacity="0.6" />;
        })}
      </g>
      </g>

      {/* The compass, bottom right, its needle settling on north. */}
      <g className="c-compass">
      <g transform="translate(838 540)">
        <ellipse cx={8} cy={14} rx={118} ry={106} fill="#1f2833" opacity="0.22" filter="url(#atlas-soft)" />
        <circle r={116} fill="url(#atlas-brass)" stroke={INK} strokeWidth="2.2" />
        <circle r={104} fill="none" stroke={INK} strokeWidth="1.2" />
        <circle r={98} fill="var(--atlas-paper)" stroke={INK} strokeWidth="1.4" />
        {Array.from({ length: 72 }, (_, i) => {
          const [x1, y1] = polar(0, 0, 98, i * 5);
          const [x2, y2] = polar(0, 0, i % 6 === 0 ? 86 : 92, i * 5);
          return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke={INK} strokeWidth={i % 6 === 0 ? 1.2 : 0.6} />;
        })}
        {(["N", "E", "S", "W"] as const).map((letter, i) => {
          const [lx, ly] = polar(0, 0, 72, i * 90);
          return (
            <text key={letter} x={lx} y={ly + 6} textAnchor="middle" fontFamily="Gloock, Georgia, serif" fontSize="18" fill={INK}>
              {letter}
            </text>
          );
        })}
        <g className="text-[var(--atlas-ink)]" opacity="0.5">
          <CompassRose cx={0} cy={0} r={52} />
        </g>
        {/* Two layers: the arrival swing (c-needle), then a gentle idle hunt for north. */}
        <g className="c-needle">
          <g className={needleClass}>
            <path d="M 0 -78 L 9 0 L -9 0 Z" fill="var(--atlas-terra)" stroke={INK} strokeWidth="1.3" strokeLinejoin="round" />
            <path d="M 0 78 L 9 0 L -9 0 Z" fill="#2a3a4c" stroke={INK} strokeWidth="1.3" strokeLinejoin="round" />
          </g>
        </g>
        <circle r={7} fill="url(#atlas-brass)" stroke={INK} strokeWidth="1.4" />
        <rect x={-10} y={-136} width={20} height={22} rx={4} fill="url(#atlas-brass)" stroke={INK} strokeWidth="1.6" />
        <circle cx={0} cy={-142} r={10} fill="none" stroke={INK} strokeWidth="4" />
        <circle cx={0} cy={-142} r={10} fill="none" stroke="url(#atlas-brass)" strokeWidth="2.4" />
      </g>
      </g>
    </svg>
  );
}

/* ------------------------------------------------------------------------ */
/* Scene 4: the crossroads                                                   */
/* ------------------------------------------------------------------------ */

/** Signpost arm anchors in scene units, for the HTML labels laid over them. */
export const CROSSROADS = { width: 1200, height: 620, post: 470 };

function Mountain({ x, base, h, w, seed = 1 }: { x: number; base: number; h: number; w: number; seed?: number }) {
  // An engraved peak: irregular ridges, a snowcap, a lit face and a hatched shadow flank.
  const j = (n: number) => Math.sin(seed * 12.9898 + n * 78.233) * 0.5 + 0.5; // stable jitter, 0..1
  const L = x - w / 2;
  const R = x + w / 2;
  const top = base - h;
  const left = `M ${L} ${base} L ${L + w * 0.18} ${base - h * (0.34 + j(1) * 0.08)} L ${L + w * 0.26} ${base - h * (0.3 + j(2) * 0.06)} L ${L + w * 0.38} ${base - h * (0.66 + j(3) * 0.08)} L ${x - w * 0.04} ${top + h * 0.06} L ${x} ${top}`;
  const right = `L ${x + w * 0.08} ${top + h * 0.1} L ${x + w * 0.16} ${top + h * (0.2 + j(4) * 0.06)} L ${x + w * 0.24} ${top + h * 0.3} L ${x + w * 0.34} ${base - h * (0.46 + j(5) * 0.08)} L ${x + w * 0.42} ${base - h * 0.32} L ${R} ${base} Z`;
  const shadow = `M ${x} ${top} L ${x + w * 0.08} ${top + h * 0.1} L ${x + w * 0.16} ${top + h * (0.2 + j(4) * 0.06)} L ${x + w * 0.24} ${top + h * 0.3} L ${x + w * 0.34} ${base - h * (0.46 + j(5) * 0.08)} L ${x + w * 0.42} ${base - h * 0.32} L ${R} ${base} L ${x + w * 0.06} ${base} L ${x + w * 0.02} ${base - h * 0.42} Z`;
  const snow = `M ${x - w * 0.11} ${top + h * 0.24} L ${x - w * 0.04} ${top + h * 0.06} L ${x} ${top} L ${x + w * 0.08} ${top + h * 0.1} L ${x + w * 0.13} ${top + h * 0.2} L ${x + w * 0.07} ${top + h * 0.17} L ${x + w * 0.03} ${top + h * 0.27} L ${x - w * 0.02} ${top + h * 0.19} L ${x - w * 0.06} ${top + h * 0.28} Z`;
  const hatch = Array.from({ length: Math.round(h / 7) }, (_, i) => {
    const t = (i + 1) / (Math.round(h / 7) + 1);
    const y = top + h * t;
    const x1 = x + w * 0.04 + w * 0.42 * t;
    return <line key={i} x1={x1} y1={y} x2={x1 - w * 0.12 * (1 - t * 0.4)} y2={y + 3} stroke={INK} strokeWidth="0.7" opacity="0.55" />;
  });
  return (
    <g>
      <path d={left + " " + right} fill="var(--atlas-paper)" stroke={INK} strokeWidth="1.5" strokeLinejoin="round" />
      <path d={shadow} fill="var(--atlas-land-deep)" fillOpacity="0.5" />
      {hatch}
      <path d={snow} fill="#fbf8f0" stroke={INK} strokeWidth="1.1" strokeLinejoin="round" />
      <path d={`M ${x} ${top + h * 0.3} L ${x - w * 0.06} ${base - h * 0.3} M ${x + w * 0.02} ${top + h * 0.4} L ${x + w * 0.12} ${base - h * 0.2}`} stroke={INK} strokeWidth="0.8" opacity="0.5" />
      <path d={left + " " + right} fill="none" stroke={INK} strokeWidth="1.5" strokeLinejoin="round" />
    </g>
  );
}

/** An engraved sun: a disc with alternating straight and wavy rays. */
function Sun({ cx, cy, r }: { cx: number; cy: number; r: number }) {
  return (
    <g>
      <g className="sun-rays">
      {Array.from({ length: 24 }, (_, i) => {
        const [x1, y1] = polar(cx, cy, r * 1.25, i * 15);
        const [x2, y2] = polar(cx, cy, r * (i % 2 ? 1.75 : 2.05), i * 15);
        return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="currentColor" strokeWidth={i % 2 ? 0.8 : 1.3} strokeLinecap="round" opacity="0.7" />;
      })}
      </g>
      <circle cx={cx} cy={cy} r={r} fill="var(--atlas-brass-hi)" fillOpacity="0.7" stroke={INK} strokeWidth="1.5" />
      <circle cx={cx} cy={cy} r={r} fill="url(#atlas-hatch)" opacity="0.5" />
    </g>
  );
}

function Tree({ x, y, s = 1 }: { x: number; y: number; s?: number }) {
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      <ellipse cx={4} cy={2} rx={14} ry={4} fill="#1f2833" opacity="0.14" />
      <line x1={0} y1={0} x2={0} y2={-18} stroke={INK} strokeWidth="2" />
      <path d="M -14 -22 C -18 -40, -4 -54, 0 -52 C 6 -56, 20 -42, 14 -22 C 10 -14, -10 -14, -14 -22 Z" fill="var(--atlas-green)" stroke={INK} strokeWidth="1.5" />
      <path d="M -4 -44 C -8 -38, -8 -30, -4 -26 M 6 -40 C 8 -34, 8 -28, 4 -24" fill="none" stroke={INK} strokeWidth="0.8" opacity="0.55" />
    </g>
  );
}

const ROAD = "M 520 620 C 520 560, 420 520, 470 480 S 640 430, 700 400 S 800 350, 860 336";

export function Crossroads({
  arms,
  className = "",
  roadDraw,
  wiggle = null,
}: {
  arms: { y: number; dir: 1 | -1; tilt: number }[];
  className?: string;
  /** 0 to 1: how much of the road is drawn (scroll-linked by the page). */
  roadDraw?: MotionValue<number>;
  /** Index of the arm to wiggle (its label is hovered or focused). */
  wiggle?: number | null;
}) {
  const { width, height, post } = CROSSROADS;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className={`atlas-art overflow-visible text-ink ${className}`} role="img" aria-label="A signpost at a crossroads in hilly country, its arms pointing toward kinds of opportunity">
      <Sun cx={170} cy={150} r={34} />
      {/* Far range. */}
      {[
        [700, 330, 120, 150],
        [790, 330, 170, 190],
        [890, 330, 130, 160],
        [990, 330, 190, 210],
        [1100, 330, 120, 150],
        [1170, 330, 150, 170],
      ].map(([x, base, h, w], i) => (
        <Mountain key={i} x={x!} base={base!} h={h!} w={w!} seed={i + 1} />
      ))}
      {/* Rolling country in front of the range. */}
      <path d="M 0 360 C 160 300, 330 330, 520 330 S 900 300, 1200 336 L 1200 620 L 0 620 Z" fill="var(--atlas-paper)" stroke={INK} strokeWidth="1.6" />
      <path d="M 0 452 C 200 410, 420 430, 640 440 S 1000 420, 1200 446 L 1200 620 L 0 620 Z" fill="var(--atlas-green)" fillOpacity="0.38" stroke={INK} strokeWidth="1.6" />
      <path d="M 0 452 C 200 410, 420 430, 640 440 S 1000 420, 1200 446 L 1200 620 L 0 620 Z" fill="url(#atlas-hatch)" opacity="0.6" />
      {/* The road: out of the foreground, over the hills, toward the range. */}
      <path d="M 520 620 C 520 560, 420 520, 470 480 S 640 430, 700 400 S 800 350, 860 336" fill="none" stroke={INK} strokeWidth="44" strokeLinecap="round" opacity="0.08" />
      <mask id="atlas-road-mask">
        <motion.path d={ROAD} fill="none" stroke="#fff" strokeWidth="8" pathLength={1} strokeDasharray="1" style={roadDraw ? { strokeDashoffset: roadDraw } : undefined} />
      </mask>
      <path d={ROAD} fill="none" stroke={INK} strokeWidth="2" strokeDasharray="2 9" strokeLinecap="round" mask="url(#atlas-road-mask)" />
      {[
        [120, 404, 1.1],
        [170, 420, 0.9],
        [960, 404, 1],
        [1030, 418, 1.2],
        [1110, 400, 0.9],
        [330, 440, 0.8],
        [760, 420, 0.8],
      ].map(([x, y, s], i) => (
        <Tree key={i} x={x!} y={y!} s={s!} />
      ))}
      {/* Birds crossing over the range. */}
      <g className="birds" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round">
        <path d="M 820 150 q 8 -8 16 0 q 8 -8 16 0" />
        <path d="M 870 128 q 6 -6 12 0 q 6 -6 12 0" />
        <path d="M 760 176 q 6 -6 12 0 q 6 -6 12 0" />
      </g>

      {/* The signpost. */}
      <ellipse cx={post + 6} cy={562} rx={70} ry={10} fill="#1f2833" opacity="0.2" filter="url(#atlas-soft)" />
      <path d={`M ${post - 9} 150 L ${post + 9} 150 L ${post + 12} 566 L ${post - 12} 566 Z`} fill="url(#atlas-wood)" stroke={INK} strokeWidth="1.8" strokeLinejoin="round" />
      <path d={`M ${post - 2} 170 L ${post - 3} 540 M ${post + 4} 200 L ${post + 5} 520`} stroke={INK} strokeWidth="0.8" opacity="0.4" />
      <path d={`M ${post - 16} 150 L ${post} 132 L ${post + 16} 150 Z`} fill="var(--atlas-wood-deep)" stroke={INK} strokeWidth="1.6" strokeLinejoin="round" />
      {arms.map((arm, i) => {
        const len = 250;
        const x0 = arm.dir === 1 ? post - 6 : post + 6;
        const x1 = x0 + arm.dir * len;
        const tip = x1 + arm.dir * 28;
        return (
          <g key={i} className="arm" style={{ ["--i" as string]: i, ["--dir" as string]: arm.dir, transformOrigin: `${post}px ${arm.y}px` }}>
          <g className={`arm-w ${wiggle === i ? "wiggle" : ""}`} style={{ ["--dir" as string]: arm.dir, transformOrigin: `${post}px ${arm.y}px` }}>
          <g transform={`rotate(${arm.tilt} ${post} ${arm.y})`}>
            <path
              d={`M ${x0} ${arm.y - 24} L ${x1} ${arm.y - 24} L ${tip} ${arm.y} L ${x1} ${arm.y + 24} L ${x0} ${arm.y + 24} Z`}
              fill="url(#atlas-paper)"
              stroke={INK}
              strokeWidth="1.8"
              strokeLinejoin="round"
            />
            <path d={`M ${x0 + arm.dir * 10} ${arm.y - 17} L ${x1} ${arm.y - 17} L ${tip - arm.dir * 10} ${arm.y}`} fill="none" stroke={INK} strokeWidth="0.6" opacity="0.5" />
            <circle cx={post} cy={arm.y} r={3} fill={INK} />
          </g>
          </g>
          </g>
        );
      })}
      <path d="M 300 600 C 340 590, 380 600, 420 594 M 600 606 C 640 598, 690 604, 720 598" fill="none" stroke={INK} strokeWidth="1" opacity="0.5" />
    </svg>
  );
}
