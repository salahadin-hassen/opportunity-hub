# Release runbook: first production release (target 2026-11-08)

| | |
| --- | --- |
| Audience | The founder, as operator, and whoever assists them |
| Release candidate | The newest green commit on `ci/m1-m2-foundation` |
| Production today | `b8da30f`, schema `ba09eb02910b` |
| Related | `PRODUCTION_READINESS.md` (risks §3.1, backup §4.1, recovery §7), `RENDER_CLIENT_IP_VERIFICATION.md` |

The deadline doesn't waive any gate. If a gate fails, the release moves. Local tests, GitHub CI and production are
three separate kinds of evidence, so don't let one stand in for another.

## 1. Daily checklist

**Day 1: constraints on GitHub**
- [x] Commit `27d6ef4` created, pushed, and green on GitHub Actions (run `41803734150`)
- [ ] Render support request sent (`RENDER_CLIENT_IP_VERIFICATION.md` §4)

**Day 2: facts from production (founder)**
- [ ] Render worksheet filled in (§2)
- [ ] Protected backup taken and restored into a scratch database (§3)
- [ ] Backup report recorded (§3.4)

**Day 3: release preparation**
- [ ] Any `render.yaml` reconciliation committed, and CI green on it
- [ ] Migration rehearsed on the restored copy (§4)
- [ ] Client-IP trust checklist complete (§2.1)
- [ ] Argon2 limits decided from real memory and worker facts (§2.2)
- [ ] Client-IP decision made: enable `render_cf_connecting_ip` (its assumptions confirmed), or keep the accepted risk

**Day 4: controlled deployment**
- [ ] Every item in the go/no-go list passes (§5)
- [ ] Founder explicitly authorizes the deployment
- [ ] Promotion done (§6)
- [ ] Post-deployment verification passes (§7)

## 2. Render worksheet (founder, in the dashboard)

The middle column is only what the repository says. Nothing here has been checked against the live service.

| Check | `render.yaml` at the candidate | Live value | Passes if |
| --- | --- | --- | --- |
| API linked branch | `feat/opportunity-hub-product` | | Understood; never `ci/**` |
| Frontend linked branch | `feat/opportunity-hub-product` | | Same |
| Auto-deploy, each service | Not set | | Recorded |
| Blueprint-managed? Auto-sync? | Not stated | | Recorded: **decides whether a push also applies `render.yaml`** |
| PR previews, Preview Environments | Not set | | Off, or proven unable to reach production |
| Preview access to production `DATABASE_URL` | Not stated | | None |
| Environment groups | None | | Recorded; none shared with a preview |
| Custom domains | Not stated | | Recorded for both services |
| `CORS_ORIGINS` | `https://opportunity-hub.onrender.com` | | Exactly the live frontend origin |
| `VITE_API_BASE` | `https://opportunity-hub-api.onrender.com` | | Exactly the live API origin |
| Python build command | `pip install --upgrade pip && pip install . -c constraints.txt` | | Will be this at release |
| Start command | `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"` | | Matches, or the difference is understood |
| Health-check path | `/health` | | `/health` |
| Plan, memory, CPU, instances | `free` | | Recorded |
| `WEB_CONCURRENCY` | Not set; Render documents a CPU-based default for services created after 2025-12-08 | | Recorded, including when no value is shown; see §2.2 |
| Other services in the workspace and region | Not stated | | Listed: matters if the API is on a paid plan |
| `ARGON2_*`, `CLIENT_IP_*`, `TRUSTED_PROXY_*` | Not set (code defaults) | | Unset, or understood |
| `AUTH_RATE_LIMIT_PER_MINUTE` | `10` | | `10` |
| `ALLOWED_HOSTS` | Not set | | Recorded |
| Database host and provider | Neon, per `docs/DEPLOYMENT.md` | | Provider and PostgreSQL version confirmed |
| `DATABASE_URL` endpoint | Not stated | | Direct or pooled: recorded (host only, never the password) |
| Cloudflare: API record proxy status | Not stated. Public DNS on 2026-11-04 indicates **Proxied** (§2.1) | | **DNS only**, if enabling the client-IP strategy |
| Cloudflare: Workers routes on the API hostname | None configured here | | None, if enabling the client-IP strategy |
| Cloudflare: Pseudo IPv4 | Not stated | | Recorded (handled in code) |

