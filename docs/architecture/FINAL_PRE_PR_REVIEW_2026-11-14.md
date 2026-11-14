# Final pre-PR review: P0 security hardening (2026-11-14)

| | |
|---|---|
| Worktree | `~/projects/opportunity-hub-p0` |
| Branch | `fix/p0-security-hardening`, HEAD `06eb905` (nothing committed; the whole change set is in the working tree) |
| Scope | Full diff against `06eb905` (27 tracked files, +946/−219) and all 16 untracked files, including fresh-review cleanup items F-1, F-3, F-4, F-6, F-7, F-8 and F-9 |
| Reviewer independence | **Not independent.** I implemented the cleanup round myself, in the same session. This is a careful self-review, not a substitute for the fresh-subagent review (`FRESH_SECURITY_REVIEW_2026-11-14.md`). A human reviewer should still read the PR |
| Mode | Read-only. The only file this review created is this report |

## Verdict

**READY FOR PR WITH DOCUMENTED ACCEPTED RISKS**

- **Code-level security blockers:** none. The original P0 fixes are intact, and F-1, F-3, F-4, F-7 and F-8 are correct.
- **Recommended before merge:**
  - **F-6** (rated Low and "Optional" by the fresh review) does not fully meet its own acceptance criterion: URL query parameters can redirect the e2e guard's target (RC-1).
  - The implementation report overstates part of the F-9 evidence (RC-2).
  - The runbook's legacy-email procedure assumes a shell that Render free instances don't have (RC-3).
- All three are small fixes that can land as follow-up commits on the PR before merge.
- If RC-1 is left unfixed, its status must be changed to "accepted" in the report.

## Addendum (same day): corrections applied before the PR

The review below is kept as written. This addendum records what was done about it. The work was again by the same author, so it is still not independent.

| Item | Resolution |
|---|---|
| **RC-1** e2e guard bypass | **Fixed.** `throwaway_database_problems` now checks the *effective* destination: it runs the URL through the same SQLAlchemy psycopg2 dialect the app uses, and has libpq parse the resulting parameters. URL query parameters are allow-listed (`sslmode`, `connect_timeout`, `application_name`, or `host=<one socket directory>` when the URL has no host). So `host`, `hostaddr`, `port`, `dbname`, `service`, `servicefile`, `options`, percent-encoded names (`%68ost`), repeated parameters and multi-host values are all refused. The effective host must be loopback or one socket directory, and the effective name must contain an `e2e`/`test` word. `PGHOSTADDR`/`PGSERVICE` in the environment are refused. The check still runs (`--check-only`) before `e2e.sh` migrates or seeds anything. 26 new regression tests. The GitHub Actions URL is still accepted |
| **RC-2** F-9 evidence | **Corrected and re-verified.** The earlier "forced test failure" was a Playwright filter matching no tests (`Error: No tests found`, exit 1). The earlier process checks did not cover Playwright or Chromium, and the earlier port probe was IPv4-only. Re-verifying exposed a real gap: Playwright launches Chromium in **its own session and process group**, so killing Playwright's group does not reach it. `e2e.sh` now records every process in its groups plus all their descendants, signals them TERM then KILL, and fails if any survives or a port listens on IPv4 or IPv6 loopback. A new driver tracked processes by ancestry and session; results are below |
| **RC-3** runbook shell | **Fixed.** Runbook §3 now gives a trusted-local-machine procedure: a clean checkout of the released commit; the connection string read at a hidden prompt into one shell's environment with history off; `APP_ENV_FILE=""`; a throwaway `JWT_SECRET`. The documented environment passes production settings validation (checked with `legacy-email-outbox --help` against a fake URL, no connection). **Not executed against any database** |
| R-A IPv6 port probe | Fixed (part of RC-2) |
| R-C publish endpoint wording | Fixed. The docstring now says "if it passes the publication completeness checks", and states that the checks do not establish source authenticity. `schema.d.ts` regenerated; that is its only change |
| R-D router blank lines | Fixed |
| R-B legacy predicate alignment | Not changed (no exposure; out of scope for this round) |
| **New: CI-only test failure** | `test_missing_app_env_is_refused_on_render` failed whenever `APP_ENV` is set in the environment, and CI's `backend-tests` job sets it. It would have failed on GitHub Actions. Both missing-`APP_ENV` tests now remove the variable |

