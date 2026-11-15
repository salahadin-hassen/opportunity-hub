import { expect, test, type Page } from "@playwright/test";

// The curator's candidate workflow against the real stack. The candidates come from
// backend/scripts/seed_e2e_candidates.py (run by scripts/e2e.sh): fixture pages pushed through the
// real pipeline, so the queue holds two candidates to review, one duplicate and one expired.
// The tests run in order and share state: the second checks what a student can see of the first's work.
// Nothing here publishes, so the public catalogue the other specs count is unchanged.

const ADMIN = { email: "admin@example.org", password: process.env.E2E_ADMIN_PASSWORD ?? "AdminPass123!" };
const studentPassword = "candidate-password-1";
const SOURCE = "E2E Fixture Institute";
const FELLOWSHIP = "E2E Marine Science Fellowship";
const SUMMER_SCHOOL = "E2E Robotics Summer School";
const SCHOLARSHIP = "E2E Heritage Scholarship";
const EDITED_TITLE = "E2E Marine Science Fellowship (reviewed)";
const KEPT_RULE = "Applicants must hold a bachelor's degree in marine biology, oceanography or a related field.";
const DROPPED_RULE = "Applicants must be available for the full twelve months of the fellowship.";

let draftId: string | undefined;

test.describe.configure({ mode: "serial" });

async function signInAsCurator(page: Page) {
  await page.goto("/login");
  await page.fill("#email", ADMIN.email);
  await page.fill("#password", ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/(discover|eligibility|opportunities)$/, { timeout: 15_000 });
}

async function openQueue(page: Page) {
  await page.goto("/curate");
  await expect(page.getByRole("heading", { name: "Curator workspace", level: 1 })).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: /Candidate Queue/ }).click();
}

const filter = (page: Page, name: string) => page.getByRole("button", { name, exact: true });
const row = (page: Page, title: string) => page.locator("tbody tr", { hasText: title });
const dialog = (page: Page) => page.getByRole("dialog", { name: "Review Ingestion Candidate" });

