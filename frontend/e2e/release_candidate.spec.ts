import { expect, test, type Page } from "@playwright/test";

const password = "release-password-1";
const freshEmail = (tag: string) => `e2e-rc-${tag}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.org`;

async function register(page: Page, email: string) {
  await page.goto("/register");
  await page.fill("#email", email);
  await page.fill("#password", password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/onboarding$/);
}

async function onboard(page: Page) {
  await page.fill("#full_name", "Release Candidate Tester");
  await page.selectOption("#citizenships", "ET");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.selectOption("#degree_level", "bachelor");
  await page.fill("#institution_name", "Addis Ababa University");
  await page.fill("#field_of_study", "Computer Science");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Python" }).click();
  await page.getByRole("button", { name: "Save and check my eligibility" }).click();
  await expect(page).toHaveURL(/\/eligibility$/, { timeout: 30_000 });
}

test("student save opportunity and unsave workflow", async ({ page }) => {
  const email = freshEmail("save");
  await register(page, email);
  await onboard(page);

  // Navigate to an opportunity detail page
  await page.goto("/opportunities");
  await page.getByRole("link", { name: /CERN Summer Student Programme/i }).first().click();
  await expect(page).toHaveURL(/\/opportunities\/[a-z0-9-]+$/);

  // Click Save Opportunity
  const saveBtn = page.getByRole("button", { name: /Save opportunity/i });
  await expect(saveBtn).toBeVisible();
  await saveBtn.click();
  await expect(page.getByRole("button", { name: /Saved to your list/i })).toBeVisible({ timeout: 15_000 });

  // Navigate to Saved page
  await page.goto("/saved");
  await expect(page.getByRole("heading", { name: "Saved opportunities", level: 1 })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("CERN Summer Student Programme").first()).toBeVisible({ timeout: 15_000 });

  // Unsave / remove bookmark
  const removeBtn = page.getByRole("button", { name: /Remove/i });
  await removeBtn.click();
  await expect(page.getByText("No saved opportunities yet")).toBeVisible({ timeout: 15_000 });
});

test("student application tracking: stage updates and checklist items", async ({ page }) => {
  const email = freshEmail("tracking");
  await register(page, email);
  await onboard(page);

  // Go to opportunity detail and track application
  await page.goto("/opportunities");
  await page.getByRole("link", { name: /Google Summer of Code/i }).first().click();

  const trackBtn = page.getByRole("button", { name: /Track application/i });
  await expect(trackBtn).toBeVisible();
  await trackBtn.click();

  // Clicking Track application navigates straight to /applications workspace
  await expect(page).toHaveURL(/\/applications$/, { timeout: 15_000 });
  await expect(page.getByRole("heading", { name: "Application tracking", level: 1 })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Google Summer of Code").first()).toBeVisible({ timeout: 15_000 });

  // Update application stage to "in_progress"
  const stageSelect = page.locator("select").first();
  await stageSelect.selectOption("in_progress");
  await expect(stageSelect).toHaveValue("in_progress");

  // Add checklist item
  const itemInput = page.getByPlaceholder("Add step or document (e.g. Transcript, Essay)...");
  await expect(itemInput).toBeVisible({ timeout: 15_000 });
  await itemInput.fill("Prepare proposal draft");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByText("Prepare proposal draft")).toBeVisible({ timeout: 15_000 });

  // Toggle checklist item (toggle button contains the label)
  const toggleBtn = page.getByRole("button", { name: /Prepare proposal draft/i });
  await toggleBtn.click();
  await expect(page.locator(".line-through").filter({ hasText: "Prepare proposal draft" })).toBeVisible({ timeout: 15_000 });
});

test("authorization: ordinary student is denied access to curator workspace", async ({ page }) => {
  const email = freshEmail("student-guard");
  await register(page, email);
  await onboard(page);

  // Verify that the Admin link is NOT present in the navigation header
  await expect(page.getByRole("navigation").getByRole("link", { name: "Admin" })).toHaveCount(0);

  // Directly navigate to /curate
  await page.goto("/curate");
  await expect(page.getByText("Curator access required")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/This workspace is restricted to authorized platform curators/)).toBeVisible();
  await expect(page.getByText(/Your current role is “student”/)).toBeVisible();
  await expect(page.getByRole("button", { name: /New Opportunity Draft/i })).toHaveCount(0);
});

test("admin journey: curator workspace, tabs, draft creation, publish guard, and opportunity closing", async ({ page }) => {
  // Sign in as admin user created in test setup
  await page.goto("/login");
  await page.fill("#email", "admin@example.org");
  await page.fill("#password", "AdminPass123!");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/(discover|eligibility|opportunities)$/, { timeout: 15_000 });

  // Verify Admin link appears in navigation
  await expect(page.getByRole("navigation").getByRole("link", { name: "Admin" })).toBeVisible({ timeout: 15_000 });

  // Navigate to /curate
  await page.goto("/curate");
  await expect(page.getByRole("heading", { name: "Curator workspace", level: 1 })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Role: admin")).toBeVisible();

  // Check Acquisition Sources tab
  await page.getByRole("button", { name: "Acquisition Sources" }).click();
  await expect(page.getByRole("heading", { name: "Acquisition Source Registry" })).toBeVisible({ timeout: 15_000 });

  // Check Audit Log tab
  await page.getByRole("button", { name: "Audit Log" }).click();
  await expect(page.getByRole("heading", { name: "Administrative & Privileged Audit Log" })).toBeVisible({ timeout: 15_000 });

  // Return to Opportunities tab
  await page.getByRole("button", { name: "Opportunities" }).click();
  await expect(page.getByRole("button", { name: /New Opportunity Draft/i })).toBeVisible({ timeout: 15_000 });

  // Open creation form and submit draft
  await page.getByRole("button", { name: /New Opportunity Draft/i }).click();
  const testSlug = `rc-fellowship-${Date.now()}`;
  await page.fill("#opp-slug", testSlug);
  await page.fill("#opp-title", "Pan-African Research Fellowship 2027");
  await page.fill("#opp-host", "African Institute for Mathematical Sciences");
  await page.fill("#opp-url", "https://example.org/fellowship");
  await page.fill("#opp-deadline", "2027-08-31T12:00");
  await page.getByRole("button", { name: /Save draft/i }).click();

  // Wait for new item in opportunities list
  const draftItem = page.locator("li", { hasText: "Pan-African Research Fellowship 2027" }).first();
  await expect(draftItem).toBeVisible({ timeout: 15_000 });
  await expect(draftItem.getByText("draft").first()).toBeVisible();

  // Attempt to publish without verified sources or verbatim rules:
  // Completeness guard MUST reject publication and show explicit error alert
  const publishBtn = draftItem.getByRole("button", { name: /Verify & Publish/i });
  await publishBtn.click();
  await expect(page.getByRole("alert")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("alert")).toContainText(/verified source/i);

  // Close an active opportunity: Find CERN or another active opportunity and close it
  const cernItem = page.locator("li", { hasText: "CERN Summer Student Programme" }).first();
  await expect(cernItem).toBeVisible({ timeout: 15_000 });
  const closeBtn = cernItem.getByRole("button", { name: /Close Cycle/i });
  await closeBtn.click();
  await expect(cernItem.getByText("closed").first()).toBeVisible({ timeout: 15_000 });

  // Re-publish the opportunity to restore active state and verify re-opening workflow
  const republishBtn = cernItem.getByRole("button", { name: /Verify & Publish/i });
  await republishBtn.click();
  await expect(cernItem.getByText("published").first()).toBeVisible({ timeout: 15_000 });
});
