/**
 * Geometry for the unfolding atlas, shared by the page and the map's render worker
 * (so it imports nothing from React or the DOM).
 *
 * The unfolding is one projection, not two pictures: its raw function blends the
 * globe's orthographic projection into Natural Earth. While the blend is below
 * OPEN_AT the globe is still a hemisphere and clips at 90°; beyond it the blend is
 * monotonic in longitude everywhere, so the back of the world can open out to the
 * antimeridian without folding over, and the outline is drawn as the image of the
 * two edge meridians and the pole lines (also used as the clip). The globe settles
 * upright and centred before it opens, which keeps that exact.
 */
import { geoNaturalEarth1, geoNaturalEarth1Raw, geoOrthographicRaw, geoPath, type GeoContext } from "d3-geo";
import type { MultiLineString } from "geojson";
import { LAND_FULL, LAND_LIGHT, LAND_MOTION } from "./geo-land";

/** Projection scale in canvas units: the hero globe's radius, so the hand-off matches stroke for stroke. */
export const SCALE = 250;
/** The flat map's central meridian: the Atlantic world in the middle, the antimeridian in the Pacific. */
export const CENTRE_LON = 10;
/** Past this blend the projection is monotonic in longitude, so the far side can open without folding. */
export const OPEN_AT = 0.55;
export const RAD = Math.PI / 180;
/** The hero globe's axial tilt (GLOBE_SCENE.tilt in Atlas.tsx). */
export const TILT = -18;
export const SPHERE = { type: "Sphere" } as const;

export const clamp01 = (t: number) => Math.min(1, Math.max(0, t));
export const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);
export const ramp = (u: number, from: number, to: number) => clamp01((u - from) / (to - from));

/** d3 draws into a context with moveTo, lineTo, closePath and arc only (d3-geo/src/path/context.js), all of which Path2D has. */
export const into = (path: Path2D) => path as unknown as GeoContext;

/** d3's raw projections are plain (λ, φ) → [x, y] functions at runtime; @types/d3-geo declares them as factories. */
type Raw = (lambda: number, phi: number) => [number, number];
const orthographicRaw = geoOrthographicRaw as unknown as Raw;
const naturalEarthRaw = geoNaturalEarth1Raw as unknown as Raw;

export function blendRaw(alpha: number): Raw {
  return (lambda, phi) => {
    const [ox, oy] = orthographicRaw(lambda, phi);
    const [nx, ny] = naturalEarthRaw(lambda, phi);
    return [ox + alpha * (nx - ox), oy + alpha * (ny - oy)];
  };
}

/** The outline of the opened world: edge meridians at ±half degrees, joined along the pole lines. */
export function lunePath(alpha: number, half: number): Path2D {
  const raw = blendRaw(alpha);
  const path = new Path2D();
  let first = true;
  const at = (lon: number, lat: number) => {
    const [x, y] = raw(lon * RAD, lat * RAD);
    if (first) path.moveTo(x * SCALE, -y * SCALE);
    else path.lineTo(x * SCALE, -y * SCALE);
    first = false;
  };
  for (let lat = -90; lat <= 90; lat += 3) at(half, lat);
  for (let lon = half; lon >= -half; lon -= 3) at(lon, 90);
  for (let lat = 90; lat >= -90; lat -= 3) at(-half, lat);
  for (let lon = -half; lon <= half; lon += 3) at(lon, -90);
  path.closePath();
  return path;
}
/** Half-width and half-height of the outline at a blend (for the sea's light). */
export function extent(alpha: number, half: number): [number, number] {
  const raw = blendRaw(alpha);
  return [raw(half * RAD, 0)[0] * SCALE, raw(0, Math.PI / 2)[1] * SCALE];
}

/**
 * A graticule with its points written out: d3's own leaves meridians as three points and relies on
 * adaptive resampling to curve them, which the morph turns off for speed.
 */
