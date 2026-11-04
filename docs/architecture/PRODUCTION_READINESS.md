# Production readiness: first CI run and the path to a release

| | |
| --- | --- |
| Status | Preparation only. **Nothing here has been executed against production.** |
| Date | 2026-11-03, updated 2026-11-04 |
| Code | `ci/m1-m2-foundation`, not pushed and not deployed; production runs `b8da30f` |
| Related | Plan §C.4, §G.4 (DEC-21), §F.8, M1-T1…T8; `RENDER_CLIENT_IP_VERIFICATION.md`; `ACCOUNT_LOCKOUT_THREAT_MODEL.md` |

Two milestones, in order:

1. **One green GitHub Actions run on `ci/m1-m2-foundation`**, with no chance of a production deploy.
2. **A production release.** It needs verified Render configuration, measured resource limits, a tested backup,
   a reviewed migration plan and explicit approval. Confirmed proxy trust follows as a separate deployment:
   releasing without it is a temporary accepted risk (§3.1).

## 1. Before the first push: manual checks

`render.yaml` links both services to `feat/opportunity-hub-product`, has no `autoDeploy` or `previews` keys,
and starts the API with `alembic upgrade head`. No checked-in service tracks `ci/**`. The file is not proof of
the live dashboard. These checks need dashboard access.

**Render, for `opportunity-hub-api` and `opportunity-hub`:**

1. The linked branch of each service. Neither may be `ci/m1-m2-foundation`, and no branch pattern may match it.
2. The auto-deploy setting of each service.
3. Pull-request previews (Manual, Automatic or Off). They only trigger for PRs against the linked branch, and none
   is planned, but record the setting.
4. Preview Environments (Blueprint level): on or off, and which branches they follow.
5. Whether previews inherit environment variables, especially `DATABASE_URL`. **A preview with the production
   `DATABASE_URL` runs `alembic upgrade head` against production.** So turning previews off alone isn't
   enough: also confirm that no preview group holds the production URL.
6. The live start command. Is it still `--proxy-headers --forwarded-allow-ips="*"`?
7. The plan and memory allocation, the CPU, and the instance count.
8. Whether `WEB_CONCURRENCY` is set. Uvicorn uses it as the worker count when `--workers` is absent.
9. The full live environment: `APP_ENV`, `CORS_ORIGINS`, `ALLOWED_HOSTS`, `AUTH_RATE_LIMIT_PER_MINUTE`, and any
   `CLIENT_IP_*`, `TRUSTED_PROXY_*` or `ARGON2_*`. Record names and non-secret values only.

**GitHub, in the repository settings:**

10. Actions are enabled, and the allowed-actions policy permits `actions/checkout`, `actions/setup-python` and
    `actions/setup-node`.
11. No branch protection or ruleset blocks pushing a new `ci/*` branch.

## 2. The commit and the push

The founder authorized the local commit on 2026-11-04. **The push still waits** for the checks in §1 and a separate
authorization. Both branches started at `b8da30f` with no divergence, so the working tree carries across.

```bash
cd /path/to/opportunity-hub
git switch ci/m1-m2-foundation                     # same commit as the current branch; keeps every change
git add --pathspec-from-file=<reviewed manifest>   # the reviewed list only; never `git add .` or `-A`
git diff --cached --name-only | wc -l              # must equal the manifest length
git diff --cached --check                          # no whitespace errors
git status --short | grep -E '^\?\? (\.vscode|artifacts|docs/presentation)/'   # still untracked
(cd backend && python -m pytest -q)                # final local run
git commit                                         # message reviewed before committing
git push origin refs/heads/ci/m1-m2-foundation:refs/heads/ci/m1-m2-foundation
```