test("curator: queue, filters, evidence, edited approval and rejection", async ({ page }) => {
  await signInAsCurator(page);
  await openQueue(page);

  // --- the queue opens on what needs review, with the source and the extracted deadline
  await expect(page.getByText("2 candidate(s)")).toBeVisible({ timeout: 15_000 });
  await expect(row(page, FELLOWSHIP)).toHaveCount(1);
  await expect(row(page, SUMMER_SCHOOL)).toHaveCount(1);
  await expect(row(page, SUMMER_SCHOOL)).toContainText(SOURCE);
  await expect(row(page, SUMMER_SCHOOL)).toContainText("needs review");
  await expect(row(page, SUMMER_SCHOOL)).toContainText(/\d{4}-\d{2}-\d{2}/);
  await expect(page.getByRole("button", { name: /Candidate Queue/ })).toContainText("2");

  // --- filtering by state
  await filter(page, "expired").click();
  await expect(page.getByText("1 candidate(s)")).toBeVisible();
  await expect(row(page, SCHOLARSHIP)).toContainText("expired");
  await expect(row(page, FELLOWSHIP)).toHaveCount(0);

  await filter(page, "duplicate").click();
  await expect(page.getByText("1 candidate(s)")).toBeVisible();
  await expect(row(page, FELLOWSHIP)).toContainText("Cand duplicate");

  await filter(page, "approved").click();
  await expect(page.getByText(/No candidates in .approved. state/)).toBeVisible();

  await filter(page, "all").click();
  await expect(page.getByText("4 candidate(s)")).toBeVisible();

  // --- a duplicate carries a warning and needs an explicit override to approve
  await filter(page, "duplicate").click();
  await row(page, FELLOWSHIP).getByRole("button", { name: "Review" }).click();
  await expect(dialog(page).getByText("Duplicate Warning")).toBeVisible({ timeout: 15_000 });
  await expect(dialog(page).getByLabel(/Force approve override/)).not.toBeChecked();
  await dialog(page).getByRole("button", { name: "Approve as Draft Opportunity" }).click();
  await expect(dialog(page).getByRole("alert")).toContainText(/explicit override/);
  await dialog(page).getByRole("button", { name: "Cancel" }).click();
  await expect(dialog(page)).toHaveCount(0);

  // --- candidate details and source evidence
  await filter(page, "needs review").click();
  await row(page, FELLOWSHIP).getByRole("button", { name: "Review" }).click();
  await expect(dialog(page)).toBeVisible({ timeout: 15_000 });
  await expect(dialog(page)).toContainText(`Source: ${SOURCE}`);
  await expect(dialog(page).getByRole("link", { name: /e2e-fixture-institute\.edu/ })).toBeVisible();

  const evidence = dialog(page).getByRole("region", { name: "Source evidence" });
  await expect(evidence).toContainText("HTTP 200");
  await expect(evidence).toContainText(/[0-9a-f]{16}…/); // the stored page's content hash
  await expect(evidence).toContainText("deterministic-1");
  await expect(evidence).toContainText(/Deadline quote:.*Application deadline: \d{1,2} \w+ \d{4}/);
  await expect(evidence).toContainText(`Title quote: ${FELLOWSHIP}`);
  await expect(evidence).toContainText(/Warning:/); // e.g. the category was inferred from wording

  // The quoted eligibility statements, all selected to begin with.
  await expect(dialog(page).getByText(KEPT_RULE)).toBeVisible();
  await expect(dialog(page).getByText(DROPPED_RULE)).toBeVisible();
  await expect(dialog(page).getByText("2 selected")).toBeVisible();

  // --- review editing: the extracted values are prefilled and can be corrected
  await expect(dialog(page).getByLabel("Title")).toHaveValue(FELLOWSHIP);
  await expect(dialog(page).getByLabel("Deadline Type")).toHaveValue("fixed");
  await expect(dialog(page).getByLabel("Deadline Date (YYYY-MM-DD)")).toHaveValue(/^\d{4}-\d{2}-\d{2}$/);
  await dialog(page).getByLabel("Title").fill(EDITED_TITLE);
  await dialog(page).getByLabel("Opportunity Type").selectOption("fellowship");
  await dialog(page).locator("label", { hasText: DROPPED_RULE }).getByRole("checkbox").uncheck();
  await expect(dialog(page).getByText("1 selected")).toBeVisible();
  await dialog(page).getByLabel("Curator Review Notes").fill("Checked against the official page");

  // --- approval creates a draft; it does not publish
  await dialog(page).getByRole("button", { name: "Approve as Draft Opportunity" }).click();
  await expect(dialog(page)).toHaveCount(0, { timeout: 15_000 });
  await expect(page.getByText("1 candidate(s)")).toBeVisible({ timeout: 15_000 });
  await expect(row(page, FELLOWSHIP)).toHaveCount(0);

  await filter(page, "approved").click();
  await expect(row(page, FELLOWSHIP)).toContainText("approved", { timeout: 15_000 });

  const approved = await page.request.get("/api/curate/candidates?state=approved");
  expect(approved.ok()).toBeTruthy();
  const [candidate] = (await approved.json()) as { opportunity_id: string }[];
  draftId = candidate.opportunity_id;
  const drafts = (await (await page.request.get("/api/curate/opportunities?status=draft")).json()) as any[];
  const draft = drafts.find((item) => item.id === draftId);
  expect(draft, "the approved candidate's opportunity is listed among the drafts").toBeTruthy();
  expect(draft.status).toBe("draft");
  expect(draft.title).toBe(EDITED_TITLE);
  expect(draft.opportunity_type).toBe("fellowship");
  // The audit trail records the decision: who corrected what, and that one quoted rule was kept.
  const audit = (await (await page.request.get("/api/admin/audit?action=ingestion.candidate_approved&limit=1")).json()) as any[];
  expect(audit[0].changes.opportunity_id).toBe(draftId);
  expect(audit[0].changes.statements_kept).toBe(1);
  expect(audit[0].changes.curator_overrides.title).toBe(EDITED_TITLE);
  expect(audit[0].reason).toBe("Checked against the official page");

  await page.getByRole("button", { name: "Opportunities", exact: true }).click();
  const draftItem = page.locator("li", { hasText: EDITED_TITLE }).first();
  await expect(draftItem).toBeVisible({ timeout: 15_000 });
  await expect(draftItem.getByText("draft").first()).toBeVisible();

  // --- rejection, with the curator's reason
  await page.getByRole("button", { name: /Candidate Queue/ }).click();
  await filter(page, "needs review").click();
  await row(page, SUMMER_SCHOOL).getByRole("button", { name: "Review" }).click();
  await expect(dialog(page).getByLabel("Title")).toHaveValue(SUMMER_SCHOOL, { timeout: 15_000 });
  await dialog(page).getByLabel("Curator Review Notes").fill("Paid course, not a funded opportunity");
  await dialog(page).getByRole("button", { name: "Reject", exact: true }).click();
  await expect(dialog(page)).toHaveCount(0, { timeout: 15_000 });
  await expect(page.getByText(/No candidates in .needs review. state/)).toBeVisible({ timeout: 15_000 });

  await filter(page, "rejected").click();
  await expect(row(page, SUMMER_SCHOOL)).toContainText("rejected", { timeout: 15_000 });
  const rejected = await (await page.request.get("/api/curate/candidates?state=rejected")).json();
  expect(rejected).toHaveLength(1);
  const detail = await (await page.request.get(`/api/curate/candidates/${rejected[0].id}`)).json();
  expect(detail.review_notes).toBe("Paid course, not a funded opportunity");
  expect(detail.opportunity_id).toBeNull();
});

