# Fresh security review of the P0 hardening change set (2026-11-14)

> **I am a separate review agent. I did not write this code and had no access to the implementer's reasoning.**
> The implementation report (`P0_SECURITY_HARDENING_2026-11-14.md`), the earlier review
> (`INDEPENDENT_P0_SECURITY_REVIEW_2026-11-14.md`), `RENDER_CLIENT_IP_VERIFICATION.md` and
> `ACCOUNT_LOCKOUT_THREAT_MODEL.md` were treated as claims. Every conclusion below comes from code,
> configuration, tests or behaviour I reproduced myself.

| | |
|---|---|
| Worktree / branch | `~/projects/opportunity-hub-p0`, branch `fix/p0-security-hardening`, HEAD `06eb905`; all changes uncommitted |
| Scope | Everything that differs from `06eb905`: 27 modified tracked files and 13 untracked files |
| Environment | My own throwaway PostgreSQL 16 cluster (port 5434, in my scratch directory; stopped and deleted afterwards). Tests and probes ran from a scratch copy of the worktree that had no `backend/.env`. The developer cluster (5433), the system Postgres (5432), the main checkout, production, Render, Cloudflare and Neon were not touched |
| GitHub Actions | **Has not run for this branch.** Nothing here says CI passed |

## Verdict

**READY FOR PR WITH DOCUMENTED ACCEPTED RISKS**

No code issue blocks the PR. Every P0 code fix (R-1, R-2, R-4, R-6) does what the report says. I
reproduced that behaviour against a live server or with committed transactions, not only through the
suite's rolled-back sessions. The backend suite (1,296), frontend checks and the Playwright suite (26)
reproduce. The findings below are Low code issues to fix soon, residual risks that must be accepted
explicitly, and infrastructure preconditions. None of them is a reason to stop the PR from being opened.
Several of them **are** reasons not to turn on email delivery or the scheduled jobs yet (see §4).

---

## 1. Change set (Step 1)

- `git status --short` matched the implementation report's file list exactly:
  - 27 modified: `.github/workflows/ci.yml`, `.gitignore`, 10 backend app files, `seed_demo.py`, 9 backend test files, `RENDER_CLIENT_IP_VERIFICATION.md`, 3 frontend files, `render.yaml`.
  - 13 untracked: `email_tokens.py`, `password_reset.py`, `seed_e2e_fixtures.py`, 7 new test files, the 2 review/report docs, `scripts/e2e.sh`.
  - Nothing was staged (`git diff --cached` was empty).
- **Completeness.** The report's "Files changed" section lists every one of these 40 files and nothing else.
- **User-owned changes.** None: every change belongs to the hardening work.
- **Secrets.** None entered the change set. I grepped the full diff and all untracked files for credential patterns. The only literal "secrets" are test values:
  - `ci-only-not-a-secret` (the CI Postgres password);
  - the e2e admin default `AdminPass123!`, accepted only by a database whose name contains `e2e` or `test`;
  - a fake SMTP password `hunter2-secret` in a unit test;
  - the test email-token key in `conftest.py`.
- **Executable bit.** `scripts/e2e.sh` is `-rwxrwxr-x`, so `git add` records it as 100755 and the CI step `run: scripts/e2e.sh` can execute it.

## 2. Findings

Severity scale: Critical / High / Medium / Low. **No finding is Critical, High or Medium as a code defect.**
The Medium items are residual or infrastructure risks.

### A. Code issues blocking the PR

**None.**

### B. Code issues to fix (not blocking; Low)

**F-1 (Low): the worker sends legacy queued rows that carry a raw token without checking that the token is still live.**
- **Where:** `backend/app/services/email_worker.py:239-242`.
- **What happens:** rows queued by the base code (`06eb905` stored `params={"token": <raw>}` in `forgot_password`) take the `params.get("token")` branch. That branch never checks the stored hash, `used_at` or `expires_at`.
- **Impact:**
  - If such rows exist in a database the old code wrote to (it is unknown whether any were ever created in production), the first worker run with `EMAIL_DELIVERY=smtp` mails stale, normally expired, links and marks them `sent`. That contradicts the module's "never sent with a dead link" guarantee.
  - The raw tokens also sit in plaintext in `email_outbox.params` until then.