**The CORS risk.** The repository's `CORS_ORIGINS` and `VITE_API_BASE` name `onrender.com`, while the documented live
site uses `opportunities.sahelyon.com` and `api.opportunities.sahelyon.com`.

- `docs/DEPLOYMENT.md` creates the services from the Blueprint, and Render's default is to sync on any push to the linked
  branch that changes `render.yaml`. The candidate changes that file (`buildCommand`), so **under the defaults, promotion
  itself triggers a sync.**
- A sync overwrites any dashboard value the Blueprint defines. That includes `CORS_ORIGINS`, `VITE_API_BASE` and possibly
  `plan`. Render's documentation says `sync: false` values such as `DATABASE_URL` are ignored on updates, and a
  `generateValue` variable is added only if it doesn't already exist.
- Measured on the real app: with `CORS_ORIGINS` set to the file's value, a page on the live origin gets a 400 preflight and
  no `Access-Control-Allow-Origin`, so the browser blocks every API call. Sign-in and the catalogue would both fail.

So correct `render.yaml` to exactly the live values first, get CI green on that commit, and promote that commit. Never
leave this to chance by assuming Auto Sync is off.

### 2.1 Client-IP trust checklist (must pass before enabling `render_cf_connecting_ip`)

Local tests and CI can't answer these. **The strategy isn't production-safe until all five have evidence.**

| # | Check | Where | Passes if | Evidence |
| --- | --- | --- | --- | --- |
| 1 | Live Render plan of `opportunity-hub-api` | Render dashboard | Free, so it can't receive private traffic. If paid, check 4 decides | |
| 2 | API DNS record proxy status | Cloudflare dashboard, zone `sahelyon.com` | **DNS only** | Public DNS only, 2026-11-04: **indicates a failure** (below). Confirm in the dashboard |
| 3 | Worker routes on the API hostname | Cloudflare dashboard | None | |
| 4 | Private-network callers | Render dashboard: every service in the same workspace and region | No service can call the API privately, or the risk is accepted in writing | |
| 5 | Black-box forged-header test | Production, **after deployment and with its own authorization** (`RENDER_CLIENT_IP_VERIFICATION.md` §5) | 11th attempt gets 429 | |

If any of checks 1 to 4 fails, leave `CLIENT_IP_STRATEGY` at `peer` and ship under the accepted risk. If check 5 fails, turn the
strategy off. Don't remove `--proxy-headers` in this release.

**Check 2, public evidence.** `dig api.opportunities.sahelyon.com` through three public resolvers on 2026-11-04 returned only
A records and no CNAME: `104.21.88.102` and `172.67.176.80`, or `188.114.96.6` and `188.114.97.6`, depending on the resolver.
All are in Cloudflare's published ranges. `opportunity-hub-api.onrender.com` resolved differently, to `216.24.57.x`, outside
them. The zone uses Cloudflare nameservers. That is what a Proxied record looks like, and a DNS-only record would show the
Render target. Cloudflare and Render don't document what `CF-Connecting-IP` holds across two Cloudflare layers. If it held a
Cloudflare address, students would share one bucket and could lock each other out, so the strategy stays off until this is
resolved.

### 2.2 Argon2 limits

Local figures only: 64.3 MiB per operation and about 82 MiB for an idle process. Use §6 of `PRODUCTION_READINESS.md`,
and replace these figures with live ones as soon as they exist.

| Memory limit | Workers | 2 slots (default) |
| --- | --- | --- |
| 512 MB | 1 | Hashing 128 MiB + idle 82 MiB ≈ 210 MiB: within the 70 % limit |
| 512 MB | 2 | About 420 MiB: **over** the 70 % limit. Reduce workers or set `ARGON2_MAX_CONCURRENCY=1` |
| Unknown | Any | **Stop**: find out first |

Never raise the limits for this release. `ARGON2_MAX_CONCURRENCY=1` removes login's reserved slot.

## 3. Backup and restore (founder; needs production credentials)

The commands are in `PRODUCTION_READINESS.md` §4.1. Additions for this release:

### 3.1 Before dumping
In the dedicated terminal, after setting the `PG*` variables and before `pg_dump`:

```bash
psql -Atc "SHOW server_version"
pg_dump --version          # must be the same major version as the server, or newer
```

