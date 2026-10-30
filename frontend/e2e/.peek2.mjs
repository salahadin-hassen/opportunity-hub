import { chromium } from "@playwright/test";
const [,, out, sel] = process.argv;
const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
await p.goto("http://localhost:5173/"); await p.waitForTimeout(1500);
await p.locator(sel).scrollIntoViewIfNeeded(); await p.waitForTimeout(2200);
const info = await p.evaluate((s) => { const img = document.querySelector(s)?.closest("section")?.querySelector("img"); return img ? { complete: img.complete, w: img.naturalWidth, clip: getComputedStyle(img).clipPath, src: img.currentSrc.slice(-40) } : null; }, sel);
console.log(JSON.stringify(info));
await p.screenshot({ path: out }); await b.close();
