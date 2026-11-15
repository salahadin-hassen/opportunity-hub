# Adversarial review of the P0 security hardening (2026-11-14)

> **Status note (added later the same day):** this review describes the branch *before* revision 2.
> R-1, R-2, R-4, R-6, R-9, R-10, R-11 and R-13 have since been addressed, and R-5 partly. See the risk
> register in `P0_SECURITY_HARDENING_2026-11-14.md`. The findings below are kept unchanged as the
> record a fresh reviewer should check revision 2 against.

| | |
|---|---|
| Subject | Uncommitted changes in worktree `~/projects/opportunity-hub-p0`, branch `fix/p0-security-hardening`, against `06eb905` (22 tracked files, +451/−159, plus 5 new files) |
| Reviewer | **Not independent.** This review was done in the same Claude Code session that wrote the changes. Every claim below was re-checked against the code and, where marked, reproduced with probes. A fresh reviewer (human or a separate agent) should still review before merge |
| Method | Code reading. Throwaway probe scripts kept outside the repo, run against the local isolated test cluster (port 5433) inside rolled-back transactions or self-cleaning fixtures. Re-runs of the test suite and migrations |
| Boundaries kept | No repository code changed. Nothing committed or pushed. No production, Render, Cloudflare or Neon access. No secrets printed |

## Verdict: **NOT READY**

The three original defects are fixed in code and the claimed test results reproduce. However, two code-level gaps undermine the guarantees the change set claims:

1. **P0-3 is still bypassable after publication.** A complete opportunity can be published, then PATCHed to remove its official URL, and it stays public (**R-1**).
2. **P0-1 now rests entirely on a setting that can be silently absent.** If `AUTH_RATE_LIMIT_PER_MINUTE` is missing, production disables *every* credential limit, and startup validation does not require it (**R-2**).

Both fixes are small (about half a day including tests). Once they are fixed, along with the rotation defect and the report corrections (R-4, R-10), the branch would be **READY FOR PR WITH DOCUMENTED ACCEPTED RISKS**. The main accepted risk is that no per-address limit exists until a trustworthy client identity is proven on the live infrastructure (**R-3**).

---

## Findings

Severity reflects impact after this change set, for an MVP with real student accounts.

### R-1 — High — Published opportunities can be edited back into an incomplete state (code)
- **Where:**
  - `backend/app/api/routers/opportunities.py:53-60` (PATCH route)
  - `backend/app/services/opportunities.py:115-132` (`update_opportunity` applies any schema field with `setattr`)
  - `backend/app/schemas/opportunity.py` (`OpportunityUpdate.official_url` accepts `null`)
- **Evidence (reproduced):** probe `probe_publication.py` (case B) publishes a complete record, then sends `PATCH {"official_url": null, "title": "Changed after publish"}`. Result: **200**, status still `published`, `official_url` is `None`, and the public `GET /opportunities/{id}` returns **200**.
- **Why insufficient:** the task required that "no alternate API route … bypasses the validation". Validation runs only at the moment of publishing; nothing keeps a published record valid afterwards. Curators already hold publish permission, so this is an integrity bypass, not privilege escalation. It still defeats the product's trust guarantee.
- **Fix:**
  - Edits to a `PUBLISHED` record must either re-run `publication_problems` and reject the edit (409, audited), or move the record back to `DRAFT`, which the publish step would then re-check.
  - Apply the same rule to future source/requirement edit endpoints.
  - Add regression tests for nulling the official URL and for edits that leave the record incomplete.

### R-2 — High — The only remaining login limit is optional and fails open (code)
- **Where:**
  - `backend/app/core/config.py:39` (`AUTH_RATE_LIMIT_PER_MINUTE: int | None = None`)
  - `backend/app/core/rate_limit.py:185-188` (`_enforce` returns immediately when unset)
  - No production validator requires the value (validators at `config.py:123,135,164,183`)
