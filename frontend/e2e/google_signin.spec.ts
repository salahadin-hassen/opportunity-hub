import { expect, test } from "@playwright/test";

// Sign in with Google in the browser, up to Google's door. scripts/e2e.sh configures placeholder
// Google credentials; every request to accounts.google.com is intercepted, so no real Google sign-in
// happens here (the callback, token checks and account linking are covered by backend tests).

test("login and registration offer Google, and the button sends the browser to Google with PKCE", async ({ page }) => {
  let authorize: URL | null = null;
  await page.route("https://accounts.google.com/**", async (route) => {
    authorize = new URL(route.request().url());
    await route.fulfill({ status: 200, contentType: "text/html", body: "<title>Google (intercepted)</title>" });
  });

  await page.goto("/register");
  await expect(page.getByRole("button", { name: "Sign up with Google" })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("button", { name: "Create account" })).toBeVisible();

  await page.goto("/login?next=/opportunities");
  const button = page.getByRole("button", { name: "Continue with Google" });
  await expect(button).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeVisible();
  await button.click();
  await expect(page).toHaveTitle("Google (intercepted)", { timeout: 15_000 });
  expect(authorize).not.toBeNull();
  const query = authorize!.searchParams;
  expect(authorize!.pathname).toBe("/o/oauth2/v2/auth");
  expect(query.get("client_id")).toContain(".apps.googleusercontent.com");
  expect(query.get("response_type")).toBe("code");
  expect(query.get("scope")).toBe("openid email profile");
  expect(query.get("code_challenge_method")).toBe("S256");
  expect(query.get("code_challenge")).toHaveLength(43);
  expect(query.get("state")?.length).toBeGreaterThan(30);
  expect(query.get("nonce")?.length).toBeGreaterThan(20);
  expect(query.get("redirect_uri")).toMatch(/\/auth\/google\/callback$/);
});

test("a refused Google sign-in explains itself, and a stale completion link is rejected", async ({ page }) => {
  await page.goto("/login?google_error=link_required");
  await expect(page.getByRole("alert")).toContainText("An account with this email already exists");
  await page.goto("/login?google_error=email_unverified");
  await expect(page.getByRole("alert")).toContainText("hasn’t verified");
  await page.goto("/auth/google/complete#code=not-a-real-handoff-code");
  await expect(page.getByRole("alert")).toContainText("expired or was already used", { timeout: 15_000 });
  expect(page.url()).not.toContain("#code=");
});

test("a password account sees its sign-in methods and can start connecting Google", async ({ page }) => {
  await page.route("https://accounts.google.com/**", (route) =>
    route.fulfill({ status: 200, contentType: "text/html", body: "<title>Google (intercepted)</title>" }));
  const email = `e2e-google-${Date.now()}@example.org`;
  await page.goto("/register");
  await page.fill("#email", email);
  await page.fill("#password", "google-e2e-password-1");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/onboarding$/, { timeout: 15_000 });
  await page.fill("#full_name", "Google Spec Student");
  await page.selectOption("#citizenships", "KE");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.selectOption("#degree_level", "bachelor");
  await page.fill("#institution_name", "University of Nairobi");
  await page.fill("#field_of_study", "Computer Science");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Python" }).click();
  await page.getByRole("button", { name: "Save and check my eligibility" }).click();
  await expect(page).toHaveURL(/\/eligibility$/, { timeout: 30_000 });

  await page.goto("/profile");
  const methods = page.getByRole("region", { name: "Sign-in methods" });
  await expect(methods).toBeVisible({ timeout: 15_000 });
  await expect(methods).toContainText("Not connected.");
  await expect(methods.getByText("Set.", { exact: true })).toBeVisible();
  await methods.getByRole("button", { name: "Connect Google" }).click();
  await expect(page).toHaveTitle("Google (intercepted)", { timeout: 15_000 });
});
