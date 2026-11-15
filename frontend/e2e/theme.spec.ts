import { expect, test, type Page } from "@playwright/test";

const DEMO = { email: "demo@example.org", password: process.env.DEMO_PASSWORD ?? "ohub-demo-2026" };
const LIGHT_BG = "rgb(245, 242, 233)";
const DARK_BG = "rgb(18, 21, 27)";

const bodyBackground = (page: Page) => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
const themeAttr = (page: Page) => page.evaluate(() => document.documentElement.dataset.theme ?? "light");
const toggle = (page: Page) => page.getByRole("switch", { name: "Dark theme" }).first();

/** Large painted surfaces that still use a light-theme colour while dark mode is on. */
async function lightSurfacesInDark(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const light = new Set([
      "rgb(245, 242, 233)", // ivory
      "rgb(251, 249, 243)", // paper
      "rgb(237, 232, 218)", // cream
      "rgb(226, 220, 203)", // sand
      "rgb(250, 251, 254)", // tint
      "rgb(255, 255, 255)",
    ]);
    const offenders: string[] = [];
    for (const element of document.querySelectorAll<HTMLElement>("body *")) {
      const style = getComputedStyle(element);
      if (!light.has(style.backgroundColor)) continue;
      const box = element.getBoundingClientRect();
      if (box.width * box.height < 600) continue; // switch knobs and similar small marks
      if (element.closest(".bg-snow")) continue; // the legend's mark discs are fixed-tone by design
      offenders.push(`${element.tagName.toLowerCase()}.${String(element.className).slice(0, 60)} ${style.backgroundColor}`);
    }
    return offenders;
  });
}

test("new visitors get the light theme by default", async ({ page }) => {
  await page.goto("/");
  expect(await themeAttr(page)).toBe("light");
  expect(await bodyBackground(page)).toBe(LIGHT_BG);
  await expect(toggle(page)).toHaveAttribute("aria-checked", "false");
});

test("dark mode applies everywhere, persists across reloads, routes and restarts, and switches back", async ({ page, context, browser }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));

  await page.goto("/");
  await toggle(page).click();
  await expect(toggle(page)).toHaveAttribute("aria-checked", "true");
  expect(await themeAttr(page)).toBe("dark");
  await expect.poll(() => bodyBackground(page)).toBe(DARK_BG);
  expect(await page.evaluate(() => localStorage.getItem("oh.theme"))).toBe("dark");

  await page.reload();
  expect(await themeAttr(page)).toBe("dark");
  // Scroll the landing page so lazy images and in-view sections render, then scan it.
  for (let y = 0; y < 12000; y += 900) await page.mouse.wheel(0, 900);
  await page.waitForTimeout(800);
  expect(await lightSurfacesInDark(page)).toEqual([]);

  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Opportunities" }).click();
  await expect(page).toHaveURL(/\/opportunities$/);
  expect(await themeAttr(page)).toBe("dark");
  await expect(page.getByText("12 opportunities")).toBeVisible();
  expect(await lightSurfacesInDark(page)).toEqual([]);

  // A "browser restart": a fresh context carrying the same localStorage.
  const state = await context.storageState();
  const restarted = await browser.newContext({ storageState: state });
  const again = await restarted.newPage();
  await again.goto("/");
  expect(await themeAttr(again)).toBe("dark");
  await restarted.close();

  await toggle(page).click();
  expect(await themeAttr(page)).toBe("light");
  await expect.poll(() => bodyBackground(page)).toBe(LIGHT_BG);
  expect(await page.evaluate(() => localStorage.getItem("oh.theme"))).toBe("light");
  expect(errors).toEqual([]);
});

test("the remembered dark theme is applied before the app renders (no light flash)", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("oh.theme", "dark"));
  await page.goto("/", { waitUntil: "commit" });
  await page.waitForFunction(() => document.body !== null);
  expect(await themeAttr(page)).toBe("dark");
});

test("unavailable localStorage falls back to light without errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript(() => {
    Object.defineProperty(window, "localStorage", {
      get() {
        throw new Error("storage disabled");
      },
    });
  });
  await page.goto("/");
  expect(await themeAttr(page)).toBe("light");
  await toggle(page).click();
  expect(await themeAttr(page)).toBe("dark");
  expect(errors).toEqual([]);
});

