"""Integration coverage for authenticated Education CRUD under /me/profile.

Every test runs inside the transaction provided by ``db_session`` and is
rolled back afterwards, so the dedicated test database stays clean. The
core flow uses real JWT bearer authentication minted with the test-only
secret — authentication is never mocked.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from app.api.deps import INVALID_CREDENTIALS_DETAIL
from app.db.session import get_db
from app.main import app
from app.models import Education, Profile, User
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.test_auth import TEST_JWT_SECRET, auth_headers, make_profile, make_user

EDUCATION_READ_FIELDS = {
    "id",
    "profile_id",
    "institution_name",
    "degree_level",
    "field_of_study",
    "country",
    "start_date",
    "end_date",
    "is_current",
    "gpa",
    "gpa_scale",
    "is_primary",
    "created_at",
}

PRIMARY_CONFLICT_DETAIL = "The profile already has a primary education."


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


def seed_user(db_session: Session) -> User:
    user = make_user()
    db_session.add(user)
    db_session.flush()
    return user


def seed_profile(db_session: Session, user: User) -> Profile:
    profile = make_profile()
    profile.user_id = user.id
    db_session.add(profile)
    db_session.flush()
    return profile


def education_payload(**overrides) -> dict:
    payload = {
        "institution_name": "Addis Ababa University",
        "degree_level": "bachelor",
        "field_of_study": "Computer Science",
        "country": "ET",
        "start_date": "2018-09-01",
        "end_date": "2022-06-30",
        "is_current": False,
        "gpa": 3.7,
        "gpa_scale": 4.0,
        "is_primary": False,
    }
    payload.update(overrides)
    return payload


async def create_education(client: AsyncClient, user: User, **overrides) -> dict:
    """Create one education record through the API and return its body."""
    response = await client.post(
        "/me/profile/education",
        json=education_payload(**overrides),
        headers=auth_headers(user),
    )
    assert response.status_code == 201
    return response.json()


def education_count(db_session: Session, profile: Profile) -> int:
    return db_session.scalar(
        select(func.count())
        .select_from(Education)
        .where(Education.profile_id == profile.id)
    )


def primary_count(db_session: Session, profile: Profile) -> int:
    return db_session.scalar(
        select(func.count())
        .select_from(Education)
        .where(
            Education.profile_id == profile.id,
            Education.is_primary.is_(True),
        )
    )


# --- GET /me/profile/education --------------------------------------------------------------

async def test_get_returns_the_owners_education_list(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    created = await create_education(client, user)
    response = await client.get(
        "/me/profile/education", headers=auth_headers(user)
    )
    assert response.status_code == 200
    body = response.json()
    assert [row["id"] for row in body] == [created["id"]]
    assert body[0]["profile_id"] == str(profile.id)


async def test_get_returns_multiple_education_records(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    first = await create_education(client, user)
    second = await create_education(client, user, field_of_study="Mathematics")
    response = await client.get(
        "/me/profile/education", headers=auth_headers(user)
    )
    assert response.status_code == 200
    assert {row["id"] for row in response.json()} == {first["id"], second["id"]}


async def test_get_order_is_deterministic(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)

    def seed_row(name: str, *, created_at: datetime, **overrides) -> Education:
        education = Education(
            profile_id=profile.id,
            institution_name=name,
            degree_level="bachelor",
            field_of_study="Studies",
            **overrides,
            created_at=created_at,
        )
        db_session.add(education)
        return education

    plain_old = seed_row("Old U", created_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
    plain_current = seed_row(
        "Current U",
        created_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
        is_current=True,
    )
    primary_row = seed_row(
        "Primary U",
        created_at=datetime(2024, 3, 1, tzinfo=timezone.utc),
        is_primary=True,
    )
    plain_new = seed_row("New U", created_at=datetime(2024, 4, 1, tzinfo=timezone.utc))
    db_session.flush()

    expected = [
        str(primary_row.id),
        str(plain_current.id),
        str(plain_old.id),
        str(plain_new.id),
    ]
    first = await client.get("/me/profile/education", headers=auth_headers(user))
    second = await client.get("/me/profile/education", headers=auth_headers(user))
    assert [row["id"] for row in first.json()] == expected
    assert [row["id"] for row in second.json()] == expected


async def test_get_returns_empty_list_when_profile_has_none(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    response = await client.get(
        "/me/profile/education", headers=auth_headers(user)
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_get_without_profile_returns_404(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    response = await client.get(
        "/me/profile/education", headers=auth_headers(user)
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Profile not found."


async def test_education_endpoints_require_authentication(client: AsyncClient):
    education_id = str(uuid.uuid4())
    assert (
        await client.get("/me/profile/education")
    ).status_code == 401
    assert (
        await client.post("/me/profile/education", json=education_payload())
    ).status_code == 401
    assert (
        await client.patch(
            f"/me/profile/education/{education_id}", json={"field_of_study": "x"}
        )
    ).status_code == 401
    assert (
        await client.delete(f"/me/profile/education/{education_id}")
    ).status_code == 401


# --- POST /me/profile/education -------------------------------------------------------------

async def test_owner_can_create_education(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    response = await client.post(
        "/me/profile/education",
        json=education_payload(),
        headers=auth_headers(user),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["institution_name"] == "Addis Ababa University"
    assert body["degree_level"] == "bachelor"
    assert body["gpa"] == 3.7
    assert body["gpa_scale"] == 4.0
    assert body["is_primary"] is False


async def test_profile_id_is_server_derived(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    body = await create_education(client, user)
    assert body["profile_id"] == str(profile.id)
    row = db_session.get(Education, uuid.UUID(body["id"]))
    assert row.profile_id == profile.id


async def test_client_cannot_control_profile_id(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    other = seed_user(db_session)
    other_profile = seed_profile(db_session, other)
    response = await client.post(
        "/me/profile/education",
        json=education_payload(profile_id=str(other_profile.id)),
        headers=auth_headers(user),
    )
    assert response.status_code == 422
    assert education_count(db_session, profile) == 0
    assert education_count(db_session, other_profile) == 0


async def test_client_cannot_control_education_id(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    response = await client.post(
        "/me/profile/education",
        json=education_payload(id=str(uuid.uuid4())),
        headers=auth_headers(user),
    )
    assert response.status_code == 422
    assert education_count(db_session, profile) == 0


async def test_create_validation_errors_return_422(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    bad_name = await client.post(
        "/me/profile/education",
        json=education_payload(institution_name=""),
        headers=auth_headers(user),
    )
    bad_degree = await client.post(
        "/me/profile/education",
        json=education_payload(degree_level="phd"),
        headers=auth_headers(user),
    )
    assert bad_name.status_code == 422
    assert bad_degree.status_code == 422
    assert education_count(db_session, profile) == 0


async def test_primary_education_can_be_created(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    body = await create_education(client, user, is_primary=True)
    assert body["is_primary"] is True
    assert primary_count(db_session, profile) == 1


async def test_duplicate_primary_returns_409(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    await create_education(client, user, is_primary=True)
    response = await client.post(
        "/me/profile/education",
        json=education_payload(is_primary=True, field_of_study="Mathematics"),
        headers=auth_headers(user),
    )
    assert response.status_code == 409
    assert response.json()["detail"] == PRIMARY_CONFLICT_DETAIL
    assert primary_count(db_session, profile) == 1
    assert education_count(db_session, profile) == 1


async def test_gpa_and_scale_constraints_are_enforced(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    over_scale = await client.post(
        "/me/profile/education",
        json=education_payload(gpa=4.5, gpa_scale=4.0),
        headers=auth_headers(user),
    )
    bad_scale = await client.post(
        "/me/profile/education",
        json=education_payload(gpa=3.0, gpa_scale=7.0),
        headers=auth_headers(user),
    )
    missing_scale = await client.post(
        "/me/profile/education",
        json=education_payload(gpa=3.5, gpa_scale=None),
        headers=auth_headers(user),
    )
    assert over_scale.status_code == 422
    assert bad_scale.status_code == 422
    assert missing_scale.status_code == 422
    assert education_count(db_session, profile) == 0


async def test_create_response_contains_no_sensitive_auth_data(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    response = await client.post(
        "/me/profile/education",
        json=education_payload(),
        headers=auth_headers(user),
    )
    assert response.status_code == 201
    assert set(response.json()) == EDUCATION_READ_FIELDS
    assert "password" not in response.text
    assert "password_hash" not in response.text
    assert TEST_JWT_SECRET not in response.text


# --- PATCH /me/profile/education/{education_id} ---------------------------------------------

async def test_owner_can_update_education(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    created = await create_education(client, user)
    response = await client.patch(
        f"/me/profile/education/{created['id']}",
        json={"institution_name": "Addis Ababa University, MSc"},
        headers=auth_headers(user),
    )
    assert response.status_code == 200
    assert response.json()["institution_name"] == "Addis Ababa University, MSc"


async def test_partial_update_preserves_unspecified_fields(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    before = await create_education(client, user)
    response = await client.patch(
        f"/me/profile/education/{before['id']}",
        json={"is_current": True},
        headers=auth_headers(user),
    )
    assert response.status_code == 200
    after = response.json()
    assert after["is_current"] is True
    for field in EDUCATION_READ_FIELDS - {"is_current"}:
        assert after[field] == before[field], field


async def test_cannot_change_profile_ownership(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    other = seed_user(db_session)
    other_profile = seed_profile(db_session, other)
    created = await create_education(client, user)
    response = await client.patch(
        f"/me/profile/education/{created['id']}",
        json={"profile_id": str(other_profile.id)},
        headers=auth_headers(user),
    )
    assert response.status_code == 422
    row = db_session.get(Education, uuid.UUID(created["id"]))
    assert row.profile_id == profile.id
    assert education_count(db_session, other_profile) == 0


async def test_cannot_change_id(client: AsyncClient, db_session: Session):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    created = await create_education(client, user)
    response = await client.patch(
        f"/me/profile/education/{created['id']}",
        json={"id": str(uuid.uuid4())},
        headers=auth_headers(user),
    )
    assert response.status_code == 422
    row = db_session.get(Education, uuid.UUID(created["id"]))
    assert str(row.id) == created["id"]


async def test_patch_validation_errors_return_422(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    created = await create_education(client, user, gpa=3.7, gpa_scale=4.0)
    bad_degree = await client.patch(
        f"/me/profile/education/{created['id']}",
        json={"degree_level": "phd"},
        headers=auth_headers(user),
    )
    over_scale = await client.patch(
        f"/me/profile/education/{created['id']}",
        json={"gpa": 4.9},
        headers=auth_headers(user),
    )
    broken_pair = await client.patch(
        f"/me/profile/education/{created['id']}",
        json={"gpa": None},
        headers=auth_headers(user),
    )
    assert bad_degree.status_code == 422
    assert over_scale.status_code == 422
    assert broken_pair.status_code == 422
    row = db_session.get(Education, uuid.UUID(created["id"]))
    assert float(row.gpa) == 3.7
    assert float(row.gpa_scale) == 4.0


async def test_other_users_education_cannot_be_modified(
    client: AsyncClient, db_session: Session
):
    victim = seed_user(db_session)
    victim_profile = seed_profile(db_session, victim)
    attacker = seed_user(db_session)
    seed_profile(db_session, attacker)
    target = await create_education(client, victim)
    response = await client.patch(
        f"/me/profile/education/{target['id']}",
        json={"institution_name": "Hijacked University"},
        headers=auth_headers(attacker),
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Education not found."
    row = db_session.get(Education, uuid.UUID(target["id"]))
    assert row.institution_name == "Addis Ababa University"
    assert row.profile_id == victim_profile.id


# --- DELETE /me/profile/education/{education_id} --------------------------------------------

async def test_owner_can_delete_education(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    created = await create_education(client, user)
    response = await client.delete(
        f"/me/profile/education/{created['id']}", headers=auth_headers(user)
    )
    assert response.status_code == 204
    assert response.content == b""
    assert education_count(db_session, profile) == 0


async def test_other_users_education_cannot_be_deleted(
    client: AsyncClient, db_session: Session
):
    victim = seed_user(db_session)
    victim_profile = seed_profile(db_session, victim)
    attacker = seed_user(db_session)
    seed_profile(db_session, attacker)
    target = await create_education(client, victim)
    response = await client.delete(
        f"/me/profile/education/{target['id']}", headers=auth_headers(attacker)
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Education not found."
    assert education_count(db_session, victim_profile) == 1


async def test_delete_leaves_other_records_intact(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    first = await create_education(client, user)
    second = await create_education(client, user, field_of_study="Mathematics")
    third = await create_education(client, user, field_of_study="Physics")
    response = await client.delete(
        f"/me/profile/education/{second['id']}", headers=auth_headers(user)
    )
    assert response.status_code == 204
    assert education_count(db_session, profile) == 2
    remaining = {
        row["id"]
        for row in (
            await client.get("/me/profile/education", headers=auth_headers(user))
        ).json()
    }
    assert remaining == {first["id"], third["id"]}


async def test_deleting_primary_promotes_nothing(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    primary = await create_education(client, user, is_primary=True)
    keep_one = await create_education(client, user, field_of_study="Mathematics")
    keep_two = await create_education(client, user, field_of_study="Physics")
    response = await client.delete(
        f"/me/profile/education/{primary['id']}", headers=auth_headers(user)
    )
    assert response.status_code == 204
    assert education_count(db_session, profile) == 2
    # No automatic promotion: the profile simply has no primary anymore.
    assert primary_count(db_session, profile) == 0
    remaining = {
        row["id"]
        for row in (
            await client.get("/me/profile/education", headers=auth_headers(user))
        ).json()
    }
    assert remaining == {keep_one["id"], keep_two["id"]}
