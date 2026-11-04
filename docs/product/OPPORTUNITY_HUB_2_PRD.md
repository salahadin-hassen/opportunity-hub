# Opportunity Hub 2.0 — Product Requirements Document

| | |
| --- | --- |
| Status | Draft rev. 2 for founder review |
| Date | 2026-11-01 |
| Baseline | Branch `feat/opportunity-hub-product`, commit `b8da30f` |
| Companion | [`docs/architecture/OPPORTUNITY_HUB_2_IMPLEMENTATION_PLAN.md`](../architecture/OPPORTUNITY_HUB_2_IMPLEMENTATION_PLAN.md) (milestones, tasks, decision register) |
| Rev. 3 changes | Automated opportunity intelligence becomes a core capability (new §M): source registry, discovery, extraction with verified quotes, deterministic rule conversion, A/B/C publication with per-source rollout, programme/cycle model, monitoring, exception-based curation. §E, §K and §L revised; curator persona and journey C9 rewritten. |
| Rev. 2 changes | Founder's preliminary decisions incorporated (custom domains, optional-rule semantics, self-review, deletion with recovery window, payment readiness). Engine gaps re-verified against code. Requirement IDs normalised and de-duplicated. Every MVP requirement mapped to a plan task (§L). |

### How to read this document
- **Status tags** (§0.2) describe the code at the baseline commit. Source code was the authority. Docs and
  pitch material were used only as pointers.
- **Everything not tagged *Existing*** is a proposal. Numerical targets are *proposed and unvalidated*.
- **"Founder preference"** marks a direction the founder has stated (rev. 2). It is still open to challenge.
  Conflicts are called out where they arise. **"Open"** marks a decision not yet made. Decision IDs (`DEC-…`)
  refer to the register in Implementation Plan §L.

---

## 0. Current-state baseline

### 0.1 Summary
Opportunity Hub is a working early product. It consists of a FastAPI + PostgreSQL API and a React 19
single-page app. According to `docs/presentation/README.md`, it is live at `https://opportunities.sahelyon.com`
with the API at `https://api.opportunities.sahelyon.com`. It runs on Render's free tier with a Neon Postgres
database. A student can register, complete a three-step onboarding, and get a deterministic, evidence-backed
eligibility verdict for each of 12 listed (+2 closed) real, hand-curated opportunities.

It is **not yet a SaaS product**. It lacks curator tooling, an account lifecycle, saved items, application
tracking, notifications and operational basics (CI, backups, monitoring).

> **Configuration drift (needs verification):** `render.yaml` still sets `CORS_ORIGINS` to
> `https://opportunity-hub.onrender.com` and `VITE_API_BASE` to `https://opportunity-hub-api.onrender.com`.
> If the custom domains work, the live values were changed in the Render dashboard and the Blueprint is out
> of date. A Blueprint sync could revert them. Plan task M1-T7 reconciles this.

### 0.2 Status legend
**Existing** (verified in code) · **Partial** (some parts exist) · **Docs only** (described, not built) ·
**Missing** · **Unverified** (insufficient evidence).

### 0.3 Capability inventory

| Area | Capability | Status | Evidence |
| --- | --- | --- | --- |
| Auth | Register (email + 8–128-char password), Argon2id | Existing | `backend/app/api/routers/auth.py`, `core/security.py` |
| | Login → HS256 JWT, 30-min TTL, no refresh | Existing | `core/security.py` `ACCESS_TOKEN_TTL` |
| | Token stored in browser `localStorage` (`oh.session`) | Existing | `frontend/src/api/client.ts` |
| | Uniform 401 for every auth failure | Existing | `api/deps.py::unauthorized` |
| | Registration discloses an existing email (409) | Existing (trade-off) | `routers/auth.py` |
| | Server-side logout / revocation | Missing | Logout only clears storage |
| | Password reset, email verification | Missing | No email capability anywhere |
| | Credential rate limit, in-memory, per process | Existing; proxy correctness Unverified | `core/rate_limit.py`; `render.yaml` start command uses `--forwarded-allow-ips="*"` |
| Profile | One profile per user; citizenship, residence, DOB, degree level, enrolment, languages, interests, links, bio | Existing | `models/profile.py`, `uq_profiles_user_id` |
| | Education with GPA + scale; one primary | Existing | partial unique `uq_education_primary_per_profile` |
| | Test scores (stored only) | Existing | no evaluator reads them |
| | Skills from curated catalog | Existing | `/skills`, `/me/profile/skills` |
| | Field/year of study read by rules | Missing | `education.field_of_study` is free text, never evaluated |
| | Missing-fact impact ranking | Partial (client-only) | `frontend/src/lib/resolve.ts` |
| Discovery | Public list + detail with rules and sources | Existing | `GET /opportunities`, `GET /opportunities/{id}` |
| | Search/filter/sort | Partial (client-side over full list) | `frontend/src/routes/Discover.tsx` |
| Opportunity data | Opportunity / Source / Requirement with verbatim `source_quote` | Existing | `models/*.py`; seed policy in `backend/scripts/seed_demo.py` |
| | Status enum draft/published/closed/archived | Partial | read filtering only; no transitions, no auto-close |
| | Create opportunity via API | Partial | `POST /opportunities` with shared `X-Admin-Token`; disabled when `ADMIN_API_TOKEN` unset (production per `docs/DEPLOYMENT.md`); cannot create requirements or sources |
| | Requirement/source write API | Missing | only the seed script writes them |
| | Creator / reviewer / publisher identity | Missing | no actor columns |
| | Verification, freshness, change history | Missing | `sources.retrieved_at/content_hash/raw_snapshot` exist but are unused by any process |
| | Automated discovery, fetching, extraction, monitoring, LLM use, programme/cycle model | Missing | no fetcher, scheduler or LLM code; one `opportunities` row per call, `slug` globally unique (§M.1) |
| Eligibility | Deterministic evaluation with per-rule evidence | Existing | `services/matching/*` |
| | Persisted match (one per profile × opportunity), evidence replaced on re-evaluation | Existing | `services/matches.py`, unique constraint |
| | `engine_version` recorded (constant `"1"`) | Existing | `services/matching/__init__.py` |
| | Optional requirements (`is_mandatory=false`) | Partial | column exists; only exempts `not_met` (see §F.4); **no seed rule sets it** (verified: `seed_demo.py` never sets `is_mandatory`) |
| | Stale-result detection | Partial (client-only, lost on reload) | `features/eligibility.tsx` |
| | Batch evaluation | Missing | client sends one POST per opportunity, 4 concurrent |
| Saved / applications | Bookmarks, tracking, checklists | Missing | |
| | "Confirmed myself" ticks | Existing (browser-only) | `hooks/useDeviceChecklist.ts` |
| Notifications | Email / in-app / reminders | Missing | |
| Administration | Roles, curator UI, publishing workflow, audit | Missing | |
| Billing | — | Missing | |
| Security | Per-user scoping on all `/me/*` | Existing | `api/deps.py::get_my_profile` |
| | Strong production JWT secret enforced at start-up | Existing | `core/config.py` |
| | Explicit CORS allow-list, `*` rejected, `allow_credentials=False` | Existing | `core/config.py`, `main.py` |
| | Account deletion | Missing; also blocked by DB (`profiles.user_id` FK `ON DELETE RESTRICT`) | `models/profile.py` |
| | Data export, audit log, CSP | Missing | `render.yaml` sets only `nosniff` and `Referrer-Policy` |
| Operations | DB-backed `/health`; migrations on start | Existing | `main.py`, `render.yaml` |
| | Backups | Docs only (manual `pg_dump`) | `docs/DEPLOYMENT.md` §5 |
| | CI, staging, error tracking, uptime monitoring | Missing | no `.github/` |
| | Tests | Existing (not executed for this document) | 501 `def test_` functions in `backend/tests/` (more cases via parametrisation), Vitest `lib/rules.test.ts`, Playwright `e2e/` |