- **Evidence:** code reading; the same "unset disables the limit" behaviour is documented in the module docstring (`rate_limit.py:22`). `render.yaml` sets `"10"`, but only a Blueprint sync applies it. A dashboard-managed service without the variable runs with no account budget and no address budget.
- **Why insufficient:** with `CLIENT_IP_STRATEGY=none`, the per-account budget is the only control on login, registration and reset requests. A missing environment variable silently removes it.
- **Fix:** in production, refuse to start unless `AUTH_RATE_LIMIT_PER_MINUTE` is a positive integer (mirroring the `JWT_SECRET` check), and add a test. Optionally log the effective limit and strategy once at startup, without addresses.

### R-3 — High (accepted risk; depends on infrastructure) — No per-address limit: spraying, credential stuffing, registration floods and Argon2 saturation
- **Where:**
  - `render.yaml` (`CLIENT_IP_STRATEGY: none` on the API)
  - `backend/app/core/rate_limit.py:215` (early return under `none`)
- **Evidence:** the per-account budget limits attempts *per email*:
  - **Spraying** (one guess per account) and **credential stuffing** (one breached pair per account) are not slowed at all.
  - **Registration** can create unlimited accounts at up to 10 per minute per email. Those accounts can then drive known-email logins, each costing Argon2 work, until the capacity guard returns 503 to everyone. This is a login-availability DoS.
  - Before this change the address budget existed but was forgeable, so **this is not a regression**. It is the honest state.
- **Why insufficient:** the deployment has no proven trustworthy client identity. `render_cf_connecting_ip` rests on Render/Cloudflare statements that have not been verified on this service (`RENDER_CLIENT_IP_VERIFICATION.md` §3). The implementation report states this correctly.
- **Fix:**
  - Founder authorises the §5 black-box check. Only if it passes, switch to `render_cf_connecting_ip`.
  - Independently of the IP question, consider server-wide controls that don't need client identity: a global failed-login rate alarm, CAPTCHA or proof-of-work after N site-wide failures, or a registration throttle tied to email verification.

### R-4 — Medium — Rotating `JWT_SECRET` makes the worker send broken reset links and mark them sent (code; report claim is false)
- **Where:**
  - `backend/app/services/email_tokens.py:30-31` (key derived from `JWT_SECRET`)
  - `backend/app/services/email_tokens.py:87-97` (`deliverable_token` rebuilds the token without checking it against `token_hash`)
  - Docstring at `email_tokens.py:5-6`
  - Implementation report, "Other remaining risks"
- **Evidence (reproduced):** probe `probe_rotation_and_race.py`. A token is issued, then `JWT_SECRET` changes before delivery. Result: `deliverable_token` returns a token, and `hash_token(token) == row.token_hash` is **False**. The worker would mail a dead link and mark the row `sent`. The report's claim that such emails are "cancelled, not mis-sent" is wrong.
- **Second effect:** tokens already delivered remain valid after rotation, because validation compares the stored hash and does not involve the key. Rotation therefore does **not** revoke outstanding reset links, contrary to the docstring.
- **Fix:**
  - In `deliverable_token`, return `None` (so the email is cancelled) unless `hmac.compare_digest(hash_token(derived), row.token_hash)`.
  - Document that rotation cancels undelivered emails but does not revoke delivered links (or revoke all unused tokens as part of the rotation procedure).
  - Add a test for both behaviours.
  - Consider a dedicated `EMAIL_TOKEN_SECRET`, so a token-key rotation doesn't force a session/JWT rotation and vice versa (see R-11).

### R-5 — Medium — Publication evidence is not bound to the opportunity (code; not reachable through the API today)
- **Where:** `backend/app/services/opportunities.py:139-160` (`publication_problems`)
- **Evidence (reproduced):** probe `probe_publication.py` (case A) publishes successfully (**200**) when:
  - the only quoted rule cites a `Source` that belongs to **another opportunity**;
  - the opportunity's own source is an **unrelated host** (`totally-unrelated.example.com`) of type `manual_entry`;
  - the official URL is a third host.