- **Not exploitable:** tokens expire after 1 h and validation is hash-based.
- **Correction:** before enabling email, cancel every pending row that has a `token` key and no `token_id` (a one-off data migration or CLI step). Alternatively, validate the legacy token against `email_tokens.token_hash`, `used_at` and `expires_at` before sending.

**F-2 (Low): the worker can send duplicate emails after a crash or timeout.**
- **Where:** `backend/app/services/email_worker.py:228-275` and `backend/app/cli.py` (`process-outbox` commits once after the whole batch).
- **What happens:** a batch of up to 50 messages (each SMTP send has a 10 s timeout) is sent first and committed once at the end. If the process dies after some sends, those rows stay `pending` and are sent again.
- **Reproduced (probe):** process, roll back as if crashed, process again: **2 emails** to the same recipient. Both carry the same, still-valid link (the token is rebuilt deterministically), so it is not an *incorrect* link.
- **Correction (when email is enabled):** commit per message, or mark the row `sending` and commit before calling SMTP.

**F-3 (Low): the global reset-queue ceiling is not atomic.**
- **Where:** `backend/app/services/password_reset.py:75-82`. The ceiling is a `count(*)` followed by an insert, with no lock across accounts.
- **Reproduced (probe):** `PASSWORD_RESET_MAX_PENDING=10`, 40 accounts, 20 threads: **15 pending rows**.
- **Impact:** the overshoot is bounded by concurrent request capacity (DB pool and workers), so it is a soft ceiling. That is acceptable for its purpose; the report and module docs should call it approximate.

**F-4 (Low): `APP_ENV` matching is brittle.**
- **Where:** `backend/app/core/config.py:271-272`. `is_production` lower-cases `APP_ENV` but does not strip it.
- **Reproduced:** with `APP_ENV=" production"`, settings accept `AUTH_RATE_LIMIT_PER_MINUTE=disabled` and `EMAIL_DELIVERY=memory`.
- **Pre-existing and related:** `backend/app/api/routers/auth.py:143` sets the cookie's `Secure` flag only when `APP_ENV == "production"` exactly, so `APP_ENV=prod` is treated as production elsewhere but gets non-`Secure` cookies.
- **Impact:** low, because `render.yaml` sets the exact literal `production`.
- **Correction:** normalise `APP_ENV` once (strip, lower) and use `settings.is_production` for the cookie flag.

**F-5 (Low): no route can take a published opportunity out of public view, and the publication invariant lives only in application code.**
- **Where:** `backend/app/api/routers/opportunities.py` (only create, patch, publish and close exist; close keeps the record public, `PUBLIC_STATUSES` at `backend/app/services/opportunities.py:18`), and `backend/app/models/requirement.py:60-63` (`source_id` `ON DELETE SET NULL`).
- **Reproduced (live server, committed transactions), probe step 6:**
  - another transaction deleted the only `sources` row and held its commit;
  - meanwhile a PATCH validated against the still-visible source and returned 200;
  - after the commit, the opportunity was **published and served publicly (GET 200)** while `publication_problems` reported two problems.
- **Constraint today:** this needs direct database access, because no API route edits sources or rules (verified: there are no PUT or DELETE routes, and `curate.py` manages `AcquisitionSource`, a different table).
- **Consequences:** it shows that `_locked_with_evidence` locks only the opportunity row, and that nothing in the database enforces the invariant.
- **Recovery gap:** once a public record is incomplete, the only remedy is a database fix, because every further PATCH is refused (409, correct) and there is no unpublish or archive operation.
- **Correction:** add a curator "unpublish/archive" operation. Any future source or rule endpoint (R-5) must lock the parent opportunity row `FOR UPDATE` before changing evidence and then call `assert_still_publishable`.

**F-6 (Low): the e2e fixture guard checks only the database name.**
- **Where:** `backend/scripts/seed_e2e_fixtures.py:36-41` and `scripts/e2e.sh:24-29`.
- **What happens:** the check is on the *name* (a word `e2e` or `test`) and on `APP_ENV`, not on the host. A remote database called, say, `staging_test` would accept a known admin password (`AdminPass123!` by default).
- **Impact:** low, because it needs operator error.
- **Correction (optional):** also require a localhost or socket host unless an explicit `--allow-remote` flag is given.

