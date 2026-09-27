"""Integration coverage for auth slice 2: registration, login, token loop.

Every test runs inside the transaction provided by ``db_session`` and is
rolled back afterwards, so the dedicated test database stays clean. Tokens
are signed with a test-only secret (monkeypatched onto settings) and no
external auth service is ever contacted.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import jwt
import pytest
from app.api.deps import INVALID_CREDENTIALS_DETAIL, get_current_user
from app.core.config import settings
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.main import app
from app.models import Profile, User
from fastapi.security import HTTPAuthorizationCredentials
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.conftest import test_engine
from tests.test_auth import TEST_JWT_SECRET, TEST_PASSWORD, make_profile, make_user


@pytest.fixture
def auth_secret(monkeypatch) -> str:
    """Point token signing at a test-only secret for one test."""
    monkeypatch.setattr(settings, "JWT_SECRET", TEST_JWT_SECRET)
    return TEST_JWT_SECRET


@pytest.fixture
async def client(db_session: Session, auth_secret: str):
    """Use the existing transaction-bound test session for API requests."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()


def register_payload(**overrides) -> dict:
    payload = {
        "email": f"signup-{uuid.uuid4().hex[:10]}@example.org",
        "password": TEST_PASSWORD,
    }
    payload.update(overrides)
    return payload


async def registered_user(client: AsyncClient, **overrides) -> tuple[dict, dict]:
    """Register one account and return ``(request_payload, response_body)``."""
    payload = register_payload(**overrides)
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 201
    return payload, response.json()


