/**
 * The world outline at levels of detail, and the rough regions, shared by the
 * hero's turnable globe and the unfolding atlas below it, so both draw the same
 * coastlines from the same source (Natural Earth 1:110m, see geo-world.ts).
 */
import { geoGraticule } from "d3-geo";
import type { MultiPolygon } from "geojson";
import { COUNTRY_CENTRES, LAND_POLYGONS } from "./geo-world";
import type { RegionKey } from "./shared";

/** The land outline at a level of detail: keep every ``stride``-th point on long coastlines, and drop islands under ``minPoints``. */
function toMultiPolygon(stride: number, minPoints = 0): MultiPolygon {
  return {
    type: "MultiPolygon",
    coordinates: LAND_POLYGONS.filter((polygon) => polygon[0]!.length / 2 >= minPoints).map((polygon) =>
      polygon.map((ring) => {
        const points: [number, number][] = [];
        const step = ring.length > 40 ? stride * 2 : 2; // thin only long coastlines; keep small islands whole
        for (let i = 0; i < ring.length; i += step) points.push([ring[i]!, ring[i + 1]!]);
        const last: [number, number] = [ring[ring.length - 2]!, ring[ring.length - 1]!];
        const tail = points[points.length - 1];
        if (tail && (tail[0] !== last[0] || tail[1] !== last[1])) points.push(last);
        return points;
      }),
    ),
  };
}
/*
 * Levels of detail, measured in Node (ms per projection, full detail = 13.4):
 * phones at rest keep about 60% of the points and islands of 8 points or more;
 * while the globe moves, about a quarter of the points and only the larger
 * landmasses (2.7 ms). Motion hides the difference, and arrival redraws in full.
 */
export const LAND_FULL = toMultiPolygon(1);
export const LAND_LIGHT = toMultiPolygon(2, 8);
export const LAND_MOTION = toMultiPolygon(4, 14);
export const GRATICULE = geoGraticule().step([15, 15])();
export const GRATICULE_MOTION = geoGraticule().step([15, 15]).precision(6)();

/** Rough regions from a country's centre; good enough to turn the globe toward the right part of the world. */
export function regionOf(code: string): RegionKey | null {
  const centre = COUNTRY_CENTRES[code];
  if (!centre) return null;
  const [lon, lat] = centre;
  if (lon < -25) return "americas";
  if (lon > 110 && lat < -10) return "oceania";
  if (lat > -36 && lat < 37 && lon > -20 && lon < 52 && !(lon > 34 && lat > 12)) return "africa";
  if (lon > -25 && lon < 45 && lat >= 35) return "europe";
  return "asia";
}