### Checks executed in this round

All database work used a throwaway PostgreSQL 16 cluster created for this round (port 55432, TCP only, deleted afterwards). The dev cluster on 5433 was not started.

| Check | Result |
|---|---|
| `test_review_cleanup.py` (incl. the new guard tests) | 66 passed (after the `APP_ENV` test fix; the first run was 65 passed, 1 failed, as described above) |
| Full backend suite with CI's `backend-tests` environment | **1362 passed, 0 failed** (199 s) |
| Playwright via `scripts/e2e.sh` | **26 passed** (2.8 min), limiter on |
| `e2e.sh` cleanup, final script, four scenarios | Normal completion exit 0. Real test failure (`smoke.spec.ts` with a 300 ms timeout; 1 failed) exit 1. SIGTERM mid-test exit 143 after 6.3 s. SIGINT mid-test exit 130 after 7.4 s. Chromium was running during each scenario. Afterwards: no tracked process (27–56 per run, 4 sessions), no `ms-playwright` process and no IPv4/IPv6 listener on 8000 or 5173 |
| Frontend | `tsc -b` 0 errors, Vitest 10 passed, build OK |
| Hygiene | `git diff --check` clean incl. untracked files; `bash -n`; `py_compile`. No Python linter or formatter is configured in the project; shellcheck is not installed |
| Secret scan of the final change set | Only test fixtures and placeholders (as in §4.4) |

Results from earlier rounds (1336 backend, 26 Playwright) were **not** re-run as such; the runs above supersede them.

### Updated verdict

**READY FOR PR WITH DOCUMENTED ACCEPTED RISKS.** RC-1, RC-2 and RC-3 are resolved. The accepted risks in §5 are unchanged.

## 1. Worktree and main-checkout state

| Check | Result |
|---|---|
| Worktree branch / HEAD | `fix/p0-security-hardening` / `06eb905`, no commits |
| Worktree changes | 27 modified tracked files and 16 untracked files before this review (17 with this report): the set listed in `P0_SECURITY_HARDENING_2026-11-14.md`, plus this report |
| Files changed by this review | **Only** `docs/architecture/FINAL_PRE_PR_REVIEW_2026-11-14.md`. No application code, test, script or other document was modified |
| Main checkout `~/projects/opportunity-hub` | Branch `ci/m1-m2-foundation` at `06eb905`. It holds only the founder's own uncommitted work: `docs/DEPLOYMENT.md`, `docs/architecture/RELEASE_RUNBOOK_2026-11.md` (modified), and `CURRENT_STATE_ASSESSMENT_2026-11-13.md`, `CURRENT_STATE_TASKS_2026-11-13.md`, `RELEASE_PR_SPECIFICATION.md` (untracked). **No branch change has leaked into it** |
| Databases | None started or modified. The project's dev cluster (port 5433) was left stopped |
| Production / Render / Neon / Cloudflare | Not accessed |

## 2. Blockers

None at code level (see the verdict).

## 3. Recommended corrections before merge

### RC-1: The F-6 e2e guard can be bypassed through URL query parameters (Medium for a test-tooling guard; Low overall)

- **Where:** `backend/scripts/seed_e2e_fixtures.py`, `throwaway_database_problems`.
- **What the guard checks:** `url.host` and `url.database`.
- **What the driver uses:** SQLAlchemy passes URL query parameters to psycopg/libpq, where they override both. I checked the guard and the driver's connect arguments for each URL below, without connecting anywhere:

| URL accepted by the guard | Where the driver would actually connect |
|---|---|
| `postgresql://u@localhost:5433/oh_e2e?host=db.example.neon.tech` | `host=db.example.neon.tech` (remote) |
| `postgresql://u@localhost:5433/oh_e2e?hostaddr=203.0.113.5` | the remote address (libpq `hostaddr` skips name resolution) |
| `postgresql://u@localhost:5433/oh_e2e?dbname=opportunity_hub` | the **developer's real local database** |
| `postgresql://u@/oh_e2e?host=/tmp,db.example.neon.tech` | a multi-host list whose second entry is remote |
| `postgresql://u@localhost:5433/oh_e2e?service=prod` | whatever the `prod` entry in `pg_service.conf` names |

