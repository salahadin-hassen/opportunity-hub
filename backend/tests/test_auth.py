"""Integration coverage for auth slice 1: identity, ownership, dependencies.

Every test runs inside the transaction provided by ``db_session`` and is
rolled back afterwards, so the dedicated test database stays clean.

Tokens are minted with a test-only secret (monkeypatched onto settings) and
no external auth service is ever contacted.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from app.api.deps import (
    INVALID_CREDENTIALS_DETAIL,
    PROFILE_FORBIDDEN_DETAIL,
    get_current_user,
)
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.main import app
from app.models import Profile, User
from app.schemas import ProfileCreate, UserRead
from fastapi.security import HTTPAuthorizationCredentials
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

TEST_JWT_SECRET = "test-only-jwt-secret-for-pytest-never-production"
TEST_PASSWORD = "correct-horse-battery-staple"


def make_user(**overrides) -> User:
    payload = {
        "email": f"user-{uuid.uuid4().hex[:10]}@example.org",
        "password_hash": hash_password(TEST_PASSWORD),
        "is_active": True,
    }
    payload.update(overrides)
    return User(**payload)


def make_profile(**overrides) -> Profile:
    payload = {
        "full_name": "Sara Bekele",
        "email": f"profile-{uuid.uuid4().hex[:10]}@example.org",
        "citizenships": ["ET"],
        "country_of_residence": "ET",
        "degree_level": "bachelor",
        "is_currently_enrolled": True,
        "languages": ["en"],
        "links": {},
        "interests": [],
    }
    payload.update(overrides)
    return Profile(**ProfileCreate(**payload).model_dump())


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def bearer_credentials(user: User) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=create_access_token(user.id))


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


# --- User ------------------------------------------------------------------------------


def test_user_can_be_created(db_session: Session):
    user = make_user()
    db_session.add(user)
    db_session.flush()
    db_session.refresh(user)

    assert user.id is not None
    assert user.email.endswith("@example.org")
    assert user.password_hash.startswith("$argon2")
    assert user.password_hash != TEST_PASSWORD
    assert verify_password(TEST_PASSWORD, user.password_hash) is True
    assert verify_password("wrong-password", user.password_hash) is False


def test_user_email_uniqueness_is_enforced(db_session: Session):
    email = f"unique-{uuid.uuid4().hex[:10]}@example.org"
    db_session.add(make_user(email=email))
    db_session.flush()

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(make_user(email=email))
            db_session.flush()


def test_user_timestamps_work(db_session: Session):
    user = make_user()
    db_session.add(user)
    db_session.flush()
    db_session.refresh(user)

    assert user.created_at is not None
    assert user.created_at.tzinfo is not None
    assert user.updated_at is not None
    assert user.updated_at.tzinfo is not None


def test_inactive_user_is_represented_correctly(db_session: Session):
    user = make_user(is_active=False)
    db_session.add(user)
    db_session.flush()
    db_session.refresh(user)

    assert user.is_active is False
    assert UserRead.model_validate(user).is_active is False


# --- Ownership -------------------------------------------------------------------------


def test_user_can_own_a_profile(db_session: Session):
    user = make_user()
    profile = make_profile()
    profile.user = user
    db_session.add_all([user, profile])
    db_session.flush()
    db_session.refresh(profile)

    assert profile.user_id == user.id


def test_profile_points_to_the_correct_user(db_session: Session):
    owner = make_user()
    stranger = make_user()
    profile = make_profile()
    profile.user = owner
    db_session.add_all([owner, stranger, profile])
    db_session.flush()
    db_session.refresh(profile)

    assert profile.user_id == owner.id
    assert profile.user.id == owner.id
    assert owner.profile.id == profile.id
    assert stranger.profile is None
    assert profile.user_id != stranger.id


def test_ownership_cardinality_is_enforced(db_session: Session):
    user = make_user()
    db_session.add(user)
    db_session.flush()
    first = make_profile()
    first.user = user
    db_session.add(first)
    db_session.flush()

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            second = make_profile()
            second.user = user
            db_session.add(second)
            db_session.flush()


@pytest.mark.asyncio
async def test_profile_without_an_owner_stays_unclaimed_and_inaccessible(
    client: AsyncClient, db_session: Session, auth_secret: str
):
    profile = make_profile()
    db_session.add(profile)
    db_session.flush()
    db_session.refresh(profile)
    assert profile.user_id is None

    viewer = make_user()
    db_session.add(viewer)
    db_session.flush()

    response = await client.get(f"/profiles/{profile.id}", headers=auth_headers(viewer))

    assert response.status_code == 403


def test_deleting_user_follows_the_documented_policy(db_session: Session):
    unowned = make_user()
    owner = make_user()
    profile = make_profile()
    profile.user = owner
    db_session.add_all([unowned, owner, profile])
    db_session.flush()

    db_session.delete(unowned)
    db_session.flush()
    assert db_session.get(User, unowned.id) is None

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.delete(owner)
            db_session.flush()

    surviving = db_session.get(Profile, profile.id)
    assert surviving is not None
    assert surviving.user_id == owner.id


# --- Authentication ---------------------------------------------------------------------


def test_valid_identity_can_be_resolved(db_session: Session, auth_secret: str):
    user = make_user()
    db_session.add(user)
    db_session.flush()

    resolved = get_current_user(bearer_credentials(user), db_session)

    assert resolved.id == user.id


@pytest.mark.asyncio
async def test_invalid_token_returns_unauthorized(client: AsyncClient, db_session: Session, auth_secret: str):
    user = make_user()
    db_session.add(user)
    db_session.flush()
    forged = jwt.encode(
        {"sub": str(user.id), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        "not-the-server-secret-0123456789abcdef",
        algorithm="HS256",
    )

    response = await client.get(
        f"/profiles/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {forged}"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_missing_token_returns_unauthorized(client: AsyncClient, db_session: Session, auth_secret: str):
    response = await client.get(f"/profiles/{uuid.uuid4()}")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_malformed_token_returns_unauthorized(client: AsyncClient, db_session: Session, auth_secret: str):
    response = await client.get(
        f"/profiles/{uuid.uuid4()}",
        headers={"Authorization": "Bearer not-a-jwt"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_inactive_user_returns_unauthorized(client: AsyncClient, db_session: Session, auth_secret: str):
    user = make_user(is_active=False)
    profile = make_profile()
    profile.user = user
    db_session.add_all([user, profile])
    db_session.flush()

    response = await client.get(f"/profiles/{profile.id}", headers=auth_headers(user))

    assert response.status_code == 401


def test_user_lookup_returns_the_correct_user(db_session: Session, auth_secret: str):
    owner = make_user()
    other = make_user()
    db_session.add_all([owner, other])
    db_session.flush()

    resolved = get_current_user(bearer_credentials(owner), db_session)

    assert resolved.id == owner.id
    assert resolved.email == owner.email
    assert resolved.is_active is True
    assert resolved.id != other.id


# --- Authorization ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_current_user_can_access_their_own_profile(
    client: AsyncClient, db_session: Session, auth_secret: str
):
    user = make_user()
    profile = make_profile()
    profile.user = user
    db_session.add_all([user, profile])
    db_session.flush()

    response = await client.get(f"/profiles/{profile.id}", headers=auth_headers(user))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(profile.id)
    assert body["full_name"] == profile.full_name


@pytest.mark.asyncio
async def test_current_user_cannot_access_another_users_profile(
    client: AsyncClient, db_session: Session, auth_secret: str
):
    owner = make_user()
    intruder = make_user()
    profile = make_profile()
    profile.user = owner
    db_session.add_all([owner, intruder, profile])
    db_session.flush()

    response = await client.get(f"/profiles/{profile.id}", headers=auth_headers(intruder))

    assert response.status_code == 403
    assert response.json()["detail"] == PROFILE_FORBIDDEN_DETAIL


@pytest.mark.asyncio
async def test_ownership_failure_returns_forbidden_while_missing_profile_returns_not_found(
    client: AsyncClient, db_session: Session, auth_secret: str
):
    user = make_user()
    db_session.add(user)
    db_session.flush()

    existing = make_profile()
    owner = make_user()
    existing.user = owner
    db_session.add_all([owner, existing])
    db_session.flush()

    forbidden = await client.get(f"/profiles/{existing.id}", headers=auth_headers(user))
    missing = await client.get(f"/profiles/{uuid.uuid4()}", headers=auth_headers(user))

    assert forbidden.status_code == 403
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Profile not found."


@pytest.mark.asyncio
async def test_profile_uuid_alone_is_not_authorization(
    client: AsyncClient, db_session: Session, auth_secret: str
):
    owner = make_user()
    other = make_user()
    profile = make_profile()
    profile.user = owner
    db_session.add_all([owner, other, profile])
    db_session.flush()
    path = f"/profiles/{profile.id}"

    unauthenticated = await client.get(path)
    wrong_user = await client.get(path, headers=auth_headers(other))
    owner_response = await client.get(path, headers=auth_headers(owner))

    assert unauthenticated.status_code == 401
    assert wrong_user.status_code == 403
    assert owner_response.status_code == 200


# --- Security ----------------------------------------------------------------------------


def test_password_hash_is_never_returned(db_session: Session):
    user = make_user()
    db_session.add(user)
    db_session.flush()
    db_session.refresh(user)

    body = UserRead.model_validate(user).model_dump()

    assert "password_hash" not in body
    assert set(UserRead.model_fields) == {"id", "email", "is_active", "created_at", "updated_at"}
    assert user.password_hash not in str(body)
    assert TEST_PASSWORD not in str(body)


@pytest.mark.asyncio
async def test_secrets_do_not_appear_in_responses(
    client: AsyncClient, db_session: Session, auth_secret: str
):
    user = make_user()
    profile = make_profile()
    profile.user = user
    db_session.add_all([user, profile])
    db_session.flush()

    response = await client.get(f"/profiles/{profile.id}", headers=auth_headers(user))

    assert response.status_code == 200
    assert TEST_JWT_SECRET not in response.text
    assert user.password_hash not in response.text
    assert TEST_PASSWORD not in response.text
    assert response.request.headers["Authorization"] not in response.text


@pytest.mark.asyncio
async def test_authentication_errors_do_not_reveal_token_details(
    client: AsyncClient, db_session: Session, auth_secret: str
):
    user = make_user()
    db_session.add(user)
    db_session.flush()
    forged = jwt.encode(
        {"sub": str(user.id), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        "not-the-server-secret-0123456789abcdef",
        algorithm="HS256",
    )
    cases = [
        {},
        {"Authorization": f"Bearer {forged}"},
        {"Authorization": "Bearer not-a-jwt"},
        {"Authorization": "Basic dXNlcjpwYXNz"},
    ]

    details = set()
    for headers in cases:
        response = await client.get(f"/profiles/{uuid.uuid4()}", headers=headers)
        assert response.status_code == 401
        detail = response.json()["detail"]
        details.add(detail)
        assert detail == INVALID_CREDENTIALS_DETAIL
        assert forged not in response.text
        assert "signature" not in detail.lower()
        assert "decode" not in detail.lower()
        assert "expired" not in detail.lower()

    assert details == {INVALID_CREDENTIALS_DETAIL}
    assert INVALID_CREDENTIALS_DETAIL == "Could not validate credentials."
