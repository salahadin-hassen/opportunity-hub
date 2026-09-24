"""Shared fixtures for database-backed tests, isolated from development data."""
from __future__ import annotations

import re
import sys
from collections.abc import Iterator
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config as AlembicConfig  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import settings  # noqa: E402


def _test_database_url() -> str:
    """Require an unmistakably separate test database; never use DATABASE_URL."""
    raw_test_url = settings.TEST_DATABASE_URL
    if not raw_test_url:
        raise RuntimeError(
            "TEST_DATABASE_URL must be set to a dedicated PostgreSQL database "
            "whose name contains 'test'; pytest will not use DATABASE_URL."
        )

    test_url = make_url(raw_test_url)
    development_url = make_url(settings.DATABASE_URL)
    if test_url.get_backend_name() != "postgresql":
        raise RuntimeError("TEST_DATABASE_URL must point to PostgreSQL.")
    database_name = test_url.database or ""
    if not re.search(r"(^|[^a-z])test([^a-z]|$)", database_name, re.IGNORECASE):
        raise RuntimeError(
            "TEST_DATABASE_URL database name must contain 'test' as a distinct "
            "word (for example, opportunity_hub_test)."
        )
    if database_name == development_url.database:
        raise RuntimeError(
            "TEST_DATABASE_URL points to the development database. "
            "Configure a different database; pytest will not migrate it."
        )
    return raw_test_url


TEST_DATABASE_URL = _test_database_url()
# Make even application code that imports app.db.session during pytest use the
# test database. This happens in conftest before test modules are imported.
settings.DATABASE_URL = TEST_DATABASE_URL
test_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)


@pytest.fixture(scope="session", autouse=True)
def _database_schema() -> Iterator[None]:
    """Bring the database to the latest migration before tests run."""
    config = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["database_url"] = TEST_DATABASE_URL
    command.upgrade(config, "head")
    yield
    test_engine.dispose()


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Session whose transaction is rolled back after every test.

    All test work runs on one connection inside a single explicit
    transaction, so tests never leave rows behind in the shared
    isolated test database and can assume a clean slate for their own data.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