- **Push scope:** `push.default` is unset (git's `simple`), and no push refspec or hook is configured. The
  explicit refspec pushes exactly one branch.
- **Never push `feat/opportunity-hub-product`.**
- **Never open a PR** without separate approval: a PR against the linked branch could create a Render preview.

## 3. Production blockers and priorities

| # | Issue | Status | Class |
| --- | --- | --- | --- |
| B1 | Pushing the production branch auto-migrates production (4 migrations) | Open; repository config | Critical production blocker |
| B2 | Client-IP spoofing (`--forwarded-allow-ips="*"`) | **Open.** Temporary accepted risk for the first release (§3.1) | High priority; must be closed after release |
| B3 | Render proxy chain, trusted header and address ranges | Unverified; support request ready, not sent | High priority; needed to close B2 |
| B4 | Automated, tested backups | None in the repository; Neon point-in-time history unverified | Critical production blocker |
| B5 | Migration recovery plan (downgrades are lossy) | Drafted below | Critical production blocker |
| H1 | Python dependency reproducibility | Outstanding; CI resolves newer versions than local (§5) | High priority |
| H2 | Argon2 limits against real memory and worker count | Unverified | High priority |
| H3 | Targeted account lockout | **Open; the release introduces it to production.** Accepted (§3.1); design deferred (device cookies, M1b) | High priority |
| O1 | Monitoring and alerting | Incomplete (§8) | Operational follow-up |
| O2 | Dev-only npm advisories (Vitest 3, `openapi-typescript` 7); GitHub Actions pinned by tag | Open | Operational follow-up |
| O3 | Stale `X-Admin-Token` in the generated `frontend/src/api/schema.d.ts` | Open; the server ignores the header | Operational follow-up |
| A1 | Login-wide Argon2 saturation | Reduced, still possible | Accepted limitation |
| A2 | Timing difference for unknown emails; registration 409 | Pre-existing | Accepted limitation |
| — | Registration-induced login starvation; CLI wrong-account role grant | Fixed locally, not deployed | — |
| D1 | Ingestion, `ruleset_version`, device cookies | Not built | Deferred feature |

### 3.1 Risks accepted for the first release

Accepted by the founder on 2026-11-04. **Neither risk is fixed.** Both stay open until the exit condition is met.

**Client-IP spoofing (remains from today's production).**
- The start command keeps `--proxy-headers --forwarded-allow-ips="*"`, so a caller chooses the address the IP
  budget counts, and can evade that budget by rotating forged `X-Forwarded-For` values. A garbage value skips it
  and logs `client_identity_degraded`.
- What still holds: the account budget (10 per minute per email) and the Argon2 cap. Credential stuffing at one
  guess per account is not meaningfully limited by anything else.
- Why accept it: the release doesn't make this worse, and it adds the account budget and the Argon2 cap, which
  production lacks today.
- Exit: Render's answer reviewed, then the start-command and trust change deployed separately
  (`RENDER_CLIENT_IP_VERIFICATION.md` §5).

**Targeted account lockout (new in production with this release).**
- Anyone who knows a student's email can keep that student's sign-in at 429, even with the correct password, from
  any address and without the password, for as long as they send more than 10 attempts a minute. The same applies
  to registering a specific email. It clears within a minute of the attacker stopping.
- Today's production has no account budget, so this risk doesn't exist there. It replaces password guessing
  limited only by a forgeable IP budget.
- There is **no operator override** for one account. `rate_limit.reset()` refuses in production, and unsetting
  `AUTH_RATE_LIMIT_PER_MINUTE` turns off every budget for everyone, so don't use that as a response.
- Detection: `account_budget_exhausted` (no account identity is recorded, so it can't say who).
- Exit: device cookies or an equivalent design (`ACCOUNT_LOCKOUT_THREAT_MODEL.md` §3, Option 5), decided with M1b.

## 4. Backups (B4): a concrete DEC-21

Until the automated job below exists, the release uses the manual procedure in §4.1.

DEC-21 already decides the design: encrypted dumps in off-provider storage, 35-day rotation. Proposal:

- **What:** `pg_dump --format=custom --no-owner` of the production database.
  - It runs as a dedicated **read-only** Postgres role (`SELECT` on all tables, no DDL).
  - Dumps include `audit_log`, so restores keep the audit trail.
- **When:** nightly (GitHub Actions `schedule`), plus manually right before every production deployment
  (`workflow_dispatch`). The pre-deploy dump is mandatory (§7).
- **Encryption:** `age` with a public key committed to the repository. The private key is kept offline by the
  founder, never in CI. A stolen dump or CI log is then useless.
- **Storage:** an off-provider bucket (Cloudflare R2 or Backblaze B2, per DEC-21).
  - The CI credential can only **write** objects under one prefix. Deletion is left to a lifecycle rule, so a
    leaked credential can't erase history.
  - A GitHub artifact is a stop-gap only (90-day maximum, same account as the code).
- **Retention:** 35 daily copies; pre-deploy dumps for 90 days.
- **Size and cost:** today's data dumps to about 60 KiB (measured on the local development dataset with the same
  12 + 2 opportunities), so 35 copies are about 2 MiB. That is within any provider's free allowance (allowances
  **unverified**). Expected cost: none at this scale. GitHub Actions minutes are free for public repositories
  and within the free quota for private ones (also unverified).
- **Verification:**
  - Each run checks the dump with `pg_restore --list` before encrypting, and fails loudly on a non-zero
    exit or an empty table of contents.
  - A monthly restore rehearsal restores into a disposable Neon branch or local database, then runs
    `alembic current`, row counts and the smoke test, and records the result in `docs/OPERATIONS_LOG.md`.
- **Objectives (proposed):**
  - RPO 24 hours (nightly), or at the last pre-deploy dump for deployment incidents.
  - RTO 2 hours: create the database, restore, repoint `DATABASE_URL`, redeploy. Measure it in the first
    rehearsal.
- **Neon point-in-time recovery:** not assumed. Check the console for the actual history window. It's a useful
  second layer, but it lives with the same provider and account.
- **Needs from you:**
  - creating the bucket and the read-only role, and storing the age private key offline (any paid
    tier requires approval);
  - the database connection secret, kept only in GitHub's encrypted secrets.

### 4.1 Manual backup and restore (for the founder; requires database credentials)

Rehearsed locally 2026-11-04 on disposable databases, **not against Neon**: a dump at `ba09eb02910b` restored
to the same revision with rows and credentials identical, and `b8da30f` signed in on it. A dump at head kept roles,
audit rows and the append-only triggers. `age` was not rehearsed. Run a dry run on Neon before release day, since a
Neon-specific object could make `--exit-on-error` stop on a local restore.

Dumps hold personal data (emails, profiles, password hashes), so keep them outside the repository, private and encrypted.

**Back up**, in a dedicated terminal. `pg_dump` must be version 16 or newer. Use Neon's direct (non-pooled) endpoint,
and supply the password this way so it stays out of shell history and process lists:

```bash
umask 077
mkdir -p ~/opportunity-hub-backups
export PGHOST='<direct endpoint>' PGUSER='<user>' PGDATABASE='<database>' PGSSLMODE=require
read -rs PGPASSWORD && export PGPASSWORD
F=~/opportunity-hub-backups/pre-deploy-$(date -u +%Y%m%dT%H%M%SZ).dump
pg_dump --format=custom --no-owner --no-privileges -f "$F"
pg_restore --list "$F" | grep -c 'TABLE DATA'         # must be non-zero
sha256sum "$F" > "$F.sha256"
psql -Atc "SELECT version_num FROM alembic_version"   # before the release: ba09eb02910b
psql -Atc "SELECT 'users', count(*) FROM users UNION ALL SELECT 'profiles', count(*) FROM profiles UNION ALL SELECT 'opportunities', count(*) FROM opportunities UNION ALL SELECT 'matches', count(*) FROM matches" | tee "$F.counts"
exit   # close this terminal, so PG* can't point at production by accident
```

**Prove the dump restores**, in a **new** terminal with no `PG*` variables, into a scratch local database:

```bash
env | grep '^PG'                                      # must print nothing
createdb -h localhost -p 5433 oh_restore_check_test
pg_restore --no-owner --no-privileges --exit-on-error -h localhost -p 5433 -d oh_restore_check_test "$F"
psql -h localhost -p 5433 -d oh_restore_check_test -Atc "SELECT version_num FROM alembic_version"
# Compare the row counts with "$F.counts", then drop the scratch database.
```

**Restore for real** (only per §7): never over the live database. Stop writes, create a new empty Neon database,
`pg_restore` into it as above, verify the revision and counts, point `DATABASE_URL` at it, and deploy code that
matches its revision. Keep the old database until the recovery is confirmed. Writes after the dump are lost.

## 5. Python dependency reproducibility (H1)

**Evidence (2026-11-03).** `pyproject.toml` bounds only SQLAlchemy. A fresh `pip install -e ".[dev]"`, CI's
exact command, today resolves `anyio` 4.16.0 and `pytest-asyncio` 1.4.1.post1, while the tested local venv has
4.15.1 and 1.4.1. The suite passed on both. Still, CI and the Render build (`pip install .`) install whatever is
newest on the day, and `anyio` governs the cancellation behaviour the Argon2 tests pin.

| Option | Reproducibility | Maintenance | Render build | New tooling |
| --- | --- | --- | --- | --- |
| **Constraints file** (`backend/constraints.txt` from `pip freeze` of the tested venv, minus the project itself) | Exact versions; no hashes | Regenerate when upgrading (one command) | `pip install -c constraints.txt .`: a one-line `buildCommand` change | None |
| Lockfile with hashes (`pip-tools` / `uv`) | Exact versions and hashes | Lock tool in the dev workflow | Install from the lock; build-command change | New dev dependency (needs approval) |
| Status quo | None | None | Unchanged | None |

**Recommendation:** a constraints file now, with no new tool.
- It's used by CI (`pip install -e ".[dev]" -c constraints.txt`) and later by the Render build.
- `pyproject.toml` keeps its ranges, so the package stays installable.
- Hash-pinned locking can follow when a lock tool is approved.

The Render half is a deployment change, made only with the release.

**Prepared 2026-11-04, deliberately not in the first commit:** `backend/constraints.txt`, 43 exact pins from a fresh
CI-style install. Evidence: a second fresh venv reproduced the versions exactly and passed all 1045 tests, and a
Render-style `pip install . -c constraints.txt` resolved with `pip check` clean and no dev packages. Nothing uses it
yet. After the first green run, commit it and change CI to `pip install -e ".[dev]" -c constraints.txt`. It needs a
`render.yaml` `buildCommand` change for the release, which needs approval. The file is generated on Linux with Python
3.12; regenerate it when the Python version or platform changes.

## 6. Production Argon2 sizing (H2)

The defaults stay `ARGON2_MAX_CONCURRENCY=2`, `ARGON2_REGISTRATION_MAX_CONCURRENCY=1` until these are known:

| Fact | Where | Why |
| --- | --- | --- |
| Instance memory limit | Render plan (dashboard) | Hard ceiling. Local: 64.3 MiB per Argon2 operation, about 82 MiB idle process, 147 MiB after one register and one login |
| Worker count | `--workers` (none in `render.yaml`) or `WEB_CONCURRENCY` (dashboard) | Total = slots × workers × instances |
| Instance count | Dashboard | Same |
| Idle and peak RSS of the live process | Render metrics after deploy | The real baseline, not the local one |
| Argon2 latency on the live CPU | One timed login on a staging copy (never a production load test) | A slower CPU holds each slot longer |
| Concurrent sign-in demand | `password_hash_capacity_exhausted` telemetry (limit `total` vs `registration`) | Whether two slots refuse real users |

**Rule:** `slots × workers × 64 MiB + measured peak RSS × workers ≤ 70 %` of the memory limit. Never raise
`ARGON2_*` on local measurements alone.

## 7. Migration deployment and recovery (B5)

**Facts (verified locally, 2026-11-03):**
- From the deployed head `ba09eb02910b`, four migrations upgrade with data unchanged. Every row count matches, and
  so does a fingerprint over every match and requirement outcome.
- Existing users get `role = student`.
- The deployed `b8da30f` code still registers and logs in on the upgraded schema, which makes rolling deploys safe.
- **Downgrade is lossy:** below `e931cedef74a` every role reverts to `student`, and below `2d0318b24522` the audit
  history is gone. Downgrade is not a recovery strategy.

**Before the deployment:**
1. A verified backup: the procedure in §4.1 (or the automated job, once it exists), including the restore proof.
2. Review the 4 migrations and note how much each one locks: three create tables, and one adds a column with a
   server default plus a CHECK.
3. Schema check against production with read-only queries. `alembic current` must be `ba09eb02910b`, and none
   of the new tables may already exist.
4. The release commit has passed CI, and the dependency set is pinned (§5).
5. Production config ready: `--forwarded-allow-ips="*"` stays for this release as an accepted risk (§3.1), and
   `ARGON2_*` stays at the defaults or is set per §6. The dashboard's `CORS_ORIGINS` and `VITE_API_BASE` are checked
   against the live domains, because `render.yaml` still names `onrender.com`.
6. A quiet window; the founder present; the demo account password known.

**After the deployment:**
- `alembic current` = `2d0318b24522`, and `/health` reports ok.
- Row counts match the pre-deploy numbers.
- The existing demo account signs in once (a single real login, no load).
- `GET /opportunities` returns the 12 listed programmes.
- The logs show no 5xx and no unexpected `client_identity_degraded`.
- Grant roles with the CLI: there are no curators or admins until someone is granted.

**If something fails:**
- **The app fails but the migrations completed:** roll the **application** back to `b8da30f` with Render's rollback.
  It runs on the new schema, as verified locally. Leave the schema at head and fix forward: correct the code or
  add a new migration, pass CI, redeploy. While rolled back, the new tables sit unused and the old in-memory
  limiter applies. Any role grants stay stored and take effect again on the next forward deploy.
- **A migration fails partway:**
  - `alembic/env.py` runs the whole `upgrade head` in **one** transaction (no `transaction_per_migration`),
    and none of the four migrations uses non-transactional DDL.
  - So a failure in any step rolls back all of them. Verified locally 2026-11-03: forcing the fourth
    migration to fail left the database at exactly `ba09eb02910b`, with no new tables and no `users.role`.
  - The start command then exits non-zero. Render should keep the old instance serving, but that behaviour is
    **unverified** for this service, especially on the free plan, where the old instance may not be running. Check
    `/health` straight away.
  - Find the cause on a restored copy, fix the migration, and redeploy.
  - A *manual* fix that runs migrations one at a time would lose this all-or-nothing property, so don't
    do that on production.
- **The data is wrong after the upgrade:** stop writes (scale to zero or put up maintenance), restore the
  pre-deploy dump into a new database, and point `DATABASE_URL` at it. Accept losing writes since the dump, or
  replay them by hand from the logs.
- **Never** run `alembic downgrade` on production as a rollback.

## 8. Minimal monitoring and alerting (O1)

No new provider until approved. Most of this runs on what exists: Render's own deploy and health
notifications, a scheduled GitHub Actions probe, and the existing log lines.

| Signal | Source | Alert when | Action |
| --- | --- | --- | --- |
| API availability | Scheduled probe of `/health` every 15 min (a GitHub Actions cron, no auth) | 2 consecutive failures | Check Render events and logs; database reachability |
| Database health | `/health` already reports `unavailable` when the DB is down; the rate limiter returns 503 | `/health` = 503 | Neon console; connection limits |
| Deploy failures | Render deploy notifications (dashboard setting) | Any failed deploy | The old instance keeps serving; read the build log |
| Auth failures | `auth_telemetry event=auth_failure` | Sustained jump over baseline | Possible stuffing; check the rate-limit events |
| Rate-limit exhaustion | `ip_budget_exhausted`, `account_budget_exhausted` | Account exhaustion on several distinct windows | Targeted-lockout pattern (H3) |
| Degraded client identity | `client_identity_degraded` (strategy, reason) | Any, after a proxy-config change | Trust config wrong; review before raising limits |
| Argon2 capacity | `password_hash_capacity_exhausted` (endpoint, operation, limit) | Repeated `limit=total` on login | Saturation or too few slots (§6) |
| Ingestion health | — | Once ingestion exists (M2) | — |

**Privacy:** telemetry labels come only from closed sets (endpoint, strategy, reason, budget, operation, limit),
with no emails, IPs, digests or account ids. Counters are per process and reset on restart. Log lines
are capped at one per minute per event with an occurrence count. Any log-based alert must read the
`occurrences=` field, not count lines.
