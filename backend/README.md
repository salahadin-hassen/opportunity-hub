# Opportunity Hub - Backend

FastAPI backend for personalized opportunity discovery platform.

## Quick Start

### 1. Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies
```bash
pip install -e ".[dev]" -c constraints.txt
```
`constraints.txt` pins the exact versions CI tests. Its header explains how to upgrade them.

### 3. Configure Environment
```bash
cp .env.example .env
# Set DATABASE_URL to your development PostgreSQL database.
# Set TEST_DATABASE_URL to a separate PostgreSQL database whose name includes "test".
```

Create the dedicated test database once (for example, with `createdb opportunity_hub_test`)
and make sure `TEST_DATABASE_URL` points to it. Pytest requires this setting, rejects
database names without a distinct `test` token, and rejects the development database
name. It never falls back to `DATABASE_URL`; its Alembic migrations and SQLAlchemy
sessions both use only `TEST_DATABASE_URL`.

### 4. Run Database Migrations
```bash
alembic upgrade head
```
Creates the tables managed by Alembic: `opportunities`, `sources`, `requirements`,
`profiles`, `education`, and `test_scores`.

### 5. Run the API
```bash
uvicorn app.main:app --reload
```

### 6. Seed the demo data (optional)
```bash
python -m scripts.seed_demo
```
Creates 14 real opportunities (12 open and listed, 2 closed for this cycle), with every rule's quote copied
verbatim from its official page, a 20-entry skill catalog, and the local demo account `demo@example.org`. The
password is read from `DEMO_PASSWORD`, falling back to the script default. The script is idempotent:
running it again resets the demo profile to its starting point and removes retired rows. It refuses to run when `APP_ENV=production`.

### 7. Verify
Open http://localhost:8000/health - should return `{"status": "ok"}`

## Public API notes
- `GET /opportunities` lists **published** opportunities only. `GET /opportunities/{id}` serves
  published and closed ones and includes their `requirements` (the rules) and `sources`
  (provenance); curator-only fields such as snapshots and notes are never exposed.
- `GET /skills` returns the canonical skill catalog; there is no HTTP route that creates skills.
- `POST /opportunities` and the `/curate/sources` routes require a signed-in curator or admin;
  `/admin/audit` requires an admin. Roles are stored on `users.role`, every account starts as a
  student, and roles change only through `python -m app.cli grant-role <email> <role>`
  (audited). The old `X-Admin-Token` header and `ADMIN_API_TOKEN` setting no longer exist.
- Match endpoints treat draft and archived opportunities as not found.

## Credential rate limiting
- Off unless `AUTH_RATE_LIMIT_PER_MINUTE` is set. When on, every `/auth/login` and `/auth/register`
  attempt is counted per client address bucket and per account email (60-second fixed windows) in the
  `rate_limit_buckets` table, shared by all instances. Keys are HMAC digests, never raw addresses or emails.
  If the table can't be written, the attempt is refused with 503 (fail closed).
- The client address comes from `CLIENT_IP_STRATEGY` (`peer`, `xff_rightmost` or `header`, with
  `TRUSTED_PROXY_CIDRS`, `TRUSTED_PROXY_HOPS` and `CLIENT_IP_HEADER`; see `app/core/config.py`).
  When no trustworthy address can be established, the address budget is skipped for that request and
  the account budget still applies. A proxy address or a placeholder is never used as a bucket.
- **Production caveat:** `render.yaml` still starts uvicorn with `--proxy-headers --forwarded-allow-ips="*"`,
  under which the client chooses its own address, so the address budget can be evaded. Don't change it
  before reading `docs/architecture/RENDER_CLIENT_IP_VERIFICATION.md`. Account-lockout risks are in
  `docs/architecture/ACCOUNT_LOCKOUT_THREAT_MODEL.md`.
- Telemetry (`app/core/auth_telemetry.py`) counts throttling, degraded identity and failures with
  bounded labels, logging at most one line per event and label set per minute.
- **Argon2 capacity:**
  - Passwords use argon2-cffi defaults (Argon2id, m=64 MiB, t=3, p=4; about 130 ms on a development
    laptop).
  - At most `ARGON2_MAX_CONCURRENCY` (default 2, allowed 1–16) hashes or verifications run at once per
    process: one memory ceiling for login and registration together.
  - Registration may hold at most `ARGON2_REGISTRATION_MAX_CONCURRENCY` of those slots (default 1; it must
    not exceed the total). The rest only ever serve sign-in, so a registration flood can't refuse login.
    Login may use every free slot. With a total of 1 nothing can be reserved, and the two share the slot.
  - A slot is held only around the Argon2 call. Login checks for capacity *before* looking the account up
    (without reserving), so a saturated service refuses known and unknown emails alike, and unknown emails
    never hold a slot.
  - When no slot is available the request gets 503 with `Retry-After: 2` at once. It's never queued, never
    hashed, and never reported as a wrong password.
  - The limit is per process: total = value × uvicorn workers (`--workers`, or `WEB_CONCURRENCY` if set) ×
    instances.
  - The default suits a 512 MB container with one worker. The live limit is unmeasured, so measure before
    raising it.
- **Registration** looks the email up before hashing, so a known email gets its 409 without Argon2. The
  unique constraint on `users.email` stays the final authority for concurrent registrations.

## Eligibility engine notes
- GPA thresholds must declare `params.scale`. A profile GPA is compared only when its `gpa_scale` equals
  the threshold's scale; a different scale returns `needs_review` (`gpa_scale_mismatch`) and a threshold
  without a scale returns `needs_review` (`gpa_threshold_scale_unspecified`). Scales are never converted.
  A missing GPA stays `unknown`.
- `date_gate` supports every operator the schema allows (`<=`, `<`, `>=`, `>`, `==`, `!=`).
- `set_membership` on citizenship supports `in` and `not_in` with one value.

## Project Structure
```
backend/
├── app/
│   ├── main.py           # FastAPI app entry point
│   ├── core/config.py    # Configuration settings
│   ├── db/
│   │   ├── session.py    # SQLAlchemy engine & session
│   │   └── base.py       # Declarative base
│   ├── models/           # SQLAlchemy models + domain enums
│   └── schemas/          # Pydantic request/response schemas
├── alembic/              # Alembic env + migration versions
├── tests/                # Test suite
├── .env.example          # Environment template
└── pyproject.toml        # Dependencies
```

## Running Tests
```bash
pytest
```
Tests upgrade the dedicated test database to the latest Alembic revision and roll
back test data after each test. Configuration always reads `backend/.env`, regardless
of the current working directory.

You can run tests from the repository root as well:

```bash
pytest
```

## Database Migrations
```bash
alembic upgrade head   # apply migrations
alembic current        # show applied revision
alembic check          # verify models match the database
alembic revision --autogenerate -m "describe change"  # create a migration
```

From the repository root, pass the backend Alembic config explicitly:

```bash
alembic -c backend/alembic.ini upgrade head
alembic -c backend/alembic.ini current
alembic -c backend/alembic.ini check
```
