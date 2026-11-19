/**
 * Paints the unfolding atlas onto a 2D canvas: the same code runs in the render
 * worker (OffscreenCanvas) and, where that isn't available, on the page.
 *
 * Each call draws one complete frame. While the shape is changing, d3 draws
 * straight into Path2Ds (no path strings); once the map is flat, the cached flat
 * paths are reused, so travel is only a canvas transform. A "lite" frame (while
 * something moves) uses motion-detail coastlines and skips the faint water
 * lines; the caller redraws in full once the view rests.
 */
import { geoPath, geoProjectionMutator, type GeoProjection } from "d3-geo";
import {
  CENTRE_LON,
  GRATICULE,
  GRATICULE_MOTION,
  LAND_FULL,
  LAND_LIGHT,
  LAND_MOTION,
  MAP_H,
  MAP_W,
  OPEN_AT,
  RAD,
  SCALE,
  SPHERE,
  blendRaw,
  clamp01,
  extent,
  flatPath,
  into,
  lunePath,
  toScreen,
  type Cam,
  type Morph,
} from "./atlas-geo";

export type Layers = { dots: number; route: number; routeOpacity: number; regions: number; pin: [number, number] | null; pinOpacity: number; globe: number };
export type Scene = { morph: Morph; cam: Cam; layers: Layers; lite: boolean };
export type MapData = { dots: { at: [number, number]; px: number }[]; route: [number, number][]; routeLengths: number[]; light: boolean };
export type Palette = Record<"seaHi" | "sea" | "seaDeep" | "land" | "ink" | "terra" | "brass" | "brassHi" | "brassDeep" | "paper", string>;
type Ctx = CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D;

export const INITIAL_LAYERS: Layers = { dots: 0, route: 0, routeOpacity: 1, regions: 0, pin: null, pinOpacity: 0, globe: 1 };
export const INITIAL_MORPH: Morph = { alpha: 0, lon: -CENTRE_LON, lat: 0, tilt: 0 };

/** The map pin (anchor at 0,0), as on the hero globe. */
const PIN = "M0 0 C -1.6 -5.2, -8.6 -10.4, -8.6 -18.2 A 8.6 8.6 0 1 1 8.6 -18.2 C 8.6 -10.4, 1.6 -5.2, 0 0 Z";

function tile(width: number, height: number) {
  if (typeof OffscreenCanvas !== "undefined") return new OffscreenCanvas(width, height);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  return canvas;
}

/** Engraving: the same diagonal hatching and water lines as the illustrated globe, as canvas patterns. */
function makePattern(ctx: Ctx, kind: "hatch" | "water"): CanvasPattern | null {
  const canvas = kind === "hatch" ? tile(5, 5) : tile(9, 5);
  const c = canvas.getContext("2d") as Ctx | null;
  if (!c) return null;
  c.strokeStyle = kind === "hatch" ? "rgba(31,40,51,0.22)" : "rgba(31,40,51,0.1)";
  c.lineWidth = kind === "hatch" ? 0.8 : 0.7;
  c.beginPath();
  if (kind === "hatch") {
    c.moveTo(0, 0);
    c.lineTo(0, 5);
  } else {
    c.moveTo(0, 2.5);
    c.lineTo(5, 2.5);
  }
  c.stroke();
  const pattern = ctx.createPattern(canvas, "repeat");
  if (pattern && kind === "hatch") pattern.setTransform(new DOMMatrix().rotate(38));
  return pattern;
}

