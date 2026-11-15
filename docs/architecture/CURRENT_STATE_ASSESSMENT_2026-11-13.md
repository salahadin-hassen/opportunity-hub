# Opportunity Hub — Current-State Assessment & Launch Readiness Audit

Date: 2026-11-13 · Auditor: Lead engineer (automated audit session) · Scope: whole repository + read-only external probes

## Verdict: NOT READY

The release candidate `06eb905` is green in CI and well-engineered in many places, but it carries
three confirmed launch blockers (spoofable IP rate limiting, password-reset tokens written to logs
instead of emailed, publication-guard bypass) and a structural data gap: there is no API or UI to
attach sources, quoted evidence or eligibility rules to an opportunity, so curators cannot produce
publishable records without direct database/script access. Production currently serves 12
opportunities.

---

## 1. Executive summary

| Area | State |
|---|---|
| Code quality | High. Typed, layered, audited, extensive tests (CI green). |
| Student journeys | Mostly built against real APIs; password reset / email verification have no UI. |
| Curator workflow | Draft create/edit/publish/close + source registry UI. **No way to add evidence/rules.** |
| Data | 12 published in production, 14 in seed script. Target 2,000. No ingestion wired. |
| Security | Strong primitives (Argon2 capacity guard, CSRF, SSRF-pinned fetcher) undermined by 3 P0s. |
| Deployment | Release not deployed; no PR open; render.yaml mixes branches and paid cron plans. |

Realistic timeline: P0 fixes ≈ 1 working day. A *credible* MVP (evidence tooling + ≥100 verified
opportunities + password reset UI + E2E in CI) ≈ 5–8 working days. 1–2 days is not realistic for the
full MVP without sacrificing data integrity.

---

## 2. Verified repository state

### Verified facts (checked in this session)

| Item | Value |
|---|---|
| Local path / branch | `~/projects/opportunity-hub`, `ci/m1-m2-foundation` |
| HEAD | `06eb905be36d1e8e382b2c84162d156f642a5a41` (= reported RC, **unchanged**) |
| `origin/ci/m1-m2-foundation` | `06eb905…` — pushed and in sync |
| `feat/opportunity-hub-product` (local = origin) | `b8da30f25bc568bbcea9e03043001e1d4d1a2e97` — **not advanced** |
| Commits on release not in production | 11 |
| Working tree | Modified: `docs/DEPLOYMENT.md` (6 lines), `docs/architecture/RELEASE_RUNBOOK_2026-11.md` (+351/−155). Untracked: `docs/architecture/RELEASE_PR_SPECIFICATION.md`. Not committed, not touched by this audit. |
| Stashes | None |
| Pull requests (GitHub API) | Only PR #1 (`feature/ui-dashboard → main`, merged 2026-09-27). **No PR exists for the release branch.** |
| Latest CI | Run `42655261149` on `06eb905`: Backend tests ✅, Frontend checks ✅, Migration checks ✅ (2026-11-09) |
| Alembic | Single head `3a14e912b77c`; 10 revisions |
| Production API (`api.opportunities.sahelyon.com/health`) | 200 `{"status":"ok"}` (via Cloudflare IPs) |
| Production frontend | 200 |
| Published opportunities (public API) | **12**, all with `official_url` |
| `POST /auth/forgot-password` on production | **404** → production is running the pre-release baseline, not the RC |
| `opportunity-hub-api.onrender.com/health` | No response in 60 s (name may carry a suffix, or service asleep) |

### Historical (reported, not re-verified)
- CI `42655261149` "all jobs passed" — confirmed via API.
- Previous staging rehearsal on Neon staging project — not re-run.

### Assumptions
- Production DB is at the revision matching `b8da30f` (inferred from 404 on release-only routes).
- Cloudflare proxies both custom domains (inferred from resolving IPs 104.21.x / 172.67.x).

### Unknowns — need founder/dashboard access
- Render: actual service names, deployed SHA, env vars (`CLIENT_IP_STRATEGY`, `TRUSTED_PROXY_CIDRS`,
  SMTP), auto-deploy setting, whether cron services exist.
- Neon: production `alembic_version`, backup/PITR window, row counts (drafts, closed, evidence).
- Cloudflare: proxy mode, "Overwrite headers"/origin lockdown, WAF rules.
- `gh` CLI is not installed; GitHub data came from the unauthenticated public API.