- **Checks that are missing:**
  - The quoted requirement's `source_id` belongs to this opportunity.
  - That source is the primary or official one, or on the official URL's host.
  - The quote appears in the stored snapshot (`raw_snapshot`).
- The error text says "verified source", but there is no verification state on `Source`.
- **Why it matters now:** no API endpoint creates sources or requirements today; only the seed script and the database do. So this is not externally exploitable yet. It will be the first hole once the P1 evidence editor ships.
- **Fix:**
  - Require that every quoted mandatory requirement's `source_id` points at a source of the same opportunity.
  - Require at least one source on the official URL's registrable domain, or flagged `is_primary` and set by a curator.
  - Make the message match what is actually checked.
  - Enforce the same-opportunity link in the database (composite FK or trigger), so future endpoints can't bypass it.

### R-6 — Medium — No cooldown on reset requests: inbox flooding and cost (code)
- **Where:** `backend/app/api/routers/auth.py:215-245`, where every accepted request mints a token and queues an email (`dedupe_key=f"reset:{email_token.id}"` at line 241, unique per request).
- **Evidence:** code reading. The only limit is the shared 10-per-minute account budget, so with `CLIENT_IP_STRATEGY=none` one sender can trigger about 14,400 reset emails a day to any registered address. That harasses users, burns provider quota and damages sender reputation.
- **Fix:**
  - At most one live, undelivered reset email per user; reuse or skip within a cooldown window such as 5–15 minutes, returning the same 200.
  - Add a daily cap per user.
  - Test that repeated requests do not grow the outbox.

### R-7 — Medium (founder decision) — Targeted login lockout is free
- **Where:** `backend/app/core/rate_limit.py:232` (account budget counts *all* attempts); `docs/architecture/ACCOUNT_LOCKOUT_THREAT_MODEL.md` §2.
- **Evidence:** existing tests (`test_lockout_a_stranger_without_the_password_locks_the_owner_out_for_the_window`). Eleven requests a minute, with no password and from anywhere, keep a known user locked out indefinitely. Removing the address budget changes nothing here, because it was forgeable before.
- **Assessment:** this is acceptable only as a recorded founder decision. The "device cookie" option in the threat model (§3, option 5) is the documented path to fix it.

### R-8 — Medium (deployment) — Scheduled jobs: branch skew, paid plan, unpinned Python, failing-by-design worker
- **Where:** `render.yaml`:
  - lines 81/83 and 123/125: `plan: starter`, `branch: ci/m1-m2-foundation`, while the web services deploy `feat/opportunity-hub-product` (lines 13, 52);
  - `PYTHON_VERSION` is set only on the API (line 25).
- **Evidence:**
  - **Branch skew:** the crons would run release code against a production database whose schema may predate `3a14e912b77c` (no `email_outbox` table), while the API runs older code.
  - **Python:** without `PYTHON_VERSION` the crons build with Render's default Python rather than the CI-tested 3.12.7.
  - **Worker:** `EMAIL_DELIVERY: disabled` makes the email worker exit 2 every two minutes on a paid plan. That is correct behaviour, but noisy and costly.
  - **Unverified wiring:** the new `JWT_SECRET` `fromService` reference to a `generateValue` variable is plausible per Render's Blueprint documentation, but not verified on the account.
  - **Undetected mismatch:** nothing detects `EMAIL_DELIVERY` differing between the API (`smtp` → users told "instructions sent") and the worker (`disabled` → nothing sent).
- **Fix (config plus founder decision):**
  - Don't create, or suspend, both crons until the release is merged to the production branch, the migration has run and SMTP is configured.
  - Set `branch:` to the production branch and add `PYTHON_VERSION: 3.12.7`.
  - Add a deploy-runbook check that `EMAIL_DELIVERY` matches on the API and the worker.