### 0.4 Capabilities to preserve
1. The deterministic engine and its conservative behaviour. A missing fact is `unknown`, never a failure,
   except for the empty-list cases in §F.6. GPA scales are never converted. Unsupported shapes go to
   `needs_review`.
2. Persisted per-rule evidence joined to label and verbatim source quote.
3. The curation policy at the top of `backend/scripts/seed_demo.py`. It becomes the curator handbook.
4. Ownership derived from the JWT. The client never names a profile.
5. UI honesty rules (`frontend/README.md`): "the organization decides", and "Read by rules" vs "Stored only" labels.
6. The "Opportunity Atlas" visual identity, the custom domains, and the missing-fact resolve loop.

---

## A. Product overview

**Vision.** For a student, Opportunity Hub is the trusted place to find out which opportunities they can
apply to, why, and what to do next. Every answer is traceable to the organization's own words.

**Problem.** Students in Ethiopia and across Africa learn about opportunities through scattered channels
(Telegram channels, aggregator blogs, word of mouth). These channels often paraphrase or misstate
eligibility and go out of date. Students waste effort on calls they could never win, miss ones they could,
and track deadlines and documents informally. *Assumption to validate (DEC-19):* the frequency and severity
of these pains have not been measured with users.

**Solution.** (1) A curated database where each condition is a structured rule stored with its verbatim
source sentence. (2) A deterministic engine producing *eligible / potential match / needs review / not
eligible* with rule-by-rule evidence. (3) Guidance on which missing facts would settle undecided verdicts.
(4) A light application workspace with saved items, status, checklist and reminders.

**Differentiators.** Explainable, evidence-backed verdicts (existing). Traceable sources (existing for seed
data). Honest uncertainty. Fit for African GPA scales, citizenship rules and mobile-first use.

**Principles.** Trust over feature count: a wrong "Eligible" is worse than a missing feature. No opaque scores
and no AI eligibility decisions. Official sources first. Human verification before anything is shown as
verified. Privacy by design. Mobile-first and accessible. Incremental evolution. A useful free product.

---

## B. Target users

| Persona | Context | Needs | Frustrations | Primary use |
| --- | --- | --- | --- | --- |
| **Hana**, undergraduate scholarship seeker (primary) | 3rd-year engineering, Ethiopian public university, Android, metered data | Short list of real options; "does my 3.4/4 count?"; deadlines | expired or paraphrased listings; exclusions discovered late | onboarding, discovery, eligibility, save, reminders |
| **Dawit**, graduate applicant | applying for funded master's programs abroad | filter by degree/field; understand ambiguous conditions; compare | "first-class or equivalent" wording; differing document sets | discovery, needs-review explanations, applications |
| **Selam**, many applications | 5–10 applications per cycle | status, deadlines, document readiness in one place | spreadsheets drift; late recommendation requests | application workspace, reminders, outcomes |
| **Curator** | trusted team member, initially the founder alone | approve sources once; handle only flagged items with the evidence in front of them; trust that automation fails safe | today every change is an edit to a 973-line seed script | source approval, exception queue, corrections, overrides with reasons, spot checks (§M) |
| **Administrator** | the founder initially | grant roles, handle deletion/export, audit, restore | — | roles, audit, account support, operations |

Institutional staff are not a 2.0 persona (§K).

---

## C. User journeys
Each journey states **Today** (verified) and **2.0** (proposed).

- **C1 Registration & onboarding.**
  - Today: `/register` → auto-login → `/onboarding` in 3 steps (personal and citizenship; degree, institution,
    field, GPA + scale; skills) → `/eligibility` checks every listed opportunity.
  - 2.0: same flow. The session is a secure cookie (AUTH-004). Email verification is requested but does not
    block discovery (AUTH-003). The first full evaluation is one server call (ELIG-006).
  - Outcome: at least one decided or potential verdict in the first session (metric *first useful match*).
- **C2 Profile completion.** Completeness counts only rule-read facts. Missing facts are ranked by how many
  undecided verdicts they would settle. Saving a fact marks affected matches stale and re-evaluates them
  (ELIG-007).
- **C3 Discovery.** Server-side search and filters (DISC-002). Closed and expired items are hidden by default
  (OPPTY-006). Each card shows verdict, deadline and verification state.
- **C4 Eligibility.** Verdict plus an evidence table split into **Required** and **Optional** sections
  (ELIG-004). `needs_review` rows say "Not checked automatically", never "Checked" (ELIG-003).
- **C5 Missing requirements.** Existing Resolve panel, now driven by server staleness.
- **C6 Saving.** Save from card or detail. `/saved` is ordered by deadline. Reminders are on by default for
  saved items, and the student can turn them off.
- **C7 Application.** "Start application" → status `planning` → checklist seeded from `document`-category
  rules → notes → status changes → outcome.
- **C8 Reminders.** Email + in-app at proposed offsets of 14, 3 and 1 days before a fixed deadline. Stopped by
  submission or withdrawal, or when the opportunity is closed or withdrawn. One-click unsubscribe.
- **C9 Opportunity reaches students without data entry.** Today a curator edits the seed script. In 2.0 the
  pipeline discovers, extracts, verifies and publishes from approved official sources (§M.8 J-INT-1). The
  curator handles only exceptions (J-INT-2). With one curator, a manual review may be self-review, and it is
  then recorded as **"self-reviewed"** and never presented as independent verification (OPPTY-003, DEC-07).
- **C10 Account deletion.** Request (password re-entry) → access disabled immediately and all sessions
  revoked → confirmation email with a cancel link valid for the recovery window → permanent purge after the
  window (AUTH-005).

---

## D. Functional requirements

Priority: **P0** = MVP blocker · **P1** = MVP · **P2** = post-MVP · **P3** = future.
"(existing)" means the baseline already satisfies it; it stays listed as a regression guard.

### D.1 Authentication & account (AUTH)

| ID | Requirement | Value | Pri | Acceptance criteria | Deps |
| --- | --- | --- | --- | --- | --- |
| AUTH-001 | Email + password registration and login (existing) | access | P0 | `tests/test_auth_api.py` stays green; Argon2id; one generic 401 shape | — |
| AUTH-002 | Password reset by single-use emailed link | recovery | P0 | token ≥ 32 random bytes, stored hashed, single-use, expires ≤ 60 min; identical response for known/unknown email; success revokes all sessions | NOTIF-001 |
| AUTH-003 | Email verification | reliable notifications | P1 | link valid ≤ 24 h; unverified users may use discovery and eligibility; no non-account email sent to unverified addresses | NOTIF-001 |
| AUTH-004 | Cookie-based server sessions replacing `localStorage` bearer tokens | XSS token theft removed; real logout | P0 | design and tests per Plan §F: `HttpOnly; Secure; SameSite=Lax` host-only cookie on the API host; server-side revocation; Origin-checked CSRF defence; idle and absolute expiry | DEC-03 |
| AUTH-005 | Account deletion with recovery window | privacy promise | P0 | on request: `is_active=false`, sessions revoked, deletion scheduled; cancel only via emailed link within the window; purge after the window removes every user-owned row (Plan §C.5); audit entry without PII | NOTIF-001, DEC-08 |
| AUTH-006 | Data export (JSON) | transparency | P1 | one file with every user-owned row; excludes hashes and tokens; rate-limited | — |
| AUTH-007 | Roles and permissions (`student`, `curator`, `admin`) with permission checks | replaces shared token | P0 | permissions checked server-side (Plan §F.6); shared `X-Admin-Token` removed after a CLI bootstrap exists | — |
| AUTH-008 | Correct, proxy-aware rate limiting on credential and email-sending endpoints | abuse resistance | P0 | forged `X-Forwarded-For` cannot reset a client's budget (test); limits hold across restarts once persisted | — |
| AUTH-009 | Change password while signed in | hygiene | P1 | requires current password; revokes other sessions | AUTH-004 |

