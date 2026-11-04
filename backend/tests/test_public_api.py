"""Public read surface: published-only listing, rule disclosure, the skill
catalog and curator-only opportunity creation."""
from __future__ import annotations

import uuid

import pytest
from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models import Opportunity, Profile, Requirement, Skill, Source, User
from app.schemas import OpportunityCreate, RequirementCreate
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

TEST_JWT_SECRET = "test-only-public-api-secret-0123456789abcdef"
#: The retired shared curator header; sending it must grant nothing.
RETIRED_ADMIN_HEADER = "X-Admin-Token"


def opportunity(status: str = "published", **overrides) -> Opportunity:
    payload = {
        "slug": f"public-{uuid.uuid4().hex[:10]}",
        "title": "Public Research Call",
        "opportunity_type": "research_program",
        "status": status,
    }
    payload.update(overrides)
    return Opportunity(**OpportunityCreate(**payload).model_dump())


def creation_payload() -> dict[str, object]:
    return {"slug": f"created-{uuid.uuid4().hex[:10]}", "title": "Created Call"}


@pytest.fixture
async def client(db_session: Session, monkeypatch):
    def override_get_db():
        yield db_session

    monkeypatch.setattr(settings, "JWT_SECRET", TEST_JWT_SECRET)
    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()


def add(db_session: Session, *rows) -> None:
    db_session.add_all(rows)
    db_session.flush()


# --- D: published-only public reads ---------------------------------------------------------


@pytest.mark.asyncio
async def test_listing_contains_only_published_opportunities(client, db_session):
    rows = {status: opportunity(status) for status in ("published", "draft", "closed", "archived")}
    add(db_session, *rows.values())

    response = await client.get("/opportunities", params={"limit": 100})

    assert response.status_code == 200
    listed = {item["id"] for item in response.json()}
    assert str(rows["published"].id) in listed
    for hidden in ("draft", "closed", "archived"):
        assert str(rows[hidden].id) not in listed
    assert {item["status"] for item in response.json()} == {"published"}


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["draft", "archived"])
async def test_non_public_detail_is_indistinguishable_from_missing(client, db_session, status):
    hidden = opportunity(status)
    add(db_session, hidden)

    response = await client.get(f"/opportunities/{hidden.id}")
    missing = await client.get(f"/opportunities/{uuid.uuid4()}")

    assert response.status_code == missing.status_code == 404
    assert response.json() == missing.json()


@pytest.mark.asyncio
async def test_closed_opportunity_detail_stays_readable(client, db_session):
    closed = opportunity("closed")
    add(db_session, closed)

    response = await client.get(f"/opportunities/{closed.id}")

    assert response.status_code == 200
    assert response.json()["status"] == "closed"


# --- C: rules and sources on the public detail ---------------------------------------------


def seed_rules(db_session: Session) -> tuple[Opportunity, Source]:
    target = opportunity()
    source = Source(
        opportunity=target,
        source_type="official_page",
        url="https://example.org/call",
        publisher="Example Org",
        is_primary=True,
        content_hash="sha256:internal",
        raw_snapshot={"html": "<p>internal</p>"},
        notes="curator note",
    )
    add(db_session, target, source)
    for index, payload in enumerate(
        [
            {
                "label": "Currently enrolled",
                "kind": "boolean_flag",
                "params": {"metric": "is_currently_enrolled", "expected": True},
                "category": "academic",
            },
            {
                "label": "GPA at least 3.0",
                "kind": "numeric_threshold",
                "params": {"metric": "gpa", "operator": ">=", "value": 3.0, "scale": 4.0},
                "category": "academic",
                "source_id": source.id,
                "source_quote": "Applicants need a GPA of at least 3.0.",
                "notes": "curator note",
            },
        ]
    ):
        requirement = Requirement(
            **RequirementCreate(**payload, order_index=1 - index).model_dump()
        )
        requirement.opportunity = target
        db_session.add(requirement)
    db_session.flush()
    db_session.expire(target)
    return target, source


@pytest.mark.asyncio
async def test_detail_includes_ordered_rules_with_quotes(client, db_session):
    target, source = seed_rules(db_session)

    body = (await client.get(f"/opportunities/{target.id}")).json()

    assert [rule["label"] for rule in body["requirements"]] == [
        "GPA at least 3.0",
        "Currently enrolled",
    ]
    gpa = body["requirements"][0]
    assert gpa["kind"] == "numeric_threshold"
    assert gpa["params"] == {"metric": "gpa", "operator": ">=", "value": 3.0, "scale": 4.0}
    assert gpa["source_id"] == str(source.id)
    assert gpa["source_quote"] == "Applicants need a GPA of at least 3.0."
    assert gpa["is_mandatory"] is True


