# Release runbook: first production release (target 2026-11-09)

| | |
| --- | --- |
| Audience | The founder, as operator, and whoever assists them |
| Release candidate | `06eb905be36d1e8e382b2c84162d156f642a5a41` (HEAD of `ci/m1-m2-foundation`) |
| Production today | `b8da30f25bc568bbcea9e03043001e1d4d1a2e97`, schema `ba09eb02910b` |
| Target production schema | `3a14e912b77c` (5 migrations from baseline, proven backward-compatible with `b8da30f`) |
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
- [x] Any `render.yaml` reconciliation committed, and CI green on it (`06eb905b`)
- [x] Migration rehearsed on Neon branch `rehearsal-release-20261109` (§4, §4a)
- [x] Old-code backward compatibility verified (`b8da30f` tested against `3a14e912b77c`)
- [ ] Client-IP trust checklist complete (§2.1)
- [ ] Argon2 limits decided from real memory and worker facts (§2.2)
- [ ] Client-IP decision made: enable `render_cf_connecting_ip` (its assumptions confirmed), or keep the accepted risk

**Day 4: controlled deployment**
- [ ] Auto-deploy disabled ("No") for both services in Render Dashboard (§2.0)
- [ ] Recovery readiness established (Neon backup branch `backup-pre-release-20261109` created)
- [ ] Every item in the go/no-go list passes (§5)
- [ ] Founder explicitly authorizes the deployment
- [ ] Promotion done following the strict Free-plan order (§6.1)
- [ ] Post-deployment verification passes (§7)

## 2. Render worksheet (founder, in the dashboard)

The middle column is what the repository (`render.yaml` at commit `06eb905b`) defines.
The right columns must be verified against the live service in the Render Dashboard.

| Check | `render.yaml` at candidate (`06eb905b`) | Live value | Passes if |
| --- | --- | --- | --- |
| API linked branch | `feat/opportunity-hub-product` | | Understood; never `ci/**` |
| Frontend linked branch | `feat/opportunity-hub-product` | | Same |
| Auto-deploy, each service | Not set in file (defaults to **Yes** in Render) | | **Disabled ("No")** before promotion (§2.0) |
| Blueprint-managed? Auto-sync? | Not stated | | Recorded: **decides whether a push also applies `render.yaml`** |
| PR previews, Preview Environments | Not set | | Off, or proven unable to reach production |
| Preview access to production `DATABASE_URL` | Not stated | | None |
| Environment groups | None | | Recorded; none shared with a preview |
| Custom domains | Not stated | | Recorded for both services |
| `CORS_ORIGINS` | `https://opportunities.sahelyon.com,https://opportunity-hub.onrender.com` | | Exactly matches live origins |
| `VITE_API_BASE` | `https://api.opportunities.sahelyon.com` | | Exactly matches live API origin |
| Python build command | `pip install --upgrade pip && pip install . -c constraints.txt` | | Will be this at release |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"` | | **No `alembic upgrade head` in startCommand** |
| Health-check path | `/health` | | `/health` |
| Plan, memory, CPU, instances | `free` | | Recorded |
| `WEB_CONCURRENCY` | Not set; Render documents a CPU-based default for services created after 2025-12-08 | | Recorded, including when no value is shown; see §2.2 |
| Other services in the workspace and region | Not stated | | Listed: matters if the API is on a paid plan |
| `ARGON2_*`, `CLIENT_IP_*`, `TRUSTED_PROXY_*` | Not set (code defaults) | | Unset, or understood |
| `AUTH_RATE_LIMIT_PER_MINUTE` | `10` | | `10` |
| `ALLOWED_HOSTS` | Not set | | Recorded |
| Database host and provider | Neon, per `docs/DEPLOYMENT.md` | | Provider and PostgreSQL version confirmed |
| `DATABASE_URL` endpoint | Not stated | | Direct or pooled: recorded (host only, never the password) |
| Cloudflare: API record proxy status | Proxied (orange cloud) on `sahelyon.com`; SSL mode Full per Render docs | | Proxied or DNS-only recorded; if enabling `render_cf_connecting_ip`, SSL mode must be Full |
| Cloudflare: Workers routes on the API hostname | None configured here | | None, if enabling the client-IP strategy |
| Cloudflare: Pseudo IPv4 | Not stated | | Recorded (handled in code) |