### D.2 Profile (PROFILE)

| ID | Requirement | Pri | Acceptance criteria | Deps |
| --- | --- | --- | --- | --- |
| PROFILE-001 | Profile, education, test score, skill CRUD (existing) | P0 | existing API tests green | — |
| PROFILE-002 | Each field labelled "Read by eligibility rules" or "Stored only" from one capability source | P1 | test fails if the label set ≠ the engine capability registry | ELIG-002 |
| PROFILE-003 | Completeness over rule-read facts, ranked by impact | P1 | same ranking semantics as `missingFactImpacts` | ELIG-007 |
| PROFILE-004 | Field of study as a rule-read fact via a curated taxonomy | P1 | unmapped value → `unknown`, never `not_met` | ELIG-002 |
| PROFILE-005 | Year of study / expected graduation as a rule-read fact | P2 | — | ELIG-002 |
| PROFILE-006 | Resolve the duplicate `profiles.email` | P1 | DEC-10 recorded; data migrated without loss | — |

### D.3 Opportunity data (OPPTY)

| ID | Requirement | Pri | Acceptance criteria | Deps |
| --- | --- | --- | --- | --- |
| OPPTY-001 | Opportunity/Source/Requirement with verbatim quotes and URLs (existing) | P0 | public schemas unchanged in meaning | — |
| OPPTY-002 | Curator API for opportunities, sources and rulesets | P0 | writes validated by per-kind params models **and** the capability registry; permission `opportunity.edit`; every write audited | AUTH-007, ADMIN-003 |
| OPPTY-003 | Workflow `draft → in_review → published → closed / withdrawn / archived` with recorded **creator, reviewer, publisher** and **published_at** | P0 | publish requires permission `opportunity.publish`; if reviewer = creator the record is flagged `self_reviewed=true` and the UI never says "independently verified"; separation of duties enforceable by a single setting (DEC-07) | ADMIN-003 |
| OPPTY-004 | Verification record: who, when, method, source hashes | P0 | publishing requires a verification within the freshness window (proposed 30 days, DEC-12) | — |
| OPPTY-005 | Ruleset versioning: published rules are never edited in place | P0 | edit → new ruleset version; old rows retired, not deleted; old evidence still resolves | ELIG-005 |
| OPPTY-006 | Auto-close at a fixed deadline | P0 | daily job; idempotent; rolling/no-deadline items rely on re-verification instead | JOB-001 |
| OPPTY-007 | Freshness states visible to curators and students | P1 | proposed: curator flag at > 30 days unverified; student notice at > 90 days; hidden from default discovery at > 180 days (DEC-12) | OPPTY-004 |
| OPPTY-008 | Change history viewable per opportunity | P1 | before/after, actor, time | ADMIN-003 |
| OPPTY-009 | Publication requires ≥ 1 requirement | P0 | resolves the zero-requirement "eligible" case (§F.7) | — |
| OPPTY-010 | Automated acquisition and publication per §M (supersedes the rev. 2 "assisted extraction, drafts only" item) | P0 | requirements in §M.4 | §M |
| OPPTY-011 | Programme (recurring) vs cycle (one opportunity row per application cycle) | P0 | unique `(program_id, cycle_key)`; existing rows backfilled 1:1 | — |

### D.4 Discovery (DISC)

| ID | Requirement | Pri | Acceptance criteria | Deps |
| --- | --- | --- | --- | --- |
| DISC-001 | Public list and detail (existing) | P0 | — | — |
| DISC-002 | Server-side text search and filters: type, degree level, eligible citizenship, deadline window | P1 | Postgres only (no search engine); paginated with total count | — |
| DISC-003 | Signed-in filter/sort by verdict, with stale markers | P1 | — | ELIG-007 |
| DISC-004 | Default order: verdict rank, then soonest deadline; closed hidden | P1 | — | OPPTY-006 |

### D.5 Eligibility (ELIG)

| ID | Requirement | Pri | Acceptance criteria | Deps |
| --- | --- | --- | --- | --- |
| ELIG-001 | Existing semantics preserved unless changed by a versioned decision | P0 | evaluator tests green; any outcome change bumps `ENGINE_VERSION` (golden test) | — |
| ELIG-002 | Every rule shape the validator accepts is evaluated; everything else is rejected at write time (Plan §E.2) | P0 | property test over all schema-accepted kind × metric × operator × arity combinations: each is either evaluated by the engine or rejected by validation | — |
| ELIG-003 | UI never implies a `needs_review` or `unknown` rule was checked | P0 | evidence rows for `needs_review` read "Not checked automatically: <reason>"; reason-code copy exists for every code (test enumerates them) | — |
| ELIG-004 | Optional requirements cannot lower the overall verdict and are shown separately (§F.4) | P0 | test matrix in Plan §E.4; API exposes `is_mandatory` per evidence row (exists via `RequirementSummary`) and separate mandatory/optional counts | DEC-04 |
| ELIG-005 | Match records `engine_version`, `ruleset_version`, `facts_version` | P0 | — | OPPTY-005 |
| ELIG-006 | Batch evaluation of all published opportunities | P1 | equivalent to per-opportunity results (test) | — |
| ELIG-007 | Server-side staleness and safe re-evaluation | P0 | stale when any version differs; stale shown in UI; re-evaluation is idempotent | ELIG-005 |
| ELIG-008 | Missing citizenship (empty list) is `unknown`, not `not_met` | P0 | changes current tested behaviour; version bump (§F.6, DEC-05) | ELIG-001 |

### D.6 Saved opportunities (SAVE)

| ID | Requirement | Pri | Acceptance criteria |
| --- | --- | --- | --- |
| SAVE-001 | Save / unsave, idempotent, one per user + opportunity | P1 | only public opportunities |
| SAVE-002 | `/saved` ordered by deadline, closed grouped separately | P1 | — |
| SAVE-003 | Server-side "confirmed myself" ticks, one-time import from `localStorage` | P2 | never affects the verdict (test) |

### D.7 Applications (APP)

| ID | Requirement | Pri | Acceptance criteria |
| --- | --- | --- | --- |
| APP-001 | Create an application (auto-saves the opportunity) | P1 | one per user + opportunity in MVP (DEC-14) |
| APP-002 | Lifecycle per §G with server-validated transitions and timestamps | P1 | exhaustive transition test |
| APP-003 | Document checklist (metadata only) | P1 | seeded from `document`-category rules + custom items |
| APP-004 | Private notes | P1 | ≤ 10 000 chars; never shown in admin UI |
| APP-005 | Personal target date | P2 | — |
| APP-006 | Outcome recording | P1 | private |
| APP-007 | Applications overview (counts, next deadlines) | P1 | mobile list, not kanban |