**F-7 (Low; test hermeticity): one production-mode test inherits `backend/.env`.**
- **Where:** `backend/tests/test_credential_limit_required.py:59-63`.
- **What happens:** the subprocess runs from `backend/` and pops `AUTH_RATE_LIMIT_PER_MINUTE` from the environment. Pydantic then falls back to `backend/.env`, so on a developer machine whose `.env` sets that variable, "unset" is not actually tested.
- **Impact:** none in CI (no `.env`), and it passed in my run, which had no `.env`.
- **Correction:** pass `_env_file=None`-equivalent isolation, for example by running the subprocess from a temporary directory with `PYTHONPATH`.

**F-8 (Low; documentation and labelling):**
- `render.yaml:104` says `JWT_SECRET` "also keys the email-token derivation, so it must match the API's". That is no longer true: email tokens use `EMAIL_TOKEN_KEYS`. `JWT_SECRET` keys only rate-limit digests, which the worker doesn't use.
- `frontend/src/routes/Curate.tsx:320` still labels the button **"Verify & Publish"**, although publication verifies nothing (R-5).

**F-9 (Low; script hygiene): `scripts/e2e.sh` leaves the Vite server running.**
- **Where:** `scripts/e2e.sh:41-45` and `:67-68`. `cleanup` kills the recorded PID, which is the `npx` wrapper, not the `vite` child.
- **Observed:** after my run exited 0, `vite --port 5191` was still listening.
- **Impact:**
  - Harmless on an ephemeral CI runner.
  - Locally it leaves a stray dev server bound to the port, and with `--strictPort` the next run fails to start.
- **Correction:** start Vite with `exec`, or put it in its own process group and kill the group.

### C. Accepted residual risks (need explicit founder acceptance)