### R-9 — Medium (test/CI integrity) — End-to-end coverage is not in CI and did not exercise the security paths
- **Evidence:**
  - `.github/workflows/ci.yml` frontend job runs `npm ci`, typecheck, `npm test` and build only (lines 217-227); there are 0 Playwright references.
  - The reported 26/26 Playwright run was local, with `AUTH_RATE_LIMIT_PER_MINUTE` **unset**, so the limiter was off. It used an admin account and profile created by hand: the spec says "created in test setup", but no setup script exists. No end-to-end test covers password reset, because there is no UI.
  - The admin journey does exercise draft creation without `status`, the publish rejection message and close/republish through the real `get_db`.
- **Missing unit tests for new behaviour:**
  - secret rotation (R-4);
  - concurrent token consumption (the probe shows exactly 1 of 2 concurrent attempts succeeds, but no committed test proves it);
  - post-publish edits (R-1);
  - evidence linkage (R-5);
  - a required rate-limit setting (R-2);
  - the `none` strategy emitting no `client_identity_degraded` telemetry;
  - real `get_db` commit of `opportunity.publish_rejected`.
- **Fix:** add a CI job that starts Postgres, migrates, seeds, creates the admin fixture with a committed script, runs the API with a limit configured, and runs Playwright. Add the unit tests above.

### R-10 — Low — Implementation report inaccuracies
1. The rotation claim (see R-4) is wrong.
2. "Verified source" overstates the check (see R-5).
3. The report doesn't mention that `AUTH_RATE_LIMIT_PER_MINUTE` is now load-bearing (see R-2).
4. It doesn't mention that the end-to-end run had the limiter disabled.

Correct the report before it's used as PR text.

### R-11 — Low — Reset-token key is derived from `JWT_SECRET`
- **Where:** `backend/app/services/email_tokens.py:30-31`
- **Assessment:**
  - **Domain separation:** sound. The key is HMAC(JWT_SECRET, `"email-token-v1"`), and each token is HMAC over purpose and a uuid4 row id, giving 256 bits of output. Tokens are unpredictable and bound to one row, which binds them to one user and one purpose.
  - **Entropy:** production requires at least 32 characters (`config.py:123`). That is a length check, not an entropy check, but Render's `generateValue` provides a random value.
  - **Exposure:** a database leak alone yields no token. A `JWT_SECRET` leak plus database read access lets an attacker rebuild pending tokens, but that secret already lets them forge access tokens, so this adds no new capability.
- **Fix (optional):** a dedicated `EMAIL_TOKEN_SECRET` for independent rotation (see R-4).

### R-12 — Low — Case-variant duplicate accounts (pre-existing)
- **Where:**
  - `backend/app/models/user.py:30` (`unique=True`, case-sensitive)
  - `backend/app/services/users.py:66` (login uses exact match)
  - `backend/app/api/routers/auth.py:231` (forgot-password uses `lower(email)` and `db.scalar`, which picks an arbitrary row if two match)
- **Evidence:** `EmailStr` keeps local-part case, so `Victim@x` and `victim@x` can be two accounts. They share one limiter key (`email.strip().lower()`), so either can lock out the other, and a reset request may target either one. Probe of eight email variants: every variant that can authenticate as the victim maps to the victim's limiter key, so **there is no limiter bypass**.
- **Fix:** add a unique index on `lower(email)` (migration, with a data check first) and use case-insensitive lookups throughout.

### R-13 — Low — Audit gaps on refused lifecycle changes
- A close refused with 409 is not audited.
- PATCH or create with lifecycle fields is refused by validation (422) before the handler runs, so it is not audited either.
- Successful publish, rejected publish and close *are* audited correctly; a probe confirmed the rejection row records `{"status": "draft"}` and the reason.
- **Fix:** audit the close 409. Optionally log a counter for 422s on lifecycle fields.

### R-14 — Low — Internal `published_at` override on `publish_opportunity`
- **Where:** `backend/app/services/opportunities.py:174`
- **Assessment:** only `scripts/seed_demo.py` passes it, and no API exposes it. It still allows backdating through an internal call. Keep it, but make it a keyword reserved for seeding, or have the seed script set the timestamp after publishing, and document it.

---

## Claims verified

