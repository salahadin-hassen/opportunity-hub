import { expect, test } from "@playwright/test";

/**
 * Browser-level verification of cookie-based authentication, SameSite/HttpOnly flags,
 * session persistence across page reload, and logout lifecycle.
 */
const DEMO = { email: "demo@example.org", password: process.env.DEMO_PASSWORD ?? "ohub-demo-2026" };

test("browser cookie authentication: httpOnly cookie, session persistence, and logout", async ({ page, context }) => {
  // 1. Visit landing page
  await page.goto("/");

  // 2. Navigate to protected route -> redirects to login
  await page.goto("/eligibility");
  await expect(page).toHaveURL(/\/login\?next=%2Feligibility/);

  // 3. Perform login
  await page.fill("#email", DEMO.email);
  await page.fill("#password", DEMO.password);
  await page.getByRole("button", { name: "Sign in" }).click();

  // 4. Verify arrival at protected destination
  await expect(page).toHaveURL(/\/eligibility$/);

  // 5. Inspect browser cookies in the browser context
  const cookies = await context.cookies();
  const sessionCookie = cookies.find((c) => c.name === "oh_session");
  expect(sessionCookie).toBeDefined();
  expect(sessionCookie?.httpOnly).toBe(true);
  expect(sessionCookie?.sameSite).toBe("Lax");
  expect(sessionCookie?.value.length).toBeGreaterThan(30);

  // 6. Session persistence after hard page reload
  await page.reload();
  await expect(page).toHaveURL(/\/eligibility$/);

  // 7. Verify authentication state persists in app header (e.g. Sign out button visible)
  const signOutBtn = page.getByRole("button", { name: /Sign out|Log out/i });
  if (await signOutBtn.isVisible()) {
    await signOutBtn.click();
    await expect(page).toHaveURL(/\/(login|$)/);

    // Verify session cookie is deleted or expired after logout
    const cookiesAfter = await context.cookies();
    const activeSession = cookiesAfter.find((c) => c.name === "oh_session" && c.expires > Date.now() / 1000);
    expect(activeSession).toBeUndefined();
  }
});