test("student: no access to the queue, and the approved draft is invisible", async ({ page }) => {
  expect(draftId, "the curator test must have approved a candidate first").toBeTruthy();

  const email = `e2e-cand-student-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.org`;
  await page.goto("/register");
  await page.fill("#email", email);
  await page.fill("#password", studentPassword);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/onboarding$/, { timeout: 15_000 });
  await page.fill("#full_name", "Ingestion Fixture Student");
  await page.selectOption("#citizenships", "ET");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.selectOption("#degree_level", "bachelor");
  await page.fill("#institution_name", "Addis Ababa University");
  await page.fill("#field_of_study", "Marine Biology");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Python" }).click();
  await page.getByRole("button", { name: "Save and check my eligibility" }).click();
  await expect(page).toHaveURL(/\/eligibility$/, { timeout: 30_000 });

  // The workspace and every candidate endpoint refuse a student.
  await page.goto("/curate");
  await expect(page.getByText("Curator access required")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("button", { name: /Candidate Queue/ })).toHaveCount(0);
  for (const path of [
    "/api/curate/candidates",
    "/api/curate/candidates?state=approved",
    "/api/curate/candidates/runs",
    "/api/curate/ingestion/source-health",
    "/api/curate/ingestion/refresh-checks",
    "/api/curate/opportunities?status=draft",
  ]) {
    expect((await page.request.get(path)).status(), path).toBe(403);
  }
  const review = await page.request.post(`/api/curate/candidates/${draftId}/review`, {
    data: { decision: "approve" },
    headers: { Origin: new URL(page.url()).origin },
  });
  expect(review.status()).toBe(403);

  // The draft is not in the catalogue, by search or by address.
  expect((await page.request.get(`/api/opportunities/${draftId}`)).status()).toBe(404);
  const listing = (await (await page.request.get("/api/opportunities?limit=100")).json()) as { title: string }[] | { items: { title: string }[] };
  const titles = (Array.isArray(listing) ? listing : listing.items).map((item) => item.title);
  expect(titles.length).toBeGreaterThan(0);
  expect(titles.filter((title) => title.startsWith("E2E "))).toEqual([]);

  await page.goto("/opportunities");
  await expect(page.getByText("12 opportunities")).toBeVisible({ timeout: 15_000 });
  await page.fill("#discover-search", "E2E Marine Science");
  await expect(page.getByText(EDITED_TITLE)).toHaveCount(0);
  await expect(page.getByText(FELLOWSHIP)).toHaveCount(0);
  await expect(page.getByText(/0 opportunities of 12|No opportunities/i).first()).toBeVisible();
});
