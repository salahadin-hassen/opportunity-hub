"""Persistence and validation coverage for the Skills domain slice.

Every test runs inside the transaction provided by ``db_session`` and is
rolled back afterwards, so the dedicated test database stays clean.

Relationship contract exercised here:

* ``Profile.skills`` / ``Skill.profiles`` are the writable many-to-many path
  over ``secondary="profile_skills"``.
* ``Profile.profile_skills`` / ``Skill.profile_skills`` are ``viewonly`` read
  views of the association rows; they never write.
* :class:`ProfileSkill` rows are created directly (association object) or
  through the secondary relationship - never both for the same pair, which the
  unique ``(profile_id, skill_id)`` constraint rejects.
"""
from __future__ import annotations

import uuid
import warnings

import pytest
from pydantic import ValidationError
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError, SAWarning

from app.models import Profile, ProfileSkill, Skill
from app.schemas import ProfileCreate, SkillCreate


def make_profile(**overrides) -> Profile:
    payload = {
        "full_name": "Hanna Girma",
        "email": f"hanna-{uuid.uuid4().hex[:10]}@example.org",
        "citizenships": ["ET"],
        "country_of_residence": "ET",
        "degree_level": "bachelor",
        "is_currently_enrolled": True,
        "languages": ["am", "en"],
        "interests": ["machine learning"],
    }
    payload.update(overrides)
    return Profile(**ProfileCreate(**payload).model_dump())


def make_skill(**overrides) -> Skill:
    payload = {"key": f"skill-{uuid.uuid4().hex[:10]}", "name": "Example Skill"}
    payload.update(overrides)
    return Skill(**SkillCreate(**payload).model_dump())


def association_count(db_session, **filters) -> int:
    stmt = select(func.count()).select_from(ProfileSkill)
    for column, value in filters.items():
        stmt = stmt.where(getattr(ProfileSkill, column) == value)
    return db_session.scalar(stmt)


def test_skill_can_be_created(db_session):
    skill = make_skill(key="python", name="Python")
    db_session.add(skill)
    db_session.flush()
    db_session.refresh(skill)

    assert skill.key == "python"
    assert skill.name == "Python"
    assert skill.profiles == []


def test_skill_persists_uuid_and_created_at(db_session):
    skill = make_skill(key="postgresql", name="PostgreSQL")
    db_session.add(skill)
    db_session.flush()
    db_session.refresh(skill)

    assert isinstance(skill.id, uuid.UUID)
    assert skill.created_at is not None
    assert skill.created_at.tzinfo is not None


def test_skill_key_must_be_unique(db_session):
    db_session.add(make_skill(key="python", name="Python"))
    db_session.flush()

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(make_skill(key="python", name="Python (duplicate)"))
            db_session.flush()

    duplicates = db_session.scalar(
        select(func.count()).select_from(Skill).where(Skill.key == "python")
    )
    assert duplicates == 1


def test_skill_schema_rejects_uppercase_key():
    for key in ("Python", "PYTHON", "PyThOn", "python3SDK"):
        with pytest.raises(ValidationError):
            SkillCreate(key=key, name="Anything")


@pytest.mark.parametrize(
    "key",
    [
        "",
        "-python",
        "python-",
        "py_thon",
        "py thon",
        "py.thon",
        "py+thon",
        "héllo",
        "hello--world",
        "python!",
        " python",
        "python ",
    ],
)
def test_skill_schema_rejects_invalid_key_formats(key):
    with pytest.raises(ValidationError):
        SkillCreate(key=key, name="Anything")


@pytest.mark.parametrize("key", ["python", "python3", "node-js", "c99", "a-b-c"])
def test_skill_schema_accepts_lowercase_slug_keys(key):
    skill = SkillCreate(key=key, name="Skill")
    assert skill.key == key


def test_skill_schema_requires_key_and_does_not_generate_it():
    with pytest.raises(ValidationError):
        SkillCreate(name="Python")

    explicit = SkillCreate(key="web-dev", name="Web Development")
    assert explicit.key == "web-dev"


def test_database_check_constraint_rejects_invalid_key(db_session):
    with pytest.raises(DBAPIError):
        with db_session.begin_nested():
            db_session.execute(
                text("INSERT INTO skills (id, key, name) VALUES (:id, :key, :name)"),
                {"id": str(uuid.uuid4()), "key": "Python", "name": "Python"},
            )

    with pytest.raises(DBAPIError):
        with db_session.begin_nested():
            db_session.execute(
                text("INSERT INTO skills (id, key, name) VALUES (:id, :key, :name)"),
                {"id": str(uuid.uuid4()), "key": "py thon", "name": "Python"},
            )


def test_profile_skills_append_creates_exactly_one_association(db_session):
    profile = make_profile()
    skill = make_skill(key="python", name="Python")
    profile.skills.append(skill)
    db_session.add(profile)
    db_session.flush()

    assert association_count(db_session, profile_id=profile.id, skill_id=skill.id) == 1
    assert skill.id is not None

    db_session.expire_all()
    reloaded = db_session.get(Profile, profile.id)
    assert [item.key for item in reloaded.skills] == ["python"]


