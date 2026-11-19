/// <reference lib="webworker" />
/**
 * The atlas map's render worker: it owns the map's canvas (an OffscreenCanvas),
 * so painting never competes with scrolling, React or input on the page's main
 * thread. The page posts small messages (the scene: shape, camera, layers);
 * the worker keeps only the latest and paints at most once per frame. Frames in
 * motion are "lite"; 130 ms after the last change the view is painted in full.
 */
import { createRenderer, type MapData, type Palette, type Scene } from "./atlas-draw";
import { warmFlat } from "./atlas-geo";

type Message =
  | { type: "init"; canvas: OffscreenCanvas }
  | { type: "size"; width: number; height: number; dpr: number }
  | { type: "data"; data: MapData }
  | { type: "palette"; palette: Palette }
  | { type: "scene"; scene: Scene }
  | { type: "stats" };

let canvas: OffscreenCanvas | null = null;
let draw: ReturnType<typeof createRenderer> | null = null;
let dpr = 1;
let data: MapData | null = null;
let palette: Palette | null = null;
let scene: Scene | null = null;
let scheduled = false;
let rest: ReturnType<typeof setTimeout> | undefined;
let warmed = false;

const nextFrame: (cb: () => void) => void =
  typeof (self as { requestAnimationFrame?: unknown }).requestAnimationFrame === "function"
    ? (cb) => void (self as unknown as { requestAnimationFrame: (cb: () => void) => number }).requestAnimationFrame(cb)
    : (cb) => void setTimeout(cb, 0);

/** Paint timings (start, duration in ms), kept for performance tests that ask for them; never sent otherwise. */
const timings: [number, number][] = [];
function paint(lite: boolean) {
  if (!draw || !data || !palette || !scene) return;
  const start = performance.now();
  draw({ ...scene, lite }, data, palette, dpr);
  timings.push([start, performance.now() - start]);
  if (timings.length > 2000) timings.splice(0, 1000);
}

/** The latest request wins: a burst of messages becomes one paint, lite if the last change was motion. */
let liteNext = false;
function schedule(lite: boolean) {
  liteNext = lite;
  clearTimeout(rest);
  if (scheduled) return;
  scheduled = true;
  nextFrame(() => {
    scheduled = false;
    paint(liteNext);
    if (liteNext) rest = setTimeout(() => paint(false), 130);
  });
}

self.onmessage = (event: MessageEvent<Message>) => {
  const message = event.data;
  switch (message.type) {
    case "init":
      canvas = message.canvas;
      draw = createRenderer(canvas.getContext("2d")!);
      return;
    case "size":
      if (!canvas) return;
      dpr = message.dpr;
      canvas.width = Math.round(message.width * dpr);
      canvas.height = Math.round(message.height * dpr);
      return schedule(false);
    case "data":
      data = message.data;
      if (!warmed) {
        warmed = true;
        warmFlat(data.light);
      }
      return schedule(false);
    case "palette":
      palette = message.palette;
      return schedule(false);
    case "scene":
      scene = message.scene;
      return schedule(message.scene.lite);
    case "stats":
      self.postMessage({ type: "stats", timings, origin: performance.timeOrigin });
      return;
  }
};
