"""Integration coverage for authenticated profile skill management.

Every test runs inside the transaction provided by ``db_session`` and is
rolled back afterwards, so the dedicated test database stays clean. The
core flow uses real JWT bearer authentication minted with the test-only
secret — authentication is never mocked. Canonical skills are seeded the
same way existing domain tests do, because no vocabulary API exists.
"""
from __future__ import annotations

import uuid

import pytest
from app.db.session import get_db
from app.main import app
from app.models import Profile, ProfileSkill, Skill, User
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.test_auth import TEST_JWT_SECRET, auth_headers, make_profile, make_user
from tests.test_skill_models import make_skill

SKILL_READ_FIELDS = {"id", "key", "name", "created_at"}


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


def seed_skill(db_session: Session, **overrides) -> Skill:
    skill = make_skill(**overrides)
    db_session.add(skill)
    db_session.flush()
    return skill


async def attach(client: AsyncClient, user: User, skill: Skill, **overrides) -> dict:
    """Attach one canonical skill through the API and return its body."""
    response = await client.post(
        "/me/profile/skills",
        json={"skill_id": str(skill.id), **overrides},
        headers=auth_headers(user),
    )
    assert response.status_code == 201
    return response.json()


def association_count(db_session: Session, profile: Profile) -> int:
    return db_session.scalar(
        select(func.count())
        .select_from(ProfileSkill)
        .where(ProfileSkill.profile_id == profile.id)
    )


# --- GET /me/profile/skills -----------------------------------------------------------------

