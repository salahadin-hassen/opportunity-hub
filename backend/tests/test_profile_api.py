"""Integration coverage for Profile API slice 1: /me/profile lifecycle.

Every test runs inside the transaction provided by ``db_session`` and is
rolled back afterwards, so the dedicated test database stays clean. The
core flow uses real JWT bearer authentication minted with the test-only
secret — authentication is never mocked.
"""
from __future__ import annotations

import uuid

import pytest
from app.api.deps import INVALID_CREDENTIALS_DETAIL
from app.db.session import get_db
from app.main import app
from app.models import Profile, User
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.test_auth import TEST_JWT_SECRET, auth_headers, make_profile, make_user

PROFILE_READ_FIELDS = {
    "id",
    "full_name",
    "email",
    "date_of_birth",
    "citizenships",
    "country_of_residence",
    "degree_level",
    "is_currently_enrolled",
    "languages",
    "links",
    "interests",
    "bio",
    "created_at",
    "updated_at",
}


@pytest.fixture
def auth_secret(monkeypatch) -> str:
    """Point token signing at a test-only secret for one test."""
    from app.core.config import settings

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


def seed_user(db_session: Session, **overrides) -> User:
    user = make_user(**overrides)
    db_session.add(user)
    db_session.flush()
    return user


def profile_payload(**overrides) -> dict:
    payload = {
        "full_name": "Sara Bekele",
        "email": f"profile-{uuid.uuid4().hex[:10]}@example.org",
        "date_of_birth": "1999-05-04",
        "citizenships": ["ET"],
        "country_of_residence": "ET",
        "degree_level": "bachelor",
        "is_currently_enrolled": True,
        "languages": ["en"],
        "links": {"github": "https://github.com/example"},
        "interests": ["ml"],
        "bio": "Aspiring researcher.",
    }
    payload.update(overrides)
    return payload


async def create_profile(client: AsyncClient, user: User, **overrides) -> dict:
    """Create the user's profile through the API and return its body."""
    response = await client.post(
        "/me/profile",
        json=profile_payload(**overrides),
        headers=auth_headers(user),
    )
    assert response.status_code == 201
    return response.json()


def owned_profile_count(db_session: Session, user: User) -> int:
    return db_session.scalar(
        select(func.count()).select_from(Profile).where(Profile.user_id == user.id)
    )


# --- GET /me/profile -----------------------------------------------------------------------