Your local tools and the local cluster are PostgreSQL 16. If the server is newer, stop: you need a matching client, and the
local cluster is no longer a valid restore target.

### 3.2 Encrypt
Immediately after `pg_dump` and the checks in §4.1. `gpg` prompts for a passphrase, so it stays out of history. Keep
the passphrase in a password manager, not beside the file. A local round trip was tested on 2026-11-04.

```bash
gpg --symmetric --cipher-algo AES256 --output "$F.gpg" "$F"
sha256sum "$F.gpg" > "$F.gpg.sha256"
```

Keep the unencrypted dump only until the restore proof is done, then `shred -u "$F"`. Store `$F.gpg` somewhere off this
machine.

### 3.3 Restore proof
In a **new** terminal with no `PG*` variables, prove the encrypted copy is what gets restored. Set `F` to the same
path again, because the new terminal doesn't have it.

```bash
umask 077
F=~/opportunity-hub-backups/<the dump file name>
sha256sum -c "$F.gpg.sha256"
gpg --decrypt --output "$F.check" "$F.gpg"
cmp "$F" "$F.check"
```

Then follow the restore steps in §4.1 using `"$F.check"`, and `shred -u "$F.check"` when finished. On
`oh_restore_check_test`, compare with the production counts and check that the schema came across:

```bash
DB="-h localhost -p 5433 -U ohub -d oh_restore_check_test"
psql $DB -Atc "SELECT version_num FROM alembic_version"
psql $DB -Atc "SELECT count(*) FROM pg_constraint WHERE connamespace = 'public'::regnamespace"
psql $DB -Atc "SELECT 'users', count(*) FROM users UNION ALL SELECT 'profiles', count(*) FROM profiles UNION ALL SELECT 'opportunities', count(*) FROM opportunities UNION ALL SELECT 'matches', count(*) FROM matches"
```

Also run those two `count` queries against production in the dedicated terminal, and compare the results. Never restore
over production. If `--exit-on-error` stops on something specific to Neon, share only the error line.

### 3.4 Backup report (fill in)

| Item | Value |
| --- | --- |
| Taken at (UTC), by | |
| Provider and PostgreSQL version | |
| Client version | |
| Dump size; encrypted size | |
| SHA-256 of the encrypted file | |
| Storage location | |
| Production revision | |
| Row counts: users, profiles, opportunities, matches | |
| Constraint count, production and restored | |
| Restored revision and counts match? | |
| Restore duration | |

## 4. Migration rehearsal on the restored copy

Local, on the scratch database, from a clean checkout of the candidate. It holds real personal data, so don't copy
it anywhere else, and drop it when you finish.

```bash
git rev-parse HEAD      # must be the candidate commit
cd backend
source .venv/bin/activate
export DATABASE_URL='postgresql://ohub@localhost:5433/oh_restore_check_test'
export APP_ENV=development JWT_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')"
alembic current         # expect ba09eb02910b
alembic upgrade head    # four steps, in one transaction
alembic current         # expect 2d0318b24522
alembic check
psql "$DATABASE_URL" -Atc "SELECT role, count(*) FROM users GROUP BY role"     # everyone is student
psql "$DATABASE_URL" -Atc "SELECT count(*) FROM pg_trigger WHERE tgname LIKE 'audit_log_no_%'"   # expect 2
uvicorn app.main:app --port 8799 --no-proxy-headers    # then GET /health and /opportunities from another terminal
```

Row counts must match §3.4. Keep the same terminal for the checks and unset `DATABASE_URL` afterwards.

**Migration review.** They run in this order, as one transaction, on top of `ba09eb02910b`:

| Revision | Effect | Risk |
| --- | --- | --- |
| `cf669b0daa53` | Creates `acquisition_sources` and `acquisition_source_hosts` with publication CHECKs | New tables only |
| `7a929229fe00` | Creates `rate_limit_buckets`, primary key `(scope, key, window_start)` | New table only |
| `e931cedef74a` | Adds `users.role` (default `student`) and its CHECK | Short exclusive lock on `users`; the CHECK scans the table |
| `2d0318b24522` | Creates `audit_log` with append-only triggers | New table only |

No existing table loses a column, and `matches` and `match_requirements` are untouched. Rehearsed locally with seeded
data; not yet on a copy of production.

### 4a. Rehearsal on a Neon branch (same provider, same role)

