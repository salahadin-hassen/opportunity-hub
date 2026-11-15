import { expect, test } from "@playwright/test";

/*
 * Production smoke test: safe to run against the public deployment. It creates
 * no accounts; it signs in only as the demo user (set DEMO_PASSWORD) and runs
 * one eligibility check. Reset the demo account afterwards (see docs/DEMO_RUNBOOK.md).
 *
 *   OH_BASE_URL=https://<frontend> OH_API_URL=https://<api> DEMO_PASSWORD=... npx playwright test e2e/smoke.spec.ts
 */
const API = process.env.OH_API_URL;
const DEMO = { email: "demo@example.org", password: process.env.DEMO_PASSWORD ?? "ohub-demo-2026" };

test("public pages, direct links, demo sign-in and a real eligibility check", async ({ page }) => {
  const problems: string[] = [];
  page.on("pageerror", (error) => problems.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    // Expected: the unauthenticated profile probe answers 404 for new visitors; nothing else should error.
    if (message.type() === "error" && !message.text().includes("404")) problems.push(`console: ${message.text()}`);
  });
  page.on("requestfailed", (request) => problems.push(`request failed: ${request.url()} ${request.failure()?.errorText}`));

  if (API) {
    const health = await page.request.get(`${API}/health`);
    expect(health.status()).toBe(200);
    expect(await health.json()).toEqual({ status: "ok" });
  }

  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("There’s more out there for you.");
  await expect(page.getByRole("heading", { name: "Open right now." })).toBeVisible();

  // Direct navigation and refresh of nested routes (SPA fallback).
  await page.goto("/opportunities");
  await expect(page.getByText("12 opportunities")).toBeVisible();
  await page.locator('a[href^="/opportunities/"]').first().click();
  await page.locator("#rules-title").waitFor();
  await page.reload();
  await page.locator("#rules-title").waitFor();
  await page.goto("/privacy");
  await expect(page.getByRole("heading", { name: "What we store, and why" })).toBeVisible();
  await page.goto("/eligibility");
  await expect(page).toHaveURL(/\/login\?next=%2Feligibility/);

  await page.fill("#email", DEMO.email);
  await page.fill("#password", DEMO.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/eligibility$/);
  await page.goto("/discover");
  await page.getByRole("button", { name: /Check my eligibility|Re-check all/ }).click();
  await page.getByRole("button", { name: "Re-check all" }).waitFor({ timeout: 45_000 });
  await expect(page.locator("li", { has: page.getByText("GitHub Student Developer Pack") }).getByText("Potential match")).toBeVisible();

  const toggle = page.getByRole("switch", { name: "Dark theme" }).first();
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-checked", "true");
  await toggle.click();

  expect(problems).toEqual([]);
});