**Impact.**
- If someone runs `scripts/e2e.sh` with such a URL, it migrates the target, seeds the demo data and resets `admin@example.org` to a known password (`AdminPass123!` unless `E2E_ADMIN_PASSWORD` is set) there.
- It needs an unusual, operator-supplied URL; the CI URL is fixed and safe.
- Even so, the user's acceptance criterion for F-6 was "refuse ambiguous targets". The report's claim of a guard with "no override" is therefore currently untrue.

**Fix (about 10 lines plus a test).**
- Refuse any of the query keys `host`, `hostaddr`, `dbname`, `service`, `port` and `options` when `url.host` is set.
- When `url.host` is empty, accept only a single `host` value that is an absolute path with no comma.
- Alternatively, allow only a small set of query keys (`sslmode`, `connect_timeout`, `application_name`).
- Add the five URLs above to `test_unsafe_or_ambiguous_targets_are_refused`.

### RC-2: Part of the F-9 evidence in the implementation report is overstated (documentation)

The revision 3 results table in `P0_SECURITY_HARDENING_2026-11-14.md` (the "E2E process cleanup (F-9)" row) says:
- the four scenarios included a "forced test failure";
- "no Vite, uvicorn or Playwright process remained".

The evidence behind them:
- **"Forced test failure":** produced by a Playwright filter that matched nothing (`Error: No tests found`, exit 1). It exercises the non-zero-exit cleanup path, which is what F-9 needs, but it is not a failing assertion. Say so.
- **"No … Playwright process remained":** the driver's process check matched only `vite` and `uvicorn` command lines in the worktree. It did not look for Playwright or Chromium. Playwright runs in its own process group, which the script terminates, so the design covers it, but the final runs didn't check it automatically. Either reword, or re-run with a check for `playwright` and `chrom` processes whose working directory is the worktree.
- **Port evidence:** the driver probed ports on `127.0.0.1` only. That evidence is valid on this machine, where both `getent ahosts localhost` and Node's `dns.lookup` give `127.0.0.1` only, so Vite listened on IPv4. See R-A for portability.

Everything else in that row is supported by the logs:
- exits 0, 1, 143 (0.4 s) and 130 (0.3 s);
- ports 8000 and 5173 free afterwards;
- no Vite or uvicorn process left.

### RC-3: Runbook §3 assumes a shell that Render free instances don't have (documentation)

- **The problem:** `P0_SECURITY_DEPLOYMENT_RUNBOOK.md` §3 says to run `python -m app.cli legacy-email-outbox` "from a one-off shell on the API service".
- **Why that fails:** the API service is `plan: free` in `render.yaml`. Render's documentation lists dashboard/SSH shell access and one-off jobs as paid-only, and says SSH is not supported for free services ([Render: Deploy for Free](https://render.com/docs/free), [Render: SSH and Shell Access](https://render.com/docs/ssh)).
- **Fix:** document the realistic route. Either run the CLI from the founder's machine with the production `DATABASE_URL`, `APP_ENV=production`, `CLIENT_IP_STRATEGY=none` and `JWT_SECRET` set, with explicit authorisation and no shell history of the URL; or upgrade the service temporarily.
- **Urgency:** not urgent. The procedure is needed only before enabling email, which I-1 blocks anyway.

## 4. Verification by area

### 4.1 The original reviewed fixes remain intact

| Area | Checked in the current diff | Status |
|---|---|---|
| P0-1 client IP | `CLIENT_IP_STRATEGY=none` exists and short-circuits to no address identity (`client_ip.py`). `peer` is refused in production when `RENDER=true` (`config.py`). `render.yaml` sets `none` on the API and both crons. Session rows store `client_identity(request).identity`, not the forgeable `request.client.host` (`auth.py`) | Intact |
| R-2 mandatory credential limit | `AUTH_RATE_LIMIT_PER_MINUTE` defaults to 10 and accepts 1–1000. `disabled` is refused in production. Every limiter call reads `settings.auth_rate_limit` | Intact |
| P0-2 / R-4 / R-6 reset email | `/auth/forgot-password` returns 503 when delivery is disabled. Tokens are HMAC-derived from versioned `EMAIL_TOKEN_KEYS`, and only `sha256` is stored. The outbox holds `{token_id, key_id}` only. The worker rebuilds the token, compares hashes with `compare_digest`, and cancels on mismatch. Consumption is `FOR UPDATE`. A successful reset revokes the account's other reset links. Cooldown, daily cap and queue ceiling apply. SMTP requires verified TLS. Logs carry no addresses or tokens | Intact |
| P0-3 / R-1 publication | `publication_problems` covers title, official http(s) URL, an own http(s) source record, rules, quotes, and mandatory rules citing own sources. Lifecycle fields can't be set on create or patch. Publishing is the only way to set `PUBLISHED` and locks the row. Closing is allowed only from `published`. Edits to public records are re-validated in a savepoint. Rejections are audited and returned (not raised), so the audit row commits. The seed goes through `publish_opportunity` | Intact |
| R-9 Playwright CI | The `e2e` job uses a `postgres:16` service, database `opportunity_hub_e2e` and `scripts/e2e.sh`, uploads diagnostics on failure, and uses no secrets. `scripts/e2e.sh` is executable (mode 775); the PR commit must keep the bit | Intact |