export function createRenderer(ctx: Ctx) {
  const mutate = geoProjectionMutator(blendRaw) as unknown as (alpha: number) => GeoProjection;
  const projection = mutate(0).scale(SCALE).translate([0, 0]).precision(0);
  const patterns = { hatch: makePattern(ctx, "hatch"), water: makePattern(ctx, "water") };
  const pin = new Path2D(PIN);

  return function draw(scene: Scene, data: MapData, colors: Palette, dpr: number) {
    const { morph: m, cam, layers, lite } = scene;
    const k = 1 / cam.z; // one screen pixel, in canvas units
    const canvas = ctx.canvas;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = 1;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (layers.globe <= 0.001) return;
    ctx.globalAlpha = layers.globe;
    ctx.setTransform(dpr * cam.z, 0, 0, dpr * cam.z, dpr * (cam.ax - cam.cx * cam.z), dpr * (cam.ay - cam.cy * cam.z));
    ctx.lineJoin = "round";
    ctx.lineCap = "round";

    // The world's shape at this point in the unfolding.
    const open = m.alpha > OPEN_AT;
    const done = m.alpha >= 0.9999;
    const half = open ? 90 + 90 * clamp01((m.alpha - OPEN_AT) / (1 - OPEN_AT)) : 90;
    let sea: Path2D;
    let land: Path2D;
    let grat: Path2D;
    if (done) {
      sea = flatPath("sea");
      land = flatPath(lite ? "motion" : data.light ? "light" : "full");
      grat = flatPath("grat");
    } else {
      mutate(m.alpha);
      projection.rotate([m.lon, open ? 0 : m.lat, 0]).clipAngle(open ? null : 90);
      if (open) sea = lunePath(m.alpha, half);
      else {
        sea = new Path2D();
        geoPath(projection, into(sea))(SPHERE);
      }
      land = new Path2D();
      geoPath(projection, into(land))(lite ? LAND_MOTION : data.light ? LAND_LIGHT : LAND_FULL);
      grat = new Path2D();
      geoPath(projection, into(grat))(lite ? GRATICULE_MOTION : GRATICULE);
    }
    const [hw, hh] = done ? [MAP_W / 2, MAP_H / 2] : open ? extent(m.alpha, half) : [SCALE, SCALE];
    const globeness = 1 - clamp01(m.alpha / 0.45);
    const engraving = 1 - clamp01((m.alpha - 0.35) / 0.4);
    const tilt = (open ? 0 : m.tilt) * RAD;

    // Sea, lit from the upper left as on the globe.
    const seaLight = ctx.createRadialGradient(-hw * 0.32, -hh * 0.4, 0, -hw * 0.32, -hh * 0.4, Math.max(hw, hh) * 1.6);
    seaLight.addColorStop(0, colors.seaHi);
    seaLight.addColorStop(0.5, colors.sea);
    seaLight.addColorStop(1, colors.seaDeep);
    ctx.fillStyle = seaLight;
    ctx.fill(sea);
    if (engraving > 0.01 && !lite && patterns.water) {
      ctx.globalAlpha = layers.globe * engraving;
      ctx.fillStyle = patterns.water;
      ctx.fill(sea);
      ctx.globalAlpha = layers.globe;
    }

    // Graticule and land, tilted with the globe and clipped to the opening outline.
    ctx.save();
    if (open && !done) ctx.clip(sea);
    if (tilt) ctx.rotate(tilt);
    ctx.strokeStyle = colors.ink;
    ctx.globalAlpha = layers.globe * 0.3;
    ctx.lineWidth = 0.6 * k;
    ctx.stroke(grat);
    ctx.globalAlpha = layers.globe;
    ctx.fillStyle = colors.land;
    ctx.fill(land);
    if (engraving > 0.01 && patterns.hatch) {
      ctx.globalAlpha = layers.globe * engraving;
      ctx.fillStyle = patterns.hatch;
      ctx.fill(land);
      ctx.globalAlpha = layers.globe;
    }
    ctx.lineWidth = 1.15 * k;
    ctx.stroke(land);
    ctx.restore();

    // The globe's shading and its brass meridian give way as it opens.
    if (globeness > 0.01) {
      ctx.globalAlpha = layers.globe * globeness;
      const shade = ctx.createRadialGradient(-hw * 0.36, -hh * 0.44, 0, -hw * 0.36, -hh * 0.44, Math.max(hw, hh) * 1.56);
      shade.addColorStop(0.52, "rgba(31,40,51,0)");
      shade.addColorStop(1, "rgba(31,40,51,0.42)");
      ctx.fillStyle = shade;
      ctx.fill(sea);
      ctx.save();
      ctx.translate(-95, -110);
      ctx.rotate(-35 * RAD);
      ctx.scale(70, 46);
      const shine = ctx.createRadialGradient(0, 0, 0, 0, 0, 1);
      shine.addColorStop(0, "rgba(255,250,240,0.75)");
      shine.addColorStop(1, "rgba(255,250,240,0)");
      ctx.fillStyle = shine;
      ctx.beginPath();
      ctx.arc(0, 0, 1, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
      ctx.globalAlpha = layers.globe;
    }
    ctx.strokeStyle = colors.ink;
    ctx.lineWidth = 1.8 * k;
    ctx.stroke(sea);
    const ringFade = 1 - clamp01(m.alpha / 0.28);
    if (ringFade > 0.01) {
      const r = 271 * (1 + m.alpha * 0.35);
      ctx.globalAlpha = layers.globe * ringFade;
      ctx.beginPath();
      ctx.arc(0, 0, r, 0, Math.PI * 2);
      ctx.lineWidth = 16;
      ctx.strokeStyle = colors.ink;
      ctx.stroke();
      const brass = ctx.createLinearGradient(0, -r, 0, r);
      brass.addColorStop(0, colors.brassHi);
      brass.addColorStop(0.5, colors.brass);
      brass.addColorStop(1, colors.brassDeep);
      ctx.lineWidth = 13;
      ctx.strokeStyle = brass;
      ctx.stroke();
      ctx.globalAlpha = layers.globe;
    }

    // Where the listings are: a dot per country, sized by count, the same size on screen at any zoom.
    if (layers.dots > 0.01) {
      ctx.globalAlpha = layers.globe * layers.dots;
      ctx.fillStyle = colors.brass;
      ctx.strokeStyle = colors.ink;
      ctx.lineWidth = 0.9 * k;
      for (const dot of data.dots) {
        ctx.beginPath();
        ctx.arc(dot.at[0], dot.at[1], dot.px * k, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      }
      ctx.globalAlpha = layers.globe;
    }

    // The route, drawn on along great circles.
    const { route, routeLengths } = data;
    if (layers.route > 0.001 && route.length > 1) {
      const until = routeLengths[routeLengths.length - 1]! * layers.route;
      ctx.globalAlpha = layers.globe * layers.routeOpacity;
      ctx.strokeStyle = colors.terra;
      ctx.lineWidth = 1.6 * k;
      ctx.setLineDash([7 * k, 5 * k]);
      ctx.beginPath();
      ctx.moveTo(route[0]![0], route[0]![1]);
      for (let i = 1; i < route.length; i += 1) {
        const [x, y] = route[i]!;
        if (routeLengths[i]! <= until) {
          ctx.lineTo(x, y);
          continue;
        }
        const [px, py] = route[i - 1]!;
        const t = (until - routeLengths[i - 1]!) / (routeLengths[i]! - routeLengths[i - 1]! || 1);
        ctx.lineTo(px + (x - px) * t, py + (y - py) * t);
        break;
      }
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // The destination's pin, in screen space, painted with the map so the two never drift apart.
    if (layers.pin && layers.pinOpacity > 0.01) {
      const [x, y] = toScreen(cam, layers.pin);
      ctx.setTransform(dpr, 0, 0, dpr, dpr * x, dpr * y);
      ctx.globalAlpha = layers.globe * layers.pinOpacity;
      ctx.fillStyle = "rgba(31,40,51,0.28)";
      ctx.beginPath();
      ctx.ellipse(2.5, 1, 6, 2.2, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = colors.terra;
      ctx.fill(pin);
      ctx.strokeStyle = colors.ink;
      ctx.lineWidth = 1.6;
      ctx.stroke(pin);
      ctx.beginPath();
      ctx.arc(0, -18.2, 3.4, 0, Math.PI * 2);
      ctx.fillStyle = colors.paper;
      ctx.fill();
      ctx.lineWidth = 1.2;
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  };
}
