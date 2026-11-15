"""Regression tests for the fresh-review cleanup round (FRESH_SECURITY_REVIEW_2026-11-14.md).

F-1 legacy raw-token outbox rows, F-3 atomic reset-queue ceiling, F-4 APP_ENV normalisation and the
session cookie's Secure flag, F-6 the e2e database guard, F-7 hermetic "unset" configuration.
F-8 (wording) and F-9 (e2e process cleanup) are covered by the Playwright suite and by running
``scripts/e2e.sh`` (see the implementation report).
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app import cli
from app.core.config import Settings, settings
from app.core.security import hash_password
from app.db.session import get_db
from app.main import app
from app.models import EmailOutbox, EmailToken, User
from app.services.email_worker import (
    LEGACY_CANCEL_REASON,
    LocalTestEmailAdapter,
    cancel_legacy_outbox,
    legacy_outbox_report,
    process_outbox,
)
from app.services.password_reset import ResetOutcome, request_password_reset
from scripts.seed_e2e_fixtures import throwaway_database_problems

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _settings(**values) -> Settings:
    return Settings(_env_file=None, DATABASE_URL="postgresql://u@h/db", JWT_SECRET="s" * 40, **values)


# --- F-1: legacy raw-token outbox rows -------------------------------------------------------------------


def _legacy(db_session: Session, status: str = "pending") -> EmailOutbox:
    row = EmailOutbox(to_address="legacy@example.org", template="password_reset", params={"token": "raw-legacy-token-value"},
                      status=status, send_after=datetime.now(timezone.utc), dedupe_key=f"legacy:{uuid.uuid4().hex}")
    db_session.add(row)
    db_session.flush()
    return row


def test_the_worker_never_sends_a_legacy_message(db_session):
    row = _legacy(db_session)
    mailbox = LocalTestEmailAdapter()
    assert process_outbox(db_session, adapter=mailbox) == 0
    assert mailbox.outbox == []
    assert (row.status, row.last_error) == ("cancelled", LEGACY_CANCEL_REASON)
    assert "token" not in row.params


def test_the_report_counts_legacy_rows_without_reading_token_material(db_session):
    _legacy(db_session)
    _legacy(db_session, status="sent")
    report = {(status, template): count for status, template, count, _, _ in legacy_outbox_report(db_session)}
    assert report[("pending", "password_reset")] >= 1 and report[("sent", "password_reset")] >= 1
    assert "raw-legacy-token-value" not in repr(legacy_outbox_report(db_session))


def test_cancel_quarantines_pending_rows_and_scrubs_every_legacy_row(db_session):
    pending, sent = _legacy(db_session), _legacy(db_session, status="sent")
    cancelled, scrubbed = cancel_legacy_outbox(db_session)
    db_session.expire_all()
    assert cancelled >= 1 and scrubbed >= 2
    assert (pending.status, pending.last_error) == ("cancelled", LEGACY_CANCEL_REASON)
    assert sent.status == "sent"  # history kept, token stripped
    assert "token" not in pending.params and "token" not in sent.params
    assert legacy_outbox_report(db_session) == []


def test_the_cancel_command_requires_confirmation(capsys):
    assert cli.main(["legacy-email-outbox", "--cancel"]) == 1
    assert "--yes" in capsys.readouterr().err


def test_new_messages_are_never_classified_as_legacy(db_session):
    user = User(email=f"new-{uuid.uuid4().hex[:8]}@example.org", password_hash="x", is_active=True)
    db_session.add(user)
    db_session.flush()
    assert request_password_reset(db_session, user.email) == ResetOutcome.QUEUED
    assert db_session.scalar(select(func.count()).select_from(EmailOutbox).where(
        EmailOutbox.user_id == user.id, EmailOutbox.params.has_key("token"))) == 0


# --- F-3: the global reset-queue ceiling under concurrency -----------------------------------------------


@pytest.fixture
def committed_accounts():
    engine = create_engine(settings.DATABASE_URL)
    factory = sessionmaker(engine)
    with factory.begin() as db:
        users = [User(email=f"ceiling-{uuid.uuid4().hex[:10]}@example.org", password_hash="x", is_active=True) for _ in range(20)]
        db.add_all(users)
        db.flush()
        ids, emails = [u.id for u in users], [u.email for u in users]
    yield factory, ids, emails
    with factory.begin() as db:
        db.execute(delete(EmailOutbox).where(EmailOutbox.user_id.in_(ids)))
        db.execute(delete(EmailToken).where(EmailToken.user_id.in_(ids)))
        db.execute(delete(User).where(User.id.in_(ids)))
    engine.dispose()


def test_twenty_concurrent_requests_cannot_exceed_a_ceiling_of_ten(committed_accounts, monkeypatch):
    factory, ids, emails = committed_accounts
    with factory() as db:
        baseline = db.scalar(select(func.count()).select_from(EmailOutbox).where(
            EmailOutbox.template == "password_reset", EmailOutbox.status == "pending"))
    monkeypatch.setattr(settings, "PASSWORD_RESET_MAX_PENDING", baseline + 10)
    barrier, outcomes = threading.Barrier(len(emails)), []

    def request(email: str) -> None:
        with factory() as db:
            barrier.wait()
            outcomes.append(request_password_reset(db, email))
            db.commit()

    threads = [threading.Thread(target=request, args=(email,)) for email in emails]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert outcomes.count(ResetOutcome.QUEUED) == 10
    assert outcomes.count(ResetOutcome.QUEUE_FULL) == 10
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(EmailOutbox).where(EmailOutbox.user_id.in_(ids))) == 10


# --- F-4: APP_ENV normalisation --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [(" production", "production"), ("PRODUCTION\n", "production"), ("Prod", "production"),
     ("development", "development"), (" DEV ", "development"), ("test", "test")],
)
def test_app_env_is_trimmed_lower_cased_and_aliased(raw, expected):
    configured = _settings(APP_ENV=raw)
    assert configured.APP_ENV == expected
    assert configured.is_production is (expected == "production")


@pytest.mark.parametrize("raw", ["staging", "", "   ", "productoin", "production-eu", "live"])
def test_unknown_app_env_values_are_refused(raw):
    with pytest.raises(ValidationError, match="APP_ENV must be one of"):
        _settings(APP_ENV=raw)


def test_missing_app_env_means_development_off_render(monkeypatch):
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)  # CI sets APP_ENV for the whole job
    assert _settings().APP_ENV == "development"


def test_missing_app_env_is_refused_on_render(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("APP_ENV", raising=False)  # CI sets APP_ENV for the whole job
    with pytest.raises(ValidationError, match="APP_ENV must be set explicitly on Render"):
        _settings(CLIENT_IP_STRATEGY="none")
    assert _settings(APP_ENV=" Production ", CLIENT_IP_STRATEGY="none").is_production


def test_malformed_production_values_can_no_longer_disable_production_controls():
    for raw in (" production", "PROD"):
        with pytest.raises(ValidationError, match="refused in production"):
            _settings(APP_ENV=raw, AUTH_RATE_LIMIT_PER_MINUTE="disabled")
        with pytest.raises(ValidationError, match="tests only"):
            _settings(APP_ENV=raw, EMAIL_DELIVERY="memory", EMAIL_TOKEN_KEYS="k1:" + "x" * 40, EMAIL_TOKEN_ACTIVE_KEY="k1")


@pytest.mark.parametrize("app_env, secure", [("production", True), ("development", False)])
async def test_the_session_cookie_secure_flag_follows_is_production(db_session, monkeypatch, app_env, secure):
    monkeypatch.setattr(settings, "APP_ENV", app_env)
    user = User(email=f"cookie-{uuid.uuid4().hex[:8]}@example.org", password_hash=hash_password("cookie-password-1"), is_active=True)
    db_session.add(user)
    db_session.flush()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            response = await client.post("/auth/login", json={"email": user.email, "password": "cookie-password-1"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert ("; secure" in cookie) is secure and "httponly" in cookie


# --- F-6: the e2e database guard -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://ohub_ci:pw@localhost:5432/opportunity_hub_e2e",  # the GitHub Actions service
        "postgresql://u@127.0.0.1:5433/oh_e2e",
        "postgresql://u@[::1]:5433/oh_test",
        "postgresql://u@/oh_e2e?host=/tmp/pg-socket",
    ],
)
def test_local_throwaway_targets_are_accepted(url):
    assert throwaway_database_problems(url, environ={}) == []


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u@localhost:5433/oh_e2e?sslmode=disable",
        "postgresql+psycopg2://u@127.0.0.1/oh_e2e?connect_timeout=5&application_name=e2e",
        "postgres://u@localhost/oh_e2e",  # the scheme some hosts hand out; normalised by the settings
    ],
)
def test_harmless_parameters_and_scheme_variants_are_accepted(url):
    from app.core.config import Settings as _S

    assert throwaway_database_problems(_S.normalize_postgres_scheme(url), environ={}) == []


@pytest.mark.parametrize(
    "url",
    [
        # RC-1: query parameters that libpq applies over the URL's apparent host and path.
        "postgresql://u@localhost/oh_e2e?host=db.neon.tech",
        "postgresql://u@localhost:5433/oh_e2e?host=db.example.neon.tech",
        "postgresql://u@localhost/oh_e2e?%68ost=db.neon.tech",  # percent-encoded parameter name
        "postgresql://u@localhost/oh_e2e?h%6Fst=db.neon.tech",
        "postgresql://u@localhost/oh_e2e?host=localhost",  # even a same-value override is ambiguous
        "postgresql://u@localhost/oh_e2e?host=/tmp",  # host given twice (URL and socket)
        "postgresql://u@localhost/oh_e2e?hostaddr=203.0.113.5",
        "postgresql://u@localhost/oh_e2e?hostaddr=127.0.0.1",
        "postgresql://u@localhost/oh_e2e?port=6543",
        "postgresql://u@localhost/oh_e2e?dbname=opportunity_hub",
        "postgresql://u@localhost/oh_e2e?d%62name=opportunity_hub",
        "postgresql://u@localhost/oh_e2e?service=prod",
        "postgresql://u@localhost/oh_e2e?servicefile=/tmp/pg_service.conf",
        "postgresql://u@localhost/oh_e2e?options=-c%20search_path%3Dpublic",
        "postgresql://u@localhost/oh_e2e?HOST=db.neon.tech",  # not a libpq keyword; still refused
        # Repeated parameters become libpq multi-host lists.
        "postgresql://u@/oh_e2e?host=/tmp&host=db.neon.tech",
        "postgresql://u@localhost/oh_e2e?sslmode=disable&sslmode=require",
        # Multi-host values.
        "postgresql://u@/oh_e2e?host=/tmp,db.neon.tech",
        "postgresql://u@localhost,db.neon.tech/oh_e2e",
        # Other drivers: the guard can only vouch for the psycopg2 path the project uses.
        "postgresql+asyncpg://u@localhost/oh_e2e",
    ],
)
def test_parameters_that_could_redirect_the_connection_are_refused(url):
    assert throwaway_database_problems(url, environ={}), url


@pytest.mark.parametrize("variable", ["PGHOSTADDR", "PGSERVICE"])
def test_libpq_environment_redirection_is_refused(variable):
    problems = throwaway_database_problems("postgresql://u@localhost/oh_e2e", environ={variable: "x"})
    assert any(variable in problem for problem in problems)


def test_the_name_checked_is_the_one_libpq_receives():
    # SQLAlchemy passes a percent-encoded path to libpq verbatim, so "oh%5Fe2e" is not "oh_e2e".
    assert throwaway_database_problems("postgresql://u@localhost/oh%5Fe2e", environ={})


@pytest.mark.parametrize(
    "url, reason",
    [
        ("postgresql://u@ep-x.eu-central-1.aws.neon.tech/opportunity_hub_e2e", "host"),  # remote, test-like name
        ("postgresql://u@db.internal:5432/staging_test", "host"),
        ("postgresql://u@localhost.attacker.example/oh_e2e", "host"),
        ("postgresql://u@10.0.0.5/oh_e2e", "host"),
        ("postgresql://u@localhost:5433/opportunity_hub", "name"),  # the developer's real database
        ("postgresql://u@localhost/production", "name"),
        ("postgresql://u@localhost/latest_data", "name"),  # "test" inside a word doesn't count
        ("postgresql://u@/oh_e2e", "explicit"),  # ambiguous: libpq default host
        ("sqlite:///oh_e2e.db", "PostgreSQL"),
        ("::not a url::", "parsed"),
    ],
)
def test_unsafe_or_ambiguous_targets_are_refused(url, reason):
    problems = throwaway_database_problems(url, environ={})
    assert problems and any(reason in problem for problem in problems)


def test_production_is_refused_whatever_the_target():
    assert "APP_ENV is production" in throwaway_database_problems("postgresql://u@localhost/oh_e2e", production=True, environ={})


def test_the_fixture_script_refuses_before_touching_the_database():
    env = {**os.environ, "APP_ENV_FILE": "", "APP_ENV": "development", "JWT_SECRET": "j" * 40,
           "DATABASE_URL": "postgresql://u@ep-x.neon.tech/opportunity_hub_e2e"}
    result = subprocess.run([sys.executable, "-m", "scripts.seed_e2e_fixtures", "--check-only"],
                            cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode != 0 and "Refusing e2e fixtures" in result.stderr


# --- F-7: "unset" really means unset ---------------------------------------------------------------------


def _effective_limit(env_file: str, tmp_path: Path) -> str:
    env = {key: value for key, value in os.environ.items() if key != "AUTH_RATE_LIMIT_PER_MINUTE"}
    env.update({"APP_ENV_FILE": env_file, "APP_ENV": "development", "DATABASE_URL": "postgresql://u@h/db", "JWT_SECRET": "j" * 40})
    code = "import sys; sys.path.insert(0, %r); from app.core.config import settings; print(settings.auth_rate_limit)" % str(BACKEND_DIR)
    return subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60).stdout.strip()


def test_app_env_file_controls_the_dotenv_file_and_empty_disables_it(tmp_path):
    dotenv = tmp_path / "custom.env"
    dotenv.write_text("AUTH_RATE_LIMIT_PER_MINUTE=3\n")
    assert _effective_limit(str(dotenv), tmp_path) == "3"  # a file is honoured when named
    assert _effective_limit("", tmp_path) == "10"  # empty: no dotenv at all, so the true default applies