def test_profile_can_have_multiple_skills(db_session):
    profile = make_profile()
    profile.skills.extend([
        make_skill(key="python", name="Python"),
        make_skill(key="fastapi", name="FastAPI"),
        make_skill(key="postgresql", name="PostgreSQL"),
    ])
    db_session.add(profile)
    db_session.flush()
    db_session.expire_all()

    reloaded = db_session.get(Profile, profile.id)
    assert {item.key for item in reloaded.skills} == {"python", "fastapi", "postgresql"}
    assert association_count(db_session, profile_id=profile.id) == 3


def test_profile_skill_direct_creation_persists(db_session):
    profile = make_profile()
    skill = make_skill(key="docker", name="Docker")
    db_session.add_all([profile, skill])
    db_session.flush()

    association = ProfileSkill(profile=profile, skill=skill)
    db_session.add(association)
    db_session.flush()

    assert association.id is not None
    assert association.profile_id == profile.id
    assert association.skill_id == skill.id
    assert association.created_at is not None
    assert association_count(db_session, profile_id=profile.id) == 1

    db_session.expire_all()
    reloaded = db_session.get(Profile, profile.id)
    assert [item.key for item in reloaded.skills] == ["docker"]


def test_duplicate_profile_skill_association_is_rejected(db_session):
    profile = make_profile()
    skill = make_skill(key="python", name="Python")
    profile.skills.append(skill)
    db_session.add(profile)
    db_session.flush()

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(ProfileSkill(profile_id=profile.id, skill_id=skill.id))
            db_session.flush()

    assert association_count(db_session, profile_id=profile.id, skill_id=skill.id) == 1


def test_secondary_append_with_association_object_does_not_duplicate(db_session):
    """The viewonly association view must not add a second row for the pair."""
    profile = make_profile()
    skill = make_skill(key="python", name="Python")
    profile.skills.append(skill)
    profile.profile_skills.append(ProfileSkill(profile=profile, skill=skill))
    db_session.add(profile)
    db_session.flush()

    assert association_count(db_session, profile_id=profile.id, skill_id=skill.id) == 1

    db_session.expire_all()
    reloaded = db_session.get(Profile, profile.id)
    assert len(reloaded.profile_skills) == 1
    assert [item.key for item in reloaded.skills] == ["python"]


def test_skill_can_be_shared_by_multiple_profiles(db_session):
    skill = make_skill(key="python", name="Python")
    first = make_profile()
    second = make_profile()
    first.skills.append(skill)
    second.skills.append(skill)
    db_session.add_all([first, second])
    db_session.flush()
    db_session.expire_all()

    assert association_count(db_session, skill_id=skill.id) == 2

    reloaded = db_session.get(Skill, skill.id)
    assert {item.email for item in reloaded.profiles} == {first.email, second.email}
    assert db_session.get(Profile, first.id) is not None
    assert db_session.get(Profile, second.id) is not None


def test_profile_skills_relationship_loads(db_session):
    profile = make_profile()
    profile.skills.extend([
        make_skill(key="python", name="Python"),
        make_skill(key="kubernetes", name="Kubernetes"),
    ])
    db_session.add(profile)
    db_session.flush()
    db_session.expire_all()

    reloaded = db_session.get(Profile, profile.id)
    assert {item.key for item in reloaded.skills} == {"python", "kubernetes"}
    assert all(isinstance(item, Skill) for item in reloaded.skills)


def test_skill_profiles_relationship_loads(db_session):
    profile = make_profile()
    skill = make_skill(key="python", name="Python")
    profile.skills.append(skill)
    db_session.add(profile)
    db_session.flush()
    db_session.expire_all()

    reloaded = db_session.get(Skill, skill.id)
    assert [item.email for item in reloaded.profiles] == [profile.email]


def test_association_object_relationships_resolve(db_session):
    profile = make_profile()
    skill = make_skill(key="python", name="Python")
    profile.skills.append(skill)
    db_session.add(profile)
    db_session.flush()
    db_session.expire_all()

    profile = db_session.get(Profile, profile.id)
    association = profile.profile_skills[0]

    assert association.profile_id == profile.id
    assert association.skill_id == skill.id
    assert association.profile is profile
    assert association.skill is skill
    assert [item.key for item in association.profile.skills] == ["python"]

    reloaded_skill = db_session.get(Skill, skill.id)
    assert [item.id for item in reloaded_skill.profile_skills] == [association.id]
    assert reloaded_skill.profile_skills[0].profile is profile