The local cluster's `ohub` role is a superuser, so the run above can't show that the live role may migrate. Tested locally:
a non-superuser that owns the tables succeeds, and one that doesn't fails with `must be owner of table users` and rolls back.
Only a branch tests the real role. A branch doesn't replace §3, because it lives with the same provider.

Neon's documentation says a branch's changes are independent of its parent and that creating one doesn't load the parent. The
Free plan lists 10 branches per project. **If the console offers a charge or an upgrade, stop.**

1. Console: **Branches → New branch**. Parent: the production branch. Include: **Current data**. Name:
   `release-rehearsal`. Leave automatic deletion on. Don't use **Restore** or **Reset from parent**.
2. **Connect**: choose `release-rehearsal`, the same database and role as the live `DATABASE_URL`, with connection pooling
   **off**.
3. In a new terminal, prove the target before any migration. **Stop if the host equals the live host recorded in §2.**

   ```bash
   git rev-parse HEAD      # must be the candidate commit
   cd backend
   source .venv/bin/activate
   read -rs DATABASE_URL && export DATABASE_URL
   python -c "import os, urllib.parse as u; print(u.urlsplit(os.environ['DATABASE_URL']).hostname)"
   ```

4. Run the `alembic` and `psql` commands from §4 from `export APP_ENV=development …` onwards, skipping the `export DATABASE_URL`
   line. Time `alembic upgrade head`, and record the database role name.
5. Close the terminal and delete the branch.

## 5. Go/no-go (every line must be yes)

- [ ] The candidate commit has a green GitHub Actions run, and it's the exact commit being promoted
- [ ] Backup taken, encrypted, stored off this machine, and restored successfully
- [ ] Migration rehearsal passed on the restored copy (§4) and on a Neon branch with the live role (§4a)
- [ ] Recovery for an unhealthy release decided: fix forward, or the old-code procedure in the stop conditions (§7), with
  the founder aware that Render's rollback alone won't start `b8da30f`
- [ ] Render worksheet complete, with no unexplained difference
- [ ] `CORS_ORIGINS` and `VITE_API_BASE` correct after promotion, whether or not a Blueprint sync happens
- [ ] The live build command uses `-c constraints.txt`, or the founder accepts the unpinned build for this release
- [ ] Argon2 limits fit the real memory and worker count
- [ ] No preview can reach the production database
- [ ] Risks in `PRODUCTION_READINESS.md` §3.1 reconfirmed by the founder
- [ ] Client-IP trust checks 1 to 4 pass (§2.1), or the strategy stays at `peer`
- [ ] Founder available for at least two hours after the deployment
- [ ] Explicit deployment authorization given

## 6. Promotion (only after authorization)

Fast-forward only, with the tested commit named explicitly. **Never force.** This triggers a production deployment and
the four migrations.

```bash
git fetch origin
RELEASE=<full hash of the green commit>
git merge-base --is-ancestor origin/feat/opportunity-hub-product "$RELEASE" && echo fast-forward-ok
git rev-parse origin/feat/opportunity-hub-product      # expect b8da30f…
git push origin "$RELEASE:refs/heads/feat/opportunity-hub-product"
```

Then watch the build and deploy logs for the API and the frontend. Confirm in the dashboard that the deployed
commit is `$RELEASE`.

## 7. Post-deployment verification (authorized production traffic)

Run in this order and record each result. A green health check alone proves very little. Set
`API=https://api.opportunities.sahelyon.com` (or the confirmed live origin), and use a new password you generate here.

| # | Check | How | Expect |
| --- | --- | --- | --- |
| 1 | Deployment and migration | Dashboard; read-only `SELECT version_num FROM alembic_version` | `$RELEASE`; `2d0318b24522` |
| 2 | Health and database | `curl -s $API/health` | 200, `{"status":"ok"}` |
| 3 | Data preserved | The §3 count queries; `curl -s "$API/opportunities?limit=100"` | Counts match or have grown only by real signups; 12 listed |
| 4 | Frontend and CORS | Browser on the live site, developer console open | Pages load; no CORS errors |
| 5 | Registration | Register `release-check-20261108@example.org` | 201; a second attempt gets 409 |
| 6 | Login | That account, right and wrong password | 200; 401 |
| 7 | Eligibility and discovery | Playwright smoke test (below) | Passes |
| 8 | Student blocked | `GET $API/curate/sources` with no token, then with the student's token | 401; 403 |
| 9 | Admin | Grant your role (below); `GET $API/curate/sources` and `GET $API/admin/audit` | 200; audit shows `user.role_changed` |
| 10 | Rate limiting (if the client-IP change is included, the black-box check in `RENDER_CLIENT_IP_VERIFICATION.md` §5 needs its own authorization; turn the strategy off if it fails) | Wait 60 s, then right after a new clock minute starts, send 11 logins for `release-check-limit@example.org` with a wrong password (windows are fixed, so straddling a minute resets the count); wait 60 s afterwards | 10 × 401, then 429 |
| 11 | Argon2 and memory | Render metrics during the checks above | Well under the limit, no restarts |
| 12 | Logs | Render logs for the whole period | No 5xx or tracebacks; `auth_telemetry` lines hold no email or IP |