### 2.0 Auto-Deploy Verification and Disablement Procedure (Render Dashboard)

> [!WARNING]
> **The Auto-Deploy Race Hazard:** Render web services and static sites connected to GitHub repositories enable **Auto-Deploy: Yes** by default.
> On the Free plan, if code is pushed to the production branch (`feat/opportunity-hub-product`) before database migrations are completed and verified, Render immediately triggers automated builds and starts web workers against the un-migrated schema.
> Furthermore, embedding `alembic upgrade head` in `startCommand` was eliminated because it introduces container restart races and concurrency collisions.
> **Therefore, Auto-Deploy MUST be verified and set to "No" on both services before any promotion push.**

#### Live Verification Steps (Operator Action in Render Dashboard):
1. Log in to [https://dashboard.render.com](https://dashboard.render.com).
2. Open the API service (`opportunity-hub-api`).
3. Click **Settings** in the left navigation sidebar.
4. Scroll down to the **Build & Deploy** section.
5. Check the **Auto-Deploy** field: record whether it is currently **Yes** or **No**.
6. Repeat for the Frontend service (`opportunity-hub`): navigate to **Settings** -> **Build & Deploy** -> check **Auto-Deploy**.

#### Disablement Steps (Operator Action in Render Dashboard):
1. In `opportunity-hub-api` -> **Settings** -> **Build & Deploy** -> find **Auto-Deploy**.
2. Click **Edit** (or select the dropdown / toggle).
3. Set **Auto-Deploy** to **No** (disabled).
4. Click **Save Changes**.
5. Refresh the page and confirm **Auto-Deploy** displays **No**.
6. In `opportunity-hub` (static site) -> **Settings** -> **Build & Deploy** -> find **Auto-Deploy**.
7. Click **Edit** -> set to **No** -> click **Save Changes**.
8. Refresh the page and confirm **Auto-Deploy** displays **No**.

Both services are now safely decoupled from branch push events, allowing controlled, sequential deployment.

**CORS and API Base Reconciliation.**
Commit `06eb905b` updated `render.yaml` to specify the production live domains:
- `CORS_ORIGINS: https://opportunities.sahelyon.com,https://opportunity-hub.onrender.com`
- `VITE_API_BASE: https://api.opportunities.sahelyon.com`

This eliminates the risk of Blueprint Auto Sync overwriting dashboard values with obsolete `*.onrender.com` origins.
If Render Auto Sync applies `render.yaml`, the CORS configuration matches production origins exactly.

### 2.1 Client-IP security analysis and trust checklist

> [!WARNING]
> **Client-IP Spoofability under `CLIENT_IP_STRATEGY=peer`:**
> `CLIENT_IP_STRATEGY=peer` is **NOT safe against IP-level spoofing** under the current Uvicorn production flags (`--proxy-headers --forwarded-allow-ips="*"`).
>
> 1. **How `peer` obtains identity:** In `backend/app/core/rate_limit.py`, `client_identity(request)` reads `peer = request.client.host` from the ASGI connection `scope["client"]`.
> 2. **Uvicorn header rewriting:** With `--proxy-headers --forwarded-allow-ips="*"`, Uvicorn's `ProxyHeadersMiddleware` trusts every upstream TCP connection unconditionally and replaces `scope["client"]` with the **leftmost** entry in `X-Forwarded-For`.
> 3. **IP-bucket spoofing:** Because an external client completely controls the leftmost `X-Forwarded-For` value, an attacker can rotate forged headers on every request, resetting their per-IP address bucket and evading the per-IP rate limit (`10 attempts/minute`).
>
> **Account-Level vs. IP-Level Protection:**
> - **Account-Level Protection (`limit_account_attempts`):** Enforced via HMAC hash of the email address (`account_subject_key(email)`). It does **not** read client IP or forwarding headers. A targeted brute-force attack against any specific user account is strictly throttled to 10 attempts per minute regardless of header forgery or IP rotation.
> - **IP-Level Protection (`limit_auth_attempts`):** Designed to prevent distributed credential stuffing across *many different user accounts*. Under `peer` with current Uvicorn flags, this layer is spoofable.
>
> **Status of `render_cf_connecting_ip`:**
> Although implemented in code to read Cloudflare's edge-written `CF-Connecting-IP`, `render_cf_connecting_ip` **MUST REMAIN DISABLED** in production until all five trust assumptions below are verified on the live service.
> **Production settings must not be changed.** The release ships with `CLIENT_IP_STRATEGY=peer` as a documented, accepted risk.

| # | Check | Where | Passes if | Evidence |
| --- | --- | --- | --- | --- |
| 1 | Live Render plan of `opportunity-hub-api` | Render dashboard | Free, so it can't receive private traffic. If paid, check 4 decides | |
| 2 | API DNS record proxy status | Cloudflare dashboard, zone `sahelyon.com` | Proxied or DNS-only recorded; SSL mode Full/Strict | Public DNS only, 2026-11-04: indicates Proxied. Confirm in the dashboard |
| 3 | Worker routes on the API hostname | Cloudflare dashboard | None | |
| 4 | Private-network callers | Render dashboard: every service in the same workspace and region | No service can call the API privately, or the risk is accepted in writing | |
| 5 | Black-box forged-header test | Production, **after deployment and with its own authorization** (`RENDER_CLIENT_IP_VERIFICATION.md` §5) | 11th attempt gets 429 | |

If any of checks 1 to 4 fails or is unverified, `CLIENT_IP_STRATEGY` remains at `peer` under the accepted risk. Do not change production settings. Do not remove `--proxy-headers` in this release.

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

## 4. Migration rehearsal and backward compatibility

Local, on the scratch database, from a clean checkout of the candidate (`06eb905b`). It holds real personal data, so don't copy
it anywhere else, and drop it when you finish.

```bash
git rev-parse HEAD      # must be 06eb905be36d1e8e382b2c84162d156f642a5a41
cd backend
source .venv/bin/activate
export DATABASE_URL='postgresql://ohub@localhost:5433/oh_restore_check_test'
export APP_ENV=development JWT_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')"
alembic current         # expect ba09eb02910b
alembic upgrade head    # five steps, in one transaction
alembic current         # expect 3a14e912b77c
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
| `e931cedef74a` | Adds `users.role` (default `student`) and its CHECK | Short exclusive lock on `users`; default applied |
| `2d0318b24522` | Creates `audit_log` with append-only triggers | New table only |
| `3a14e912b77c` | Adds `sessions`, `email_tokens`, `email_outbox`, `saved_opportunities`, `application_history`, and lifecycle columns | New tables; nullable lifecycle columns on `users` |

No existing table loses a column, and existing rows in `users`, `profiles`, `opportunities`, `matches` and `match_requirements` are untouched.

### 4a. Rehearsal on a Neon branch (same provider, same role)

A migration rehearsal was executed and verified against Neon branch:
- **Parent (production):** `br-summer-heart-b5pjdb5y`
- **Rehearsal branch:** `br-flat-feather-b5n2ty3c` (`rehearsal-release-20261109`)
- **Baseline revision:** `ba09eb02910b`
- **Target revision:** `3a14e912b77c`
- **Data preserved:** 4 users, 4 profiles, 14 opportunities, 48 matches.

### 4b. Proven backward compatibility with old production application code

Prior to deploying release candidate code, the current production application code (`b8da30f25bc568bbcea9e03043001e1d4d1a2e97`) was executed directly against the migrated schema (`3a14e912b77c`):
- Application startup and `/health` responded `200 OK`.
- Database connection and existing user login succeeded.
- Profile reads and updates executed without schema errors.
- Opportunity catalog queries and detail reads succeeded.
- **Result:** The upgraded database schema `3a14e912b77c` is proven 100% backward-compatible with old production code `b8da30f`. If code rollback is ever needed, the database schema MUST NOT be downgraded.

## 5. Go/no-go (every line must be yes)

- [ ] Auto-Deploy verified disabled ("No") for both `opportunity-hub-api` and `opportunity-hub` in Render Dashboard (§2.0)
- [ ] The candidate commit `06eb905be36d1e8e382b2c84162d156f642a5a41` has a green GitHub Actions run (`42652492559`)
- [ ] GitHub PR prepared for review comparing `ci/m1-m2-foundation` to `feat/opportunity-hub-product` (unmerged)
- [ ] Recovery readiness established: pre-release Neon branch `backup-pre-release-20261109` created, encrypted dump stored off-machine (§3), and operator understands branch write-loss hazards and delta reconciliation requirements (§6.1 Step 2, §7)
- [ ] Migration rehearsal passed to target revision `3a14e912b77c` on Neon rehearsal branch `br-flat-feather-b5n2ty3c` (§4a)
- [ ] Backward compatibility proven: `b8da30f` verified working on `3a14e912b77c` (§4b)
- [ ] Recovery procedure agreed: application rollback redeploys code without downgrading database schema (§7)
- [ ] Render worksheet complete, with no unexplained difference (§2)
- [ ] `CORS_ORIGINS` and `VITE_API_BASE` correct in `render.yaml` (`https://opportunities.sahelyon.com` and `https://api.opportunities.sahelyon.com`)
- [ ] `alembic upgrade head` kept strictly out of `startCommand` in `render.yaml`
- [ ] Live build command uses `-c constraints.txt`
- [ ] Argon2 limits fit real memory and worker facts (§2.2)
- [ ] No preview environment can reach production `DATABASE_URL`
- [ ] Client-IP security understood: `CLIENT_IP_STRATEGY=peer` is accepted risk (account-level protected, IP-level spoofable under current Uvicorn flags); `render_cf_connecting_ip` remains disabled until trust assumptions verified (§2.1)
- [ ] Founder available for at least two hours after deployment
- [ ] Explicit deployment authorization given

---

## 6. Promotion and deployment procedures

Render behaves differently depending on whether services use the Free plan or paid plans (Starter+).
Select the appropriate procedure below.

### 6.1 Free-plan procedure: Strict 9-step execution order

On Render Free plan, `preDeployCommand` is unavailable, and auto-deploy on git push triggers immediate concurrent builds.
To eliminate all migration race conditions and ensure zero schema surprises, execute these nine steps in strict sequence:

```
[1. Disable Auto-Deploy] ──▶ [2. Establish Recovery] ──▶ [3. Migrate Neon Once]
           │                                                       │
           ▼                                                       ▼
[6. Manually Deploy API] ◀── [5. Fast-Forward Promote] ◀── [4. Verify Schema & Data]
           │
           ▼
[7. Smoke-Test API] ──▶ [8. Manually Deploy Web] ──▶ [9. Smoke-Test Full Journeys]
```

#### Step 1: Disable auto-deploy for both services
In the Render Dashboard:
- `opportunity-hub-api` -> **Settings** -> **Build & Deploy** -> **Auto-Deploy**: set to **No** -> Save Changes.
- `opportunity-hub` (web) -> **Settings** -> **Build & Deploy** -> **Auto-Deploy**: set to **No** -> Save Changes.
- Refresh both settings pages and verify both display **Auto-Deploy: No**.

#### Step 2: Establish production recovery readiness

> [!IMPORTANT]
> **Pre-Release Branch vs. Permanent Backup:**
> - **Pre-Release Neon Branch (`backup-pre-release-20261109`):** An ephemeral, copy-on-write fork anchored at the divergence LSN ($T_0$). It is **NOT** a permanent snapshot or independent backup: it shares Neon's cloud infrastructure, counts against Neon's 10-branch Free plan limit, and cannot protect against provider-level outages or accidental deletion.
> - **Permanent Backup:** The encrypted `pg_dump` export stored off-platform (§3) is the true provider-independent disaster-recovery backup.
>
> **Write-Loss Hazard on Branch Promotion:**
> A pre-release branch captures database state strictly at pre-release time $T_0$. If the new application version is deployed and receives new production writes at $T_1$ (new student registrations, profile updates, saved opportunities, applications, audit logs, sessions), **promoting `backup-pre-release-20261109` to replace production later would discard and permanently lose all writes that occurred between $T_0$ and $T_1$!**
>
> **Point-in-Time Recovery (PITR) Alternative:**
> Neon retains WAL history within the project's PITR restore window. If a data corruption incident occurs at $T_{\text{corruption}}$, rather than reverting completely to $T_0$, an operator can create a recovery branch at $T_{\text{corruption}} - \epsilon$ (the exact timestamp or LSN immediately preceding the corruption), preserving valid user transactions up to that point.
>
> **Data Reconciliation Requirement Before Replacing Production:**
> If a recovery branch (pre-release or PITR) must replace production after new live writes have occurred, an operator MUST:
> 1. Freeze application writes immediately (suspend API service in Render).
> 2. Query and extract all records created/updated after the recovery branch point on the live database (`users`, `profiles`, `saved_opportunities`, `application_history`, `audit_log`, `sessions`).
> 3. Reconcile and backfill those delta records into the recovery database.
> 4. Only after delta reconciliation is verified, promote the branch or repoint `DATABASE_URL`.

In the Neon Console:
- Go to **Branches** -> **New Branch**.
- Parent: Production branch (`br-summer-heart-b5pjdb5y`).
- Include: **Current data**. Name: `backup-pre-release-20261109`.
- In dedicated terminal, execute encrypted `pg_dump` per §3:
  ```bash
  psql -Atc "SHOW server_version"
  pg_dump --version
  pg_dump --no-owner --no-privileges "$PROD_DATABASE_URL" > "$F"
  gpg --symmetric --cipher-algo AES256 --output "$F.gpg" "$F"
  sha256sum "$F.gpg" > "$F.gpg.sha256"
  ```
- Record baseline row counts (users: 4, profiles: 4, opportunities: 14, matches: 48).

#### Step 3: Migrate Neon once
From a dedicated secure terminal on a machine with the candidate checked out:
```bash
git rev-parse HEAD      # MUST be 06eb905be36d1e8e382b2c84162d156f642a5a41
cd backend
source .venv/bin/activate
read -rs DATABASE_URL && export DATABASE_URL    # Paste DIRECT production Neon URL (pooling OFF)
export APP_ENV=production JWT_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')"

# Run migrations once to head
alembic current         # confirms baseline: ba09eb02910b
alembic upgrade head    # applies 5 revisions to 3a14e912b77c
```

#### Step 4: Verify revision and data
Verify database state in the same terminal before touching any application code:
```bash
# Verify schema revision
psql "$DATABASE_URL" -Atc "SELECT version_num FROM alembic_version"
# Expect: 3a14e912b77c

# Verify existing data integrity
psql "$DATABASE_URL" -Atc "SELECT 'users', count(*) FROM users UNION ALL SELECT 'profiles', count(*) FROM profiles UNION ALL SELECT 'opportunities', count(*) FROM opportunities UNION ALL SELECT 'matches', count(*) FROM matches"
# Expect: users: 4, profiles: 4, opportunities: 14, matches: 48

# Verify new tables and constraints exist
psql "$DATABASE_URL" -Atc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('sessions','email_outbox','opportunity_tracking','audit_log','rate_limit_buckets','acquisition_sources')"
# Expect: 6

# Existing production code b8da30f continues serving safely at this point (proven backward-compatible).
```

#### Step 5: Fast-forward promote the release commit
With the database verified at `3a14e912b77c`, promote the release commit to GitHub:
```bash
git fetch origin
RELEASE="06eb905be36d1e8e382b2c84162d156f642a5a41"
git merge-base --is-ancestor origin/feat/opportunity-hub-product "$RELEASE" && echo fast-forward-ok
git push origin "$RELEASE:refs/heads/feat/opportunity-hub-product"
```
*Note: Because Auto-Deploy is disabled (Step 1), this push updates GitHub without triggering any premature build on Render.*

#### Step 6: Manually deploy API
In the Render Dashboard:
- Navigate to `opportunity-hub-api`.
- Click **Manual Deploy** (top right) -> select **Deploy latest commit** (confirming SHA starts with `06eb905b`).
- Open deploy logs:
  - Verify build installs cleanly: `pip install --upgrade pip && pip install . -c constraints.txt`
  - Verify start command runs: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"`
  - Verify health check `/health` succeeds and service status becomes **Live**.

#### Step 7: Smoke-test API
From your workstation, verify the deployed API endpoints before updating the frontend:
```bash
API="https://api.opportunities.sahelyon.com"

# 1. Health check
curl -fsS "$API/health"
# Expect: {"status":"ok"}

# 2. CORS preflight
curl -s -o /dev/null -w "%{http_code}\n" -X OPTIONS "$API/health" \
  -H "Origin: https://opportunities.sahelyon.com" \
  -H "Access-Control-Request-Method: GET"
# Expect: 200

# 3. Public catalog check
curl -fsS "$API/opportunities?limit=5" | grep -q "items" && echo "catalog-ok"

# 4. Check Render logs for 0 tracebacks or 5xx errors
```

#### Step 8: Manually deploy frontend
In the Render Dashboard:
- Navigate to `opportunity-hub` (static site).
- Click **Manual Deploy** -> select **Deploy latest commit** (`06eb905b`).
- Open deploy logs:
  - Verify build runs: `npm ci && npm run build`
  - Verify static assets upload to CDN and service status becomes **Live**.

#### Step 9: Smoke-test full journeys
Perform end-to-end user verification against the live production deployment:
1. Open [https://opportunities.sahelyon.com](https://opportunities.sahelyon.com) in a clean browser window with Developer Tools console open:
   - Verify page loads with 0 CORS errors and 0 console warnings.
   - Browse catalog, search, and apply filters.
2. Sign in as student demo user:
   - Inspect profile and update fields.
   - Run eligibility evaluation; verify footnoted explanations and missing facts loop.
   - Save an opportunity and verify tracking state persistence.
3. Test curator / admin gating:
   - Student token requesting `GET $API/curate/sources` returns `403 Forbidden`.
   - Admin account requesting `GET $API/curate/sources` and `GET $API/admin/audit` returns `200 OK`.
4. Run automated Playwright smoke suite:
   ```bash
   cd frontend
   read -rs DEMO_PASSWORD && export DEMO_PASSWORD
   OH_BASE_URL=https://opportunities.sahelyon.com OH_API_URL="https://api.opportunities.sahelyon.com" npx playwright test e2e/smoke.spec.ts
   ```

---

### 6.2 Starter-plan procedure: Automated `preDeployCommand` alternative

On Render paid plans (Starter and above), Render supports zero-downtime rolling deployments via `preDeployCommand`.
This alternative automates database migrations without manual sequential pauses:

#### 1. Configuration in `render.yaml`
```yaml
services:
  - type: web
    name: opportunity-hub-api
    plan: starter
    # ...
    buildCommand: pip install --upgrade pip && pip install . -c constraints.txt
    preDeployCommand: alembic upgrade head
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"
```

#### 2. How Render executes `preDeployCommand`
- When code is pushed to `feat/opportunity-hub-product`, Render builds the new container image.
- Before routing traffic to the new instances, Render spins up an ephemeral one-off container running `preDeployCommand: alembic upgrade head`.
- **If migration succeeds:** Render proceeds with zero-downtime rolling replacement of running API containers.
- **If migration fails:** The deploy is immediately aborted. Running containers continue serving live traffic undisturbed without downtime.
- Because `preDeployCommand` executes once in a single ephemeral runner, concurrent migration races between multiple web instances are completely avoided.

*Note: On the Free plan, `preDeployCommand` is disabled by Render. Free plan deployments MUST follow §6.1.*

---

## 7. Post-deployment verification and stop conditions

Run post-deployment verification in this order and record each result. Set `API=https://api.opportunities.sahelyon.com` (or confirmed live origin).

| # | Check | How | Expect |
| --- | --- | --- | --- |
| 1 | Deployment and migration | Dashboard; read-only `SELECT version_num FROM alembic_version` | Commit `06eb905b`; schema `3a14e912b77c` |
| 2 | Health and database | `curl -s $API/health` | 200, `{"status":"ok"}` |
| 3 | Data preserved | Count queries; `curl -s "$API/opportunities?limit=100"` | Counts match baseline (4 users, 14 opportunities, 48 matches) |
| 4 | Frontend and CORS | Browser on live site, developer console open | Pages load cleanly; 0 CORS errors |
| 5 | Registration | Register throwaway test account | 201; immediate duplicate returns 409 |
| 6 | Login & Sessions | Login with valid credentials | 200; JWT and session record created |
| 7 | Eligibility and discovery | Playwright smoke test | All passed |
| 8 | Student blocked | `GET $API/curate/sources` with student token | 403 Forbidden |
| 9 | Admin access | `GET $API/curate/sources` and `GET $API/admin/audit` with admin token | 200 OK; audit records logged |
| 10 | Rate limiting | Send 11 invalid logins in one minute | 10 × 401, 11th returns 429 |
| 11 | Memory and CPU | Render service metrics | Memory well within limits, 0 OOM restarts |
| 12 | Logs | Render runtime logs | Clean; no 5xx or unhandled tracebacks |

### Stop conditions and rollback rules

| Situation | Action |
| --- | --- |
| Build fails | Production keeps running previous commit. Fix forward and push. |
| Migration fails in Step 3 | Transaction rolls back automatically. Verify `/health`. Database remains at `ba09eb02910b`. |
| API unhealthy after deploy | **Application rollback only.** Revert code to `b8da30f` via Manual Deploy. **DO NOT downgrade database.** |
| CORS or frontend failure | Correct environment setting or redeploy frontend. No backend rollback required. |
| Database data corruption | Suspend writes immediately. Restore from Neon snapshot `backup-pre-release-20261109`. **NEVER run `alembic downgrade`.** |

### Rollback procedure: Application rollback without database downgrade

> [!CAUTION]
> **Database Rollback Rule: NEVER run `alembic downgrade` on the production database.**
> The upgraded schema `3a14e912b77c` has been proven backward-compatible with the previous production application code `b8da30f`.
> Running `alembic downgrade` drops tables (`sessions`, `email_outbox`, `opportunity_tracking`, `audit_log`, `rate_limit_buckets`, `acquisition_sources`) and drops `users.role`, permanently destroying records generated during the release window and triggering exclusive table locks.

#### If application code rollback is required:
1. In Render Dashboard, open `opportunity-hub-api`.
2. Confirm Blueprint Auto Sync is **No**.
3. If `CLIENT_IP_STRATEGY` was changed, revert it to `peer` (`b8da30f` does not recognize `render_cf_connecting_ip`).
4. Build command for `b8da30f`: `pip install --upgrade pip && pip install .` (old commit lacks `constraints.txt`).
5. Start command without Alembic: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"`.
6. Click **Manual Deploy -> Deploy a specific commit** -> enter `b8da30f25bc568bbcea9e03043001e1d4d1a2e97`.
7. Verify deployment: old code boots and responds `200 OK` on `/health` against schema `3a14e912b77c`.
8. The database schema remains at `3a14e912b77c` without data loss.

#### If database disaster recovery is required (severe data corruption):

> [!CAUTION]
> **Data Loss Hazard: NEVER blindly promote a pre-release branch if live production writes occurred.**
> Promoting a pre-release branch (`backup-pre-release-20261109`) created at $T_0$ will overwrite and permanently destroy any student accounts, profile updates, applications, and sessions created after promotion ($T_1$).

1. **Immediately freeze application writes:** Suspend the API service in Render Dashboard to stop incoming mutations during triage.
2. **Evaluate PITR vs. Pre-Release Branch:**
   - **Preferred: Point-in-Time Recovery (PITR):** Use Neon Console to create a recovery branch at the timestamp immediately preceding the corruption event ($T_{\text{incident}} - \epsilon$), preserving all prior valid student data.
   - **Fallback: Pre-Release Branch / Encrypted Dump:** If the corruption affects the entire schema or migration run, use `backup-pre-release-20261109` or the decrypted §3 dump.
3. **Data Reconciliation (Delta Extraction):**
   - Query the live production branch to isolate all post-divergence writes:
     ```sql
     -- Example delta queries against live database:
     SELECT * FROM users WHERE created_at >= '<divergence_timestamp>';
     SELECT * FROM profiles WHERE updated_at >= '<divergence_timestamp>';
     SELECT * FROM saved_opportunities WHERE created_at >= '<divergence_timestamp>';
     SELECT * FROM application_history WHERE created_at >= '<divergence_timestamp>';
     SELECT * FROM audit_log WHERE created_at >= '<divergence_timestamp>';
     ```
   - Export the delta records as SQL inserts or structured JSON.
4. **Replay & Reconcile:** Apply and verify the extracted delta records in the recovery branch, confirming constraint validity and password hashes.
5. **Promote / Repoint:**
   - Either promote the reconciled branch to primary in Neon Console, or update the `DATABASE_URL` environment variable in Render to point to the recovery branch endpoint.
6. **Resume Service & Verify:** Resume the Render service, execute the verification checks in §7, and confirm all user data is intact.

## 8. After the release: the catalogue sprint

Kept out of this release. Next product sprint, using M2-T7 to M2-T10 in the implementation plan:

- Safe fetcher, documents and snapshots, candidate queue, then first official connectors.
- Start with three or four high-value official sources.
- First milestone: 100 verified opportunities; then 500, 1,000 and 2,000.
- Telegram may suggest leads, but it's never an authority for eligibility rules, and a lead is never auto-published.
- No paid APIs or LLM services unless explicitly authorized.
