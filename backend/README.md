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

### 6. Verify
Open http://localhost:8000/health - should return `{"status": "ok"}`

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