Check 10 also fills your address's budget for the minute. Without the client-IP change it can't show that a spoofed
address is limited, because that remains open. Don't load-test Argon2 in production: saturating it refuses real students. The capacity behaviour is proven
locally; production only confirms the memory.

The test account stays in the database, because there is no self-service deletion. Record its address.

**Smoke test** (signs in as the demo account and runs one eligibility check; `docs/DEMO_RUNBOOK.md` covers resetting it):

```bash
cd frontend
read -rs DEMO_PASSWORD && export DEMO_PASSWORD
OH_BASE_URL=https://opportunities.sahelyon.com OH_API_URL="$API" npx playwright test e2e/smoke.spec.ts
```

**Granting your role** (from your machine, with a checkout of the release and the account already registered). This
writes to production. `JWT_SECRET` isn't used by this command, so generate a throwaway value rather than copying the
real one. Tested locally: the environment's `DATABASE_URL` takes priority over `backend/.env`. Check the printed
result, and close the terminal afterwards.

```bash
cd backend
read -rs DATABASE_URL && export DATABASE_URL
export APP_ENV=production JWT_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')"
python -m app.cli show-role '<your exact email>'
python -m app.cli grant-role '<your exact email>' admin
```

### Stop conditions

| Situation | Action |
| --- | --- |
| Build fails | Production keeps running. Fix, CI, and promote again |
| Migration fails | All four roll back. Check `/health` at once, then follow `PRODUCTION_READINESS.md` §7 |
| App unhealthy after the migrations | **Don't rely on Render's rollback.** Fix forward if you can; otherwise use the old-code procedure below. The schema stays at head |
| CORS or frontend failure | Correct the environment value and redeploy. No rollback needed if the API is healthy |
| Wrong data | Stop writes; restore into a **new** database (§7). Never `alembic downgrade` |

### Running the old code after the migrations

Render's documentation says a rollback reuses the target deploy's start command. For `b8da30f` that begins with
`alembic upgrade head`, and its code doesn't know the new revision. Tested locally on a migrated database: the command
exits 255 with `Can't locate revision identified by '2d0318b24522'`, so uvicorn never starts. `b8da30f` does serve correctly on
that schema when uvicorn runs alone (also tested locally). **This procedure hasn't been run on Render.** It changes
production settings, so it needs authorization at the time:

1. Set Blueprint **Auto Sync** to No and pause pushes, because a sync would overwrite the commands below.
2. If `CLIENT_IP_STRATEGY` was changed, set it back to `peer`: `b8da30f` refuses the new value.
3. Build command: `pip install --upgrade pip && pip install .` (`b8da30f` has no `constraints.txt`).
4. Start command, without Alembic: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"`
5. **Manual Deploy → Deploy a specific commit → `b8da30f`.** This turns auto-deploy off. Render's page doesn't state that this
   kind of deploy uses the current commands, so read the deploy log to confirm.
6. Before the next forward deploy, restore both commands and re-enable Auto Sync and auto-deploy.

## 8. After the release: the catalogue sprint

Kept out of this release. Next product sprint, using M2-T7 to M2-T10 in the implementation plan:

- Safe fetcher, documents and snapshots, candidate queue, then first official connectors.
- Start with three or four high-value official sources.
- First milestone: 100 verified opportunities; then 500, 1,000 and 2,000.
- Telegram may suggest leads, but it's never an authority for eligibility rules, and a lead is never auto-published.
- No paid APIs or LLM services unless explicitly authorized.