**R-3 (High residual): there is no trustworthy per-IP limit.**
- **State:** with `CLIENT_IP_STRATEGY=none` (`render.yaml:44-45`), the code has **no per-address control at all**.
- **What the code controls:**
  - a per-account budget (10 per minute per endpoint scope);
  - the process-wide Argon2 concurrency ceiling (`ARGON2_MAX_CONCURRENCY`, with registration's share);
  - known emails rejected before hashing;
  - over-budget requests do no hashing (`auth.py:93` and `:117` run before `create_user` and `authenticate_user`).
- **What remains open:**
  - **Password spraying and credential stuffing:** one guess per account across many accounts is not limited by anything in code.
  - **Registration floods:** each fresh email has its own budget, so account creation is unbounded except by Argon2 capacity.
  - **Argon2 saturation:** an attacker sending wrong passwords for many *existing* accounts can keep every Argon2 slot busy. Legitimate users then get `503 busy`. CPU and memory are protected, but availability is not.
  - **Other unauthenticated endpoints** (public listing, opportunity detail, reset-password token submission) have no limit in code.
- **Where protection must come from:** only from Render and Cloudflare, and that protection is unproven (`RENDER_CLIENT_IP_VERIFICATION.md` §5 has not been run). **No per-IP solution exists in this change set.**
- **Mitigations to plan:**
  - a global failed-login rate alarm;
  - a registration throttle or challenge;
  - Cloudflare rate-limiting rules, if the zone is proxied.

**R-7 (Medium residual): targeted login lockout.**
- **Where:** `backend/app/core/rate_limit.py:233-239`.
- **What happens:** anyone can send 11 login attempts a minute for a victim's email, without the password. While the attacker continues, the victim's correct-password logins get `429`. Each over-budget attempt costs the server one counter upsert and no Argon2, so it is cheap to sustain.
- **Consequences:** a denial-of-service against named users (for example curators or admins), and support load. It is not account compromise.
- **Assessment:** the 10 per minute burst limit gives 14,400 guesses per account per day, so it is not a strong guessing defence either. For a small public launch with email-only accounts, accepting this is defensible **only together with** monitoring of `account_budget_exhausted` telemetry. The policy should be revisited once a trustworthy client identity exists (for example per-(account, IP) budgets).

**R-6 residual (Medium): account-recovery denial.**
- **Where:** `backend/app/services/password_reset.py:62-73`.
- **Reproduced (probe):** a request every 16 minutes for 24 h gives exactly **5 queued, 85 refused**, and none after the cap within the rolling day.
- **Attack:** with only the victim's email, an attacker can spend the victim's 5 daily reset emails in about an hour. Once the last link expires (1 h each), the victim cannot obtain a new reset link for about 22 hours. The attacker repeats this daily at a cost of 5 requests.
- **What still holds:** the victim always *receives* those 5 emails, and each link stays usable for its hour. The claim that a legitimate user "retains a usable link" is true only inside that window.
- **Other cost:** a cancelled email (for example after its key was removed) still consumes the cooldown and daily quota (probe: `cooldown` after a cancellation).
- **Assessment:** acceptable for launch only together with the R-7 acceptance, and with a support path for manual recovery.
- **Verified working:**
  - Cooldown under concurrency: 20 simultaneous requests for one account, mixing case and whitespace variants, gave **1 token, 1 outbox row, 19 `cooldown`**. The `FOR UPDATE` lock on the user row and the `dedupe_key` work.
  - No account-existence signal: the same 200 body whatever the outcome; the same 503 for everyone when delivery is disabled (`auth.py:223-235`). A timing difference remains between known and unknown accounts (an extra query or insert); it is small and pre-existing.

**R-12 (Low, pre-existing): case-variant duplicate accounts.** Unchanged. The reset flow targets the oldest active match. The account budget lower-cases the email, so variants share one budget and cannot be used to bypass it.

**R-14 (Low): `published_at` override for seeding.** It is used only by the seed script, after `publish_opportunity`'s full validation (`backend/scripts/seed_demo.py:847-852`).

### D. Infrastructure decisions (not code; founder or ops)

**R-8 (Medium): scheduled jobs in `render.yaml`.** **Recommendation:** keep both crons **suspended / not created** until all of the following hold:
1. this release is merged and migrated;
2. a reset page exists in the frontend (I-1 below);
3. an SMTP provider is verified;
4. F-1 is addressed;
5. the branch is aligned and `PYTHON_VERSION` is pinned.

The problems:
- **Branch.** Both crons deploy from `ci/m1-m2-foundation` (`render.yaml:92`, `:144`), while the API and frontend deploy from `feat/opportunity-hub-product` (`:13`, `:61`). The workflow's comment (`.github/workflows/ci.yml:20-21`) says `ci/**` branches are ones "no Render service tracks". That is false if the Blueprint creates the crons: a push to `ci/m1-m2-foundation` would deploy them against the production `DATABASE_URL` (via `fromService`).
- **Plan.** `plan: starter` (`:90`, `:142`) is paid.
- **Python version.** No `PYTHON_VERSION` on either cron, whereas the API pins `3.12.7` (`:25-26`).
- **Failing-by-design worker.** With `EMAIL_DELIVERY=disabled` the worker exits 2 every 2 minutes (`cli.py`, `process-outbox`): 720 failed runs a day, paid, for no purpose.
- **Email settings.**
  - The API needs `SMTP_HOST` and `SMTP_FROM` for `EMAIL_DELIVERY=smtp` (`config.py`, `require_complete_email_delivery_settings`), but the API service in `render.yaml` declares neither.
  - Enabling smtp on the API while the worker is undeployed would queue emails nobody sends. Users would see "instructions sent", and after 1,000 pending rows nothing more would queue.
  - Env-var changes on the API don't redeploy the worker, so `EMAIL_TOKEN_*` rotation needs both services redeployed together, as the procedure already says.
- **Operational necessity.**
  - The email worker is unnecessary while email is disabled.
  - Account purge is needed only once account deletion is live. Account deletion's grace-period purge can wait for a manual `python -m app.cli purge-deleted-accounts` run until the cron is properly configured.

**R-3 / client IP.**
- Authorise the §5 black-box check before switching to `render_cf_connecting_ip`.
- **Deploy precondition:** the live API must receive `CLIENT_IP_STRATEGY=none` (a Blueprint sync). With the variable absent, the default `peer` is now refused on Render in production, and the new release will not start.

**Email enablement.** Choose an SMTP provider, generate `EMAIL_TOKEN_KEYS`, and set `EMAIL_DELIVERY=smtp` on the API and the worker together.

**I-1 (blocks email enablement, not this PR): no password-reset page exists.**
- The reset email links to `https://opportunities.sahelyon.com/reset-password#token=…` (`backend/app/services/email_worker.py:41`, `:171`) and tells users to "paste this token on the reset page".
- The SPA has no `/reset-password` (or forgot-password) route: `frontend/src/app/App.tsx:147-161` falls through to `NotFound`.
- Reset is therefore unusable for real users even once SMTP works. Don't enable delivery before this exists.

### E. Features that must not ship until R-5 is addressed

**What publication validates** (`backend/app/services/opportunities.py:181-218`) is *structural completeness only*:
- a non-blank title;
- an `http(s)` official URL with a host;
- at least one source *record* of this opportunity with an `http(s)` URL;
- at least one rule, and at least one quoted rule;
- every mandatory rule has a non-blank quote **and** cites one of this opportunity's own source records.

**What it does not do.**
- It does **not** prove that a source is official, that its host relates to `official_url`, that a quote appears on the source page, or that a snapshot exists.
- A "source record" association is not authenticity, and a quote string is not verified evidence.
- No database constraint binds `requirements.source_id` to the same opportunity, and `ON DELETE SET NULL` can silently strip citations (F-5).

**Must not ship before R-5 controls exist:**
1. **An evidence/source/rule editor (API or UI).**
   - It must lock the parent opportunity row `FOR UPDATE` and re-run `assert_still_publishable` in the same transaction.
   - It must be audited.
   - It needs a database-level guarantee that a requirement's source belongs to the same opportunity (a composite FK or trigger).
   - Deleting a cited source must be refused (`RESTRICT`) or must re-validate.
2. **Automated ingestion or publishing** (the acquisition-source registry feeding opportunities). It additionally needs:
   - a source verification state (who verified the source, when, and against which snapshot);
   - host or official-domain matching;
   - quote-in-snapshot verification;
   - human approval before anything becomes public.
3. **Any UI or copy that says "verified"** (see F-8, the "Verify & Publish" label).

---

## 3. Verification by area

### R-1: published opportunity integrity (verified)

**Live uvicorn on my `probe_test` database, real `get_db` commits (`probe_r1.py`).**

| Probe | Result |
|---|---|
| `PATCH {"official_url": null}` on a published record (the old bypass) | **409**, row unchanged (`published`, URL intact), public GET still 200, `opportunity.update_rejected` audit row **committed** (read from a separate connection) |
| `{"title": "Changed", "official_url": null}` | 409; the title is **not** changed (atomic) |
| PATCH `status`, PATCH `published_at` | 422, 422 (`extra="forbid"`) |
| PUT, DELETE | 405, 405 |
| `official_url: "ftp://…"` | 422 |
| 20 concurrent PATCHes alternating a null URL and valid URLs | 10 × 200, 10 × 409; final row published with a valid URL |
| Uncommitted out-of-band source delete racing a PATCH | See F-5 (database access only) |

**Code review:**
- `update_opportunity` (`opportunities.py:134-170`) takes `SELECT … FOR UPDATE` with `populate_existing`. It applies the edit inside a savepoint, then calls `assert_still_publishable`, and rolls back on any exception.
- `publish_opportunity` locks and validates the record. `close_opportunity` locks it and allows only `PUBLISHED`.
- PATCH, publish and close therefore serialise on the row, and a PATCH that waited on a publish sees the new status and is validated.
- Create forces `DRAFT` (`opportunities.py:50-53`).
- The seed script goes through `publish_opportunity`.
- I found no other writer of `Opportunity.status` (grep of `app/` and `scripts/`).

### R-2: mandatory authentication limit (verified)

**Configuration matrix** (`Settings(_env_file=None, …)`, `RENDER=true`, strategy `none`):

| Value | production / prod | development |
|---|---|---|
| unset | 10 | 10 |
| `""`, `0`, `-1`, `abc`, `1001`, `1.5`, `+5`, boolean | refused | refused |
| `disabled` / `DISABLED` | refused | `None` (explicit off) |
| `" 10 "` | 10 | 10 |

`peer` is refused in production when `RENDER=true`.

**Placement.** The account budget runs before both the DB lookup and Argon2: `auth.py:93` before `create_user`, `:117` before `authenticate_user`, and `:223` on forgot-password.

**Email normalisation.**
- The key is `email.strip().lower()` of the `EmailStr`-validated value (`rate_limit.py:238-239`).
- The login lookup matches exactly (`users.py:66`), so the key is *coarser* than the lookup: no variant that reaches the same account escapes the budget.

**Store failure.** `RateLimitStoreUnavailable` leads to a 503 (fail closed), at `rate_limit.py:190-198`.

**Tests exercise the limiter.**
- `conftest.py` disables it globally (explicit `"disabled"`), and the limiter tests set their own budgets.
- The production-mode uvicorn test (`test_credential_limit_required.py:97-111`) passed in my run: `[401]*10 + [429, 429]` with rotating forged `X-Forwarded-For`.
- In my E2E run the limiter was on (`AUTH_RATE_LIMIT_PER_MINUTE=10`).

R-7 is assessed in §2.C.

### R-4: versioned reset-token keys (verified experimentally)

**Probe:** `probe_r4.py`, committed sessions, in-process worker with a memory adapter, throwaway keys A and B.

| Step | Result |
|---|---|
| 1. Issue and deliver a link under A | queued, 1 sent |
| 2. Queue an email under A | queued; `email-token-key-usage` reports `{a: 1}` |
| 3. Activate B, keep A; new request | queued under B; usage `{a: 1, b: 1}` |
| 4. Process the queue | 2 sent |
| 5. Queued-A email contains a valid link | **True** (consumed successfully) |
| 6. Previously delivered A link still works | **True** |
| 7. Consumed link reused / expired link | **False / False** |
| 8. Remove A while one A link is delivered (unused) and one A email is queued | Queued email **cancelled, not sent**. The delivered A link **still valid** (validation is hash-only, `email_tokens.py:194-211`). The user is then in cooldown |

**`email-token-key-usage` CLI.**
- It counts only *pending outbox rows with a live token* (`email_tokens.py:249-257`).
- That is the correct set: delivered tokens never need the key (step 8 proves it). Removing a key cannot invalidate a delivered, unexpired link.
- It does not need to count delivered tokens. To kill delivered links, run `revoke-reset-tokens --yes`.
- Run as a subprocess, it printed `a: 1 live pending email(s)`.

**Mismatch handling.** A wrong secret under the same id, a removed key or a missing `key_id` all cancel the email, never sending a dead link (`email_tokens.py:224-246`, compared with `hmac.compare_digest`). The one exception is legacy rows (F-1).

**Retries.**
- A failed send keeps the row `pending`, with `attempts+1` and backoff. `last_error` holds only the exception type: my adapter raised an exception whose message contained part of the email body, and only `RuntimeError` was stored (`email_worker.py:190-193`).
- A restart before commit sends a duplicate of the same valid link (F-2).

**Token disclosure.**
- Outbox params hold `{token_id, key_id}` only.
- `EmailTokenKeyUnavailable` messages name the key id only.
- Worker logs carry the outbox id and template only.
- The reset link uses a URL fragment.

**Concurrent consumption.** `consume` is `FOR UPDATE` and re-checks `used_at`. The suite's four-session test passed. `reset_password` (`auth.py:244-276`) consumes and then hashes. A 503 on Argon2 capacity raises, so `get_db` rolls back and the token is **not** burned.

### R-5: source and evidence trust

See §2.E. The report's description, "partly addressed: mandatory rules must cite own http(s) source record", is accurate.

### R-6: reset-email abuse

See §2.C and F-3:
- the cooldown is atomic (verified, 20 concurrent requests);
- the daily cap holds;
- the queue ceiling is soft (15 pending against a ceiling of 10);
- no existence leak in responses;
- disabled delivery: 503 for all and nothing written.

### R-9: Playwright CI

**Workflow (`.github/workflows/ci.yml:231-310`):**
- The `e2e` job uses a `postgres:16` service with database `opportunity_hub_e2e` and a CI-only password, a pinned Python and Node, and `npx playwright install --with-deps chromium`. It then runs `scripts/e2e.sh`.
- Diagnostics are uploaded **only on failure**: `frontend/test-results/` (traces) and `frontend/e2e-artifacts/` (API and Vite logs), kept for 7 days.

**Isolation:**
- `e2e.sh` refuses database names without a separate `e2e` or `test` word.
- It exports `DATABASE_URL`, `APP_ENV=development`, `AUTH_RATE_LIMIT_PER_MINUTE=10`, `CLIENT_IP_STRATEGY=none` and `EMAIL_DELIVERY=disabled`.
- The fixture script repeats the name and production checks (see F-6 for the host gap).
- In CI the database is the job's own container.

**Admin fixture.**
- Reproducible and idempotent: it creates or resets the account, its `admin` role and a profile. It is run before the API starts.

**Artifact safety.**
- Playwright traces contain request bodies, that is the CI-only test passwords and the public default admin password, plus session tokens of ephemeral CI accounts. No production data is involved, and email is disabled, so no reset tokens exist.
- On a public repository the artifacts are readable by anyone with read access. That is acceptable for this content.

**Triggers and permissions.**
- `on: pull_request` runs for same-repo and fork PRs. `permissions: contents: read`, no secrets, no `pull_request_target`, so a fork PR cannot exfiltrate anything.
- First-time fork contributors need maintainer approval, which is GitHub's default.

**Test count reconciliation.**
- I collected test IDs at `06eb905` (scratch export) and in the worktree:
  - **base 1,156 → final 1,296 (+140)**;
  - no test was removed;
  - modified test files gained no new IDs.
- The new files hold: `test_client_ip_hardening` 11, `test_publication_guard` 21, `test_email_delivery_safety` 24, `test_credential_limit_required` 38, `test_email_token_rotation` 18, `test_password_reset_requests` 9, `test_public_opportunity_edits` 19.
- **How the report's numbers fit:**
  - Revision 1 = 1,156 + 11 + 21 + 23 = **1,211** (consistent with `test_email_delivery_safety` then holding 23).
  - Revision 2 adds 19 + 38 + 18 + 9 = 84 listed tests, **plus one test added to `test_email_delivery_safety.py` (23 → 24)**, which the report mentions only as "(now 24)" and leaves out of its category list.
  - So 1,211 + 85 = 1,296 is arithmetically correct. The "missing" test is the 24th test in `test_email_delivery_safety.py`.

---

## 4. Tests and probes I ran (exact commands and results)

**Paths.** Throwaway cluster and scratch copy:
`S=<scratch directory>/fresh-review`.

**Interpreter.** `PY=<worktree>/backend/.venv/bin/python`.

**Why a scratch copy.** Backend code ran from `$S/wt/backend`, an `rsync` copy of the worktree's `backend/` without `.env` and `.venv`; `diff -rq` showed it identical to the worktree. `import app` resolved to that copy, so `backend/.env` could not leak in.

```bash
# Cluster (deleted at the end)
/usr/lib/postgresql/16/bin/initdb -D $S/pg -U ohub --auth=trust
/usr/lib/postgresql/16/bin/pg_ctl -D $S/pg -o "-p 5434 -c unix_socket_directories='' -c listen_addresses=localhost -c max_connections=200" start
createdb -h localhost -p 5434 -U ohub {ohub_test,ohub_dummy,ohub_base_test,opportunity_hub_e2e,probe_test}

# Full backend suite
cd $S/wt/backend && env -i HOME=$HOME PATH=/usr/bin:/bin APP_ENV=development JWT_SECRET=<review-only> \
  DATABASE_URL=postgresql://ohub@localhost:5434/ohub_dummy \
  TEST_DATABASE_URL=postgresql://ohub@localhost:5434/ohub_test $PY -m pytest -q -p no:cacheprovider
#  -> 1293 passed, 3 failed (307.8 s). The 3 failures were test_render_yaml_settings_boot_in_production_on_render[*]:
#     FileNotFoundError for <copy>/render.yaml, because my copy lacked the repo-root render.yaml (an artifact of my layout).
#  After copying render.yaml beside the copy:
$PY -m pytest -q -p no:cacheprovider tests/test_client_ip_hardening.py   # -> 11 passed
#  => 1296 / 1296 pass; the report's "1296 passed" reproduces.

# Test-count reconciliation
(git archive 06eb905 backend | tar -x -C $S/base); pytest --collect-only in base and copy -> 1156 vs 1296 IDs

# Frontend (scratch copy of frontend/ with a hard-linked node_modules from the main checkout; package-lock identical)
npm run typecheck   # tsc -b: clean
npm test            # Vitest: 10 passed
npm run build       # built OK (chunk-size warning only)

# Playwright through the CI entry point (scratch copy of scripts/e2e.sh, backend/, frontend/)
env -i HOME=$HOME PATH=/usr/bin:/bin:/usr/local/bin E2E_DATABASE_URL=postgresql://ohub@localhost:5434/opportunity_hub_e2e \
  E2E_PYTHON=$PY E2E_API_PORT=8012 E2E_WEB_PORT=5191 bash scripts/e2e.sh
#  -> 26 passed (4.1 min), exit 0. Limiter active: rate_limit_buckets held /auth/login 13 and /auth/register 8
#     account counters; 0 responses with status 429 in api.log; no "password" or "token=" strings in api.log.
#     After the script exited, the Vite process (child of npx) was still listening on :5191 (see F-9); I killed it.

# Probes (scratch scripts, not in the repo)
probe_r1.py   live uvicorn :8011, AUTH_RATE_LIMIT_PER_MINUTE=10, CLIENT_IP_STRATEGY=none -> results in §3 R-1
probe_r4.py   committed sessions, memory adapter, keys A/B                     -> results in §3 R-4, §2.C, F-2, F-3
probe_cfg.py  Settings matrix                                                  -> results in §3 R-2, F-4
```

Not run: GitHub Actions (nothing was pushed, and `gh` is unavailable), Alembic round-trip (no migration in this change set; `alembic upgrade head` on fresh `probe_test` and `opportunity_hub_e2e` databases succeeded to head `3a14e912b77c`).

## 5. Summary table

| ID | Severity | Class | Location | Status |
|---|---|---|---|---|
| R-1 | (was High) | Code | `services/opportunities.py:123-170`, `routers/opportunities.py:53-93` | **Fixed; reproduced** |
| R-2 | (was High) | Code | `core/config.py:181-218`, `core/rate_limit.py:186-239` | **Fixed; reproduced** |
| R-4 | (was Medium) | Code | `services/email_tokens.py`, `services/email_worker.py:202-276`, `cli.py` | **Fixed; 8-step sequence reproduced** |
| R-6 | (was Medium) | Code | `services/password_reset.py` | **Fixed**; residual recovery denial accepted (§2.C) |
| R-9 | (was Medium) | CI | `ci.yml:231-310`, `scripts/e2e.sh` | Implemented; local run reproduces; **Actions not yet run** |
| F-1 | Low | Code | `email_worker.py:239-242` | Fix before enabling email |
| F-2 | Low | Code | `email_worker.py:228-275`, `cli.py` | Fix before enabling email |
| F-3 | Low | Code | `password_reset.py:75-82` | Document as soft ceiling |
| F-4 | Low | Code | `config.py:271-272`, `auth.py:143` | Fix soon |
| F-5 | Low | Code / design | `routers/opportunities.py`, `models/requirement.py:60-63` | Precondition for R-5 editor |
| F-6 | Low | Script | `seed_e2e_fixtures.py:36-41` | Optional |
| F-7 | Low | Test | `test_credential_limit_required.py:59-63` | Optional |
| F-9 | Low | Script | `scripts/e2e.sh:41-45,67-68` | Optional |
| F-8 | Low | Docs / UI | `render.yaml:104`, `Curate.tsx:320` | Fix soon |
| R-3 | High residual | Accepted risk / infra | `render.yaml:44-45` | Founder acceptance + §5 check |
| R-7 | Medium residual | Accepted risk | `rate_limit.py:233-239` | Founder acceptance + monitoring |
| R-6 residual | Medium residual | Accepted risk | `password_reset.py:62-73` | Founder acceptance + support path |
| R-8 | Medium | Infra | `render.yaml:86-163`, `ci.yml:20-21` | Keep crons suspended/uncreated |
| I-1 | Medium (feature gap) | Frontend / infra | `email_worker.py:41`, `App.tsx:147-161` | Blocks enabling email, not the PR |
| R-5 | Medium | Feature gate | `services/opportunities.py:181-218` | No evidence editor or ingestion until done |

## Verdict

**READY FOR PR WITH DOCUMENTED ACCEPTED RISKS**
