"""Cookie-authenticated mutating requests: the Origin/Referer must match an allowed origin exactly."""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from app.api.deps import _origin_of
from app.core.config import settings
from app.core.security import hash_password
from app.db.session import get_db
from app.main import app
from app.models import User

ALLOWED = "https://opportunities.sahelyon.com"


@pytest.mark.parametrize(
    "value, expected",
    [
        (ALLOWED, ALLOWED),
        ("HTTPS://Opportunities.Sahelyon.com:443/", ALLOWED),
        (f"{ALLOWED}/curate?tab=1", ALLOWED),  # a Referer carries a path
        ("https://opportunities.sahelyon.com.evil.example", "https://opportunities.sahelyon.com.evil.example"),
        ("https://opportunities.sahelyon.com:8443", "https://opportunities.sahelyon.com:8443"),
        ("null", None),
        ("javascript:alert(1)", None),
        ("https://opportunities.sahelyon.com:notaport", None),
        ("https://opportunities.sahelyon.com@evil.example", None),  # user info: the real host is evil.example
        ("https://user:pw@opportunities.sahelyon.com", None),  # browsers never send user info in Origin
        ("opportunities.sahelyon.com", None),  # no scheme
        ("https://", None),
        ("https://[::1", None),  # unparsable
        ("", None),
    ],
)
def test_origin_normalisation(value, expected):
    assert _origin_of(value) == expected


@pytest.mark.parametrize(
    "origin, status",
    [
        (ALLOWED, 200),
        (f"{ALLOWED}/some/page?x=1", 200),
        ("https://opportunities.sahelyon.com.evil.example", 403),  # accepted by the old prefix match
        ("https://opportunities.sahelyon.comevil.example", 403),
        ("http://opportunities.sahelyon.com", 403),  # scheme downgrade
        ("https://opportunities.sahelyon.com:8443", 403),
        ("null", 403),
        ("https://opportunities.sahelyon.com@evil.example", 403),
        ("https://sahelyon.com", 403),  # parent domain
        ("https://api.opportunities.sahelyon.com", 403),  # sibling/sub-domain
        ("https://sibling.sahelyon.com", 403),  # same-site sibling subdomain
        ("not a url", 403),
    ],
)
async def test_cookie_requests_need_an_exactly_allowed_origin(db_session: Session, monkeypatch, origin, status):
    assert await _logout_with_cookie(db_session, monkeypatch, {"Origin": origin}) == status


async def test_an_unparsable_configured_origin_never_matches_an_unparsable_request_origin(db_session, monkeypatch):
    """Two values that both fail to parse must not compare as equal."""
    assert await _logout_with_cookie(db_session, monkeypatch, {"Origin": "null"}, configured=f"{ALLOWED},not-an-origin") == 403
    assert await _logout_with_cookie(db_session, monkeypatch, {"Origin": ALLOWED}, configured=f"{ALLOWED},not-an-origin") == 200


async def test_the_referer_is_used_when_there_is_no_origin(db_session, monkeypatch):
    assert await _logout_with_cookie(db_session, monkeypatch, {"Referer": f"{ALLOWED}/discover"}) == 200
    assert await _logout_with_cookie(db_session, monkeypatch, {"Referer": "https://evil.example/x"}) == 403


async def test_cookie_mutating_requests_without_origin_or_referer_are_rejected(db_session, monkeypatch):
    """Ambient cookie authority requires an explicit trusted origin; missing Origin and Referer must fail."""
    assert await _logout_with_cookie(db_session, monkeypatch, {}) == 403


async def test_bearer_authenticated_requests_are_exempt_from_csrf_origin_checks(db_session, monkeypatch):
    """Bearer tokens are explicit request credentials, not ambient browser authority."""
    # Untrusted origin with bearer token -> succeeds
    assert await _logout_with_cookie(db_session, monkeypatch, {"Origin": "https://evil.example"}, bearer=True) == 200
    # Missing Origin and Referer with bearer token -> succeeds
    assert await _logout_with_cookie(db_session, monkeypatch, {}, bearer=True) == 200
    # Origin: null with bearer token -> succeeds
    assert await _logout_with_cookie(db_session, monkeypatch, {"Origin": "null"}, bearer=True) == 200
    # Cross-site metadata with bearer token -> succeeds
    assert await _logout_with_cookie(db_session, monkeypatch, {"Sec-Fetch-Site": "cross-site", "Origin": "https://evil.example"}, bearer=True) == 200


