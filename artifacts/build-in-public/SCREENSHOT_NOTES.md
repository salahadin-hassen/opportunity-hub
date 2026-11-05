# Build-in-public screenshots — notes

Captured 2026-11-01 with Playwright (Chromium, headless) from the real app on branch
`feat/opportunity-hub-product` @ `b8da30f`: Vite dev server + FastAPI backend + PostgreSQL.

- **Database:** a separate disposable database, `opportunity_hub_screenshots`, in the local dev cluster
  (:5433). It was created with `alembic upgrade head` and filled by the repo's own `scripts.seed_demo`.
  The existing `opportunity_hub*` databases were not touched.
- **Data:** the seeded dataset. All 12 listed opportunities are real programs, with rules quoted from the
  official pages (retrieved 30 Oct 2026). The account is the fictional demo profile "Mekdes Tadesse"
  (`demo@example.org`, a reserved domain), so no real person's data appears.
- **Verdicts** come from the real engine through the UI's **Re-check all** and **Save and re-check**
  buttons. Nothing was edited or staged.
- **Desktop:** viewport 1440 × 1000 at deviceScaleFactor 2, so the files are 2880 × 2000 px.
- **Mobile:** viewport 390 × 844 at deviceScaleFactor 3, so the file is 1170 × 2532 px. This is the
  real responsive layout, not a cropped desktop image.
- Light theme, 100% zoom, viewport captures only (no full-page stitching), cursor parked in a corner.
- No browser frames, overlays or retouching.

| File | Route | Shows | Why selected | Context before posting |
| --- | --- | --- | --- | --- |
| `01-product-overview.png` | `/` (signed out) | Hero: "There's more out there for you.", value proposition, CTAs, "12 programs open now, each with its official rules quoted" | Strongest first impression and visual identity | Photos are credited stock/CC images (see `/credits`) |
| `02-opportunity-discovery.png` | `/discover` (signed in) | Search, type and sort filters, type tabs with counts, verdict filter chips, "Closing soonest" cards with deadlines and verdicts | Shows discovery and verdicts in one view | Verdicts belong to the demo profile |
| `03-opportunity-details.png` | `/opportunities/1724320f-…` (ETH Student Summer Research Fellowship 2027) | Provider, deadline with countdown, language, official-page link, rules with required vs. profile value, verbatim official wording with source and retrieval date, "Needs review" standing | Real detail page with sourced rules | Rules are a curated, structured reading of the official page |
| `04-eligibility-evaluation.png` | `/opportunities/3f662f38-…` (GitHub Student Developer Pack), scrolled to "The rules" | One rule met, one missing ("Not in your profile"), with official quotes, "Potential match" standing and the "not an admission" disclaimer | The clearest example of explainable evaluation | Genuine output: the demo profile has no date of birth on purpose |
| `05-student-profile.png` | `/profile` | Eligibility-facts meter (4/6), "Used in eligibility" vs. "Stored only" labels, missing facts flagged | Shows which facts the engine reads | Shows the demo email `demo@example.org` (fictional) |
| `06-mobile-experience.png` | `/eligibility` at 390 × 844 | Responsive verdict summary (0 / 1 / 8 / 3), bottom tab bar | Real mobile layout | Captured before the date-of-birth update |
| `07-verdict-change.png` | `/eligibility` after **Fill the gaps → date of birth → Save and re-check** | "Your update changed 1 verdict: GitHub Student Developer Pack, Potential match → Eligible"; counts now 1 / 0 / 8 / 3 | The "one missing fact" loop, which sets the product apart (shot 6) | The date of birth (18 Apr 2003) is the fictional value from `docs/DEMO_RUNBOOK.md`. The "1 verdict changed" toast is visible at the bottom. |

## Defects noticed (not fixed)

- **Discover, scrolled:** filter-chip text shows faintly through the translucent sticky header. I
  avoided it by capturing the top of the page.
- **Mobile detail page:** "Your standing" and "Sources" come before "The rules", so the evaluation sits
  well below the fold on phones.
- **Eligibility page:** mixed font styles in "Last check 1 Nov, 15:47" (mono date inside sans text) look
  slightly uneven.
- **Environment note:** the dev cluster was shut down externally mid-session (a "fast shutdown" in
  `.devdb/log.txt`). This is not an app defect. It was restarted with `scripts/dev-db.sh start`.