async def login_token(client: AsyncClient, payload: dict) -> str:
    """Log in with the credentials from ``payload`` and return the token."""
    response = await client.post(
        "/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def decode_claims(token: str) -> dict:
    return jwt.decode(token, TEST_JWT_SECRET, algorithms=["HS256"])


# --- Registration --------------------------------------------------------------------------

async def test_valid_registration_succeeds(client: AsyncClient):
    payload = register_payload()
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == payload["email"]
    assert body["is_active"] is True
    assert uuid.UUID(body["id"])
    assert body["created_at"] and body["updated_at"]


async def test_registration_returns_only_safe_user_fields(client: AsyncClient):
    _, body = await registered_user(client)
    assert set(body) == {"id", "email", "is_active", "created_at", "updated_at"}


async def test_registration_never_returns_password_material(client: AsyncClient):
    payload = register_payload()
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert "password" not in body
    assert "password_hash" not in body
    assert payload["password"] not in response.text


async def test_stored_password_is_an_argon2id_hash(client: AsyncClient, db_session: Session):
    payload, _ = await registered_user(client)
    user = db_session.scalar(select(User).where(User.email == payload["email"]))
    assert user is not None
    assert user.password_hash.startswith("$argon2id$")
    assert verify_password(payload["password"], user.password_hash)
    assert not verify_password("wrong-password-attempt", user.password_hash)


async def test_plaintext_password_is_never_stored(client: AsyncClient, db_session: Session):
    payload, _ = await registered_user(client)
    user = db_session.scalar(select(User).where(User.email == payload["email"]))
    assert payload["password"] not in user.password_hash


async def test_duplicate_email_registration_conflicts(client: AsyncClient):
    payload = register_payload()
    first = await client.post("/auth/register", json=payload)
    second = await client.post("/auth/register", json=payload)
    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["detail"] == "An account with this email already exists."


async def test_invalid_email_is_rejected(client: AsyncClient):
    payload = register_payload(email="not-an-email")
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 422


async def test_too_short_password_is_rejected(client: AsyncClient):
    payload = register_payload(password="short7c")
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 422


async def test_forbidden_registration_fields_are_rejected(client: AsyncClient, db_session: Session):
    payload = register_payload(
        id=str(uuid.uuid4()),
        password_hash="$argon2id$fake",
        is_active=False,
        roles=["admin"],
        profile_id=str(uuid.uuid4()),
    )
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 422
    count = db_session.scalar(
        select(func.count()).select_from(User).where(User.email == payload["email"])
    )
    assert count == 0


async def test_registration_stays_within_the_request_transaction(
    client: AsyncClient, db_session: Session
):
    payload = register_payload()
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 201
    # The service flushed inside the request-scoped session...
    user_id = db_session.scalar(select(User.id).where(User.email == payload["email"]))
    assert user_id is not None
    # ...but the route never commits: nothing is visible outside the test transaction.
    with test_engine.connect() as connection:
        committed = connection.scalar(
            select(func.count()).select_from(User).where(User.email == payload["email"])
        )
    assert committed == 0


async def test_registration_does_not_create_a_profile(client: AsyncClient, db_session: Session):
    _, registration = await registered_user(client)
    user = db_session.get(User, uuid.UUID(registration["id"]))
    assert user.profile is None
    profile_count = db_session.scalar(
        select(func.count()).select_from(Profile).where(Profile.user_id == user.id)
    )
    assert profile_count == 0


# --- Login ---------------------------------------------------------------------------------

async def test_valid_credentials_return_an_access_token(client: AsyncClient):
    payload, _ = await registered_user(client)
    response = await client.post(
        "/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access_token", "token_type"}
    assert isinstance(body["access_token"], str) and body["access_token"]


async def test_login_token_type_is_bearer(client: AsyncClient):
    payload, _ = await registered_user(client)
    response = await client.post(
        "/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert response.json()["token_type"] == "bearer"


async def test_login_token_authenticates_through_get_current_user(
    client: AsyncClient, db_session: Session
):
    payload, registration = await registered_user(client)
    token = await login_token(client, payload)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    resolved = get_current_user(credentials, db_session)
    assert resolved.id == uuid.UUID(registration["id"])
    assert resolved.email == payload["email"]


async def test_login_token_authorizes_the_owned_profile_endpoint(
    client: AsyncClient, db_session: Session
):
    payload, registration = await registered_user(client)
    token = await login_token(client, payload)
    user = db_session.get(User, uuid.UUID(registration["id"]))
    profile = make_profile()
    profile.user = user
    db_session.add(profile)
    db_session.flush()
    response = await client.get(
        f"/profiles/{profile.id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["id"] == str(profile.id)


async def test_wrong_password_is_rejected(client: AsyncClient):
    payload, _ = await registered_user(client)
    response = await client.post(
        "/auth/login",
        json={"email": payload["email"], "password": "wrong-password-99"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == INVALID_CREDENTIALS_DETAIL


async def test_unknown_email_is_rejected(client: AsyncClient):
    response = await client.post(
        "/auth/login",
        json={
            "email": f"ghost-{uuid.uuid4().hex[:10]}@example.org",
            "password": TEST_PASSWORD,
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"] == INVALID_CREDENTIALS_DETAIL


async def test_inactive_account_cannot_login(client: AsyncClient, db_session: Session):
    user = make_user(is_active=False)
    db_session.add(user)
    db_session.flush()
    response = await client.post(
        "/auth/login", json={"email": user.email, "password": TEST_PASSWORD}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == INVALID_CREDENTIALS_DETAIL


async def test_all_login_failures_share_one_generic_error(client: AsyncClient):
    payload, _ = await registered_user(client)
    wrong_password = await client.post(
        "/auth/login",
        json={"email": payload["email"], "password": "wrong-password-99"},
    )
    unknown_email = await client.post(
        "/auth/login",
        json={
            "email": f"ghost-{uuid.uuid4().hex[:10]}@example.org",
            "password": TEST_PASSWORD,
        },
    )
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.json()["detail"] == INVALID_CREDENTIALS_DETAIL


async def test_login_responses_carry_no_sensitive_material(client: AsyncClient):
    payload, _ = await registered_user(client)
    success = await client.post(
        "/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert success.status_code == 200
    assert set(success.json()) == {"access_token", "token_type"}

    failure = await client.post(
        "/auth/login",
        json={"email": payload["email"], "password": "wrong-password-99"},
    )
    assert set(failure.json()) == {"detail"}
    assert payload["password"] not in failure.text
    assert "password_hash" not in failure.text
    assert TEST_JWT_SECRET not in failure.text


# --- JWT claims ----------------------------------------------------------------------------

async def test_token_subject_names_the_registered_user(client: AsyncClient):
    payload, registration = await registered_user(client)
    claims = decode_claims(await login_token(client, payload))
    assert claims["sub"] == registration["id"]


async def test_token_carries_an_expiry_claim(client: AsyncClient):
    payload, _ = await registered_user(client)
    claims = decode_claims(await login_token(client, payload))
    assert isinstance(claims["exp"], int)


async def test_token_carries_an_issued_at_claim(client: AsyncClient):
    payload, _ = await registered_user(client)
    claims = decode_claims(await login_token(client, payload))
    assert isinstance(claims["iat"], int)


async def test_token_claims_contain_no_password_material(client: AsyncClient):
    payload, _ = await registered_user(client)
    claims = decode_claims(await login_token(client, payload))
    assert set(claims) == {"sub", "exp", "iat"}
    assert payload["password"] not in str(claims)


async def test_expired_token_is_rejected_by_get_current_user(
    client: AsyncClient, db_session: Session, auth_secret: str
):
    user = make_user()
    db_session.add(user)
    db_session.flush()
    expired = create_access_token(user.id, ttl=timedelta(minutes=-1))
    response = await client.get(
        f"/profiles/{uuid.uuid4()}", headers={"Authorization": f"Bearer {expired}"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == INVALID_CREDENTIALS_DETAIL


async def test_malformed_token_is_rejected(client: AsyncClient):
    response = await client.get(
        f"/profiles/{uuid.uuid4()}", headers={"Authorization": "Bearer not.a.token"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == INVALID_CREDENTIALS_DETAIL