@pytest.mark.asyncio
async def test_detail_never_exposes_curator_internals(client, db_session):
    target, _ = seed_rules(db_session)

    body = (await client.get(f"/opportunities/{target.id}")).json()

    assert body["sources"] == [
        {
            "id": body["sources"][0]["id"],
            "source_type": "official_page",
            "url": "https://example.org/call",
            "publisher": "Example Org",
            "retrieved_at": body["sources"][0]["retrieved_at"],
            "is_primary": True,
        }
    ]
    for rule in body["requirements"]:
        assert set(rule) == {
            "id", "order_index", "label", "kind", "params", "is_mandatory",
            "category", "source_id", "source_quote", "is_ambiguous",
        }


@pytest.mark.asyncio
async def test_listing_stays_lightweight_without_rules(client, db_session):
    target, _ = seed_rules(db_session)

    listed = (await client.get("/opportunities", params={"limit": 100})).json()

    row = next(item for item in listed if item["id"] == str(target.id))
    assert "requirements" not in row and "sources" not in row


# --- Matching respects visibility ------------------------------------------------------------


def seed_owner_with_profile(db_session: Session) -> User:
    user = User(email=f"owner-{uuid.uuid4().hex[:8]}@example.test", password_hash="x")
    add(db_session, user)
    profile = Profile(
        user_id=user.id,
        full_name="Owner",
        email=f"profile-{uuid.uuid4().hex[:8]}@example.test",
        degree_level="bachelor",
    )
    add(db_session, profile)
    return user


@pytest.mark.asyncio
async def test_drafts_cannot_be_evaluated_or_read_through_matching(client, db_session):
    user = seed_owner_with_profile(db_session)
    draft = opportunity("draft")
    add(db_session, draft)
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}

    evaluated = await client.post(f"/me/opportunities/{draft.id}/match", headers=headers)
    read = await client.get(f"/me/opportunities/{draft.id}/match", headers=headers)

    assert evaluated.status_code == read.status_code == 404
    assert evaluated.json() == read.json() == {"detail": "Opportunity not found."}


@pytest.mark.asyncio
async def test_published_opportunity_can_still_be_evaluated(client, db_session):
    user = seed_owner_with_profile(db_session)
    published = opportunity()
    add(db_session, published)
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}

    response = await client.post(f"/me/opportunities/{published.id}/match", headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "eligible"


# --- B: skill catalog ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skill_catalog_is_public_and_ordered_by_key(client, db_session):
    suffix = uuid.uuid4().hex[:6]
    add(
        db_session,
        Skill(key=f"zz-python-{suffix}", name="Python"),
        Skill(key=f"aa-matlab-{suffix}", name="MATLAB"),
    )

    response = await client.get("/skills")

    assert response.status_code == 200
    keys = [item["key"] for item in response.json()]
    assert keys == sorted(keys)
    assert {f"zz-python-{suffix}", f"aa-matlab-{suffix}"} <= set(keys)
    assert set(response.json()[0]) == {"id", "key", "name", "created_at"}


@pytest.mark.asyncio
async def test_skill_catalog_has_no_write_route(client):
    response = await client.post("/skills", json={"key": "rust", "name": "Rust"})

    assert response.status_code == 405


# --- Curator-only creation ------------------------------------------------------------------


def bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def seed_user(db_session: Session, role: str) -> User:
    user = User(email=f"{role}-{uuid.uuid4().hex[:8]}@example.test", password_hash="x", role=role)
    add(db_session, user)
    return user


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [{}, {RETIRED_ADMIN_HEADER: "anything"}, {RETIRED_ADMIN_HEADER: ""}])
async def test_creation_requires_a_signed_in_account(client, headers):
    response = await client.post("/opportunities", json=creation_payload(), headers=headers)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_a_student_account_cannot_create(client, db_session):
    user = seed_owner_with_profile(db_session)

    response = await client.post("/opportunities", json=creation_payload(), headers=bearer(user))

    assert response.status_code == 403
    assert response.json() == {"detail": "You do not have permission for this action."}


@pytest.mark.asyncio
async def test_the_retired_shared_header_adds_nothing_to_a_student(client, db_session):
    user = seed_owner_with_profile(db_session)

    response = await client.post(
        "/opportunities", json=creation_payload(), headers={**bearer(user), RETIRED_ADMIN_HEADER: "anything"}
    )

    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["curator", "admin"])
async def test_curators_and_admins_can_create(client, db_session, role):
    response = await client.post("/opportunities", json=creation_payload(), headers=bearer(seed_user(db_session, role)))

    assert response.status_code == 201