### D.8 Notifications (NOTIF)

| ID | Requirement | Pri | Acceptance criteria |
| --- | --- | --- | --- |
| NOTIF-001 | Transactional email through a provider-independent sender and DB outbox | P0 | SPF + DKIM + DMARC on `sahelyon.com` sender subdomain; retries with backoff; failures logged without content |
| NOTIF-002 | Deadline reminders | P1 | exactly one per offset (dedupe key); suppression rules per C8 |
| NOTIF-003 | In-app notification list | P1 | unread count; mark read; 90-day retention (proposed) |
| NOTIF-004 | Preferences and one-click unsubscribe | P1 | signed token; works signed out |
| NOTIF-005 | Weekly digest of new eligible/potential matches | P2 | opt-in; only fresh matches |
| NOTIF-006 | Change notice for saved items (rules, deadline, withdrawal) | P2 | — |

### D.9 Administration (ADMIN)

| ID | Requirement | Pri | Acceptance criteria |
| --- | --- | --- | --- |
| ADMIN-001 | Curator workspace UI | P0 | uses OPPTY-002 API only |
| ADMIN-002 | Review & publish screen with diff and quote-beside-rule view; self-review warning | P0 | — |
| ADMIN-003 | Append-only audit log of privileged and account-lifecycle actions | P0 | no tokens, passwords or profile content in entries |
| ADMIN-004 | Grant/revoke roles; deactivate users | P1 | audited; exact-email lookup only |
| ADMIN-005 | Data-quality dashboard | P2 | — |
| ADMIN-006 | Public "suggest an opportunity" queue | P2 | never publishes; rate-limited |

### D.10 Operations (OPS)

| ID | Requirement | Pri | Acceptance criteria |
| --- | --- | --- | --- |
| OPS-001 | CI on every push/PR: backend tests on Postgres, `alembic check`, frontend typecheck/tests/build | P0 | merge blocked on failure |
| OPS-002 | Automated daily backups stored off-provider + documented, tested restore | P0 | restore rehearsal recorded at least monthly (proposed) |
| OPS-003 | Always-on API for public launch (no ~1-min cold start) | P0 before launch | DEC-15 |
| OPS-004 | Deployment config as code matches production | P0 | `render.yaml` ≡ dashboard (M1-T7) |
| OPS-005 | Error visibility (structured logs; optional error tracker) | P1 | DEC-17 |
| OPS-006 | Staging environment | P2 | — |

### D.11 Monetization (BILL)

| ID | Requirement | Pri | Acceptance criteria |
| --- | --- | --- | --- |
| BILL-001 | Entitlement model (`plan`, feature flags), everyone `free` | P2 | no user-visible change |
| BILL-002 | Willingness-to-pay validation process (§H.3) | P2 | evidence reviewed against founder-set criteria |
| BILL-003 | Payment integration | P3 | only after BILL-002 passes (DEC-18) |

### D.12 Future (P3, requires validation)
APP-008 document uploads · DISC-005 saved searches · ELIG-009 language-test rules · ELIG-010 age at a
reference date · I18N-001 Amharic UI · INST-001 institution portals · MOB-001 native apps · ADMIN-007 partner ingestion · SOURCE-009 search-API discovery (see §M.6 for automation items).

---

## E. Opportunity data quality

The detailed rules are in §M (automation) and plan §O. This section summarises the policy for every
opportunity, whatever its origin.

1. **Source preference:** approved `official` sources (`official_page`, `partner_api`, organisation-confirmed
   `manual_entry`) are the only citable authority. Aggregators, mirrors, newsletters, search results and
   community tips are leads (SOURCE-003).
2. **Original statements preserved:** every requirement keeps a verbatim `source_quote`. For automated
   records the quote is the exact substring of a stored snapshot of the official page (VALID-001), together
   with its URL and retrieval time.
3. **Discovered ≠ verified:** automated discovery creates candidates. A candidate is public only after the
   gates pass (Level A/B) or a curator approves it.
4. **Verification:** automated verification = quote verification + gates G1–G9 on an approved source.
   Human verification = a curator attesting the official page was checked. The student UI says which applied
   (§M.3).
5. **Structuring:** a condition becomes a structured rule only when its wording maps exactly onto a fact the
   engine reads, and a deterministic parser agrees (RULE-002). Otherwise it is stored as `unparsed`, which
   gives `needs_review`. "Or equivalent" sets `is_ambiguous`.
6. **Review & publish:** method (automatic or curator), creator, reviewer, publisher, policy version and
   `published_at` are recorded (PUB-006). Self-review is flagged (DEC-07).
7. **Expiration & withdrawal:** a passed fixed deadline → `closed`; a cancelled call → `withdrawn`; a missing
   page past the confirmation window → `unavailable` (MON-006).
8. **Versioning & history:** published rules are immutable. A change creates a new ruleset version within the
   cycle; next year's call is a new cycle (OPPTY-005, OPPTY-011).
9. **Staleness:** monitoring re-checks each cycle by policy (MON-001). Freshness is shown to students, and
   changes follow the fail-closed rules (MON-003…006).

---

## F. Eligibility engine requirements

### F.1 Outcomes and verdict (existing, `backend/app/services/matching/evaluate.py`)
Rule outcomes: `met`, `not_met`, `unknown` (profile lacks the fact), `needs_review` (cannot be decided
automatically). Overall verdict, first match wins:
1. any **mandatory** `not_met` → `not_eligible`;
2. else any `needs_review` (mandatory **or optional**) → `needs_review`;
3. else any `unknown` (mandatory **or optional**) → `potential_match`;
4. else `eligible` (also for zero requirements).

### F.2 `unknown` vs `needs_review` (preserve)
- `unknown` = the *student* can fix it by adding a fact. The UI offers the field.
- `needs_review` = *nobody* can decide it automatically: the rule is unparsed, ambiguous, uses an unsupported
  shape, or the GPA scales differ. The UI says what a person must check, with the quote.
- The precedence `needs_review` > `unknown` is kept. Adding facts cannot resolve a review item, so
  "Needs review" is the more honest overall label.

### F.3 Supported rules
See Implementation Plan §E.1 for the verified table of what the validator accepts versus what the engine
evaluates. **Decision (DEC-06): reject at validation** every shape the engine does not evaluate. Evaluators
for additional operators are added later, one at a time, each with tests and an `ENGINE_VERSION` bump.
Existing stored rows stay readable and keep producing `needs_review`.

### F.4 Optional requirements (founder preference; proposed change)
**Semantics.** The overall verdict is computed from **mandatory requirements only**. For an optional
requirement:

| Optional rule outcome | Effect on overall verdict | Shown to the student as |
| --- | --- | --- |
| `met` | none | "Optional: met" |
| `not_met` | none (never `not_eligible`) | "Optional: not met. The organization may prefer applicants who meet this" |
| `unknown` | none (never downgrades) | "Optional: add <fact> to see whether you meet this" |
| `needs_review` | none (never downgrades) | "Optional: not checked automatically" plus the quote |

Rationale for `needs_review`: an optional condition, by definition, cannot make an applicant ineligible.
Letting its review state drive the verdict would label a student "Needs review" for something that cannot
block them. The review item still appears, so nothing is hidden.

**Consequences.**
- An opportunity whose rules are all optional evaluates as if it had zero mandatory rules. OPPTY-009 is
  therefore tightened: publishing requires ≥ 1 **mandatory** rule, or a curator acknowledgement that the call
  is open to all.