async def test_get_returns_the_owners_skills(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    skill = seed_skill(db_session, key="python", name="Python")
    attached = await attach(client, user, skill)
    response = await client.get("/me/profile/skills", headers=auth_headers(user))
    assert response.status_code == 200
    body = response.json()
    assert [row["id"] for row in body] == [attached["id"]]
    assert body[0]["key"] == "python"
    assert body[0]["name"] == "Python"
    assert association_count(db_session, profile) == 1


async def test_get_returns_multiple_skills(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    first = seed_skill(db_session, key="python", name="Python")
    second = seed_skill(db_session, key="docker", name="Docker")
    await attach(client, user, first)
    await attach(client, user, second)
    response = await client.get("/me/profile/skills", headers=auth_headers(user))
    assert response.status_code == 200
    assert {row["key"] for row in response.json()} == {"python", "docker"}


async def test_get_order_follows_canonical_key(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    for key in ("rust", "java", "python"):
        await attach(client, user, seed_skill(db_session, key=key, name=key.title()))
    first = await client.get("/me/profile/skills", headers=auth_headers(user))
    second = await client.get("/me/profile/skills", headers=auth_headers(user))
    keys = [row["key"] for row in first.json()]
    assert keys == sorted(keys)
    assert keys == ["java", "python", "rust"]
    assert [row["key"] for row in second.json()] == keys


async def test_get_returns_empty_list_without_skills(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    response = await client.get("/me/profile/skills", headers=auth_headers(user))
    assert response.status_code == 200
    assert response.json() == []


async def test_get_without_profile_returns_404(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    response = await client.get("/me/profile/skills", headers=auth_headers(user))
    assert response.status_code == 404
    assert response.json()["detail"] == "Profile not found."


async def test_endpoints_require_authentication(client: AsyncClient):
    skill_id = str(uuid.uuid4())
    assert (await client.get("/me/profile/skills")).status_code == 401
    assert (
        await client.post("/me/profile/skills", json={"skill_id": skill_id})
    ).status_code == 401
    assert (
        await client.delete(f"/me/profile/skills/{skill_id}")
    ).status_code == 401


async def test_response_exposes_canonical_key_and_name(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    body = await attach(
        client, user, seed_skill(db_session, key="web-dev", name="Web Development")
    )
    assert set(body) == SKILL_READ_FIELDS
    assert body["key"] == "web-dev"
    assert body["name"] == "Web Development"
    response = await client.get("/me/profile/skills", headers=auth_headers(user))
    assert set(response.json()[0]) == SKILL_READ_FIELDS


# --- POST /me/profile/skills ----------------------------------------------------------------

async def test_owner_can_attach_existing_skill(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    skill = seed_skill(db_session, key="python", name="Python")
    body = await attach(client, user, skill)
    assert body["id"] == str(skill.id)
    association = db_session.scalar(
        select(ProfileSkill).where(ProfileSkill.profile_id == profile.id)
    )
    assert association.skill_id == skill.id


async def test_profile_ownership_is_server_derived(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    other = seed_user(db_session)
    other_profile = seed_profile(db_session, other)
    skill = seed_skill(db_session, key="python", name="Python")
    await attach(client, user, skill)
    assert association_count(db_session, profile) == 1
    assert association_count(db_session, other_profile) == 0


async def test_client_cannot_provide_profile_id(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    other = seed_user(db_session)
    other_profile = seed_profile(db_session, other)
    skill = seed_skill(db_session, key="python", name="Python")
    response = await client.post(
        "/me/profile/skills",
        json={"skill_id": str(skill.id), "profile_id": str(other_profile.id)},
        headers=auth_headers(user),
    )
    assert response.status_code == 422
    assert association_count(db_session, profile) == 0
    assert association_count(db_session, other_profile) == 0


async def test_canonical_skill_remains_unchanged(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    skill = seed_skill(db_session, key="python", name="Python")
    before = (skill.id, skill.key, skill.name, skill.created_at)
    await attach(client, user, skill)
    db_session.refresh(skill)
    assert (skill.id, skill.key, skill.name, skill.created_at) == before


async def test_duplicate_association_returns_409(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    skill = seed_skill(db_session, key="python", name="Python")
    await attach(client, user, skill)
    response = await client.post(
        "/me/profile/skills",
        json={"skill_id": str(skill.id)},
        headers=auth_headers(user),
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "The profile already has this skill."
    assert association_count(db_session, profile) == 1


async def test_duplicate_does_not_create_second_row(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    skill = seed_skill(db_session, key="python", name="Python")
    await attach(client, user, skill)
    await client.post(
        "/me/profile/skills",
        json={"skill_id": str(skill.id)},
        headers=auth_headers(user),
    )
    rows = db_session.scalars(
        select(ProfileSkill).where(ProfileSkill.profile_id == profile.id)
    ).all()
    assert len(rows) == 1


async def test_nonexistent_skill_returns_404(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    response = await client.post(
        "/me/profile/skills",
        json={"skill_id": str(uuid.uuid4())},
        headers=auth_headers(user),
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Skill not found."
    assert association_count(db_session, profile) == 0


async def test_invalid_input_returns_422(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    not_a_uuid = await client.post(
        "/me/profile/skills",
        json={"skill_id": "not-a-uuid"},
        headers=auth_headers(user),
    )
    missing_field = await client.post(
        "/me/profile/skills", json={}, headers=auth_headers(user)
    )
    assert not_a_uuid.status_code == 422
    assert missing_field.status_code == 422


# --- DELETE /me/profile/skills/{skill_id} ---------------------------------------------------

async def test_owner_can_remove_skill_association(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    skill = seed_skill(db_session, key="python", name="Python")
    await attach(client, user, skill)
    response = await client.delete(
        f"/me/profile/skills/{skill.id}", headers=auth_headers(user)
    )
    assert response.status_code == 204
    assert response.content == b""
    assert association_count(db_session, profile) == 0


async def test_canonical_skill_row_remains(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    skill = seed_skill(db_session, key="python", name="Python")
    await attach(client, user, skill)
    await client.delete(f"/me/profile/skills/{skill.id}", headers=auth_headers(user))
    surviving = db_session.get(Skill, skill.id)
    assert surviving is not None
    assert surviving.key == "python"
    assert surviving.name == "Python"


async def test_profile_remains_after_detach(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    skill = seed_skill(db_session, key="python", name="Python")
    await attach(client, user, skill)
    await client.delete(f"/me/profile/skills/{skill.id}", headers=auth_headers(user))
    assert db_session.get(Profile, profile.id) is not None
    assert db_session.get(User, user.id) is not None


async def test_other_skills_remain_attached(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    keep = seed_skill(db_session, key="python", name="Python")
    drop = seed_skill(db_session, key="docker", name="Docker")
    await attach(client, user, keep)
    await attach(client, user, drop)
    await client.delete(f"/me/profile/skills/{drop.id}", headers=auth_headers(user))
    remaining = {
        row["key"]
        for row in (
            await client.get("/me/profile/skills", headers=auth_headers(user))
        ).json()
    }
    assert remaining == {"python"}
    assert association_count(db_session, profile) == 1


async def test_missing_association_returns_404(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    skill = seed_skill(db_session, key="python", name="Python")
    response = await client.delete(
        f"/me/profile/skills/{skill.id}", headers=auth_headers(user)
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Skill is not attached to this profile."


async def test_another_users_association_cannot_be_removed(
    client: AsyncClient, db_session: Session
):
    victim = seed_user(db_session)
    victim_profile = seed_profile(db_session, victim)
    attacker = seed_user(db_session)
    seed_profile(db_session, attacker)
    skill = seed_skill(db_session, key="python", name="Python")
    await attach(client, victim, skill)
    response = await client.delete(
        f"/me/profile/skills/{skill.id}", headers=auth_headers(attacker)
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Skill is not attached to this profile."
    assert association_count(db_session, victim_profile) == 1


async def test_delete_requires_authentication(client: AsyncClient):
    response = await client.delete(f"/me/profile/skills/{uuid.uuid4()}")
    assert response.status_code == 401


# --- Ownership / security -------------------------------------------------------------------

async def test_user_a_cannot_attach_skill_to_user_b_profile(
    client: AsyncClient, db_session: Session
):
    victim = seed_user(db_session)
    victim_profile = seed_profile(db_session, victim)
    attacker = seed_user(db_session)
    attacker_profile = seed_profile(db_session, attacker)
    skill = seed_skill(db_session, key="python", name="Python")
    response = await client.post(
        "/me/profile/skills",
        json={"skill_id": str(skill.id), "profile_id": str(victim_profile.id)},
        headers=auth_headers(attacker),
    )
    assert response.status_code == 422
    assert association_count(db_session, victim_profile) == 0
    # Without a profile_id the association always lands on the caller.
    await attach(client, attacker, skill)
    assert association_count(db_session, attacker_profile) == 1
    assert association_count(db_session, victim_profile) == 0


async def test_user_a_cannot_remove_user_b_association(
    client: AsyncClient, db_session: Session
):
    victim = seed_user(db_session)
    victim_profile = seed_profile(db_session, victim)
    attacker = seed_user(db_session)
    seed_profile(db_session, attacker)
    skill = seed_skill(db_session, key="python", name="Python")
    await attach(client, victim, skill)
    await client.delete(f"/me/profile/skills/{skill.id}", headers=auth_headers(attacker))
    assert association_count(db_session, victim_profile) == 1


async def test_arbitrary_profile_id_cannot_change_ownership(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    other = seed_user(db_session)
    other_profile = seed_profile(db_session, other)
    skill = seed_skill(db_session, key="python", name="Python")
    response = await client.post(
        "/me/profile/skills",
        json={"skill_id": str(skill.id), "profile_id": str(other_profile.id)},
        headers=auth_headers(user),
    )
    assert response.status_code == 422
    assert association_count(db_session, other_profile) == 0
    assert association_count(db_session, profile) == 0
    # The legitimate path still attaches to the caller's own profile.
    await attach(client, user, skill)
    row = db_session.scalar(select(ProfileSkill).where(ProfileSkill.skill_id == skill.id))
    assert row.profile_id == profile.id


async def test_skill_id_is_not_a_backdoor_to_other_profiles(
    client: AsyncClient, db_session: Session
):
    victim = seed_user(db_session)
    victim_profile = seed_profile(db_session, victim)
    attacker = seed_user(db_session)
    seed_profile(db_session, attacker)
    skill = seed_skill(db_session, key="python", name="Python")
    await attach(client, victim, skill)
    listed = await client.get("/me/profile/skills", headers=auth_headers(attacker))
    assert listed.status_code == 200
    assert listed.json() == []
    removed = await client.delete(
        f"/me/profile/skills/{skill.id}", headers=auth_headers(attacker)
    )
    assert removed.status_code == 404
    assert association_count(db_session, victim_profile) == 1


# --- Domain integrity -----------------------------------------------------------------------

async def test_same_skill_can_belong_to_multiple_profiles(
    client: AsyncClient, db_session: Session
):
    first_user = seed_user(db_session)
    first_profile = seed_profile(db_session, first_user)
    second_user = seed_user(db_session)
    second_profile = seed_profile(db_session, second_user)
    skill = seed_skill(db_session, key="python", name="Python")
    await attach(client, first_user, skill)
    await attach(client, second_user, skill)
    assert association_count(db_session, first_profile) == 1
    assert association_count(db_session, second_profile) == 1
    assert db_session.scalar(
        select(func.count()).select_from(ProfileSkill).where(ProfileSkill.skill_id == skill.id)
    ) == 2


async def test_duplicate_constraint_prevented_at_db_level(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    skill = seed_skill(db_session, key="python", name="Python")
    await attach(client, user, skill)
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(ProfileSkill(profile_id=profile.id, skill_id=skill.id))
            db_session.flush()


async def test_deleting_profile_preserves_canonical_skills(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    skill = seed_skill(db_session, key="python", name="Python")
    await attach(client, user, skill)
    profile_id, skill_id = profile.id, skill.id
    db_session.delete(profile)
    db_session.flush()
    assert db_session.get(Profile, profile_id) is None
    assert db_session.get(Skill, skill_id) is not None
    assert db_session.scalar(
        select(func.count()).select_from(ProfileSkill).where(ProfileSkill.profile_id == profile_id)
    ) == 0


async def test_deleting_skill_removes_associations_and_preserves_profile(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    skill = seed_skill(db_session, key="python", name="Python")
    await attach(client, user, skill)
    profile_id, skill_id = profile.id, skill.id
    db_session.delete(skill)
    db_session.flush()
    assert db_session.get(Skill, skill_id) is None
    assert db_session.get(Profile, profile_id) is not None
    assert db_session.scalar(
        select(func.count()).select_from(ProfileSkill).where(ProfileSkill.skill_id == skill_id)
    ) == 0