async def test_fetch_metadata_and_same_site_cross_origin_requests(db_session, monkeypatch):
    """Sec-Fetch-Site alone does not distinguish authorized from unauthorized same-site subdomains.

    Both legitimate frontend (opportunities.sahelyon.com) and attacker subdomains
    (sibling.sahelyon.com) produce Sec-Fetch-Site: same-site when requesting api.opportunities.sahelyon.com.
    CSRF defense must strictly enforce that the Origin/Referer matches settings.cors_origins.
    """
    # Allowed origin with same-site metadata -> 200
    assert await _logout_with_cookie(
        db_session, monkeypatch,
        {"Sec-Fetch-Site": "same-site", "Origin": ALLOWED},
    ) == 200
    # Sibling subdomain with same-site metadata -> 403
    assert await _logout_with_cookie(
        db_session, monkeypatch,
        {"Sec-Fetch-Site": "same-site", "Origin": "https://sibling.sahelyon.com"},
    ) == 403
    # Same-site metadata but missing Origin and Referer -> 403
    assert await _logout_with_cookie(
        db_session, monkeypatch,
        {"Sec-Fetch-Site": "same-site"},
    ) == 403
    # Cross-site metadata with untrusted origin -> 403
    assert await _logout_with_cookie(
        db_session, monkeypatch,
        {"Sec-Fetch-Site": "cross-site", "Origin": "https://evil.example"},
    ) == 403


async def test_other_cookie_mutating_endpoints_enforce_csrf(db_session: Session, monkeypatch):
    """CSRF validation protects any mutating endpoint resolved through get_current_user."""
    monkeypatch.setattr(settings, "CORS_ORIGINS", ALLOWED)
    user = User(email=f"csrf-del-{uuid.uuid4().hex[:8]}@example.org", password_hash=hash_password("csrf-password-1"), is_active=True)
    db_session.add(user)
    db_session.flush()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            token = (await client.post("/auth/login", json={"email": user.email, "password": "csrf-password-1"})).json()["access_token"]
            cookie_auth = {"Cookie": f"oh_session={token}"}

            # 1. Missing Origin on /me/account/request-deletion -> 403
            res_missing = await client.post("/me/account/request-deletion", headers=cookie_auth)
            assert res_missing.status_code == 403
            assert res_missing.json()["detail"] == "CSRF validation failed."

            # 2. Untrusted Origin on /me/account/request-deletion -> 403
            res_evil = await client.post("/me/account/request-deletion", headers={**cookie_auth, "Origin": "https://evil.example"})
            assert res_evil.status_code == 403

            # 3. Allowed Origin on /me/account/request-deletion -> 200 (passes CSRF to handler)
            res_ok = await client.post("/me/account/request-deletion", headers={**cookie_auth, "Origin": ALLOWED})
            assert res_ok.status_code == 200

            # 4. Bearer token without Origin on fresh session -> 200 (bearer exempt from CSRF)
            fresh_token = (await client.post("/auth/login", json={"email": user.email, "password": "csrf-password-1"})).json()["access_token"]
            res_bearer = await client.post("/me/account/cancel-deletion", headers={"Authorization": f"Bearer {fresh_token}"})
            assert res_bearer.status_code == 200
    finally:
        app.dependency_overrides.clear()


async def test_empty_or_invalid_cors_origins_rejects_cookie_auth_mutations_fail_closed(db_session: Session, monkeypatch):
    """CSRF must fail closed: if the configured allowlist is empty or has only invalid origins,

    cookie-authenticated mutations must be rejected (403), while bearer-token requests still work (200).
    """
    # 1. Empty allowlist rejects cookie mutation even if Origin is provided
    assert await _logout_with_cookie(db_session, monkeypatch, {"Origin": ALLOWED}, configured="") == 403
    # 2. Empty allowlist rejects cookie mutation when Origin is omitted
    assert await _logout_with_cookie(db_session, monkeypatch, {}, configured="") == 403
    # 3. Allowlist with only invalid origins rejects cookie mutation
    assert await _logout_with_cookie(db_session, monkeypatch, {"Origin": ALLOWED}, configured="invalid:origin,null") == 403
    # 4. Valid configured origin permits legitimate cookie-authenticated mutation
    assert await _logout_with_cookie(db_session, monkeypatch, {"Origin": ALLOWED}, configured=ALLOWED) == 200
    # 5. Bearer-token requests continue to work when the origin allowlist is empty
    assert await _logout_with_cookie(db_session, monkeypatch, {"Origin": ALLOWED}, configured="", bearer=True) == 200
    assert await _logout_with_cookie(db_session, monkeypatch, {}, configured="", bearer=True) == 200


async def _logout_with_cookie(db_session: Session, monkeypatch, headers: dict, *, configured: str = ALLOWED, bearer: bool = False) -> int:
    monkeypatch.setattr(settings, "CORS_ORIGINS", configured)
    user = User(email=f"csrf-{uuid.uuid4().hex[:8]}@example.org", password_hash=hash_password("csrf-password-1"), is_active=True)
    db_session.add(user)
    db_session.flush()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            token = (await client.post("/auth/login", json={"email": user.email, "password": "csrf-password-1"})).json()["access_token"]
            client.cookies.clear()
            auth = {"Authorization": f"Bearer {token}"} if bearer else {"Cookie": f"oh_session={token}"}
            response = await client.post("/auth/logout", headers={**auth, **headers})
    finally:
        app.dependency_overrides.clear()
    return response.status_code