- `any_of` children have no mandatory flag. The schema forbids it, and the `any_of` group's own flag applies.
- **Compatibility.** No seed rule sets `is_mandatory=false`, and no API can create requirements, so in
  principle the change does not alter existing verdicts. This must be confirmed read-only on production
  (`SELECT count(*) FROM requirements WHERE NOT is_mandatory`) before the change ships (M2-T4). Even if the
  count is 0, `ENGINE_VERSION` becomes `"2"` and all v1 matches are marked stale. Stored evidence is not
  rewritten.

### F.5 Evidence reproducibility
Latest evaluation only, as today. No history table in MVP. A match is reproducible because it records
`engine_version`, `ruleset_version` (requirements are retired, not deleted) and `facts_version`. Profile facts
themselves are not snapshotted; the evidence `actual` values already capture what was read.

### F.6 Empty-list facts (proposed change, DEC-05)
Today a profile with an empty citizenship list gets `not_met` for any "citizen of X" rule. This is
deliberate and tested (`test_set_membership_empty_citizenship_collection_is_not_met`). Because onboarding
initialises citizenships to `[]`, a student who skipped the field is told "Not eligible". Everyone holds at
least one citizenship, so an empty list means *missing*: proposed → `unknown` (`profile_fact_unavailable`).
Skills differ: having no skills can be true. Proposed: keep `not_met` for skills, but count the skills step as
"completed" only after the student has visited and confirmed it (PROFILE-003). Founder approval required.

### F.7 Zero requirements
Today such an opportunity is `eligible`. Proposed: block publication without a mandatory rule (OPPTY-009)
instead of inventing a new verdict.

### F.8 Re-evaluation triggers
| Trigger | Action |
| --- | --- |
| Rule-read profile fact changes | `facts_version` +1 → that student's matches stale → batch re-evaluation in the same user action |
| Ruleset published | that opportunity's matches stale → re-evaluated lazily on next read, or by jobs before any notification |
| `ENGINE_VERSION` bump | all matches stale → lazy re-evaluation |
| Closed/withdrawn | no re-evaluation; status shown |

---

## G. Application management
```
SavedOpportunity ──start──► planning ⇄ in_progress ──► submitted ──► outcome
                               └──────────┴──────────────┴──► withdrawn
outcome ∈ {accepted, rejected, waitlisted, no_response}
```
- Allowed backward moves: `in_progress → planning` and `submitted → in_progress` (correction; timestamped).
- An outcome is set only after `submitted`. `withdrawn` can be set from any non-terminal state.
- Checklist items: `todo / in_progress / ready / submitted / not_applicable`, sourced from a requirement or
  custom. Metadata only, no file uploads.
- Progress is shown as "4 of 7 documents ready", not a score.
- Unsaving is blocked while an active application exists. Deleting an application keeps the saved item.
- Notes and outcomes are private. Any aggregate use requires explicit opt-in and minimum cohort sizes (P3).

---

## H. SaaS and monetization

### H.1 Free, always
Discovery, all verdicts and evidence, source quotes, saved items, basic applications and checklists, and
basic deadline reminders.

### H.2 Premium candidates (unvalidated, not to be built yet)
Advanced alerts (custom schedules, more channels), application planning (personal timelines, recommender
tracking), productivity tools (templates, calendar sync beyond a basic iCal feed), enhanced tracking (history,
cross-cycle views). Human review services (CV or essay feedback) are a service business, not software.

### H.3 Payment-readiness validation process (founder preference: no payments until evidence)
1. **Problem interviews:** structured interviews with target students. The number is set by the founder; the
   plan suggests at least 15 across 2+ universities. Record current tools, pains and spending.
2. **Feature demand:** in-product interest capture ("Notify me when <feature> is available") on each premium
   candidate, measured against active users who saw it.
3. **Willingness-to-pay test:** price-sensitivity questions (e.g. Van Westendorp) or a fake-door price page.
   Responses are logged; no money is taken.
4. **Paid pilot:** a small, manually invoiced or prepaid pilot for one feature with a handful of students or
   one institution.
5. **Conversion:** only after the pilot, offer a paid tier to the free base and measure actual conversion.

**Gate:** before steps 4 and 5, the founder writes down which evidence would justify continuing (DEC-18). This
document sets no benchmark. Payment-provider research (local mobile money and international processors)
happens in parallel with steps 1–3 and builds nothing.

### H.4 Institutional direction (later)
Career and international offices, foundations: verified listing management, consented aggregate cohort
insights. Requires multi-tenancy, institution verification and support capacity. Out of scope for 2.0.

---

## I. Non-functional requirements