### 4.2 The cleanup fixes

| Item | Assessment |
|---|---|
| **F-3** global reset-queue ceiling | **Correct.** `pg_advisory_xact_lock(RESET_QUEUE_LOCK_KEY)` is taken after the user-row lock and before the count. Lock order is the same everywhere, so there is no deadlock cycle, and the lock is released at commit or rollback. The key (`0x0E4A117E5E70001`) fits in a signed bigint. The test uses 20 committed accounts, 20 threads and a barrier against a ceiling of baseline + 10, and asserts exactly 10 `QUEUED`, 10 `QUEUE_FULL` and 10 rows. Cost: reset requests that reach the ceiling check are serialised across the deployment. That is acceptable at this volume |
| **F-4** APP_ENV | **Correct.** A `before` validator strips whitespace and lower-cases the value, maps the aliases `dev` and `prod`, and allows only `development`, `test` and `production`. `None` or blank is refused. On Render, an `APP_ENV` absent from `model_fields_set` is refused. Values from the environment or dotenv count as set, so `render.yaml`'s `APP_ENV: production` passes. `is_production` is now an exact comparison. Every consumer (session cookie, limiter `reset()`, seeds, e2e guard) goes through `is_production`; a grep found no other raw `APP_ENV` comparison. Tests cover whitespace, case, aliases, unknown values, missing on and off Render, malformed production values that previously dodged the production checks, and the cookie's `Secure` flag over a real login |
| **F-6** e2e database guard | **Partly correct.** It is PostgreSQL-only, with a word-bounded `e2e`/`test` name, a loopback host or socket directory, and a production refusal. `e2e.sh` runs `--check-only` before migrating. The GitHub Actions URL is accepted. 10 unsafe targets are refused. **Gap: query-parameter overrides (RC-1)** |
| **F-7** hermetic "unset" | **Correct.** `APP_ENV_FILE` (empty disables the dotenv file) is read once at import. `test_credential_limit_required` and `test_review_cleanup` start subprocesses with `APP_ENV_FILE=""`, and `AUTH_RATE_LIMIT_PER_MINUTE` is removed from the environment. A positive control shows a named file is honoured. In production, Render never sets `APP_ENV_FILE`, so behaviour is unchanged (`backend/.env` is not in the repository) |
| **F-8** wording | **Correct** for the UI ("Check & publish", a tooltip stating that sources are not independently verified, corrected header text) and for the `render.yaml` worker `JWT_SECRET` comment. Leftover: the OpenAPI description of `POST /curate/opportunities/{id}/publish` still says "after checking source and rule verification" (`routers/opportunities.py`, mirrored in `frontend/src/api/schema.d.ts:328`). It is curator-facing API documentation only; see R-C |
| **F-9** e2e process cleanup | **Correct by design and by the process evidence.** `setsid` gives each of the API, Vite and Playwright its own group. A PID fallback covers the window before `setsid` runs. Playwright runs in the background with `wait`, so INT and TERM are handled at once. `on_exit` stops every group (TERM, then KILL) and preserves the exit status. Evidence wording: RC-2. Port-probe portability: R-A |
| **F-1** legacy raw-token messages | **Correct; see 4.3** |

### 4.3 Can a legacy raw token be exposed or sent?

I traced every path. **No path sends or prints a raw token from `params`.**

