"""R-1 regression tests: an edit can never leave a published (or closed, publicly readable) opportunity
failing publication requirements; plus the evidence-linkage rules publication now enforces.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models import AuditLog, Opportunity, OpportunityStatus, Requirement, Source, User
from app.schemas import OpportunityCreate, OpportunityUpdate
from app.services.opportunities import (
    OpportunityWouldBecomeIncompleteError,
    create_opportunity,
    publish_opportunity,
    update_opportunity,
)

OFFICIAL = "https://example.org/fellowship"


@pytest.fixture
async def client(db_session: Session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def curator(db_session: Session) -> dict[str, str]:
    user = User(email=f"curator-{uuid.uuid4().hex[:8]}@example.org", password_hash="x", role="curator")
    db_session.add(user)
    db_session.flush()
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def make_complete(db_session: Session, *, status: OpportunityStatus | None = OpportunityStatus.PUBLISHED) -> Opportunity:
    """A complete opportunity, published through the validated path (then closed if asked)."""
    opp = create_opportunity(
        db_session,
        OpportunityCreate(slug=f"edit-{uuid.uuid4().hex[:10]}", title="Complete Fellowship", official_url=OFFICIAL,
                          description="Original description"),
    )
    source = Source(opportunity_id=opp.id, source_type="official_page", url=OFFICIAL, retrieved_at=datetime.now(timezone.utc), is_primary=True)
    db_session.add(source)
    db_session.flush()
    db_session.add(Requirement(opportunity_id=opp.id, order_index=0, label="Bachelor", kind="equality",
                               params={"metric": "degree_level", "expected": "bachelor"}, is_mandatory=True,
                               category="academic", source_id=source.id, source_quote="Applicants must hold a bachelor degree."))
    db_session.flush()
    if status in (OpportunityStatus.PUBLISHED, OpportunityStatus.CLOSED):
        publish_opportunity(db_session, opp.id)
    if status == OpportunityStatus.CLOSED:
        opp.status = OpportunityStatus.CLOSED
        db_session.flush()
    return opp


def fresh(db_session: Session, opp_id) -> Opportunity:
    db_session.expire_all()
    return db_session.get(Opportunity, opp_id)


def actions(db_session: Session, opp_id) -> list[AuditLog]:
    return list(db_session.scalars(select(AuditLog).where(AuditLog.target_id == str(opp_id)).order_by(AuditLog.id)))


# --- The reported reproduction ---------------------------------------------------------------------------


async def test_patching_official_url_to_null_on_a_published_opportunity_is_refused(client, db_session, curator):
    opp = make_complete(db_session)

    response = await client.patch(f"/curate/opportunities/{opp.id}", headers=curator, json={"official_url": None})

    assert response.status_code == 409
    assert "official http(s) URL" in response.json()["detail"]
    row = fresh(db_session, opp.id)
    assert row.status == OpportunityStatus.PUBLISHED and row.official_url == OFFICIAL
    assert (await client.get(f"/opportunities/{opp.id}")).json()["official_url"] == OFFICIAL
    rejection = actions(db_session, opp.id)[-1]
    assert rejection.action == "opportunity.update_rejected"
    assert rejection.changes == {"fields": ["official_url"], "status": "published"}
    assert "official http(s) URL" in rejection.reason


async def test_a_rejected_edit_changes_none_of_its_fields(client, db_session, curator):
    opp = make_complete(db_session)

    response = await client.patch(
        f"/curate/opportunities/{opp.id}", headers=curator,
        json={"description": "Sneaky new text", "host_name": "Someone", "official_url": None},
    )

    assert response.status_code == 409
    row = fresh(db_session, opp.id)
    assert (row.description, row.host_name, row.official_url) == ("Original description", None, OFFICIAL)
    assert "opportunity.updated" not in [entry.action for entry in actions(db_session, opp.id)]


async def test_closed_opportunities_are_public_and_protected_too(client, db_session, curator):
    opp = make_complete(db_session, status=OpportunityStatus.CLOSED)
    response = await client.patch(f"/curate/opportunities/{opp.id}", headers=curator, json={"official_url": None})
    assert response.status_code == 409
    assert fresh(db_session, opp.id).official_url == OFFICIAL


async def test_edits_that_keep_a_published_opportunity_complete_are_allowed_and_audited(client, db_session, curator):
    opp = make_complete(db_session)

    response = await client.patch(
        f"/curate/opportunities/{opp.id}", headers=curator,
        json={"description": "Clarified", "official_url": "https://example.org/fellowship-2027"},
    )

    assert response.status_code == 200
    row = fresh(db_session, opp.id)
    assert row.status == OpportunityStatus.PUBLISHED and row.official_url == "https://example.org/fellowship-2027"
    assert actions(db_session, opp.id)[-1].action == "opportunity.updated"


async def test_drafts_may_be_incomplete_while_being_edited(client, db_session, curator):
    opp = make_complete(db_session, status=None)
    response = await client.patch(f"/curate/opportunities/{opp.id}", headers=curator, json={"official_url": None})
    assert response.status_code == 200
    assert fresh(db_session, opp.id).official_url is None


@pytest.mark.parametrize(
    "body",
    [{"title": None}, {"title": "   "}, {"opportunity_type": None}, {"deadline_type": None},
     {"location_mode": None}, {"countries": None}, {"languages": None}, {"tags": None}],
)
async def test_required_fields_cannot_be_nulled_or_blanked_on_any_opportunity(client, db_session, curator, body):
    for status in (OpportunityStatus.PUBLISHED, None):
        opp = make_complete(db_session, status=status)
        response = await client.patch(f"/curate/opportunities/{opp.id}", headers=curator, json=body)
        assert response.status_code == 422, (status, body)
        assert fresh(db_session, opp.id).title == "Complete Fellowship"


async def test_evidence_removed_outside_the_api_blocks_further_edits_until_restored(client, db_session, curator):
    """Other completeness inputs (rules, quotes, sources) are re-checked on every edit of a public record."""
    opp = make_complete(db_session)
    requirement = fresh(db_session, opp.id).requirements[0]
    requirement.source_quote = " "
    db_session.flush()

    blocked = await client.patch(f"/curate/opportunities/{opp.id}", headers=curator, json={"description": "x"})
    assert blocked.status_code == 409 and "verbatim source quote" in blocked.json()["detail"]

    requirement.source_quote = "Applicants must hold a bachelor degree."
    db_session.flush()
    assert (await client.patch(f"/curate/opportunities/{opp.id}", headers=curator, json={"description": "x"})).status_code == 200


def test_the_service_refuses_and_rolls_back_without_the_api(db_session):
    opp = make_complete(db_session)
    with pytest.raises(OpportunityWouldBecomeIncompleteError):
        update_opportunity(db_session, opp.id, OpportunityUpdate(official_url=None, description="changed"))
    row = fresh(db_session, opp.id)
    assert (row.official_url, row.description) == (OFFICIAL, "Original description")


# --- Evidence linkage ------------------------------------------------------------------------------------


async def _publish(client, curator, opp_id):
    return await client.post(f"/curate/opportunities/{opp_id}/publish", headers=curator)


async def test_a_mandatory_rule_citing_no_source_blocks_publication(client, db_session, curator):
    opp = make_complete(db_session, status=None)
    fresh(db_session, opp.id).requirements[0].source_id = None
    db_session.flush()
    response = await _publish(client, curator, opp.id)
    assert response.status_code == 400
    assert "do not cite one of this opportunity's own source records" in response.json()["detail"]


async def test_a_mandatory_rule_citing_another_opportunitys_source_blocks_publication(client, db_session, curator):
    other = make_complete(db_session, status=None)
    opp = make_complete(db_session, status=None)
    fresh(db_session, opp.id).requirements[0].source_id = fresh(db_session, other.id).sources[0].id
    db_session.flush()
    response = await _publish(client, curator, opp.id)
    assert response.status_code == 400
    assert "own source records" in response.json()["detail"]
    assert fresh(db_session, opp.id).status == OpportunityStatus.DRAFT


async def test_a_rule_citing_its_own_non_http_source_is_not_evidence(client, db_session, curator):
    opp = make_complete(db_session, status=None)
    fresh(db_session, opp.id).sources[0].url = "file:///tmp/page.html"
    db_session.flush()
    response = await _publish(client, curator, opp.id)
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "source record with an http(s) URL" in detail and "own source records" in detail


async def test_messages_do_not_claim_verification(client, db_session, curator):
    opp = create_opportunity(db_session, OpportunityCreate(slug=f"bare-{uuid.uuid4().hex[:8]}", title="Bare"))
    detail = (await _publish(client, curator, opp.id)).json()["detail"]
    assert "verified" not in detail.lower()