async def test_get_me_profile_returns_200_for_user_with_profile(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    created = await create_profile(client, user)
    response = await client.get("/me/profile", headers=auth_headers(user))
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


async def test_get_me_profile_returns_the_correct_profile(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    created = await create_profile(client, user)
    response = await client.get("/me/profile", headers=auth_headers(user))
    assert response.status_code == 200
    body = response.json()
    assert body == created
    assert body["full_name"] == "Sara Bekele"
    assert body["citizenships"] == ["ET"]
    assert body["degree_level"] == "bachelor"


async def test_get_me_profile_requires_authentication(client: AsyncClient):
    response = await client.get("/me/profile")
    assert response.status_code == 401
    assert response.json()["detail"] == INVALID_CREDENTIALS_DETAIL


async def test_get_me_profile_without_profile_returns_404(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    response = await client.get("/me/profile", headers=auth_headers(user))
    assert response.status_code == 404
    assert response.json()["detail"] == "Profile not found."


async def test_another_users_profile_is_unreachable_through_me_profile(
    client: AsyncClient, db_session: Session
):
    owner = seed_user(db_session)
    stranger = seed_user(db_session)
    created = await create_profile(client, owner)
    # The stranger has no profile of their own, so /me/profile cannot reach
    # the owner's row, and no route accepts a profile id under /me.
    response = await client.get("/me/profile", headers=auth_headers(stranger))
    assert response.status_code == 404
    by_id = await client.get(
        f"/me/profile/{created['id']}", headers=auth_headers(stranger)
    )
    assert by_id.status_code == 404


async def test_ownerless_legacy_profile_is_not_exposed(
    client: AsyncClient, db_session: Session
):
    legacy = make_profile()
    db_session.add(legacy)
    db_session.flush()
    user = seed_user(db_session)
    response = await client.get("/me/profile", headers=auth_headers(user))
    assert response.status_code == 404
    db_session.refresh(legacy)
    assert legacy.user_id is None


# --- POST /me/profile ----------------------------------------------------------------------

async def test_create_me_profile_returns_201(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    response = await client.post(
        "/me/profile", json=profile_payload(), headers=auth_headers(user)
    )
    assert response.status_code == 201
    body = response.json()
    assert uuid.UUID(body["id"])
    assert body["full_name"] == "Sara Bekele"


async def test_create_me_profile_assigns_user_id_from_authenticated_user(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    body = await create_profile(client, user)
    profile = db_session.get(Profile, uuid.UUID(body["id"]))
    assert profile.user_id == user.id


async def test_client_cannot_control_user_id(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    response = await client.post(
        "/me/profile",
        json=profile_payload(user_id=str(uuid.uuid4())),
        headers=auth_headers(user),
    )
    assert response.status_code == 422
    assert owned_profile_count(db_session, user) == 0


async def test_client_cannot_control_profile_id(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    response = await client.post(
        "/me/profile",
        json=profile_payload(id=str(uuid.uuid4())),
        headers=auth_headers(user),
    )
    assert response.status_code == 422
    assert owned_profile_count(db_session, user) == 0


async def test_duplicate_profile_returns_409(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    await create_profile(client, user)
    response = await client.post(
        "/me/profile", json=profile_payload(), headers=auth_headers(user)
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "The user already has a profile."


async def test_duplicate_profile_creates_no_second_row(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    await create_profile(client, user)
    await client.post(
        "/me/profile", json=profile_payload(), headers=auth_headers(user)
    )
    assert owned_profile_count(db_session, user) == 1


async def test_invalid_profile_input_returns_422(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    response = await client.post(
        "/me/profile",
        json=profile_payload(email="not-an-email"),
        headers=auth_headers(user),
    )
    assert response.status_code == 422
    assert owned_profile_count(db_session, user) == 0


async def test_create_response_contains_no_sensitive_auth_data(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    response = await client.post(
        "/me/profile", json=profile_payload(), headers=auth_headers(user)
    )
    assert response.status_code == 201
    body = response.json()
    assert set(body) == PROFILE_READ_FIELDS
    assert "password" not in response.text
    assert "password_hash" not in response.text
    assert TEST_JWT_SECRET not in response.text


# --- PATCH /me/profile ---------------------------------------------------------------------

async def test_patch_updates_editable_fields(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    await create_profile(client, user)
    response = await client.patch(
        "/me/profile",
        json={"full_name": "Sara Hassen", "citizenships": ["ET", "KE"]},
        headers=auth_headers(user),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Sara Hassen"
    assert body["citizenships"] == ["ET", "KE"]


async def test_patch_partial_update_preserves_unspecified_fields(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    before = await create_profile(client, user)
    response = await client.patch(
        "/me/profile", json={"bio": "Short updated bio."}, headers=auth_headers(user)
    )
    assert response.status_code == 200
    after = response.json()
    assert after["bio"] == "Short updated bio."
    for field in PROFILE_READ_FIELDS - {"bio", "updated_at"}:
        assert after[field] == before[field], field


async def test_patch_cannot_change_user_id(client: AsyncClient, db_session: Session):
    user = seed_user(db_session)
    created = await create_profile(client, user)
    other = seed_user(db_session)
    response = await client.patch(
        "/me/profile",
        json={"user_id": str(other.id)},
        headers=auth_headers(user),
    )
    assert response.status_code == 422
    profile = db_session.get(Profile, uuid.UUID(created["id"]))
    assert profile.user_id == user.id


async def test_patch_cannot_change_id(client: AsyncClient, db_session: Session):
    user = seed_user(db_session)
    created = await create_profile(client, user)
    response = await client.patch(
        "/me/profile", json={"id": str(uuid.uuid4())}, headers=auth_headers(user)
    )
    assert response.status_code == 422
    assert response.json()  # structured 422, not a partial success
    profile = db_session.get(Profile, uuid.UUID(created["id"]))
    assert str(profile.id) == created["id"]


async def test_patch_cannot_control_server_timestamps(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    before = await create_profile(client, user)
    response = await client.patch(
        "/me/profile",
        json={
            "created_at": "2000-01-01T00:00:00Z",
            "updated_at": "2000-01-01T00:00:00Z",
        },
        headers=auth_headers(user),
    )
    assert response.status_code == 422
    # A legitimate update still leaves created_at server-owned.
    patched = await client.patch(
        "/me/profile", json={"full_name": "Renamed"}, headers=auth_headers(user)
    )
    assert patched.status_code == 200
    assert patched.json()["created_at"] == before["created_at"]
    assert patched.json()["updated_at"] != "2000-01-01T00:00:00Z"


async def test_patch_without_profile_returns_404(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    response = await client.patch(
        "/me/profile", json={"bio": "x"}, headers=auth_headers(user)
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Profile not found."
    assert owned_profile_count(db_session, user) == 0


async def test_patch_requires_authentication(client: AsyncClient):
    response = await client.patch("/me/profile", json={"bio": "x"})
    assert response.status_code == 401
    assert response.json()["detail"] == INVALID_CREDENTIALS_DETAIL


async def test_patch_invalid_input_returns_422(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    await create_profile(client, user)
    response = await client.patch(
        "/me/profile", json={"degree_level": "phd"}, headers=auth_headers(user)
    )
    assert response.status_code == 422


# --- Email / domain behavior ---------------------------------------------------------------

async def test_profile_email_is_independent_of_user_email(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    payload = profile_payload(email=f"contact-{uuid.uuid4().hex[:10]}@example.org")
    response = await client.post(
        "/me/profile", json=payload, headers=auth_headers(user)
    )
    assert response.status_code == 201
    assert response.json()["email"] == payload["email"]
    db_session.refresh(user)
    assert user.email != payload["email"]


async def test_profile_email_change_does_not_sync_user_email(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    await create_profile(client, user)
    original_user_email = user.email
    new_contact = f"contact-{uuid.uuid4().hex[:10]}@example.org"
    response = await client.patch(
        "/me/profile", json={"email": new_contact}, headers=auth_headers(user)
    )
    assert response.status_code == 200
    assert response.json()["email"] == new_contact
    db_session.refresh(user)
    assert user.email == original_user_email