| Claim | Result | How |
|---|---|---|
| Account limit runs before Argon2 | **True** | `auth.py:117` `limit_account_attempts` precedes `authenticate_user` at `:119`; the router dependency `auth.py:59` runs before the handler |
| Email variants can't evade the account key | **True** | 8-variant probe (case, whitespace, domain case, Unicode lookalikes, NFD): all variants that authenticate share the key |
| Shared across workers and instances | **True** | Postgres `rate_limit_buckets`, upsert per hit (`rate_limit.py:53-61`) |
| Fails closed when the store is down | **True** | `rate_limit.py:191` → 503; existing test |
| `none` validated at startup | **True** | `config.py` validator plus `test_client_ip_hardening.py`; `peer` refused on Render in production |
| Every Python Render service has the strategy and `JWT_SECRET` | **True in `render.yaml`** | `test_render_yaml_settings_boot_in_production_on_render` parses the file; live dashboard state unknown |
| Raw token never stored or logged | **True** for outbox, token table and app logs | `test_the_raw_token_is_never_stored_or_logged` plus code reading. The worker logs id, template and exception type only. Request bodies are not access-logged. Reset links use a URL fragment |
| Single use under concurrency | **True** | Probe: 2 concurrent attempts → exactly 1 success (`FOR UPDATE` re-check) |
| Disabled delivery doesn't reveal accounts | **True** | Identical 503 body and status for known and unknown emails; no rows written (test) |
| SMTP failures, timeouts and restarts | **Acceptable** | 10-second socket timeout, retries with backoff, max 5 attempts, type-only `last_error`. A restart mid-batch re-sends: at-least-once delivery, same valid token |
| No alternate create or publish path | **True for create and publish; false for post-publish edits (R-1)** | PUT and DELETE return 405; no bulk or CLI writer of `status`; seed goes through `publish_opportunity` |
| Failed publish leaves no partial state | **True** | Savepoint plus test asserting status and `published_at` unchanged |
| 1,211 backend tests | see Test results | |
| 26 Playwright tests | Plausible, not re-run here; see R-9 for what they don't cover | |

## Test results (this review)

| Check | Result |
|---|---|
| Full backend suite (local isolated test DB) | **1211 passed**, 0 failed (205 s): matches the report |
| Fresh disposable DB: `alembic upgrade head` → `check` → `downgrade base` → `upgrade head` | Clean; head `3a14e912b77c`; "No new upgrade operations detected" |
| `seed_demo` on that fresh DB, run twice | 14 created / 12 listed, then 0 created / 14 refreshed: reproducible and idempotent through the validated publish path |
| Probe: secret rotation before delivery | **Defect**: a non-working token is produced and would be marked sent (R-4) |
| Probe: 2 concurrent consumptions of one token | 1 success, as intended |
| Probe: cross-opportunity or unrelated evidence | **Publishes** (R-5) |
| Probe: post-publish PATCH `official_url=null` | **Stays public** (R-1) |
| Probe: PUT / DELETE on curator opportunity route | 405 / 405 |
| Probe: 8 email variants vs. limiter key | No bypass |
| Playwright | Not re-run in this review; not in CI (R-9) |

## Code fixes vs. infrastructure and founder decisions

**Code (needed before PR):** R-1, R-2, R-4, plus the R-10 report corrections. Recommended in the same PR: R-6 and the R-9 unit tests.

**Code (before the evidence editor ships):** R-5. **Later:** R-12, R-13, R-14.

**Infrastructure and founder decisions:**
- R-3: the client-IP black-box check and whether to switch strategy.
- R-7: the lockout policy.
- R-8: cron creation or suspension, branch, plan and Python version; SMTP provider; `EMAIL_DELIVERY` parity between API and worker.
- Confirming `AUTH_RATE_LIMIT_PER_MINUTE` is set on the live API, until R-2 is enforced in code.

## Reproduction

The probe scripts live outside the repository, in the session scratchpad (`probes/probe_rotation_and_race.py`, `probes/probe_publication.py`). Run them from `backend/` with the test database configured. They roll back or delete everything they create.