def test_deleting_profile_removes_associations_and_preserves_skill(db_session):
    profile = make_profile()
    skill = make_skill(key="python", name="Python")
    profile.skills.append(skill)
    db_session.add(profile)
    db_session.flush()
    db_session.expire_all()

    profile = db_session.get(Profile, profile.id)
    assert len(profile.skills) == 1
    assert len(profile.profile_skills) == 1
    profile_id, skill_id = profile.id, skill.id

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        db_session.delete(profile)
        db_session.flush()

    assert not [item for item in caught if issubclass(item.category, SAWarning)]
    db_session.expire_all()
    assert association_count(db_session, profile_id=profile_id) == 0
    assert db_session.get(Profile, profile_id) is None
    assert db_session.get(Skill, skill_id) is not None


def test_deleting_skill_removes_associations_and_preserves_profile(db_session):
    profile = make_profile()
    skill = make_skill(key="python", name="Python")
    profile.skills.append(skill)
    db_session.add(profile)
    db_session.flush()
    db_session.expire_all()

    profile = db_session.get(Profile, profile.id)
    skill = db_session.get(Skill, skill.id)
    assert len(skill.profiles) == 1
    assert len(skill.profile_skills) == 1
    profile_id, skill_id = profile.id, skill.id

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        db_session.delete(skill)
        db_session.flush()

    assert not [item for item in caught if issubclass(item.category, SAWarning)]
    db_session.expire_all()
    assert association_count(db_session, skill_id=skill_id) == 0
    assert db_session.get(Skill, skill_id) is None
    assert db_session.get(Profile, profile_id) is not None


def test_profile_without_skills_has_empty_collections(db_session):
    profile = make_profile()
    db_session.add(profile)
    db_session.flush()
    db_session.expire_all()

    reloaded = db_session.get(Profile, profile.id)
    assert list(reloaded.skills) == []
    assert list(reloaded.profile_skills) == []
    assert association_count(db_session, profile_id=reloaded.id) == 0


def test_skills_schema_tables_columns_and_constraints(db_session):
    inspector = inspect(db_session.get_bind())

    assert {"skills", "profile_skills"} <= set(inspector.get_table_names())

    skill_columns = {column["name"]: column for column in inspector.get_columns("skills")}
    assert set(skill_columns) == {"id", "key", "name", "created_at"}
    assert str(skill_columns["id"]["type"]) == "UUID"
    assert skill_columns["id"]["nullable"] is False
    assert str(skill_columns["key"]["type"]) == "VARCHAR(255)"
    assert skill_columns["key"]["nullable"] is False
    assert str(skill_columns["name"]["type"]) == "VARCHAR(255)"
    assert skill_columns["created_at"]["type"].timezone is True
    assert "now" in (skill_columns["created_at"]["default"] or "")

    association_columns = {column["name"]: column for column in inspector.get_columns("profile_skills")}
    assert set(association_columns) == {"id", "profile_id", "skill_id", "created_at"}
    for name in ("id", "profile_id", "skill_id"):
        assert str(association_columns[name]["type"]) == "UUID"
        assert association_columns[name]["nullable"] is False
    assert association_columns["created_at"]["type"].timezone is True
    assert "now" in (association_columns["created_at"]["default"] or "")

    assert inspector.get_pk_constraint("skills")["constrained_columns"] == ["id"]
    assert inspector.get_pk_constraint("profile_skills")["constrained_columns"] == ["id"]

    foreign_keys = {
        tuple(foreign_key["constrained_columns"]): foreign_key
        for foreign_key in inspector.get_foreign_keys("profile_skills")
    }
    profile_fk = foreign_keys[("profile_id",)]
    assert profile_fk["referred_table"] == "profiles"
    assert profile_fk["referred_columns"] == ["id"]
    assert profile_fk["options"]["ondelete"] == "CASCADE"
    skill_fk = foreign_keys[("skill_id",)]
    assert skill_fk["referred_table"] == "skills"
    assert skill_fk["referred_columns"] == ["id"]
    assert skill_fk["options"]["ondelete"] == "CASCADE"

    assert any(
        constraint["column_names"] == ["key"]
        for constraint in inspector.get_unique_constraints("skills")
    )
    assert any(
        constraint["column_names"] == ["profile_id", "skill_id"]
        for constraint in inspector.get_unique_constraints("profile_skills")
    )

    check_constraints = {
        constraint["name"]: constraint["sqltext"]
        for constraint in inspector.get_check_constraints("skills")
    }
    key_check = check_constraints["ck_skills_key_format"]
    assert "^[a-z0-9]+(?:-[a-z0-9]+)*$" in key_check

    index_names = {index["name"] for index in inspector.get_indexes("profile_skills")}
    assert {"ix_profile_skills_profile_id", "ix_profile_skills_skill_id"} <= index_names
    skill_indexes = {index["name"]: index for index in inspector.get_indexes("skills")}
    assert skill_indexes["skills_key_key"]["unique"] is True

    assert inspector.get_enums() == []
    for table in ("skills", "profile_skills"):
        assert not any(
            type(column["type"]).__name__ == "ENUM"
            for column in inspector.get_columns(table)
        )