---

## 3. Test results (this session)

| Check | Result |
|---|---|
| Frontend typecheck (`tsc -b`) | ✅ exit 0 |
| Frontend unit tests (`vitest`) | ✅ 1 file, **10 tests** passed (`src/lib/rules.test.ts`) — very thin |
| Production build (`npm run build`) | ✅ built in 12.7 s; warning: chunk > 500 kB |
| Backend `pytest` | ⚠️ **Not runnable locally**: 1,156 errors, all `Connection refused` on `localhost:5433` (test Postgres not running; no docker on host). Not a code failure. CI run `42655261149` is the evidence of a green backend suite. |
| Alembic heads | ✅ single head `3a14e912b77c` |
| `alembic check` / round-trip | Not run locally (no isolated DB); passed in CI "Migration checks" job |
| Playwright E2E | **Not run** — needs live API + DB. **Not run in CI either** (`.github/workflows/ci.yml` runs only typecheck + build for frontend). 5 specs exist in `frontend/e2e/`. |

To re-run the backend suite locally: start the dev DB (`scripts/dev-db.sh`) on port 5433, then
`cd backend && .venv/bin/pytest -q`.

---

## 4. Product feature matrix (student)

Legend: ✅ implemented & verified (CI tests/real API) · 🟡 implemented, under-tested · 🟠 partial · ❌ missing/broken

| # | Journey | Status | Evidence |
|---|---|---|---|
| 1 | Landing & navigation | 🟡 | `frontend/src/routes/Landing.tsx` (562 lines), `App.tsx:147-161`, `NotFound` route |
| 2 | Registration / login | ✅ | `auth.py:90,109`; httpOnly cookie `auth.py:141-142`; demo login gated on `import.meta.env.DEV` (`AuthContext.tsx:19`) |
| 3 | Profile onboarding | 🟡 | `Onboarding.tsx` → `/me/profile`, education, skills, test-scores endpoints |
| 4 | Profile edit/persistence | 🟡 | `GET,POST,PATCH /me/profile`; `Profile.tsx`; no frontend unit tests |
| 5 | Discovery/browsing | 🟡 | `Discover.tsx`; loads **all** pages client-side (`api/queries.ts:47`) — fine at 12, not at 2,000 |
| 6 | Search/filter/sort | 🟠 | Client-side only (`Discover.tsx:95-97`, sort `:46`); no server search |
| 7 | Detail page | 🟡 | `OpportunityDetail.tsx` |
| 8 | Eligibility & explanation | ✅ | `/me/opportunities/{id}/match`, batch-evaluate; backend evaluator tests; `rules.test.ts` |
| 9 | Saved opportunities | ✅ (RC only) | `/me/saved-opportunities`; **not live in production** |
| 10 | Application tracking | ✅ (RC only) | `/me/applications` CRUD; `Applications.tsx`; not live |
| 11 | Stages, notes, deadlines, items | 🟡 | PATCH notes `Applications.tsx:95-98`, items endpoints; no reminders/notifications |
| 12 | Account/session lifecycle | 🟠 | Sessions list/revoke, deletion request/cancel exist. **Password reset & email verification have no frontend page**; email links to `/reset-password` which hits `NotFound`. Verification email is never enqueued (no `"email_verification"` producer in `app/`). |
| 13 | Logout & expiry | ✅ | `auth.py:149`; 30-min session TTL `auth.py:134` |
| 14 | Responsive/mobile | 🟡 | Tailwind responsive classes; `capture.mjs` screenshot script; no mobile E2E in CI |
| 15 | Empty/loading/error/success | 🟡 | Present in routes inspected (e.g. `Applications.tsx:147`); not systematically tested |

## 5. Curator / admin

| Capability | Status | Evidence |
|---|---|---|
| RBAC | ✅ | `app/core/permissions.py:15-50`; `require_permission` deps |
| Admin provisioning | 🟠 CLI only | `python -m app.cli grant-role` (`cli.py:56,82`). No admin UI/API for roles. |
| Opportunity create/edit | ✅ | `POST /opportunities`, `PATCH /curate/opportunities/{id}` |
| **Sources/evidence/rules on an opportunity** | ❌ | No endpoint creates `Requirement`/source links; only `scripts/seed_demo.py` and `app/intelligence/gold.py` do |
| Draft → publish lifecycle | 🟠 | `publish_opportunity` guard (`services/opportunities.py:131-139`) — **bypassable**, see P0-3 |
| Source registry | ✅ | `/curate/sources` CRUD, terms review, status, publish-mode, history |
| Audit log | ✅ | `audit.record` in same transaction; `GET /admin/audit` |
| Admin UI | 🟠 | `Curate.tsx` (446 lines): opportunities, sources, audit tabs; no rule/evidence editor |