| Area | Requirement |
| --- | --- |
| Security | OWASP ASVS L1 as checklist (proposed); server-side authorisation on every route; CSP; no secrets or PII in logs; dependency audit in CI |
| Privacy | data minimisation; privacy page generated from the same field/capability list (PROFILE-002); deletion + export; notes and outcomes private; no advertising or analytics trackers (current promise); any third-party processor (email, error tracking) disclosed on `/privacy`; applicable law (e.g. Ethiopia's personal data protection proclamation, GDPR for EU residents) **requires legal review** (DEC-09) |
| Accessibility | WCAG 2.2 AA target; verdicts never colour-only (existing shape-coded marks); reduced motion (existing) |
| Mobile | primary target 360–414 px Android; every flow completable on a phone |
| Performance (proposed) | landing interactive < 3 s on "Fast 3G"; API p95 < 500 ms list/detail warm; batch evaluation ≤ 100 opportunities < 2 s p95 |
| Reliability | always-on API before public launch; proposed 99% monthly availability; jobs idempotent and re-runnable |
| Failure handling | email send failures retried, never lose the request; job failures recorded and visible to admins; evaluation errors return 5xx without partial matches (existing savepoint pattern) |
| Scalability | one instance for ~10 000 students / 2 000 opportunities (proposed); no sharding, no microservices |
| Data integrity | invariants as DB constraints (existing convention); request-scoped transactions (existing) |
| Backup & recovery | proposed RPO 24 h, RTO 4 h; backups expire on a fixed schedule (§C.5 of the plan) |

---

## J. Product metrics
Computed from first-party data (SQL views first; a minimal event table only if needed). No third-party
analytics.

| Metric | Definition | Why |
| --- | --- | --- |
| Onboarding completion | profiles created within 24 h / registrations | funnel |
| Rule-read profile completion | median share of rule-read facts filled | controls decided verdicts |
| First useful match | new profiles with ≥ 1 `eligible`/`potential_match` in first session | core value |
| Decided-verdict rate | (`eligible` + `not_eligible`) / current matches | engine + data usefulness (baseline: 8 of 12 listed programs have ≥ 1 review condition per `docs/JUDGE_QA.md`) |
| Evaluation completion | sessions completing a full evaluation / sessions starting one | reliability |
| Saves per active user; application initiation; submission rate | — | workspace value |
| Reminder effectiveness | submitted before deadline after ≥ 1 reminder / reminded | notification value |
| WAU, 4-week retention | — | habit |
| Verification freshness | published verified ≤ 30 days / published | trust |
| Self-review share | published with `self_reviewed` / published | separation-of-duties progress |
| Pipeline metrics | §M.9 (yield, level mix, quote verification, false structured rules, curator minutes per cycle, cost per cycle) | whether automation earns trust |
| Curator throughput; error-report rate | — | cost and accuracy of coverage |
| Premium interest / pilot conversion | §H.3 | monetization evidence |

---

## K. Scope boundaries: 2.0 MVP excludes
Payments and paywalls · document uploads by students · **AI eligibility decisions** (AI may only propose
fields and rules, §M.2) · chat assistants · automated publication from non-official sources · search-API
discovery, aggregator connectors, PDF ingestion and JavaScript rendering in the first automated release
(§M.6) · bypassing robots, CAPTCHAs, logins or paywalls (never) · institution accounts and partner APIs ·
native apps · SMS, Telegram or WhatsApp channels · social features · scoring or ranking beyond verdict +
deadline · multi-language UI · GPA scale conversion.

---

## L. Requirement → implementation traceability (MVP: P0/P1)

| Requirement | Plan tasks |
| --- | --- |
| OPS-001 | M1-T1 |
| AUTH-008 | M1-T2, M1-T3 |
| OPS-002 / OPS-003 / OPS-004 / OPS-005 | M1-T5 / M1-T6 / M1-T7 / M1-T8 |
| AUTH-007 | M1-T4 (foundation), M2-T1 |
| AUTH-004, AUTH-009 | M1-T9 (design), M1b-T1…T4 |
| ADMIN-003, OPPTY-008 | M2-T2 (+ history view in M2-T20) |
| OPPTY-005, OPPTY-011, ELIG-005, ELIG-007, DEDUP-001 | M2-T3 |
| ELIG-001, ELIG-002, ELIG-004, ELIG-008 | M2-T4 |
| OPPTY-006, OPPTY-007, INGEST-006 | M2-T5 (+ freshness in M2-T19) |
| SOURCE-001…006, SEC-ING-007 | M2-T6 |
| INGEST-002, INGEST-003, SOURCE-006, SEC-ING-001…004 | M2-T7 |
| INGEST-004, INGEST-005, MON-002 | M2-T8 |
| INGEST-001, INGEST-007 | M2-T9 (+ curator URL submission UI in M2-T20) |
| SOURCE-007 | M2-T10 |
| EXTRACT-001, COST-001 | M2-T11 |
| EXTRACT-002…007, COST-002, COST-003, SEC-ING-005, SEC-ING-006 | M2-T12 |
| VALID-001…008 | M2-T13 |
| RULE-001…005 | M2-T14 |
| DEDUP-002…004 | M2-T15 |
| OPS-007 | M2-T16 |
| PUB-001, PUB-002, PUB-004…008, OPPTY-003, OPPTY-004, OPPTY-009, OPPTY-010 | M2-T17 |
| PUB-003, PUB-009, PUB-010 | M2-T18 (+ student UI states in M3-T3) |
| MON-001, MON-003…007 | M2-T19 |
| CUR-001…008, ADMIN-001, ADMIN-002, OPPTY-002 | M2-T20 |
| OPS-008, COST-004 | M2-T21 |
| ADMIN-004 | M2-T1 |
| ELIG-003, RULE-006 | M3-T3 |
| ELIG-006, DISC-002…004 | M3-T1, M3-T2 |
| PROFILE-002…004, PROFILE-006 | M3-T3, M3-T4 |
| SAVE-001/002, APP-001…004, APP-006/007 | M3-T5, M3-T6 |
| NOTIF-001, AUTH-002, AUTH-003 | M4-T1, M4-T2 |
| AUTH-005, AUTH-006 | M4-T4 |
| NOTIF-002…004 | M4-T3, M4-T5 |

---

## M. Automated opportunity intelligence

### M.1 Today versus proposed
| Capability | Today | Proposed (rev. 3) |
| --- | --- | --- |
| How opportunities enter the database | by hand in `backend/scripts/seed_demo.py` (973 lines, 14 opportunities) | scheduled pipeline from approved official sources (plan §O) |
| Source records | `sources` rows per opportunity; `content_hash` and `raw_snapshot` columns exist but are unused | registry of acquisition sources + stored, hashed text snapshots; `sources` stays as the citation link |
| Evidence | verbatim quotes typed by the curator | quotes proposed by an extractor and **verified by string match against the stored snapshot** |
| Eligibility rules | written by the curator | structured only with deterministic parser agreement; otherwise kept as quoted `unparsed` text |
| Publication | the seed sets `published` | per-source rollout (`off → shadow → listing_only → full`) and A/B/C gates |
| Recurring programmes | not modelled (a closed cycle is a `closed` row) | programmes with one opportunity row per cycle |
| Monitoring | none | scheduled re-fetch, snapshot diff, fail-closed change handling |
| Curator role | data entry | exception handling and source approval |

**Nothing in this section exists in the code yet.**

### M.2 Product principles for automation
1. **AI proposes, deterministic code decides.**
   - A model may extract text and propose fields and rules.
   - It never decides whether an opportunity is genuine or whether a student qualifies.
   - Model confidence is never a publication criterion.
2. **Listing and eligibility are separate.**
   - An opportunity may be listed while its rules are not assessed.
   - In that case no verdict is shown at all, so no student is told "Eligible" or "Not eligible" on
     incomplete rules.
3. **Discovered ≠ verified.** Secondary sources (aggregators, newsletters, search results, community tips)
   only produce leads. Every published claim cites an approved official source.
4. **Fail closed.** If safety can't be established, nothing is published, and existing listings move to the
   safer state.
5. **Human effort goes to sources and exceptions.** A person approves each source once, sets how far its
   automation may go, and handles flagged items.
6. **Automation is measured, not promised.** No automation percentage is claimed. Yield and accuracy metrics
   (§M.9) decide how far each source is trusted.

### M.3 What a student sees
| Publication | Listing | Eligibility area |
| --- | --- | --- |
| Level A (automatic, full) | shown, labelled "Collected automatically from <official page> on <date>; not reviewed by a person" | verdict computed; quoted conditions the engine can't check are listed as "Not checked automatically" |
| Level B (automatic, listing only) | shown with the same label | "Eligibility not yet assessed; check the official page". **No verdict.** |
| Curator-reviewed | "Reviewed by the Opportunity Hub team on <date>" | as Level A |
| Under re-check after a source change | shown | "Eligibility is being re-checked"; no verdict until resolved |
| Level C / unavailable | not listed (an unavailable page is readable by link with a notice) | — |

### M.4 Requirements

Classes: **R1** = first automated release · **R2** = post-MVP · **F** = future.

#### Sources (SOURCE)
| ID | Requirement | Value | Pri / class | Acceptance criteria | Deps |
| --- | --- | --- | --- | --- | --- |
| SOURCE-001 | Registry of acquisition sources with name, domain and allowed hosts, category, authority level, discovery method, connector config, crawl policy, provider identity, terms/robots status, health and lifecycle status | one place to manage trust | P0 / R1 | all fields stored and validated; per-connector config schema | ADMIN-003 |
| SOURCE-002 | Lifecycle `proposed → testing → approved → paused → retired` | controlled growth | P0 / R1 | approval requires a passing test run and a recorded terms review; transitions audited | SOURCE-001 |
| SOURCE-003 | Authority levels: only `official` sources can be cited for published claims; `secondary`/`community` produce leads only | trust | P0 / R1 | a claim citing a non-official source fails publication (test) | — |
| SOURCE-004 | Per-source `publish_mode` (`off`, `shadow`, `listing_only`, `full`), admin-only, audited | gradual, reversible automation | P0 / R1 | changing mode needs admin permission; `off`/`shadow` stop publication immediately | AUTH-007 |
| SOURCE-005 | Automatic pause after N consecutive failures (configurable) | protects data quality | P1 / R1 | — | INGEST-006 |
| SOURCE-006 | Compliance: robots.txt (RFC 9309), recorded terms review, rate limits, identifying user agent; no CAPTCHA, login, paywall or anti-bot bypass; no JavaScript execution | lawful, polite crawling | P0 / R1 | robots disallow → no fetch (test); no headless browser in the dependency tree | — |
| SOURCE-007 | First connectors: sitemap, RSS/Atom, HTML index with configured link patterns, URL list; new connectors without pipeline changes | extensibility | P0 / R1 | adding a connector touches only its own module and config schema | INGEST-001 |
| SOURCE-008 | Lead-only connectors for aggregators/newsletters, after legal review per source | coverage | P2 / R2 | leads never publish; official URL resolution required | SOURCE-003 |
| SOURCE-009 | Search-API discovery | coverage | P3 / F | evaluated on cost and terms first | — |

#### Ingestion (INGEST)
| ID | Requirement | Value | Pri / class | Acceptance criteria | Deps |
| --- | --- | --- | --- | --- | --- |
| INGEST-001 | Scheduled discovery producing candidates from approved sources | no manual searching | P0 / R1 | — | SOURCE-007 |
| INGEST-002 | Safe fetching: allow-listed hosts only; SSRF protections (plan §O.13); redirect re-validation; size, time and type caps | security | P0 / R1 | the SSRF test suite passes | — |
| INGEST-003 | Politeness: per-host concurrency 1, minimum delay, backoff, `Retry-After` honoured | good citizenship | P0 / R1 | — | — |
| INGEST-004 | Canonical URLs, content fingerprints, stored text snapshots | change detection, evidence | P0 / R1 | identical content creates no new snapshot | — |
| INGEST-005 | Snapshot retention: referenced snapshots kept; unreferenced pruned after a configurable period | storage control | P1 / R1 | — | — |
| INGEST-006 | Idempotent, resumable runs: unique keys, leases, advisory locks, retry with backoff, run records | reliability | P0 / R1 | rerun = same state; two workers never share an item | — |
| INGEST-007 | Curator-submitted URL (approved hosts only) enters the same pipeline | manual path keeps the evidence standard | P1 / R1 | unapproved host → source proposal, no fetch | SOURCE-002 |
| INGEST-008 | PDF ingestion with sandboxed parsing and caps | coverage (many calls are PDFs) | P2 / R2 | — | INGEST-002 |

#### Extraction (EXTRACT)
| ID | Requirement | Value | Pri / class | Acceptance criteria | Deps |
| --- | --- | --- | --- | --- | --- |
| EXTRACT-001 | Deterministic content isolation and relevance filtering before any model call | cost, focus | P0 / R1 | irrelevant pages skipped and counted | INGEST-004 |
| EXTRACT-002 | Provider-independent extractor interface with a versioned output schema | no lock-in | P0 / R1 | the provider is swappable by configuration | DEC-22 |
| EXTRACT-003 | General fields (title, provider, description, category, location, eligible countries/regions, funding/benefits, application and info URLs, deadline + time zone, duration, study level, cycle) | complete listings | P0 / R1 | — | — |
| EXTRACT-004 | Eligibility statements (citizenship, enrolment, degree, field, GPA + scale, age/DOB, skills, experience, language, other), each with a verbatim quote and an explicit/unclear mandatory marker | rule input | P0 / R1 | — | — |
| EXTRACT-005 | Field status: explicit, not found, ambiguous, conflicting or inferred; inferred values never shown as official | honesty | P0 / R1 | a UI test shows no inferred value outside the curator view | — |
| EXTRACT-006 | Provenance per extraction: snapshot (gives URL and retrieval time), extractor/schema/prompt/model versions, timestamps, usage | auditability | P0 / R1 | — | — |
| EXTRACT-007 | Untrusted-input boundary: no tools, no browsing, no secrets; page text as data; schema-constrained output; output URLs only as leads | safety | P0 / R1 | prompt-injection fixtures cause no side effects | — |

#### Validation (VALID)
| ID | Requirement | Pri / class | Acceptance criteria |
| --- | --- | --- | --- |
| VALID-001 | Quote verification: every displayed claim's quote occurs in the stored snapshot; the stored quote is the snapshot substring | P0 / R1 | a fabricated quote is rejected (test) |
| VALID-002 | Dates normalised with explicit time zones or the date-only convention; ambiguous numeric dates flagged | P0 / R1 | fixture table |
| VALID-003 | Countries (ISO 3166-1) and currencies (ISO 4217) via curated dictionaries; regions expanded only with curated lists | P0 / R1 | unmapped stays unmapped |
| VALID-004 | Degree levels and categories via synonym tables; GPA only with explicit scale; no conversion | P0 / R1 | — |
| VALID-005 | Required fields, types, URLs and date order | P0 / R1 | — |
| VALID-006 | Provider/source consistency | P0 / R1 | mismatch → not Level A/B |
| VALID-007 | Contradiction detection (deadlines, cycles, citizenship across official pages) | P0 / R1 | — |
| VALID-008 | Completeness tracked separately from correctness | P1 / R1 | both reported per record |

#### Eligibility rule generation (RULE)
| ID | Requirement | Pri / class | Acceptance criteria |
| --- | --- | --- | --- |
| RULE-001 | Structured rules only in shapes the capability registry supports (engine v2) | P0 / R1 | registry validation on every rule |
| RULE-002 | Acceptance requires quote verification **and** an identical rule from a deterministic parser for that family | P0 / R1 | disagreement → `unparsed` (test) |
| RULE-003 | Unsupported or uncertain statements stored as `unparsed` with the quote and a reason; never dropped | P0 / R1 | coverage check: 0 dropped statements |
| RULE-004 | Mandatory/optional only when the wording is explicit (DEC-25) | P0 / R1 | — |
| RULE-005 | Every requirement records origin (seed, extracted or curator), review status and evaluation support | P0 / R1 | — |
| RULE-006 | UI never shows a requirement as checked unless the engine evaluated it (extends ELIG-003) | P0 / R1 | test |
| RULE-007 | Parsers for further families (field of study, language tests) as the engine gains support | P2 / R2 | — |

#### Duplicates and cycles (DEDUP)
| ID | Requirement | Pri / class | Acceptance criteria |
| --- | --- | --- | --- |
| DEDUP-001 | Programmes (recurring) and cycles (opportunity rows) are modelled separately (OPPTY-011) | P0 / R1 | — |
| DEDUP-002 | Re-ingesting the same page updates the same cycle | P0 / R1 | — |
| DEDUP-003 | A new year or intake becomes a new cycle of the same programme | P0 / R1 | — |
| DEDUP-004 | Ambiguous matches go to the curator, never auto-merged | P0 / R1 | — |

#### Publication (PUB)
| ID | Requirement | Pri / class | Acceptance criteria |
| --- | --- | --- | --- |
| PUB-001 | Critical gates G1–G9 (plan §O.8.2); any failure → not public | P0 / R1 | one test per gate; a gate error counts as failure |
| PUB-002 | Level A requires eligibility gates E1–E3 and `publish_mode=full` | P0 / R1 | — |
| PUB-003 | Level B publishes the listing with "eligibility not yet assessed" and **no verdict** | P0 / R1 | no verdict API result for `not_assessed` cycles (test) |
| PUB-004 | A listing is never treated as open just because the page is reachable (currency gate) | P0 / R1 | — |
| PUB-005 | Model confidence is not used by any gate | P0 / R1 | test |
| PUB-006 | Decision records: level, gate results, policy/validator/extraction versions, method, actor, override reason | P0 / R1 | append-only |
| PUB-007 | Curator overrides need a reason and are audited and visible in history | P0 / R1 | — |
| PUB-008 | Shadow mode: decisions recorded without publishing; promotion per source on founder-set criteria (DEC-24) | P0 / R1 | — |
| PUB-009 | Publication is one transaction (cycle, citations, ruleset version, decision, stale marks) | P0 / R1 | an injected failure leaves no partial rows |
| PUB-010 | Student-facing disclosure of publication method (§M.3) | P0 / R1 | — |

#### Monitoring (MON)
| ID | Requirement | Pri / class | Acceptance criteria |
| --- | --- | --- | --- |
| MON-001 | Configurable monitoring policies (active near deadline, active, rolling, closed watch, index) | P0 / R1 | changeable without a deploy |
| MON-002 | Snapshot comparison and field-level change classification | P0 / R1 | — |
| MON-003 | A later deadline with a verified quote is applied and audited | P1 / R1 | — |
| MON-004 | An earlier deadline or a closed/cancelled statement is applied immediately (the safe direction) | P0 / R1 | — |
| MON-005 | Eligibility text change → ruleset `under_review`, verdicts suppressed, new version staged through the gates, old version and evidence preserved, matches stale | P0 / R1 | — |
| MON-006 | Missing page past the confirmation window → `unavailable`, hidden from discovery | P0 / R1 | — |
| MON-007 | New cycle detection on programme pages | P1 / R1 | — |
| MON-008 | Notify savers of changes (with NOTIF-006) | P2 / R2 | — |

#### Curator exceptions (CUR)
| ID | Requirement | Pri / class |
| --- | --- | --- |
| CUR-001 | Queues by reason: review needed, extraction failures, source proposals, source health, conflicts, possible duplicates, Level B awaiting assessment, rulesets under review, monitoring failures | P0 / R1 |
| CUR-002 | Evidence view: snapshot text with quotes highlighted in context, field statuses, gate results | P0 / R1 |
| CUR-003 | Approve or reject candidates; promote B → A | P0 / R1 |
| CUR-004 | Correct a field (recorded as curator origin; gates re-run) | P0 / R1 |
| CUR-005 | Override a decision with a mandatory reason | P0 / R1 |
| CUR-006 | Reprocess a candidate; pause or disable a source | P0 / R1 |
| CUR-007 | Review and accept ruleset changes | P0 / R1 |
| CUR-008 | Spot-check queue of recent automatic publications | P1 / R1 |

#### Cost (COST) and ingestion security (SEC-ING)
| ID | Requirement | Pri / class |
| --- | --- | --- |
| COST-001 | Deterministic extraction first; model only for relevant pages that need it | P0 / R1 |
| COST-002 | Extraction cached per snapshot and version (never paid twice) | P0 / R1 |
| COST-003 | Hard daily and monthly spend caps; alert at 80% (DEC-23) | P0 / R1 |
| COST-004 | Cost per run, per source and per published opportunity reported | P1 / R1 |
| SEC-ING-001 | Fetch only approved hosts; block private, loopback, link-local, metadata, CGNAT and reserved addresses | P0 / R1 |
| SEC-ING-002 | DNS pinning against rebinding; every redirect re-validated | P0 / R1 |
| SEC-ING-003 | Size, decompression, time and content-type limits; HTML never rendered or served | P0 / R1 |
| SEC-ING-004 | User-submitted URLs never trigger fetching on unapproved hosts | P0 / R1 |
| SEC-ING-005 | Model receives no tools, no secrets and no network; outputs schema-validated | P0 / R1 |
| SEC-ING-006 | API keys only in the host secret store; never logged | P0 / R1 |
| SEC-ING-007 | `publish_mode` changes, overrides and approvals are permission-checked and audited | P0 / R1 |

#### Operations (OPS)
| ID | Requirement | Pri / class |
| --- | --- | --- |
| OPS-007 | Gold evaluation set (the 14 seeded opportunities plus newly labelled pages, DEC-26) and a shadow evaluation harness | P0 / R1 |
| OPS-008 | Pipeline dashboard: runs, states, failures, source health, spend vs caps, quality metrics | P1 / R1 |

### M.5 Non-functional requirements for automation
| Area | Requirement (targets are proposed and unvalidated) |
| --- | --- |
| Data accuracy | measured on the gold set and through error reports. **False structured rules** (structured rule ≠ gold) is the headline metric, and the founder sets the acceptable level before any source reaches `full` (DEC-24) |
| Provenance | 100% of displayed claims quote-verified or deterministically derived (enforced by gate G9, not a target) |
| Freshness | monitored per policy; share of published cycles checked within their policy window is reported; past-deadline cycles closed within one day of the deadline (daily job) |
| Reliability | runs resumable; a failed run never alters published data; source failures isolated per source |
| Security | §M.4 SEC-ING; ingestion code reviewed against plan §O.13 before the first live source |
| Cost control | hard caps; cost per published opportunity reported |
| Auditability | every automated publication reproducible from decision → extraction → snapshot |

### M.6 First automated release (R1) versus later
- **R1:**
  - a few approved official sources, proposed from the 14 existing opportunities' providers;
  - sitemap/feed/index/URL-list connectors and the safe fetcher;
  - text snapshots, one extraction provider, quote verification;
  - parsers for the six rule families the engine evaluates;
  - A/B/C gates, shadow mode then per-source promotion;
  - monitoring with fail-closed changes;
  - the curator exception queue and the cost caps.
- **R2:** PDFs; lead-only aggregator connectors; more rule families as the engine grows; change
  notifications to savers; better duplicate matching.
- **F:** search APIs, partner feeds, institution self-service submission.

### M.7 Guard for the student product
Pipeline work must not block M3 (student experience). It shares only the cycle/version schema (M2-T3) and
engine v2 (M2-T4). If the pipeline slips, students keep seeing curated and seeded data exactly as today.

### M.8 Journeys
- **J-INT-1 Automatic publication:**
  1. The `discover` job finds a new call on an approved university source.
  2. The page is fetched and snapshotted, found relevant and extracted.
  3. Quotes are verified, two of three rules are accepted by parser agreement, and the third is kept as
     `unparsed`.
  4. All gates pass and the source is `full`, so the listing goes live as Level A.
  5. A student sees a verdict with one "Not checked automatically" item.
- **J-INT-2 Exception:** a page shows two different deadlines. G5 fails, the candidate is quarantined, and
  the curator sees both quotes in context, corrects the deadline citing the right sentence, and the gates
  re-run.
- **J-INT-3 Change:** the monitor sees changed eligibility text. The cycle becomes "being re-checked" and
  verdicts are hidden. The new ruleset passes the gates and is published as version 2, and students' matches
  re-evaluate.

### M.9 Pipeline metrics
| Metric | Definition | Why |
| --- | --- | --- |
| Yield per source | published cycles / relevant candidates | how much automation actually delivers |
| Level mix | share A / B / C / curator | where human effort goes |
| Quote-verification rate | verified quotes / proposed quotes | extractor honesty |
| Rule acceptance rate | accepted structured rules / proposed | engine coverage of real data |
| False structured rules | structured rules contradicting gold or later corrected | the most important accuracy signal |
| Curator minutes per published cycle | measured from action timestamps | the automation goal, measured |
| Freshness compliance | cycles checked within policy window / published | currency |
| Time to unpublish | detection of a closed or missing page → hidden | safety |
| Cost per published cycle | LLM + jobs spend / published cycles | budget |
