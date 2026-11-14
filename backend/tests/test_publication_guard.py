"""P0-3 regression tests: only the validated publish operation may make an opportunity public.

Covers malicious or accidental payloads that try to create or edit an opportunity straight into
``published`` (or forge ``published_at``), the draft -> close shortcut to public visibility, and the
audit trail for both accepted and rejected publication.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models import (
    AuditLog,
    Opportunity,
    OpportunityStatus,
    Requirement,
    RequirementCategory,
    RequirementKind,
    Source,
    SourceType,
    User,
)
from app.schemas import OpportunityCreate
from app.services.opportunities import create_opportunity, publish_opportunity

FORGED_AT = "2020-01-01T00:00:00Z"


@pytest.fixture
async def client(db_session: Session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def curator(db_session: Session) -> tuple[User, dict[str, str]]:
    user = User(email=f"curator-{uuid.uuid4().hex[:8]}@example.org", password_hash="x", role="curator")
    db_session.add(user)
    db_session.flush()
    return user, {"Authorization": f"Bearer {create_access_token(user.id)}"}


def draft_payload(**extra) -> dict:
    return {"slug": f"guard-{uuid.uuid4().hex[:10]}", "title": "Guarded Fellowship", **extra}


def complete(db_session: Session, opportunity_id: uuid.UUID, *, quote: str | None = "Applicants must be enrolled.") -> None:
    """Attach the evidence publication requires (official URL, an http(s) source, a quoted mandatory rule)."""
    opp = db_session.get(Opportunity, opportunity_id)
    opp.official_url = "https://example.org/fellowship"
    source = Source(
        opportunity_id=opportunity_id,
        source_type=SourceType.OFFICIAL_PAGE,
        url="https://example.org/fellowship",
        retrieved_at=datetime.now(timezone.utc),
        is_primary=True,
    )
    db_session.add(source)
    db_session.flush()
    db_session.add(
        Requirement(
            opportunity_id=opportunity_id,
            order_index=0,
            label="Enrolled student",
            kind=RequirementKind.EQUALITY,
            params={"metric": "degree_level", "expected": "bachelor"},
            is_mandatory=True,
            category=RequirementCategory.ACADEMIC,
            source_id=source.id,
            source_quote=quote,
        )
    )
    db_session.flush()


def actions_for(db_session: Session, opportunity_id) -> list[str]:
    rows = db_session.scalars(
        select(AuditLog).where(AuditLog.target_type == "opportunity", AuditLog.target_id == str(opportunity_id)).order_by(AuditLog.id)
    )
    return [row.action for row in rows]


async def create(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    response = await client.post("/opportunities", headers=headers, json=draft_payload())
    assert response.status_code == 201
    return uuid.UUID(response.json()["id"])


# --- Create ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "extra",
    [
        {"status": "published"},
        {"status": "closed"},  # closed is publicly readable too
        {"status": "draft"},  # any lifecycle key is refused, not silently honoured
        {"published_at": FORGED_AT},
        {"status": "published", "published_at": FORGED_AT},
    ],
)
async def test_create_refuses_lifecycle_fields_and_writes_nothing(client, db_session, curator, extra):
    _, headers = curator
    payload = draft_payload(**extra)
    response = await client.post("/opportunities", headers=headers, json=payload)
    assert response.status_code == 422
    assert db_session.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.slug == payload["slug"])) == 0


async def test_create_always_produces_an_unpublished_draft(client, db_session, curator):
    _, headers = curator
    response = await client.post("/opportunities", headers=headers, json=draft_payload())
    assert response.status_code == 201
    assert response.json()["status"] == "draft"
    assert response.json()["published_at"] is None
    assert (await client.get(f"/opportunities/{response.json()['id']}")).status_code == 404


def test_the_service_forces_draft_whatever_it_is_given(db_session):
    opp = create_opportunity(db_session, OpportunityCreate(**draft_payload()))
    assert opp.status == OpportunityStatus.DRAFT and opp.published_at is None


# --- Update ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"status": "published"},
        {"status": "closed"},
        {"published_at": FORGED_AT},
        {"title": "Innocent edit", "status": "published"},
    ],
)
async def test_patch_refuses_lifecycle_fields_and_changes_nothing(client, db_session, curator, body):
    _, headers = curator
    opp_id = await create(client, headers)
    complete(db_session, opp_id)  # even a complete draft may only be published through /publish

    response = await client.patch(f"/curate/opportunities/{opp_id}", headers=headers, json=body)

    assert response.status_code == 422
    db_session.expire_all()
    row = db_session.get(Opportunity, opp_id)
    assert row.status == OpportunityStatus.DRAFT
    assert row.published_at is None
    assert row.title == "Guarded Fellowship"
    assert "opportunity.updated" not in actions_for(db_session, opp_id)


async def test_patch_cannot_rewrite_published_at_of_a_published_opportunity(client, db_session, curator):
    _, headers = curator
    opp_id = await create(client, headers)
    complete(db_session, opp_id)
    published = await client.post(f"/curate/opportunities/{opp_id}/publish", headers=headers)
    original = published.json()["published_at"]

    response = await client.patch(f"/curate/opportunities/{opp_id}", headers=headers, json={"published_at": FORGED_AT})

    assert response.status_code == 422
    db_session.expire_all()
    assert db_session.get(Opportunity, opp_id).published_at.isoformat().startswith(original[:19])


# --- Close -----------------------------------------------------------------------------------------------


async def test_a_draft_cannot_be_closed_into_public_view(client, db_session, curator):
    _, headers = curator
    opp_id = await create(client, headers)

    response = await client.post(f"/curate/opportunities/{opp_id}/close", headers=headers)

    assert response.status_code == 409
    db_session.expire_all()
    assert db_session.get(Opportunity, opp_id).status == OpportunityStatus.DRAFT
    assert (await client.get(f"/opportunities/{opp_id}")).status_code == 404
    assert "opportunity.closed" not in actions_for(db_session, opp_id)


# --- Publish ---------------------------------------------------------------------------------------------


async def test_incomplete_publication_is_rejected_audited_and_changes_nothing(client, db_session, curator):
    user, headers = curator
    opp_id = await create(client, headers)

    response = await client.post(f"/curate/opportunities/{opp_id}/publish", headers=headers)

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "official http(s) URL" in detail and "source" in detail and "eligibility rule" in detail
    db_session.expire_all()
    row = db_session.get(Opportunity, opp_id)
    assert row.status == OpportunityStatus.DRAFT and row.published_at is None
    rejection = db_session.scalar(
        select(AuditLog).where(AuditLog.action == "opportunity.publish_rejected", AuditLog.target_id == str(opp_id))
    )
    assert rejection is not None and rejection.actor_user_id == user.id
    assert "official http(s) URL" in rejection.reason
    assert rejection.changes == {"status": "draft"}


async def test_an_unquoted_mandatory_rule_blocks_publication(client, db_session, curator):
    _, headers = curator
    opp_id = await create(client, headers)
    complete(db_session, opp_id, quote="   ")

    response = await client.post(f"/curate/opportunities/{opp_id}/publish", headers=headers)

    assert response.status_code == 400
    assert "verbatim source quote" in response.json()["detail"]
    db_session.expire_all()
    assert db_session.get(Opportunity, opp_id).status == OpportunityStatus.DRAFT


async def test_a_non_http_source_is_not_evidence(client, db_session, curator):
    _, headers = curator
    opp_id = await create(client, headers)
    complete(db_session, opp_id)
    for source in db_session.get(Opportunity, opp_id).sources:
        source.url = "file:///etc/passwd"
    db_session.flush()

    response = await client.post(f"/curate/opportunities/{opp_id}/publish", headers=headers)

    assert response.status_code == 400
    assert "source record with an http(s) URL" in response.json()["detail"]


async def test_complete_publication_succeeds_and_is_audited(client, db_session, curator):
    _, headers = curator
    opp_id = await create(client, headers)
    complete(db_session, opp_id)

    response = await client.post(f"/curate/opportunities/{opp_id}/publish", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "published"
    published_at = datetime.fromisoformat(body["published_at"].replace("Z", "+00:00"))
    assert abs((datetime.now(timezone.utc) - published_at).total_seconds()) < 60  # server time, never the client's
    assert (await client.get(f"/opportunities/{opp_id}")).status_code == 200
    assert actions_for(db_session, opp_id) == ["opportunity.created", "opportunity.published"]


@pytest.mark.parametrize("status", [OpportunityStatus.PUBLISHED, OpportunityStatus.ARCHIVED])
async def test_publish_is_refused_from_published_or_archived(client, db_session, curator, status):
    _, headers = curator
    opp_id = await create(client, headers)
    complete(db_session, opp_id)
    db_session.get(Opportunity, opp_id).status = status  # test arrangement through the ORM
    db_session.flush()

    response = await client.post(f"/curate/opportunities/{opp_id}/publish", headers=headers)

    assert response.status_code == 409
    assert "opportunity.publish_rejected" in actions_for(db_session, opp_id)


def test_the_service_refuses_incomplete_publication_without_writing(db_session):
    from app.services.opportunities import IncompleteOpportunityError

    opp = create_opportunity(db_session, OpportunityCreate(**draft_payload()))
    with pytest.raises(IncompleteOpportunityError):
        publish_opportunity(db_session, opp.id)
    db_session.expire_all()
    assert db_session.get(Opportunity, opp.id).status == OpportunityStatus.DRAFT


async def test_students_cannot_publish_or_close(client, db_session):
    student = User(email=f"student-{uuid.uuid4().hex[:8]}@example.org", password_hash="x", role="student")
    db_session.add(student)
    db_session.flush()
    headers = {"Authorization": f"Bearer {create_access_token(student.id)}"}
    for path in ("publish", "close"):
        assert (await client.post(f"/curate/opportunities/{uuid.uuid4()}/{path}", headers=headers)).status_code == 403
    assert (await client.post("/opportunities", headers=headers, json=draft_payload())).status_code == 403