Operations still requiring DB/CLI: role grants, adding evidence/rules/sources to opportunities,
seeding, running migrations, purging accounts.

## 6. Data pipeline

| Item | Value |
|---|---|
| Published in production | 12 (verified via public API) |
| Real opportunities in seed | 14 (`scripts/seed_demo.py`, `OPPORTUNITIES`) + 1 retired slug |
| Unpublished / closed / with quotes / with rules in prod | **Unknown** (no DB access) |
| Source registry | Implemented (`acquisition_source` model, API, UI) |
| Safe fetcher | Implemented: DNS-resolve + pin, `is_global` checks, manual redirect validation (`intelligence/fetcher.py:92-258`) |
| Fetcher used anywhere? | **No** — `fetch_url` has no callers outside `fetcher.py` |
| Candidate discovery / ingestion / refresh | Modules exist (`discovery.py`, `lifecycle.py`, `connectors/`) but **no cron/CLI/API wires them** |
| Duplicate detection | Slug uniqueness only |
| Expiry | Manual `close`; public list filters `PUBLISHED` only (`services/opportunities.py:49`) — past deadlines are not auto-closed |

### Growth strategy (honest)
1. **0 → 100 (week 1–2):** build the evidence/rule editor (P1-1). One curator at ~10 min/record ≈ 15 h.
   Focus on one region/type (e.g. scholarships open to Ethiopian students) to keep it relevant.
2. **100 → 500 (month 1–2):** wire `discovery.py` + safe fetcher into a "candidate inbox" that proposes drafts from
   *approved* registry sources; humans quote evidence and author rules. Add auto-close on deadline and
   a weekly link check.
3. **500 → 1,000:** connectors for structured sources with permissive terms (official APIs/feeds), dedupe on
   normalized host+title, curator throughput metrics, second curator.
4. **1,000 → 2,000:** recurring-cycle cloning (annual programs), stale-record re-verification queue,
   server-side search/pagination (P2-1). Never publish AI-drafted rules without a human-verified quote.

---

## 7. Security assessment

### P0-1 — IP rate limiting is spoofable (CONFIRMED)
- `render.yaml` startCommand: `uvicorn … --proxy-headers --forwarded-allow-ips="*"`.
- Uvicorn `0.54.0` (`backend/constraints.txt`): with `"*"`, `ProxyHeadersMiddleware` sets the ASGI client to
  `x_forwarded_for_hosts[0]` — the **leftmost, client-supplied** entry
  (`.venv/…/uvicorn/middleware/proxy_headers.py:176-177`).
- Rate limiter reads that rewritten value: `app/core/rate_limit.py:177` `peer=request.client.host`.
- Default `CLIENT_IP_STRATEGY="peer"` (`config.py:60`); `render.yaml` sets no strategy.
- Result: an attacker sends `X-Forwarded-For: <random>` per request and gets a fresh bucket → unlimited
  login/registration/reset attempts. There is **no account lockout** (no lockout fields in `app/`).
- `client_ip.py` itself is careful; the defect is the Uvicorn flag in front of it.
- Fix direction (needs proof on staging first): drop `--proxy-headers`/`--forwarded-allow-ips`, then either
  `xff_rightmost` with a verified hop count, or `render_cf_connecting_ip` **only** after proving the origin
  is unreachable except via Cloudflare. Add per-account failed-login throttling independent of IP.
- `create_session` also records `request.client.host` (`auth.py:133`) — spoofable audit data.

### P0-2 — Password-reset tokens logged, emails never sent (CONFIRMED)
- `email_worker.py:121`: `_default_adapter = ConsoleEmailAdapter()`. No code in `app/` constructs the SMTP
  adapter; `cli.py:108-109` calls `process_outbox(db, …)` without an adapter.