- **Rendering:** the worker never reads `params["token"]` for rendering. `render_template(template, token)` receives only the token from `email_tokens.deliverable_token`, which is rebuilt from `token_id` and `key_id` and accepted only if its hash matches the stored `token_hash`.
- **Pre-hardening rows** (`token` present, `token_id` absent) are cancelled before any other processing, and the token is stripped by `_cancel`. Unknown templates are cancelled the same way. The sent and permanently-failed branches also strip any `token` key.
- **The CLI report** selects only status, template, count and min/max `created_at`. `params` is used only inside `WHERE params ? 'token'` and is never loaded into Python. The test asserts the token string is absent from the report.
- **`--cancel`** requires `--yes`. It cancels pending legacy rows and removes the `token` key from every row that has one (`params - 'token'`), whatever its status, then prints counts only.
- **Logs** carry the outbox id, template and an error label (exception type plus SMTP code); never the recipient, body or token.
- **With delivery disabled,** the worker raises before locking any row, so legacy rows sit untouched (still holding the raw token at rest) until the CLI or a delivery-enabled worker runs. The runbook makes running the CLI a prerequisite for enabling email (subject to RC-3).
- **Minor inconsistency (no exposure):** `is_legacy` means "`token` and no `token_id`", while the report and cancel use "has `token`". A hypothetical row carrying both keys would be sent with the *rebuilt, hash-checked* token and its stray `token` stripped on completion, while the CLI would count it as legacy. Neither code version ever writes such a row. See R-B.

### 4.4 Secrets, credentials and unrelated files

| Check | Result |
|---|---|
| Secret-pattern scan over the full diff and untracked files (cloud keys, private keys, GitHub tokens, Neon hosts/passwords, `password = "…"`) | Only test fixtures and placeholders: `release-password-1` (spec), `hunter2-secret` (unit test), fake `ep-x…neon.tech` hosts in guard tests, the CI-only Postgres password `ci-only-not-a-secret` (already used by the existing jobs), and the e2e admin password `AdminPass123!`. That password already existed in `release_candidate.spec.ts` at `06eb905` and is now applied only by the guarded fixture script (see RC-1) |
| Real credentials, `.env` files, keys | None |
| `.vscode/`, `artifacts/`, `docs/presentation/` | Untouched |
| Unrelated features | No changes outside auth, rate limiting, email, publication, seeds, CI/e2e, `render.yaml` and the related docs. `.gitignore` adds only `frontend/e2e-artifacts/` |
| Build/run debris | `node_modules`, `dist`, `test-results`, `e2e-artifacts` and `__pycache__` are not part of the change set (`git status` lists none) |

### 4.5 Tests and CI consistency

| Check | Result |
|---|---|
| Full backend suite | **1336 passed, 0 failed**, from the previous round's run at 12:40–12:44. That run finished after the last backend edit (12:14:18, `test_production_features.py`). The run before it (`2 failed, 1334 passed`, 12:14:04) predates that fix. Not re-run here: no backend file has changed since, and re-running needs the project's dev Postgres cluster, which this review was told not to start |
| `test_review_cleanup.py` | 40 tests; I read them all. They test real behaviour; no vacuous assertion remains |
| Playwright via `scripts/e2e.sh` | 26 passed (`e2e-cleanup2-complete`, 12:37), after the last edits to `e2e.sh` (12:34) and the spec (12:23) |
| Frontend | `tsc` 0 errors, Vitest 10 passed, build OK, `schema.d.ts` equal to a fresh generation (previous round; `Curate.tsx` and `schema.d.ts` unchanged since) |
| CI ↔ script consistency | The CI database name `opportunity_hub_e2e` on `localhost:5432` satisfies the guard (also a test case). `PG_USER` is defined at workflow level. `setsid` and `/dev/tcp` are available on `ubuntu-24.04`. `playwright.config.ts` has no `webServer`, so nothing competes with the script for ports. The env exported by `e2e.sh` (`APP_ENV=development`, `APP_ENV_FILE=""`, limit 10, `CLIENT_IP_STRATEGY=none`, `EMAIL_DELIVERY=disabled`, `RENDER` unset) is valid under the new validators |
| GitHub Actions | **Has not run.** The first run will be the PR's |

### 4.6 Documentation of accepted risks and prerequisites

Checked in `P0_SECURITY_HARDENING_2026-11-14.md` (revision 3) and `P0_SECURITY_DEPLOYMENT_RUNBOOK.md`.