function denseGraticule(step: number): MultiLineString {
  const lines: [number, number][][] = [];
  for (let lon = -180; lon < 180; lon += 15) {
    const line: [number, number][] = [];
    for (let lat = -90; lat <= 90; lat += step) line.push([lon, lat]);
    lines.push(line);
  }
  for (let lat = -75; lat <= 75; lat += 15) {
    const line: [number, number][] = [];
    for (let lon = -180; lon <= 180; lon += step) line.push([lon, lat]);
    lines.push(line);
  }
  return { type: "MultiLineString", coordinates: lines };
}
export const GRATICULE = denseGraticule(5);
export const GRATICULE_MOTION = denseGraticule(10);
export { LAND_FULL, LAND_LIGHT, LAND_MOTION };

/** The finished map: the blend at 1, i.e. Natural Earth on the same centre and scale. */
export const flat = geoNaturalEarth1().scale(SCALE).translate([0, 0]).rotate([-CENTRE_LON, 0]).precision(0);
/** Routes are great circles, so they need resampling to curve. */
export const fine = geoNaturalEarth1().scale(SCALE).translate([0, 0]).rotate([-CENTRE_LON, 0]).precision(0.3);
export const MAP_W = 2 * SCALE * naturalEarthRaw(Math.PI, 0)[0];
export const MAP_H = 2 * SCALE * naturalEarthRaw(0, Math.PI / 2)[1];
export const flatPoint = (lonLat: readonly [number, number]) => (flat([lonLat[0], lonLat[1]]) ?? [0, 0]) as [number, number];

/** The flat map as cached paths, each built once: travel never reprojects. */
export type FlatKey = "sea" | "full" | "light" | "motion" | "grat";
const flatCache = new Map<FlatKey, Path2D>();
export function flatPath(key: FlatKey): Path2D {
  let path = flatCache.get(key);
  if (!path) {
    if (key === "sea") path = lunePath(1, 180);
    else {
      path = new Path2D();
      const object = key === "full" ? LAND_FULL : key === "light" ? LAND_LIGHT : key === "motion" ? LAND_MOTION : GRATICULE;
      geoPath(flat, into(path))(object);
    }
    flatCache.set(key, path);
  }
  return path;
}
/** Build what this screen will draw ahead of time, one path per slice so no single task is long. */
export function warmFlat(light: boolean) {
  const keys: FlatKey[] = ["sea", "grat", "motion", light ? "light" : "full"];
  const idle = (globalThis as { requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number }).requestIdleCallback;
  const next = () => {
    const key = keys.shift();
    if (!key) return;
    flatPath(key);
    if (idle) idle(next, { timeout: 2000 });
    else setTimeout(next, 40);
  };
  if (idle) idle(next, { timeout: 2000 });
  else setTimeout(next, 200);
}

/** The globe's shape at a point in the unfolding: settle (turn upright, face the Atlantic), then open. */
export type Morph = { alpha: number; lon: number; lat: number; tilt: number };
export function morphAt(m: number, from: readonly [number, number]): Morph {
  const settle = ease(clamp01(m / 0.45));
  let dLon = -CENTRE_LON - from[0];
  dLon = ((((dLon + 180) % 360) + 360) % 360) - 180; // the short way round
  return {
    alpha: ease(clamp01((m - 0.2) / 0.8)),
    lon: from[0] + dLon * ease(clamp01(m / 0.55)),
    lat: from[1] * (1 - settle),
    tilt: TILT * (1 - settle),
  };
}

/** A camera: the canvas point (cx, cy) appears at screen point (ax, ay), magnified z times. */
export type Cam = { ax: number; ay: number; z: number; cx: number; cy: number };
export function lerpCam(a: Cam, b: Cam, t: number, arc = 0): Cam {
  const z = Math.exp(Math.log(a.z) + (Math.log(b.z) - Math.log(a.z)) * t) * (1 - arc * Math.sin(Math.PI * t));
  return { ax: a.ax + (b.ax - a.ax) * t, ay: a.ay + (b.ay - a.ay) * t, z, cx: a.cx + (b.cx - a.cx) * t, cy: a.cy + (b.cy - a.cy) * t };
}
export const toScreen = (c: Cam, p: readonly [number, number]): [number, number] => [(p[0] - c.cx) * c.z + c.ax, (p[1] - c.cy) * c.z + c.ay];
