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
pip install -e ".[dev]"
```

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
- `POST /opportunities` is curator-only: it requires the `X-Admin-Token` header to match
  `ADMIN_API_TOKEN`. With no token configured, creation is disabled.
- Match endpoints treat draft and archived opportunities as not found.

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