| Item | Documented | Accurate |
|---|---|---|
| Required production settings (`APP_ENV`, `CLIENT_IP_STRATEGY=none`, limit, `JWT_SECRET`, `EMAIL_DELIVERY=disabled`) and their start-up refusals | Yes (runbook §1) | Yes, matches the validators |
| Deploy order, migration head `3a14e912b77c`, smoke tests (11th wrong login → 429; forgot-password → 503) | Yes (§2) | Yes |
| F-1 legacy procedure as a precondition for enabling email | Yes (§3, §4.1) | Yes, except **RC-3** (no shell on free plan) |
| I-1 `/reset-password` page missing, blocking email | Yes (§4.2) | Yes |
| SMTP, token keys, `EMAIL_DELIVERY` on both API and worker | Yes (§4) | Yes, matches `render.yaml` (`fromService` for the worker's keys) |
| F-2 at-least-once delivery accepted | Yes (§4) | Yes |
| R-8 crons kept suspended or uncreated (branch `ci/m1-m2-foundation`, `starter` plan, no `PYTHON_VERSION`) | Yes (§5) | Yes, matches `render.yaml` lines 86–160 |
| R-3 no per-address limit, R-7 targeted lockout | Yes (§6) | Yes |
| R-5 blocks the evidence editor, ingestion and auto-publishing | Yes (§6) | Yes |
| R-6 residual, F-5 code-only invariant / no unpublish | Yes (§6) | Yes |
| F-6 "no override" and F-9 evidence | Yes (report) | **No:** RC-1, RC-2 |

## 5. Accepted risks (carried forward, unchanged)

| Risk | Status |
|---|---|
| R-3 No per-address credential limit until the CF-Connecting-IP check passes | Open (infrastructure) |
| R-7 Anyone can keep a known account locked out (11 requests/minute) | Open (founder decision) |
| R-5 Sources and evidence are not verified | Open; **blocks** the evidence editor, automated ingestion and auto-publishing, and any "verified" wording |
| R-6 residual: a victim's 5 daily reset emails can be used up | Accepted |
| F-2 Duplicate email after a worker crash | Accepted |
| F-5 Publication invariant enforced only in code; no unpublish operation | Accepted until the R-5 editor |
| I-1 No `/reset-password` page | Blocks enabling email, not the PR |
| R-8 Cron configuration | Keep suspended or uncreated |
| R-12, R-14 | Low, as in the risk register |

## 6. Recommendations (non-blocking)

- **R-A:** `e2e.sh`'s `port_in_use` probes only `127.0.0.1`. A listener bound only to `::1` is not detected (checked with a temporary `[::1]` listener on a spare port). On machines where Node resolves `localhost` to `::1`, the script's "port still in use" self-check could miss a leaked Vite. Probe `::1` too, or use `ss -Hltn "sport = :$port"`. Process-group termination itself is unaffected.
- **R-B:** align `is_legacy` with the CLI predicate (any `token` key), or narrow the CLI to the same definition, so the worker, the report and the cancel command agree.
- **R-C:** change the publish endpoint's docstring to "after checking publication completeness" and regenerate `schema.d.ts`.
- **R-D:** cosmetic. `opp_status_for_audit` sits between the two router declarations in `routers/opportunities.py` without the usual blank lines.
- **R-E:** once the founder's edits to `RELEASE_RUNBOOK_2026-11.md` land, link `P0_SECURITY_DEPLOYMENT_RUNBOOK.md` from its pre-deploy section.
- **R-F:** a genuinely independent human or fresh-agent pass on the PR diff, given this review's authorship.

## 7. What I ran for this review

All runs were read-only or used scratch data; nothing was written to the repository except this report.

- `git status`, `git diff 06eb905` (full) and every untracked file, in both checkouts.
- A secret-pattern grep over the diff and untracked files.
- For RC-1: `throwaway_database_problems(url)` and `engine.dialect.create_connect_args(url)` for the five URLs, with no connection opened.
- For R-A: a temporary IPv6-only listener on `[::1]:5999`, probed with `e2e.sh`'s exact `port_in_use` body (result: not detected). Then `getent ahosts localhost` and Node `dns.lookup('localhost')`, both giving `127.0.0.1`.
- Ordered the previous round's test logs against file modification times to confirm the 1336-passed result covers the current code.
- Checked Render's documentation on free-plan shell access (RC-3).