test("the signed-in journey works in dark mode and no surface stays light", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("oh.theme", "dark"));
  await page.goto("/login");
  expect(await lightSurfacesInDark(page)).toEqual([]);
  await page.fill("#email", DEMO.email);
  await page.fill("#password", DEMO.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/discover$/);

  await page.getByRole("button", { name: /Check my eligibility|Re-check all/ }).click();
  await page.getByRole("button", { name: "Re-check all" }).waitFor({ timeout: 30_000 });
  expect(await lightSurfacesInDark(page)).toEqual([]);

  await page.goto("/eligibility");
  await page.locator("#group-needs_review-title").waitFor();
  expect(await lightSurfacesInDark(page)).toEqual([]);

  await page.getByRole("link", { name: "KAUST Visiting Student Research Program (VSRP)" }).first().click();
  await page.locator("#rules-title").waitFor();
  // Evidence stays readable: the quote text is light on the dark page.
  const quoteColor = await page.getByText("“Minimum GPA: 3.5 on a 4-point scale (or equivalent).”").evaluate((node) => getComputedStyle(node).color);
  expect(quoteColor).toBe("rgb(239, 234, 223)");
  expect(await lightSurfacesInDark(page)).toEqual([]);

  await page.goto("/profile");
  await page.locator("#identity-title").waitFor();
  expect(await lightSurfacesInDark(page)).toEqual([]);
  expect(await themeAttr(page)).toBe("dark");
});

test("onboarding renders in dark mode", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("oh.theme", "dark"));
  await page.goto("/register");
  await page.fill("#email", `theme-${Date.now()}@example.org`);
  await page.fill("#password", "theme-password-1");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/onboarding$/);
  expect(await lightSurfacesInDark(page)).toEqual([]);
  await expect(toggle(page)).toHaveAttribute("aria-checked", "true");
});

test("the toggle works on mobile next to the menu", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await toggle(page).click();
  expect(await themeAttr(page)).toBe("dark");
  await page.getByRole("button", { name: "Open menu" }).click();
  await expect(page.getByRole("navigation", { name: "Mobile" })).toBeVisible();
  expect(await lightSurfacesInDark(page)).toEqual([]);
  await toggle(page).focus();
  await page.keyboard.press("Enter");
  expect(await themeAttr(page)).toBe("light");
});

for (const theme of ["light", "dark"] as const) {
  test(`phone listing and detail pages: no overflow, toggle and menu work (${theme})`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    if (theme === "dark") await page.addInitScript(() => localStorage.setItem("oh.theme", "dark"));
    for (const path of ["/opportunities", "detail"]) {
      if (path === "detail") {
        await page.goto("/opportunities");
        await page.locator('a[href^="/opportunities/"]').first().click();
        await page.locator("#rules-title").waitFor();
      } else {
        await page.goto(path);
        await expect(page.getByText("12 opportunities")).toBeVisible();
      }
      const widths = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
      expect(widths[0]).toBe(widths[1]);
      const headerHeight = await page.locator("header").first().evaluate((node) => node.getBoundingClientRect().height);
      expect(headerHeight).toBe(65); // 64px row + 1px rule, as before

      await page.getByRole("button", { name: "Open menu" }).click();
      const menu = page.getByRole("navigation", { name: "Mobile" });
      await expect(menu.getByRole("link", { name: "Opportunities" })).toBeVisible();
      await expect(page.getByRole("link", { name: "Get started" })).toBeVisible();
      await page.getByRole("button", { name: "Close menu" }).click();
      await expect(menu).toBeHidden();
    }
    await toggle(page).click();
    expect(await themeAttr(page)).toBe(theme === "dark" ? "light" : "dark");
  });
}

test("notifications keep the light look and gain a readable dark surface", async ({ page }) => {
  const toastColors = async () => {
    await page.goto("/profile");
    await page.locator("#identity-title").waitFor();
    await page.fill("#p-name", `Mekdes Tadesse ${Date.now() % 1000}`);
    await page.locator("form", { has: page.locator("#p-name") }).getByRole("button", { name: "Save changes" }).click();
    const toast = page.getByText("Profile saved");
    await expect(toast).toBeVisible();
    return toast.evaluate((node) => {
      const style = getComputedStyle(node);
      return { background: style.backgroundColor, color: style.color };
    });
  };
  await page.goto("/login");
  await page.fill("#email", DEMO.email);
  await page.fill("#password", DEMO.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/discover$/);

  expect(await toastColors()).toEqual({ background: "rgb(24, 36, 58)", color: "rgb(255, 255, 255)" });
  await page.evaluate(() => localStorage.setItem("oh.theme", "dark"));
  expect(await toastColors()).toEqual({ background: "rgb(39, 45, 57)", color: "rgb(239, 234, 223)" });
});
