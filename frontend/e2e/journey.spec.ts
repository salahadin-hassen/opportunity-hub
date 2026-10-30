import { expect, test, type Page } from "@playwright/test";

const password = "journey-password-1";
const freshEmail = (tag: string) => `e2e-${tag}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.org`;

async function register(page: Page, email: string) {
  await page.goto("/register");
  await page.fill("#email", email);
  await page.fill("#password", password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/onboarding$/);
}

/** Onboard as an Ethiopian bachelor's student with no date of birth and an optional GPA. */
async function onboard(page: Page, gpa?: { value: string; scale: string }) {
  await page.fill("#full_name", "Journey Tester");
  await page.selectOption("#citizenships", "ET");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.selectOption("#degree_level", "bachelor");
  await page.fill("#institution_name", "Addis Ababa University");
  await page.fill("#field_of_study", "Aerospace Engineering");
  if (gpa) {
    await page.fill("#gpa", gpa.value);
    await page.selectOption("#gpa_scale", gpa.scale);
  }
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Python" }).click();
  await page.getByRole("button", { name: "Save and check my eligibility" }).click();
  await expect(page).toHaveURL(/\/eligibility$/, { timeout: 30_000 });
}

test("landing page loads real opportunities and the hero demonstration", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("There’s more out there for you.");
  await expect(page.getByRole("heading", { name: "Open right now." })).toBeVisible();
  // Proof section renders live rules from the API.
  await expect(page.getByText("Minimum GPA: 3.5 on a 4-point scale (or equivalent).").first()).toBeVisible();
  await page.getByRole("link", { name: "Explore opportunities" }).first().click();
  await expect(page).toHaveURL(/\/opportunities$/);
  await expect(page.getByRole("link", { name: /GitHub Student Developer Pack/ }).first()).toBeVisible();
});

test("full journey: register, onboard, check, resolve a missing fact, verdict changes", async ({ page }) => {
  await register(page, freshEmail("journey"));
  await onboard(page);

  // Real verdicts from the engine: the GitHub Pack waits on a date of birth.
  const card = page.locator("li", { has: page.getByRole("link", { name: "GitHub Student Developer Pack" }) }).first();
  await expect(card.getByText("Potential match")).toBeVisible();
  await expect(page.getByText("Ruled out by a mandatory rule")).toBeVisible();

  // Evidence on the detail page explains the missing fact.
  await card.getByRole("link", { name: "GitHub Student Developer Pack" }).click();
  await expect(page.getByText("Your profile has no date of birth")).toBeVisible();
  // Official wording is shown as numbered footnotes on the detail page.
  await expect(page.getByText("“Are at least 13 years old.”")).toBeVisible();
  await expect(page.getByText(/isn’t an admission, award or approval/)).toBeVisible();

  // Resolve the fact inline and re-check: the verdict changes for real.
  await page.goto("/eligibility");
  await page.fill("#resolve-date_of_birth", "2003-04-18");
  await page.locator("form", { has: page.locator("#resolve-date_of_birth") }).getByRole("button", { name: "Save and re-check" }).click();
  const summary = page.getByRole("status").filter({ hasText: "Your update changed" });
  await expect(summary).toBeVisible({ timeout: 20_000 });
  await expect(summary.getByText("GitHub Student Developer Pack")).toBeVisible();
  await expect(summary.getByText("Eligible")).toBeVisible();

  // The persisted match agrees.
  await page.goto("/discover");
  const row = page.locator("li", { has: page.getByText("GitHub Student Developer Pack") });
  await expect(row.getByText("Eligible")).toBeVisible();
});

test("a GPA on a different scale is sent to review, never compared raw", async ({ page }) => {
  await register(page, freshEmail("scale"));
  await onboard(page, { value: "8.4", scale: "10" });
  await page.getByRole("link", { name: "KAUST Visiting Student Research Program (VSRP)" }).first().click();
  const gpaRow = page.locator("li", { hasText: "GPA of at least 3.5 on a 4.0 scale" });
  await expect(gpaRow.getByText("GPA 8.4 on a 10.0 scale")).toBeVisible();
  await expect(gpaRow.getByText(/different grading scale/)).toBeVisible();
});

test("a signed-in person without a profile is sent to onboarding", async ({ page }) => {
  await register(page, freshEmail("noprofile"));
  await page.goto("/discover");
  await expect(page).toHaveURL(/\/onboarding$/);
});

test("an expired session returns to sign-in and then to the intended page", async ({ page }) => {
  const email = freshEmail("expiry");
  await register(page, email);
  await onboard(page);
  // Replace the stored token with an expired, invalid one and reload a protected page.
  await page.evaluate(() => {
    const raw = window.localStorage.getItem("oh.session")!;
    const session = JSON.parse(raw) as { email: string };
    window.localStorage.setItem("oh.session", JSON.stringify({ ...session, token: "expired.token.value", expiresAt: Date.now() + 60_000 }));
  });
  await page.goto("/profile");
  await expect(page).toHaveURL(/\/login\?expired=1&next=%2Fprofile/);
  await expect(page.getByText("Your session expired")).toBeVisible();
  // Signing in again returns to the page that was interrupted.
  await page.fill("#email", email);
  await page.fill("#password", password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/profile$/);
  await expect(page.getByRole("heading", { name: "Profile", level: 1 })).toBeVisible();
});

test("invalid forms show specific errors", async ({ page }) => {
  await page.goto("/register");
  await page.fill("#email", "not-an-email");
  await page.fill("#password", "short");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("Enter a valid email address.")).toBeVisible();
  await expect(page.getByText("Use at least 8 characters.")).toBeVisible();

  await page.goto("/login");
  await page.fill("#email", "nobody@example.org");
  await page.fill("#password", "wrong-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("That email and password don’t match an account.")).toBeVisible();
});

test("failed and empty API responses render error and empty states", async ({ page }) => {
  await page.route("**/opportunities?*", (route) => route.fulfill({ status: 500, body: "{}" }));
  await page.goto("/opportunities");
  await expect(page.getByRole("alert")).toContainText("The server had a problem");

  await page.unroute("**/opportunities?*");
  await page.route("**/opportunities?*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.goto("/opportunities");
  await expect(page.getByText("No opportunities are published yet")).toBeVisible();
});

test("unknown opportunities show a not-found state", async ({ page }) => {
  await page.goto("/opportunities/00000000-0000-0000-0000-000000000000");
  await expect(page.getByText("This opportunity isn’t available")).toBeVisible();
});

test("search and type filters narrow the listing", async ({ page }) => {
  await page.goto("/opportunities");
  await expect(page.getByText("12 opportunities")).toBeVisible();
  await page.keyboard.press("/");
  await expect(page.locator("#discover-search")).toBeFocused();
  await page.keyboard.type("NASA");
  await expect(page.getByText("2 opportunities of 12")).toBeVisible();
  await page.getByRole("button", { name: /Clear filters|All types/ }).first().click();
  await page.fill("#discover-search", "");
  await page.getByRole("button", { name: /^Scholarships/ }).click();
  await expect(page.getByText("3 opportunities of 12")).toBeVisible();
});

test("mobile navigation opens and routes", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Open menu" }).click();
  await page.getByRole("navigation", { name: "Mobile" }).getByRole("link", { name: "Opportunities" }).click();
  await expect(page).toHaveURL(/\/opportunities$/);
});