- Console adapter logs `text_content[:200]` (`email_worker.py:73-77`); the reset body puts the raw token
  at roughly characters 130–175, inside the logged 200 (`email_worker.py:137-143`). Messages are then marked sent.
- Result in production: users never receive reset emails; valid reset tokens appear in Render logs
  (account takeover for anyone with log access). `SMTP_*` env vars in `render.yaml` are unused.
- Raw token is also persisted in `email_outbox.params` (hash only in `email_token`) — clear it after send.

### P0-3 — Publication guard bypass (CONFIRMED)
- `OpportunityCreate` accepts `status` and `published_at` (`schemas/opportunity.py:40-41`);
  `create_opportunity` does `Opportunity(**payload.model_dump())` (`services/opportunities.py:34`).
- `OpportunityUpdate.status` (`schemas/opportunity.py:73`) is applied via `setattr` in `update_opportunity`.
- Any curator can publish with no verified source, no rule, no quote — the guard at
  `services/opportunities.py:131-139` only runs on `/publish`. Not a privilege escalation (curators hold
  `OPPORTUNITY_PUBLISH`), but it defeats the product's core trust guarantee.

### Other findings
| Area | Assessment |
|---|---|
| Password hashing | ✅ Argon2id defaults (64 MiB, t=3, p=4) with capacity guard (`security.py:25-26`, `config.py:130`) |
| Cookies | ✅ httpOnly, `secure` in production, `SameSite=Lax`. Works for `opportunities.` ↔ `api.opportunities.` (same site); **not** for the `*.onrender.com` fallback origin in CORS (cross-site → cookies dropped). |
| CSRF | ✅ check on cookie-authenticated mutations (`api/deps.py:78-87`) |
| CORS | 🟡 explicit list incl. `opportunity-hub.onrender.com`; remove if not used |
| SSRF | ✅ strong, but currently unused code |
| Audit log | ✅ written in the same transaction as the change |
| Migrations | ✅ single head, CI round-trip; manual "Path A" execution on free plan — operator-dependent |
| Secrets | ✅ `JWT_SECRET generateValue`, `DATABASE_URL sync:false`; no secrets found in tracked config |
| Workers | 🟠 crons on **paid `starter` plan** and on branch **`ci/m1-m2-foundation`** while web services deploy `feat/opportunity-hub-product` — version skew vs. DB schema |
| Monitoring/alerting | ❌ none beyond `/health` and logs |
| Backup/DR | Unknown — depends on Neon plan's PITR window; no restore drill documented as verified |

---

## 8. Deployment readiness (`render.yaml`)

| Item | State |
|---|---|
| API | Python 3.12.7, free plan, Frankfurt, `pip install . -c constraints.txt`, `/health` check |
| Frontend | static, Node 22, SPA rewrite, cache + security headers; `VITE_API_BASE=https://api.opportunities.sahelyon.com` |
| Migrations | No `preDeployCommand`; operator runs `alembic upgrade head` before deploy (free plan) |
| Crons | email worker `*/2 * * * *`, purge `0 3 * * *` — `plan: starter` (costs money), branch mismatch |
| Deploy order | Must be: migrate DB → API → frontend → crons. Additive migrations per runbook. |
| Rollback | Redeploy prior SHA on Render; migrations assumed backward-compatible — not proven for downgrade of data written by new features |
| Auto-deploy | Unknown (dashboard) |

---

## 9. Hidden gaps found
- No TODO/FIXME/`NotImplementedError` markers in `backend/app` or `frontend/src` — but absence of markers hid real gaps:
  - SMTP adapter written, never wired (P0-2).
  - Fetcher, discovery, lifecycle and connectors modules written, never invoked.
  - Email verification endpoint exists, no producer of verification emails, no UI.
  - Reset-password email points to a frontend route that does not exist.
- Frontend unit coverage: 10 tests in one file; E2E not in CI.
- Client-side full-list pagination will not scale.
- No automatic expiry of past-deadline opportunities.

---

## 10. Scores (0–100)

