"""Release hardening: production settings, health, credential rate limits, CORS and the production seed."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import rate_limit
from app.core.config import EXAMPLE_JWT_SECRET, Settings, settings
from app.db.session import get_db
from app.main import app
from app.models import Match, Opportunity, Profile, User
from app.services.matches import evaluate_and_persist_match_for_user
from scripts import seed_demo

BACKEND_DIR = Path(__file__).resolve().parents[1]
STRONG_SECRET = "s" * 40


def make_settings(**overrides) -> Settings:
    values = {"DATABASE_URL": "postgresql://u@h/db", "JWT_SECRET": STRONG_SECRET, **overrides}
    return Settings(_env_file=None, **values)


# --- Settings ---------------------------------------------------------------------------------


def test_production_refuses_the_example_or_a_short_jwt_secret():
    with pytest.raises(ValidationError):
        make_settings(APP_ENV="production", JWT_SECRET=EXAMPLE_JWT_SECRET)
    with pytest.raises(ValidationError):
        make_settings(APP_ENV="production", JWT_SECRET="short")
    assert make_settings(APP_ENV="production").is_production
    # Development keeps working with short local secrets.
    assert make_settings(JWT_SECRET="dev").JWT_SECRET == "dev"


def test_postgres_scheme_is_normalized_for_sqlalchemy():
    assert make_settings(DATABASE_URL="postgres://u:p@h:5432/db").DATABASE_URL == "postgresql://u:p@h:5432/db"
    assert make_settings(DATABASE_URL="postgresql://u@h/db?sslmode=require").DATABASE_URL.endswith("sslmode=require")


def test_cors_origins_must_be_explicit():
    with pytest.raises(ValidationError):
        make_settings(CORS_ORIGINS="*")
    configured = make_settings(CORS_ORIGINS="https://a.example, https://b.example")
    assert configured.cors_origins == ["https://a.example", "https://b.example"]
    assert make_settings().cors_origins == []


# --- Health -----------------------------------------------------------------------------------


async def test_health_reports_unavailable_without_the_database(monkeypatch):
    class Broken:
        def connect(self):
            raise RuntimeError("connection refused")

    monkeypatch.setattr("app.main.engine", Broken())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


# --- Credential rate limit ----------------------------------------------------------------------


@pytest.fixture
def api(db_session: Session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    rate_limit.set_limiter(None)
    rate_limit.reset()
    # A frozen clock, so a test cannot straddle a window boundary and see its counters reset.
    rate_limit.set_limiter(rate_limit.PostgresRateLimiter(rate_limit.get_limiter().engine, clock=lambda: 1_800_000_000.0))
    yield
    rate_limit.set_limiter(None)
    rate_limit.reset()
    app.dependency_overrides.clear()


async def test_login_attempts_are_limited_per_client(api, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 3)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        statuses = [
            (await client.post("/auth/login", json={"email": "nobody@example.org", "password": "wrong-password"})).status_code
            for _ in range(4)
        ]
        limited = await client.post("/auth/login", json={"email": "nobody@example.org", "password": "x"})
    assert statuses == [401, 401, 401, 429]
    assert limited.status_code == 429
    assert limited.json()["detail"].startswith("Too many attempts")
    assert int(limited.headers["Retry-After"]) >= 1


async def _login_from(address: str, email: str) -> int:
    """POST one login as if it came from ``address`` (what a forged X-Forwarded-For yields)."""
    transport = ASGITransport(app=app, client=(address, 40000))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/auth/login", json={"email": email, "password": "wrong-password"})
    return response.status_code


async def test_rotating_client_addresses_cannot_reset_one_accounts_budget(api, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 3)
    statuses = [await _login_from(f"203.0.113.{i}", "target@example.org") for i in range(1, 5)]
    assert statuses == [401, 401, 401, 429]


async def test_account_budget_ignores_email_case_and_surrounding_space(api, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 2)
    emails = ["Target@Example.org", "target@example.org", "TARGET@EXAMPLE.ORG"]
    statuses = [await _login_from(f"198.51.100.{i}", email) for i, email in enumerate(emails, 1)]
    assert statuses == [401, 401, 429]


async def test_account_budget_does_not_block_other_accounts(api, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 2)
    statuses = [await _login_from(f"192.0.2.{i}", f"user{i}@example.org") for i in range(1, 6)]
    assert statuses == [401] * 5


async def test_registration_is_budgeted_per_account(api, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 2)
    statuses = []
    for i in range(1, 4):
        transport = ASGITransport(app=app, client=(f"203.0.113.{i}", 40000))
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/auth/register", json={"email": "probe@example.org", "password": "long-enough-password"}
            )
        statuses.append(response.status_code)
    assert statuses == [201, 409, 429]


async def test_rate_limit_is_off_unless_configured(api, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        statuses = {
            (await client.post("/auth/login", json={"email": "nobody@example.org", "password": "x"})).status_code
            for _ in range(15)
        }
    assert statuses == {401}


# --- Production seed --------------------------------------------------------------------------


def _demo_profile(db_session: Session) -> Profile:
    user = db_session.scalar(select(User).where(User.email == seed_demo.DEMO_EMAIL))
    return db_session.scalar(select(Profile).where(Profile.user_id == user.id))


def test_production_seed_only_inserts_and_keeps_other_users_matches(db_session):
    seed_demo.seed(db_session, password="first-demo-password")
    someone = User(email="real-student@example.org", password_hash="x")
    db_session.add(someone)
    db_session.flush()
    profile = Profile(user_id=someone.id, full_name="Real Student", email=someone.email, degree_level="bachelor")
    db_session.add(profile)
    db_session.flush()
    opportunity = db_session.get(Opportunity, seed_demo.stable_id("opportunity", "cern-summer-student-programme"))
    evaluate_and_persist_match_for_user(db_session, profile, opportunity.id)
    opportunity_ids = {row.id for row in db_session.scalars(select(Opportunity))}

    counts = seed_demo.seed(db_session, password="second-demo-password", production=True)

    assert counts == {"opportunities_created": 0, "opportunities_refreshed": 0}
    assert {row.id for row in db_session.scalars(select(Opportunity))} == opportunity_ids
    assert db_session.scalar(select(func.count()).select_from(Match).where(Match.profile_id == profile.id)) == 1


def test_demo_user_only_resets_just_the_demo_account(db_session):
    seed_demo.seed(db_session, password="first-demo-password")
    demo = _demo_profile(db_session)
    demo.date_of_birth = demo.created_at.date().replace(year=2003)
    db_session.flush()
    before = db_session.scalar(select(func.count()).select_from(Opportunity))

    seed_demo.seed(db_session, password="second-demo-password", production=True, demo_user_only=True)

    assert _demo_profile(db_session).date_of_birth is None
    assert db_session.scalar(select(func.count()).select_from(Opportunity)) == before


def test_production_seed_requires_the_flag_and_a_strong_password(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    with pytest.raises(SystemExit, match="--allow-production"):
        seed_demo.main([])
    with pytest.raises(SystemExit, match="DEMO_PASSWORD"):
        seed_demo.main(["--allow-production"])
    monkeypatch.setenv("DEMO_PASSWORD", seed_demo.DEFAULT_DEMO_PASSWORD)
    with pytest.raises(SystemExit, match="DEMO_PASSWORD"):
        seed_demo.main(["--allow-production"])


# --- CORS and trusted hosts on a real server ----------------------------------------------------


@pytest.fixture(scope="module")
def production_server():
    """Run the API under uvicorn with production-style settings against the test database."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = {
        **os.environ,
        "APP_ENV": "production",
        "DATABASE_URL": settings.DATABASE_URL,
        "JWT_SECRET": STRONG_SECRET,
        "CORS_ORIGINS": "https://app.example.org",
        "ALLOWED_HOSTS": "127.0.0.1,api.example.org",
        "AUTH_RATE_LIMIT_PER_MINUTE": "10",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--proxy-headers"],
        cwd=BACKEND_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{base}/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        process.terminate()
        pytest.fail("production-style server did not become healthy")
    yield base
    process.terminate()
    process.wait(timeout=10)


def test_preflight_allows_only_the_configured_frontend(production_server):
    preflight = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization,content-type"}
    allowed = httpx.options(f"{production_server}/auth/login", headers={"Origin": "https://app.example.org", **preflight})
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://app.example.org"
    assert "authorization" in allowed.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-credentials" not in allowed.headers

    other = httpx.options(f"{production_server}/auth/login", headers={"Origin": "https://evil.example", **preflight})
    assert other.status_code == 400
    assert "access-control-allow-origin" not in other.headers

    listing = httpx.get(f"{production_server}/opportunities", headers={"Origin": "https://app.example.org"})
    assert listing.status_code == 200
    assert listing.headers["access-control-allow-origin"] == "https://app.example.org"


def test_unknown_hosts_are_rejected(production_server):
    assert httpx.get(f"{production_server}/health").json() == {"status": "ok"}
    assert httpx.get(f"{production_server}/health", headers={"Host": "attacker.example"}).status_code == 400
