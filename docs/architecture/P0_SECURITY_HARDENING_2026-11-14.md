# P0 security hardening — implementation report (2026-11-14, revision 3)

| | |
|---|---|
| Branch | `fix/p0-security-hardening` (worktree `~/projects/opportunity-hub-p0`); HEAD `06eb905`, all work uncommitted |
| State | Not committed, pushed, merged or deployed. No production, Render, Cloudflare or Neon change |
| Revision 2 | Addresses review `INDEPENDENT_P0_SECURITY_REVIEW_2026-11-14.md`: R-1, R-2, R-4 fixed; R-6, R-9 implemented; R-13 fixed; R-5 partly addressed; earlier inaccuracies corrected (see "Corrections") |
| Revision 3 | Fixes F-3, F-4, F-6, F-7, F-8 and F-9 from `FRESH_SECURITY_REVIEW_2026-11-14.md`; F-1 handled in code plus an operator procedure; F-2 accepted. Deployment steps are in `P0_SECURITY_DEPLOYMENT_RUNBOOK.md` (see "Revision 3") |
| Revision 4 | Pre-PR corrections from `FINAL_PRE_PR_REVIEW_2026-11-14.md`: RC-1 (the F-6 guard now validates the effective libpq destination), RC-2 (F-9 evidence corrected; `e2e.sh` now also stops Chromium, which Playwright starts in its own session, and checks IPv6 loopback), RC-3 (runbook §3 for Render's free plan), publish endpoint wording, and two tests that failed under CI's job-level `APP_ENV` |
| Verdict | **PARTIALLY COMPLETE**: every code-level P0 item is fixed and tested, but credential protection still has no per-address component because no trustworthy client identity is proven on the live infrastructure (R-3) |

## Revision 3: fresh-review cleanup

| Finding | Fix | Where | Tests |
|---|---|---|---|
| **F-3** Reset-queue ceiling not atomic (15 queued against 10) | Count and insert run under a transaction-scoped Postgres advisory lock (`pg_advisory_xact_lock`), taken only after the per-account checks pass. Lock order is always user row, then queue lock | `services/password_reset.py` | `test_twenty_concurrent_requests_cannot_exceed_a_ceiling_of_ten`: 20 accounts, 20 threads, committed rows; exactly 10 queued, 10 refused |
| **F-4** `APP_ENV` brittle; cookie `Secure` used a different comparison | `APP_ENV` is stripped and lower-cased. `dev` and `prod` are aliases. Anything other than `development`, `test` or `production` (e.g. `staging`) is refused. On Render (`RENDER=true`) it must be set explicitly. The cookie uses `settings.is_production` | `core/config.py`, `api/routers/auth.py` | Whitespace, case, aliases, unknown and blank values, missing off and on Render; malformed production values can no longer allow `disabled`/`memory`; the cookie is `Secure` exactly when production |
| **F-6** E2E guard checked the name only | `throwaway_database_problems` validates the *effective* destination: the parameters SQLAlchemy's psycopg2 dialect passes to libpq, as libpq parses them (URL query parameters override the URL's host and path, after percent-decoding). PostgreSQL via psycopg2 only; URL query parameters allow-listed (`sslmode`, `connect_timeout`, `application_name`, or `host=<one socket directory>` when the URL has no host), so `host`, `hostaddr`, `port`, `dbname`, `service`, `servicefile`, `options`, encoded names and repeated parameters are refused; effective host loopback or one socket directory; effective name contains an `e2e`/`test` word; `PGHOSTADDR`/`PGSERVICE` in the environment refused; not production. No override. `scripts/e2e.sh` runs `seed_e2e_fixtures --check-only` before migrating. *Revision 4:* the revision 3 version checked only the apparent host and path and could be redirected by query parameters (final pre-PR review RC-1) | `scripts/seed_e2e_fixtures.py`, `scripts/e2e.sh` | 7 accepted targets (incl. the GitHub Actions service and harmless parameters); 10 unsafe targets and 20 redirecting URLs refused (incl. `?host=db.neon.tech`, `%68ost=`, `hostaddr`, `port`, `dbname`, `service`, repeated and multi-host values); both environment variables; production refusal; the script refuses before touching a database |
| **F-7** Production-mode subprocess test could read a developer's `backend/.env` | New `APP_ENV_FILE` setting names the dotenv file (empty disables it). The test sets `APP_ENV_FILE=""` | `core/config.py`, `tests/test_credential_limit_required.py` | A subprocess shows a named file is honoured and an empty value gives the true default (10) |
| **F-8** Stale wording | `render.yaml` worker comment now says `JWT_SECRET` keys sessions and rate-limit digests, not email tokens. The curator button reads **"Check & publish"**, with a tooltip saying what is checked and that sources are not verified. The header no longer says "verified opportunity drafts" | `render.yaml`, `frontend/src/routes/Curate.tsx`, `frontend/e2e/release_candidate.spec.ts` | Playwright admin journey |
| **F-9** `e2e.sh` left Vite running | API, Vite and Playwright each run in their own session (`setsid`). On exit, test failure, INT or TERM, every process group gets TERM, then KILL. The script then fails if any process remains in those groups (`pgrep -g`; Chromium runs in Playwright's group) or if its ports still accept connections on IPv4 **or IPv6** loopback (revision 4; revision 3 probed IPv4 only), and refuses to start if they are already taken | `scripts/e2e.sh` | Four-scenario check below |
| **F-1** Legacy raw-token rows | The worker **never sends** a row whose `params` has `token` without `token_id`: it is cancelled and the token stripped. `python -m app.cli legacy-email-outbox` reports metadata only; `--cancel --yes` cancels pending legacy rows and strips tokens from every legacy row | `services/email_worker.py`, `cli.py`; procedure in the runbook §3 | Never sent, report has no token material, cancel and scrub (incl. historical `sent` rows), confirmation required, new messages are never legacy |
| **F-2** Duplicate email after a crash | **Accepted** at-least-once behaviour; documented (runbook §4) | — | Existing `test_email_worker_at_least_once_delivery_semantics_on_crash` |

**Also changed while verifying:**
- **Race in the first F-9 rewrite (my bug, found by running it).** `wait_for` probed the process group before the child had run `setsid`, so one run aborted with "API exited early". Liveness now checks the process itself, and signalling falls back to the PID.
- **Playwright flake.** `register()` waited only the 5-second default for the onboarding URL. It failed once under load, while the registration itself had succeeded (201) in about 1.2 s and the follow-up login took about 2.3 s. It is now 15 s, like the spec's other waits. The spec passed 12/12 on `--repeat-each=3`.
- **Older worker tests.** Two tests (retry/backoff, at-least-once) queued legacy-format messages. They now queue current-format messages backed by live token rows, so they still test retries rather than F-1 cancellation.

### Revision 3 results
All runs used the isolated local cluster (`scripts/dev-db.sh`, port 5433) and throwaway databases on it. GitHub Actions has **not** run.

| Check | Result |
|---|---|
| Full backend suite | **1336 passed, 0 failed** (220 s): revision 2's 1296, plus 40 in `test_review_cleanup.py`. No other test was added or removed; the two worker tests were adapted, not added |
| Focused, revision 3 | `test_review_cleanup.py` 40 passed. With the adjusted revision 1/2 files (`test_credential_limit_required.py`, `test_email_delivery_safety.py`, `test_client_ip_hardening.py`, `test_production_features.py`, `test_password_reset_requests.py`, `test_email_token_rotation.py`) all passed |
| Playwright via `scripts/e2e.sh` (CI entry point) | **26 passed** (2.7 min) with `AUTH_RATE_LIMIT_PER_MINUTE=10`, `CLIENT_IP_STRATEGY=none`; release-candidate spec 12/12 on `--repeat-each=3`. One earlier run had 1 failure, the `register()` timing flake above, before the wait was aligned |
| **E2E process cleanup (F-9), revision 3 run** | Exits 0, 1, 143 (0.4 s after SIGTERM) and 130 (0.3 s after SIGINT); ports 8000 and 5173 free on IPv4 (valid here: `localhost` resolves to `127.0.0.1` on this machine); no Vite or uvicorn process left. **Corrected wording (revision 4):** the exit-1 case was a Playwright filter that matched no tests (`Error: No tests found`), not a failing assertion; that run's process check did not look for Playwright or Chromium. Superseded by the revision 4 run below |
| Alembic on a fresh throwaway DB | single head `3a14e912b77c`; `check` clean before and after `downgrade base` → `upgrade head`; no migration in this change set |
| Clean-DB seeds | `seed_demo` 14 created / 12 listed, then 0 created / 14 refreshed; `seed_e2e_fixtures` OK; `legacy-email-outbox` reports none |
| Frontend | `tsc -b` 0 errors; Vitest 10 passed; build OK; `schema.d.ts` identical to a fresh generation from the app's OpenAPI |

### Revision 4 results
All runs used a throwaway PostgreSQL 16 cluster created for this round in a temporary directory (TCP port 55432, deleted afterwards), **not** the project's dev cluster on 5433. GitHub Actions has not run before the PR.

| Check | Result |
|---|---|
| Full backend suite, with CI's `backend-tests` environment (`APP_ENV=development` and the CI `JWT_SECRET` set job-wide) | **1362 passed, 0 failed** (199 s): revision 3's 1336 plus 26 new guard tests. A first focused run found that `test_missing_app_env_is_refused_on_render` failed when `APP_ENV` is set in the environment, as CI sets it; both missing-`APP_ENV` tests now remove the variable |
| F-6 guard (RC-1) | 7 accepted targets; 10 unsafe and 20 redirecting URLs refused, incl. `?host=db.neon.tech`, `?%68ost=…`, `?hostaddr=…`, `?port=…`, `?dbname=…`, `?d%62name=…`, `?service=…`, `?servicefile=…`, `?options=…`, repeated `host`/`sslmode`, `host=/tmp,remote`, `localhost,remote` and a non-psycopg2 driver; `PGHOSTADDR`/`PGSERVICE` refused; the e2e script accepted the throwaway target in every run below |
| Playwright via `scripts/e2e.sh` | **26 passed** (2.8 min), limiter on |
| **E2E process cleanup (F-9)**, final `e2e.sh` | A driver tracked every process started under the script by ancestry and session, and checked listeners with `ss` on all addresses. **Normal completion:** exit 0. **Real test failure** (`e2e/smoke.spec.ts --timeout=300`, 1 failed on the timeout): exit 1. **SIGTERM** mid-test: exit 143, 6.3 s after the signal. **SIGINT** mid-test: exit 130, 7.4 s after. Chromium was running during every scenario; afterwards, in every scenario, no tracked process (27–56 per run, across 4 sessions), no `ms-playwright` process and no listener on 8000 or 5173 remained. Exits after a signal take longer than revision 3 (0.3–0.6 s) because the script now waits up to 5 s for every descendant before KILL |
| Frontend | `tsc -b` 0 errors; Vitest 10 passed; build OK; `schema.d.ts` regenerated from the app's OpenAPI (only change: the publish endpoint description) |
| Hygiene | `git diff --check` clean (including untracked files); `bash -n scripts/e2e.sh`; `py_compile` on changed Python. The project configures no Python linter or formatter, and shellcheck is not installed |

## Corrections to revision 1

1. **Key rotation (was wrong).** Revision 1 said rotating `JWT_SECRET` cancels queued reset emails "rather than mis-sending" them. In fact the worker rebuilt a token that no longer matched the stored hash, mailed a dead link and marked it sent. Delivered links also stayed valid after rotation. Both behaviours are now defined, implemented and tested; see "Key rotation".
2. **"Verified source" (overstated).** Nothing verifies a source. Publication checks are *structural completeness* checks:
   - an official http(s) URL;
   - a source *record* with an http(s) URL, belonging to the opportunity;
   - rules with verbatim quotes;
   - and, new in revision 2, each mandatory rule citing one of the opportunity's own source records.

   No check proves a source is official, that its host matches the official URL, or that a quote appears on the page (R-5). Messages no longer say "verified".
3. **The revision 1 Playwright run had the per-account credential limiter disabled**: it ran with `AUTH_RATE_LIMIT_PER_MINUTE` unset, which then meant "off". It also used an admin account created by hand. Both are fixed: the limiter is now on in E2E runs and the admin account comes from a committed fixture script (R-9).
4. **The account limit was optional.** Revision 1 didn't state that the per-account budget, the only remaining credential limit, could be silently switched off by a missing variable (R-2, now fixed).

## Test results (this revision)

All runs used the project's isolated local cluster (`scripts/dev-db.sh`, port 5433) and throwaway databases on it.

| Check | Result |
|---|---|
| Full backend suite | **1296 passed, 0 failed** (265 s). Revision 1 had 1211; 85 tests added |
| Focused, revision 2 | `test_public_opportunity_edits.py` 19, `test_credential_limit_required.py` 38, `test_email_token_rotation.py` 18, `test_password_reset_requests.py` 9: all passed |
| Focused, revision 1 (still passing) | `test_publication_guard.py`, `test_email_delivery_safety.py` (now 24), `test_client_ip_hardening.py` |
| Playwright via `scripts/e2e.sh` (the CI entry point), fresh `opportunity_hub_e2e` database | **26 passed** (4.4 min), with `AUTH_RATE_LIMIT_PER_MINUTE=10` and `CLIENT_IP_STRATEGY=none` |
| Limiter active during E2E | `rate_limit_buckets` held 13 login and 8 registration account counters; 0 responses were 429; API log contains no passwords or tokens |
| Alembic on a fresh throwaway DB | single head `3a14e912b77c`; `check` clean before and after `downgrade base` → `upgrade head`; no migration in this change set |
| Seeds on a clean DB | `seed_demo` 14 created / 12 listed, then 0 created / 14 refreshed; `seed_e2e_fixtures` idempotent; refuses the non-test database `opportunity_hub` |
| Frontend | `tsc -b` clean; Vitest 10 passed; production build OK; `schema.d.ts` regenerated from the app's OpenAPI |
| GitHub Actions | **Not run**: nothing was pushed. The new `e2e` job runs the same `scripts/e2e.sh` that passed locally; its first real run happens on the PR |

---

## R-1 — published opportunities can't be edited into an incomplete state

**Fix:**
- `update_opportunity` (`backend/app/services/opportunities.py`) locks the row `FOR UPDATE` with its sources and rules, applies the edit inside a savepoint, then calls `assert_still_publishable`.
- For any **publicly visible** status (`published` or `closed`; closed is readable too), `publication_problems` must still pass, or the whole edit is rolled back and `OpportunityWouldBecomeIncompleteError` is raised.
- The PATCH route returns **409** and records `opportunity.update_rejected` (changed fields, status, reason). The error is returned rather than raised, so the audit row commits.
- Drafts may be incomplete while being edited.

**Fields affecting validity:**
- Through the API: `official_url` and `title`.
- Through the record's relations (no API yet): sources, rules, quotes and citations.
- Every edit of a public record re-runs the full check, so a record that became incomplete by other means cannot be edited further until restored (tested).
- Explicit `null` on NOT NULL columns (`title`, `opportunity_type`, `deadline_type`, `location_mode`, `countries`, `languages`, `tags`) and a blank title are now 422, instead of reaching the database.

**Other routes:**
- No PUT or DELETE (405).
- Create forces a draft; publish and close have their own validated operations.
- No bulk, CLI or import path writes opportunities. The seed script goes through `publish_opportunity`.
- Any future source or rule endpoint must call `assert_still_publishable`.

**Also:** a refused close (409) is now audited as `opportunity.close_rejected` (review R-13).

**Tests (`test_public_opportunity_edits.py`):**
- the `PATCH {"official_url": null}` reproduction: 409, unchanged, still publicly served, rejection audited;
- multi-field atomicity;
- closed records;
- allowed complete edits;
- drafts;
- eight null/blank cases on both public and draft records;
- evidence removed outside the API;
- the service-level rollback.

## R-2 — the credential limit is mandatory

**Fix (`backend/app/core/config.py`):**
- `AUTH_RATE_LIMIT_PER_MINUTE: int | "disabled" = 10`.
- Values must be integers from 1 to 1000; zero, negative, non-numeric, blank and out-of-range values are refused in every environment.
- `disabled` is accepted only outside production and must be written explicitly. The test suite sets it in `conftest.py`, and tests that exercise the limiter set their own budget.
- All readers use `settings.auth_rate_limit`.
- The store-unavailable behaviour is unchanged: 503, fail closed.

**Tests (`test_credential_limit_required.py`):**
- the configuration matrix;
- a real **production-mode** uvicorn (`RENDER=true`, `CLIENT_IP_STRATEGY=none`, variable unset) answers `[401]*10 + [429, 429]` for one account, even with rotating forged `X-Forwarded-For`;
- production processes with `0`, `-1`, `abc`, empty or `disabled` exit before serving.

This gives **no per-address protection** (R-3).

## R-4 — reset-token keys and rotation

**Fix (`backend/app/services/email_tokens.py`):**
- A dedicated `EMAIL_TOKEN_KEYS` (`id:secret[,id:secret…]`, each secret at least 32 characters) and `EMAIL_TOKEN_ACTIVE_KEY`, independent of `JWT_SECRET`. Validated at startup, and required whenever `EMAIL_DELIVERY` is not `disabled`.
- Token = HMAC(key, purpose:token_row_id). The database stores `sha256(token)` and the outbox stores `{"token_id", "key_id"}`; never the token.
- The worker rebuilds the link with the recorded key version and sends only if it matches the stored hash (constant-time comparison). Otherwise the email is **cancelled, never sent with a dead link**.
- New CLI commands:
  - `python -m app.cli email-token-key-usage`: key versions still needed by live pending emails;
  - `python -m app.cli revoke-reset-tokens --yes`: invalidate every outstanding reset link.

**Already-delivered links:** validation compares hashes and never uses the key, so **rotation does not affect delivered links**. They stay valid until they are used or expire (1 hour). To kill them (for example after a mailbox, log or database compromise), run `revoke-reset-tokens --yes`.

**Tests (`test_email_token_rotation.py`):**
- the five-step sequence: queue under A → rotate to B (A kept) → process → link works; then the delivered link follows expiry, not the key;
- new requests use B;
- a removed key cancels its queued email;
- a changed secret under the same id cancels;
- key-usage reporting;
- revoke, and the revoke confirmation;
- six malformed-configuration cases;
- independence from `JWT_SECRET`;
- **concurrent consumption** of one token by four committed sessions: exactly one succeeds.

### Key rotation procedure
1. Generate a secret, e.g. `openssl rand -base64 48`, and choose a new id, e.g. `k2`.
2. On the API, set `EMAIL_TOKEN_KEYS=k2:<new>,k1:<old>` and `EMAIL_TOKEN_ACTIVE_KEY=k2`. The worker reads both from the API via `render.yaml` `fromService`; if it is configured separately, set the same values there. Deploy the API and worker together.
3. Wait until `python -m app.cli email-token-key-usage` (run on the worker or a one-off shell) no longer lists `k1`. This takes at most 1 hour, the token lifetime.
4. Remove `k1` from `EMAIL_TOKEN_KEYS` and deploy. A `k1` email still queued at that point is cancelled, never sent broken.
5. If the reason for rotating is a suspected compromise, also run `python -m app.cli revoke-reset-tokens --yes`.

## R-6 — reset-request flooding

**Fix (`backend/app/services/password_reset.py`):**
- Per account, under a row lock on the user:
  - **cooldown** `PASSWORD_RESET_COOLDOWN_SECONDS` (default 900): no new email while one issued within the window exists;
  - **daily cap** `PASSWORD_RESET_DAILY_LIMIT` (default 5 per rolling 24 h).
- Per deployment: **queue ceiling** `PASSWORD_RESET_MAX_PENDING` (default 1000 pending reset emails).
- The outbox `dedupe_key` is per account per cooldown window, as a second guard against duplicates.
- Same 200 body for new, throttled, unknown and inactive accounts; with delivery disabled, the same 503 for everyone and nothing written.
- None of this depends on client IP.

**User experience under abuse:** an attacker submitting a victim's address triggers at most one email per 15 minutes and 5 per day. The victim's link from that email stays valid for its full hour, so a victim who then asks for a reset already has a working link (tested). The worst case is a victim who has used or lost all 5 daily links and must wait.

**Tests (`test_password_reset_requests.py` and `test_email_token_rotation.py`):**
- normal reset;
- repeated requests;
- identical answers;
- cooldown expiry;
- daily cap and rolling recovery;
- full queue;
- the attacker/victim scenario;
- disabled delivery;
- case variants;
- **five concurrent committed requests → one email, one token**.

## R-9 — Playwright in CI

- `.github/workflows/ci.yml` has a new `e2e` job:
  - Postgres 16 service with throwaway database `opportunity_hub_e2e`;
  - the same pinned Python and Node setup as the other jobs, plus `npx playwright install --with-deps chromium`;
  - runs `scripts/e2e.sh`;
  - uploads traces and logs **only on failure**, kept 7 days. They contain only CI test accounts, and email is disabled, so no reset tokens exist.
- `scripts/e2e.sh`:
  - refuses database names without `e2e` or `test`;
  - migrates, then runs `seed_demo` and `seed_e2e_fixtures`;
  - starts the API with `AUTH_RATE_LIMIT_PER_MINUTE=10`, `CLIENT_IP_STRATEGY=none` and `EMAIL_DELIVERY=disabled`, then Vite, then Playwright.
- `backend/scripts/seed_e2e_fixtures.py` creates the admin account and profile idempotently. It refuses production and non-test database names. The password comes from `E2E_ADMIN_PASSWORD`, defaulting to the spec's test-only value.
- `release_candidate.spec.ts` reads the admin credentials from the same constant and expects the corrected "source record" message.

---

## Files changed (against `06eb905`)

**Backend app:**
- `api/routers/auth.py`
- `api/routers/opportunities.py`
- `cli.py`
- `core/auth_telemetry.py`
- `core/client_ip.py`
- `core/config.py`
- `core/rate_limit.py`
- `schemas/opportunity.py`
- `services/email_worker.py`
- `services/opportunities.py`
- new: `services/email_tokens.py`, `services/password_reset.py`

**Revision 3 additions and changes** (on top of the lists below):
- Backend app: `api/routers/auth.py` (cookie flag), `cli.py` (`legacy-email-outbox`), `core/config.py` (`APP_ENV`, `APP_ENV_FILE`), `services/email_worker.py` (legacy cancel and report), `services/password_reset.py` (advisory lock)
- Backend scripts: `scripts/seed_e2e_fixtures.py` (host and name guard, `--check-only`)
- Backend tests: new `test_review_cleanup.py`; modified `test_client_ip_hardening.py`, `test_credential_limit_required.py`, `test_email_delivery_safety.py`, `test_production_features.py`
- Frontend: `src/routes/Curate.tsx`, `e2e/release_candidate.spec.ts`
- Repository: `scripts/e2e.sh`, `render.yaml`
- Docs: new `docs/architecture/P0_SECURITY_DEPLOYMENT_RUNBOOK.md`; this report; `FRESH_SECURITY_REVIEW_2026-11-14.md` (the reviewer's report, unchanged by me)

**Backend scripts:**
- `seed_demo.py`
- new: `seed_e2e_fixtures.py`

**Backend tests:**
- Modified: `conftest.py`, `test_curator_opportunities.py`, `test_match_models.py`, `test_matches.py`, `test_opportunity_api.py`, `test_opportunity_models.py`, `test_password_hash_capacity.py`, `test_production_features.py`, `test_public_api.py`
- New: `test_client_ip_hardening.py`, `test_credential_limit_required.py`, `test_email_delivery_safety.py`, `test_email_token_rotation.py`, `test_password_reset_requests.py`, `test_public_opportunity_edits.py`, `test_publication_guard.py`

**Frontend:**
- `e2e/release_candidate.spec.ts`
- `src/api/schema.d.ts` (regenerated)
- `src/routes/Curate.tsx`

**Repository:**
- `.github/workflows/ci.yml`
- `.gitignore` (`frontend/e2e-artifacts/`)
- `render.yaml`
- new: `scripts/e2e.sh`

**Docs:**
- `docs/architecture/RENDER_CLIENT_IP_VERIFICATION.md`
- this report
- `docs/architecture/INDEPENDENT_P0_SECURITY_REVIEW_2026-11-14.md`

## Configuration requirements

| Variable | Where | Value |
|---|---|---|
| `APP_ENV` | API, both crons | `production` (normalised; `prod` alias). Must be set explicitly on Render; unknown values refuse to start |
| `APP_ENV_FILE` | Nowhere in production | Optional path of a dotenv file; empty disables it (tests, `scripts/e2e.sh`) |
| `AUTH_RATE_LIMIT_PER_MINUTE` | API | 1–1000; `render.yaml` sets 10; unset also means 10; never `disabled` in production |
| `CLIENT_IP_STRATEGY` | API, both crons | `none` until the §5 check in `RENDER_CLIENT_IP_VERIFICATION.md` passes |
| `JWT_SECRET` | API (generated); crons via `fromService` | Required by production settings |
| `EMAIL_DELIVERY` | API **and** worker, identical | `disabled` until the provider works, then `smtp` |
| `EMAIL_TOKEN_KEYS`, `EMAIL_TOKEN_ACTIVE_KEY` | API (secret, `sync: false`); worker via `fromService` | Required once delivery is on; see rotation procedure |
| `SMTP_HOST`, `SMTP_FROM`, `SMTP_PORT`, `SMTP_SECURITY` | API and worker | Required for `smtp`; TLS only |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Worker | Set together or not at all |
| `PASSWORD_RESET_COOLDOWN_SECONDS`, `_DAILY_LIMIT`, `_MAX_PENDING` | API | Optional; defaults 900, 5, 1000 |

## Risk register (after revision 3)

| ID | Severity | Status | Owner |
|---|---|---|---|
| R-1 Edits making public records incomplete | High | **Fixed and tested** | — |
| R-2 Optional credential limit | High | **Fixed and tested** | Confirm the live API value after deploy |
| R-3 No per-address limit (spraying, stuffing, registration floods, Argon2 saturation) | High | **Open: depends on infrastructure.** No trustworthy client identity is proven | Founder: authorise the §5 black-box check; consider identity-free controls (global failure alarm, challenge, registration throttle) |
| R-4 Key rotation | Medium | **Fixed and tested**; procedure above | Founder: generate and store keys when enabling email |
| R-5 Evidence not proven official or quoted from the page | Medium | **Partly addressed**: mandatory rules must cite the opportunity's own http(s) source record. Still open: host or official-source matching, snapshot quote check, database-level constraint | Before the evidence editor ships |
| R-6 Reset flooding | Medium | **Fixed and tested** | — |
| R-7 Free targeted login lockout (11 requests a minute) | Medium | **Open: founder decision** (`ACCOUNT_LOCKOUT_THREAT_MODEL.md`) | Founder |
| R-8 Scheduled jobs: release branch, paid plan, no `PYTHON_VERSION`, worker fails every 2 min while email is disabled; `EMAIL_DELIVERY` parity between API and worker | Medium | **Open: founder/config decision**; not changed here | Founder |
| R-9 Playwright not in CI | Medium | **Implemented**; passes locally through the CI script; first Actions run on the PR | — |
| R-10 Report inaccuracies | Low | **Corrected** (above) | — |
| R-11 Token key tied to `JWT_SECRET` | Low | **Fixed** by dedicated keys | — |
| R-12 Case-variant duplicate accounts | Low | Open (pre-existing); reset now targets the oldest active match | Later |
| R-13 Refused close not audited | Low | **Fixed** | — |
| R-14 Internal `published_at` override for seeding | Low | Open, internal only | Later |
| F-1 Legacy raw-token outbox rows | Low | **Fixed in code** (never sent); **operator step before SMTP**: runbook §3 | Founder: run the report and cancel before enabling email |
| F-2 Duplicate email after worker crash | Low | **Accepted** (at-least-once; same valid link) | Revisit when email volume matters |
| F-3 Queue ceiling not atomic | Low | **Fixed and tested** | — |
| F-4 `APP_ENV` normalisation, cookie flag | Low | **Fixed and tested** | Founder: `APP_ENV` must be set explicitly on Render |
| F-5 Invariant in code only, no unpublish | Low | **Open**; must be solved with the evidence editor (R-5) | Before the evidence editor |
| F-6 E2E guard host check | Low | **Fixed and tested** (revision 4: effective libpq destination; query-parameter redirection refused, RC-1) | — |
| F-7 Test read `backend/.env` | Low | **Fixed** | — |
| F-8 Stale wording | Low | **Fixed** | — |
| F-9 E2E process cleanup | Low | **Fixed and verified** (revision 4: four scenarios with Chromium tracked; IPv4 and IPv6 port checks) | — |
| I-1 No `/reset-password` page | Medium | **Open**; blocks enabling email | Before SMTP activation |

## Infrastructure decisions still with the founder
1. Authorise the client-IP black-box check; switch to `render_cf_connecting_ip` only if it passes (R-3).
2. Decide the lockout policy (R-7).
3. Scheduled jobs: don't create them, or suspend them, until the release is merged and migrated and SMTP works. Then align the branch to production, add `PYTHON_VERSION: 3.12.7` and confirm the plan (R-8).
4. Choose an SMTP provider and verify the sending domain. Generate `EMAIL_TOKEN_KEYS`. Set `EMAIL_DELIVERY=smtp` on the API and the worker together.
5. Confirm the live API has `AUTH_RATE_LIMIT_PER_MINUTE` and `CLIENT_IP_STRATEGY` set. A Blueprint sync applies them; otherwise the new release refuses to start and Render keeps the previous deploy.
6. Review, commit, push and open the PR (the first GitHub Actions run of the `e2e` job), then authorise the migration and deploy.