| Area | Score | Why |
|---|---|---|
| Student experience | 62 | Core flows real and persisted; reset/verify UI missing; tracking not deployed |
| Opportunity discovery | 45 | Works for 12 items; client-side only; tiny catalog |
| Eligibility engine | 72 | Typed evaluators, gold-set tests, explanations; depends on rules curators can't yet author |
| Application tracking | 65 | Full CRUD + items/notes in RC; no reminders; not live |
| Curator/admin | 35 | Lifecycle UI exists but no evidence/rule authoring; guard bypass; roles via CLI |
| Data quality | 20 | 12 published records vs. 2,000 target; quality per record looks high |
| Security | 45 | Excellent primitives, three confirmed P0s |
| Reliability | 50 | Transactions/audit good; no monitoring; worker version skew |
| Deployment readiness | 40 | No PR, manual migrations, branch/plan mismatches in blueprint |
| **Overall MVP** | **48** | |

---

## 11. Issue register

### P0 — launch blockers
| ID | Issue | Effort |
|---|---|---|
| P0-1 | Spoofable client IP (uvicorn `*`) + no account-level throttle | 0.5 d code + staging proof |
| P0-2 | Email worker uses console adapter; reset tokens in logs; raw token kept in outbox | 0.5 d |
| P0-3 | `status`/`published_at` writable on create/PATCH → guard bypass | 2 h |
| P0-4 | `render.yaml` crons on release branch + paid plan; must match deployed API and budget | 1 h + founder decision |
| P0-5 | Release has no PR / review; must be merged through a PR before deploy | 1 h |

### P1 — credible MVP
| ID | Issue | Effort |
|---|---|---|
| P1-1 | Curator API + UI for sources, quoted evidence, eligibility rules on an opportunity | 2–3 d |
| P1-2 | Frontend `/reset-password` and `/verify-email` pages; enqueue verification email on register | 0.5 d |
| P1-3 | Reach ≥100 verified published opportunities | ~15–20 curator hours after P1-1 |
| P1-4 | Run Playwright E2E in CI against a service Postgres | 0.5 d |
| P1-5 | Auto-close past-deadline opportunities (cron or query filter) | 2 h |
| P1-6 | Basic monitoring: uptime check on `/health`, error alerting (e.g. Sentry free tier) | 2 h |
| P1-7 | Confirm Neon PITR window + one restore drill to a branch | 1 h founder |

### P2 — post-launch
Server-side search/filter/pagination; admin role-management UI; code-split frontend bundle; deadline
reminder emails; duplicate detection beyond slug; remove `onrender.com` CORS origin.

### P3 — roadmap
Wire discovery + fetcher into a candidate inbox; connectors for structured sources; re-verification
queue; curator throughput analytics; scale to 2,000.

---

## 12. 48-hour plan

**Day 1 (security + deploy hygiene)** — critical path: P0-3 → P0-2 → P0-1 → P0-4 → tests → PR.
1. P0-3 strip `status`/`published_at` from create/update schemas (2 h).
2. P0-2 wire SMTP adapter from settings in production, fail closed if unset, redact body in console adapter, null `params.token` after send (4 h).
3. P0-1 remove `--proxy-headers`; add per-email failed-login throttle; deploy to staging and prove which header Render/Cloudflare sets before choosing a strategy (4 h + founder).
4. P0-4 align cron branches to production branch; decide paid crons vs. none.
5. P1-2 reset/verify pages (parallelizable with 3).

**Day 2 (product)**
6. P1-1 start evidence/rule editor (will not finish in one day).
7. P1-4 Playwright in CI; P1-5 auto-expiry; P1-6 monitoring.
8. Open PR `ci/m1-m2-foundation → feat/opportunity-hub-product`, review, green CI.

**Launch** realistically after P1-1 + P1-3: ~1 more week.

Parallelizable: P1-2, P1-4, P1-5, P1-6 are independent of P0 work. Data entry (P1-3) can start in
parallel via `seed_demo.py`-style reviewed scripts only if each record has a quoted official source.

## 13. Founder actions required
- Render: confirm deployed SHA, env vars, auto-deploy off for the API until migrations run, cron plan budget.
- Render/Cloudflare: confirm whether the origin is reachable bypassing Cloudflare; Cloudflare header settings.
- SMTP provider: create account, set `SMTP_*` on the worker (and API if it sends).
- Neon: confirm PITR window, current `alembic_version`, run a restore-to-branch drill.
- Approve the PR, the production migration, and the deploy — none were done in this audit.

## 14. Not done in this audit (by design)
No deploys, migrations, merges, pushes, DB writes, env/DNS changes, or code fixes. The uncommitted doc
edits in the working tree were left untouched.
