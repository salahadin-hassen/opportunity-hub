// Visual QA capture: drives the real app (dev server + API) and saves screenshots.
// Usage: node e2e/capture.mjs <round-name>   (needs the seeded backend and `npm run dev`)
import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const BASE = process.env.OH_BASE_URL ?? "http://localhost:5173";
const ROUND = process.argv[2] ?? "latest";
const OUT = path.resolve(import.meta.dirname, "../../docs/screenshots", ROUND);
// OH_THEME=dark captures the dark theme by seeding the stored preference, as a returning visitor would have it.
const THEME = process.env.OH_THEME ?? "light";
const DEMO = { email: "demo@example.org", password: process.env.DEMO_PASSWORD ?? "ohub-demo-2026" };

const VIEWPORTS = {
  desktop: { width: 1440, height: 900 },
  mobile: { width: 390, height: 844 },
};

await mkdir(OUT, { recursive: true });
const browser = await chromium.launch();
const problems = [];

async function session(name, viewport) {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1, reducedMotion: "no-preference" });
  if (THEME === "dark") await context.addInitScript(() => window.localStorage.setItem("oh.theme", "dark"));
  const page = await context.newPage();
  page.on("console", (message) => {
    if (message.type() === "error") problems.push(`[${name}] console: ${message.text()}`);
  });
  page.on("pageerror", (error) => problems.push(`[${name}] pageerror: ${error.message}`));
  page.on("response", (response) => {
    if (response.status() >= 500) problems.push(`[${name}] ${response.status()} ${response.url()}`);
  });
  return { context, page };
}

async function shot(page, file, options = {}) {
  await page.waitForTimeout(options.wait ?? 600);
  await page.screenshot({ path: path.join(OUT, `${file}.png`), fullPage: options.full ?? false });
}

async function signIn(page) {
  await page.goto(`${BASE}/login`);
  await page.fill("#email", DEMO.email);
  await page.fill("#password", DEMO.password);
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/(discover|onboarding)/);
}

for (const [device, viewport] of Object.entries(VIEWPORTS)) {
  const { context, page } = await session(device, viewport);

  await page.goto(BASE);
  await shot(page, `${device}-01-hero`, { wait: 3200 });
  // Scroll the whole page once so in-view reveals and lazy images settle, then capture it.
  for (let y = 0; y < 14000; y += 600) {
    await page.mouse.wheel(0, 600);
    await page.waitForTimeout(140);
  }
  await page.waitForTimeout(1200);
  await page.evaluate(() => window.scrollTo(0, 0));
  await shot(page, `${device}-02-landing-full`, { full: true, wait: 500 });
  for (const [id, name] of [["engine", "engine"], ["legend-title", "legend"], ["resolve-title", "resolve"]]) {
    await page.locator(`#${id}`).scrollIntoViewIfNeeded();
    await shot(page, `${device}-02-landing-${name}`, { wait: 900 });
  }
  if (device === "mobile") {
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.getByRole("button", { name: "Open menu" }).click();
    await shot(page, "mobile-02-landing-menu", { wait: 700 });
    await page.getByRole("button", { name: "Close menu" }).click();
  }

  await page.goto(`${BASE}/opportunities`);
  await page.waitForSelector("text=Deadline", { state: "attached" });
  await shot(page, `${device}-03-opportunities-guest`, { full: true });

  await page.locator('a[href^="/opportunities/"]').first().click();
  await page.waitForSelector("#rules-title");
  await shot(page, `${device}-04-detail-guest`, { full: true });

  await page.goto(`${BASE}/login`);
  await shot(page, `${device}-05-login`);

  await signIn(page);
  await page.goto(`${BASE}/discover`);
  await page.waitForSelector("text=Deadline", { state: "attached" });
  const runButton = page.getByRole("button", { name: /Check my eligibility|Re-check all/ });
  await runButton.click();
  await page.waitForTimeout(250);
  await shot(page, `${device}-06-discover-running`, { wait: 0 });
  await page.getByRole("button", { name: "Re-check all" }).waitFor();
  await shot(page, `${device}-07-discover-verdicts`, { full: true });

  await page.goto(`${BASE}/eligibility`);
  await page.locator("#group-needs_review-title").waitFor();
  await shot(page, `${device}-08-eligibility`, { full: true });

  const kaust = page.getByRole("link", { name: "KAUST Visiting Student Research Program (VSRP)" }).first();
  await kaust.click();
  await page.waitForSelector("#rules-title");
  await shot(page, `${device}-09-detail-verdict`, { full: true });

  await page.goto(`${BASE}/profile`);
  await page.waitForSelector("#identity-title");
  await shot(page, `${device}-10-profile`, { full: true });

  await context.close();
}

// Onboarding with a fresh account (desktop + mobile, first two steps).
for (const [device, viewport] of Object.entries(VIEWPORTS)) {
  const { context, page } = await session(`${device}-onboarding`, viewport);
  const email = `qa-${device}-${Date.now()}@example.org`;
  await page.goto(`${BASE}/register`);
  await page.fill("#email", email);
  await page.fill("#password", "qa-password-123");
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/onboarding/);
  await shot(page, `${device}-11-onboarding-1`, { full: true });
  await page.fill("#full_name", "Quality Check");
  await page.getByRole("button", { name: "Continue" }).click();
  await shot(page, `${device}-12-onboarding-2`, { full: true });
  await context.close();
}

// The wow moment: add the missing date of birth and watch the verdict change (mutates the demo
// profile; re-run the seed afterwards to reset it).
{
  const { context, page } = await session("resolve", VIEWPORTS.desktop);
  await signIn(page);
  await page.goto(`${BASE}/eligibility`);
  await page.locator("#resolve-date_of_birth").waitFor();
  await shot(page, "desktop-13-resolve-before");
  await page.fill("#resolve-date_of_birth", "2003-04-18");
  await page.locator("form", { has: page.locator("#resolve-date_of_birth") }).getByRole("button", { name: "Save and re-check" }).click();
  await page.getByText(/Your update changed/).waitFor({ timeout: 15000 });
  await shot(page, "desktop-14-resolve-after", { wait: 900 });
  await page.getByRole("link", { name: "GitHub Student Developer Pack" }).first().click();
  await page.waitForSelector("#rules-title");
  await shot(page, "desktop-15-detail-after-resolve", { full: true });
  await context.close();
}

await browser.close();
console.log(`Saved screenshots to ${OUT}`);
console.log(problems.length ? `Problems:\n${problems.join("\n")}` : "No console errors, page errors or 5xx responses.");
