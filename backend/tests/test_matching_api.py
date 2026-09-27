"""Integration tests for the Match HTTP API.

Every test runs inside the transaction provided by ``db_session`` and is
rolled back afterwards, so the dedicated test database stays clean.

The core integration tests exercise the real PostgreSQL-backed matching
service end to end — no part of the matching engine is mocked:

``POST /profiles/{id}/opportunities/{id}/match -> evaluate_and_persist_match``
``GET  /profiles/{id}/opportunities/{id}/match -> persisted Match only``
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from app.db.session import get_db
from app.main import app
from app.models import Match, MatchRequirement, Requirement, Source
from app.schemas import MatchRead, RequirementCreate
from app.services.matching import ENGINE_VERSION
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from tests.test_matches import (
    ANY_OF_REQUIREMENT_PAYLOADS,
    BOOLEAN,
    CITIZENSHIP,
    GPA,
    SKILLS,
    UNPARSED_REQUIREMENT_PAYLOADS,
    seed,
)


def match_path(profile_id: uuid.UUID, opportunity_id: uuid.UUID) -> str:
    """Return the path of both match endpoints for one profile x opportunity pair."""
    return f"/profiles/{profile_id}/opportunities/{opportunity_id}/match"


def rows_by_requirement(body: dict) -> dict[str, dict]:
    """Index a match response body by requirement id."""
    return {row["requirement_id"]: row for row in body["requirements"]}


def count(db_session: Session, model) -> int:
    return db_session.scalar(select(func.count()).select_from(model))


def seed_sourced_requirement(db_session: Session):
    """Seed a profile, an opportunity and one requirement carrying source metadata."""
    profile, opportunity, _ = seed(db_session, requirements=[])
    source = Source(
        opportunity=opportunity,
        source_type="official_page",
        url="https://example.org/call",
        is_primary=True,
    )
    db_session.add(source)
    db_session.flush()
    payload = {
        "label": "GPA at least 3.5",
        "kind": "numeric_threshold",
        "params": {"metric": "gpa", "operator": ">=", "value": 3.5, "scale": 4.0},
        "order_index": 0,
        "is_mandatory": False,
        "category": "academic",
        "source_id": source.id,
        "source_quote": "Applicants need a GPA of at least 3.5.",
    }
    requirement = Requirement(**RequirementCreate(**payload).model_dump())
    requirement.opportunity = opportunity
    db_session.add(requirement)
    db_session.flush()
    return profile, opportunity, requirement, source


EXPECTED_REQUIREMENT_SUMMARY = {
    "label": "GPA at least 3.5",
    "kind": "numeric_threshold",
    "category": "academic",
    "is_mandatory": False,
}


@pytest.fixture
async def client(db_session: Session):
    """Use the existing transaction-bound test session for API requests."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()


# --- POST: evaluate / re-evaluate ------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_returns_ok_with_match_read_schema(client: AsyncClient, db_session: Session):
    profile, opportunity, _ = seed(db_session)

    response = await client.post(match_path(profile.id, opportunity.id))

    assert response.status_code == 200
    body = response.json()
    validated = MatchRead.model_validate(body)
    assert validated.id == uuid.UUID(body["id"])
    assert uuid.UUID(body["profile_id"]) == profile.id
    assert uuid.UUID(body["opportunity_id"]) == opportunity.id


@pytest.mark.asyncio
async def test_evaluate_exposes_status_engine_version_evaluated_at_and_facts(
    client: AsyncClient, db_session: Session
):
    profile, opportunity, _ = seed(db_session)

    body = (await client.post(match_path(profile.id, opportunity.id))).json()

    assert body["status"] == "eligible"
    assert body["engine_version"] == ENGINE_VERSION
    evaluated_at = datetime.fromisoformat(body["evaluated_at"])
    assert evaluated_at.tzinfo is not None
    assert body["facts"] == {
        "total": 5,
        "met": 5,
        "not_met": 0,
        "unknown": 0,
        "needs_review": 0,
    }


@pytest.mark.asyncio
async def test_evaluate_returns_every_requirement_result_in_domain_order(
    client: AsyncClient, db_session: Session
):
    profile, opportunity, requirements = seed(db_session)

    body = (await client.post(match_path(profile.id, opportunity.id))).json()

    assert len(body["requirements"]) == 5
    assert [row["requirement_id"] for row in body["requirements"]] == [
        str(requirement.id) for requirement in requirements
    ]
    assert len({row["id"] for row in body["requirements"]}) == 5
    assert all(uuid.UUID(row["id"]) for row in body["requirements"])


@pytest.mark.asyncio
async def test_requirement_results_carry_nested_requirement_metadata(
    client: AsyncClient, db_session: Session
):
    profile, opportunity, requirement, source = seed_sourced_requirement(db_session)

    body = (await client.post(match_path(profile.id, opportunity.id))).json()

    row = body["requirements"][0]
    assert row["requirement_id"] == str(requirement.id)
    assert row["requirement"] == {
        **EXPECTED_REQUIREMENT_SUMMARY,
        "source_id": str(source.id),
        "source_quote": "Applicants need a GPA of at least 3.5.",
    }


@pytest.mark.asyncio
async def test_evaluate_preserves_expected_actual_reason_and_message(
    client: AsyncClient, db_session: Session
):
    profile, opportunity, requirements = seed(db_session)

    body = (await client.post(match_path(profile.id, opportunity.id))).json()
    rows = rows_by_requirement(body)

    gpa_row = rows[str(requirements[GPA].id)]
    assert gpa_row["outcome"] == "met"
    assert gpa_row["reason_code"] == "numeric_threshold_met"
    assert gpa_row["expected"] == {"metric": "gpa", "operator": ">=", "value": 3.5}
    assert gpa_row["actual"] == {"value": 3.75}
    assert gpa_row["message"] == "Profile satisfies the numeric threshold requirement."

    boolean_row = rows[str(requirements[BOOLEAN].id)]
    assert boolean_row["outcome"] == "met"
    assert boolean_row["reason_code"] == "boolean_flag_matches"
    assert boolean_row["expected"] == {"metric": "is_currently_enrolled", "value": True}
    assert boolean_row["actual"] == {"value": True}
    assert boolean_row["message"] == "Profile satisfies the requirement."


@pytest.mark.asyncio
async def test_repeated_evaluate_updates_the_same_match(client: AsyncClient, db_session: Session):
    profile, opportunity, requirements = seed(db_session)
    path = match_path(profile.id, opportunity.id)

    first = (await client.post(path)).json()
    profile.citizenships = ["Kenya"]
    db_session.flush()
    second = (await client.post(path)).json()

    assert second["id"] == first["id"]
    assert second["status"] == "not_eligible"
    assert second["facts"] == {
        "total": 5,
        "met": 4,
        "not_met": 1,
        "unknown": 0,
        "needs_review": 0,
    }
    assert count(db_session, Match) == 1
    assert count(db_session, MatchRequirement) == 5
    row = rows_by_requirement(second)[str(requirements[CITIZENSHIP].id)]
    assert row["outcome"] == "not_met"
    assert row["reason_code"] == "set_membership_does_not_match"
    assert row["actual"] == {"values": ["Kenya"]}


@pytest.mark.asyncio
async def test_evaluate_missing_profile_returns_not_found(client: AsyncClient, db_session: Session):
    _, opportunity, _ = seed(db_session)

    response = await client.post(match_path(uuid.uuid4(), opportunity.id))

    assert response.status_code == 404
    assert response.json()["detail"] == "Profile not found."
    assert count(db_session, Match) == 0


@pytest.mark.asyncio
async def test_evaluate_missing_opportunity_returns_not_found(
    client: AsyncClient, db_session: Session
):
    profile, _, _ = seed(db_session)

    response = await client.post(match_path(profile.id, uuid.uuid4()))

    assert response.status_code == 404
    assert response.json()["detail"] == "Opportunity not found."
    assert count(db_session, Match) == 0


@pytest.mark.asyncio
async def test_evaluate_ignores_client_supplied_match_fields(
    client: AsyncClient, db_session: Session
):
    profile, opportunity, _ = seed(db_session)
    profile.citizenships = ["Kenya"]
    db_session.flush()

    response = await client.post(
        match_path(profile.id, opportunity.id),
        json={
            "status": "eligible",
            "engine_version": "999",
            "facts": {"total": 99, "met": 99, "not_met": 0, "unknown": 0, "needs_review": 0},
            "requirements": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_eligible"
    assert body["engine_version"] == ENGINE_VERSION
    assert body["facts"]["total"] == 5
    assert len(body["requirements"]) == 5


# --- GET: retrieve an existing match ---------------------------------------------------


@pytest.mark.asyncio
async def test_get_returns_the_persisted_match_with_its_requirement_results(
    client: AsyncClient, db_session: Session
):
    profile, opportunity, requirements = seed(db_session)
    path = match_path(profile.id, opportunity.id)
    posted = (await client.post(path)).json()

    response = await client.get(path)

    assert response.status_code == 200
    body = response.json()
    assert MatchRead.model_validate(body)
    assert body["id"] == posted["id"]
    assert body["status"] == posted["status"]
    assert body["engine_version"] == posted["engine_version"]
    assert body["evaluated_at"] == posted["evaluated_at"]
    assert body["facts"] == posted["facts"]
    assert body["requirements"] == posted["requirements"]
    assert [row["requirement_id"] for row in body["requirements"]] == [
        str(requirement.id) for requirement in requirements
    ]


@pytest.mark.asyncio
async def test_get_returns_nested_requirement_metadata(client: AsyncClient, db_session: Session):
    profile, opportunity, requirement, source = seed_sourced_requirement(db_session)
    path = match_path(profile.id, opportunity.id)
    assert (await client.post(path)).status_code == 200

    response = await client.get(path)

    assert response.status_code == 200
    row = response.json()["requirements"][0]
    assert row["requirement_id"] == str(requirement.id)
    assert row["requirement"] == {
        **EXPECTED_REQUIREMENT_SUMMARY,
        "source_id": str(source.id),
        "source_quote": "Applicants need a GPA of at least 3.5.",
    }


@pytest.mark.asyncio
async def test_get_without_match_returns_not_found(client: AsyncClient, db_session: Session):
    profile, opportunity, _ = seed(db_session)

    response = await client.get(match_path(profile.id, opportunity.id))

    assert response.status_code == 404
    assert response.json()["detail"] == "Match not found."


@pytest.mark.asyncio
async def test_get_does_not_trigger_evaluation_or_create_a_match(
    client: AsyncClient, db_session: Session
):
    profile, opportunity, _ = seed(db_session)
    path = match_path(profile.id, opportunity.id)

    first = await client.get(path)
    second = await client.get(path)

    assert first.status_code == 404
    assert second.status_code == 404
    assert count(db_session, Match) == 0
    assert count(db_session, MatchRequirement) == 0


@pytest.mark.asyncio
async def test_get_loads_evidence_with_a_fixed_number_of_queries(
    client: AsyncClient, db_session: Session
):
    profile, opportunity, _ = seed(db_session)
    path = match_path(profile.id, opportunity.id)
    assert (await client.post(path)).status_code == 200
    db_session.expire_all()

    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    connection = db_session.connection()
    event.listen(connection, "before_cursor_execute", record)
    try:
        response = await client.get(path)
    finally:
        event.remove(connection, "before_cursor_execute", record)

    assert response.status_code == 200

    def occurrences(fragment: str) -> int:
        return sum(fragment in statement for statement in statements)

    # One query for the evidence collection and at most one for ALL requirement
    # metadata — never one requirement query per row, and GET never writes.
    assert occurrences("FROM match_requirements") == 1
    assert occurrences("FROM requirements") <= 1
    assert occurrences("INSERT") == 0
    assert occurrences("UPDATE") == 0
    assert len(statements) <= 6


# --- Real matching behaviour exposed through the API ----------------------------------


@pytest.mark.asyncio
async def test_eligible_result_is_exposed(client: AsyncClient, db_session: Session):
    profile, opportunity, _ = seed(db_session)

    body = (await client.post(match_path(profile.id, opportunity.id))).json()

    assert body["status"] == "eligible"
    assert body["facts"] == {
        "total": 5,
        "met": 5,
        "not_met": 0,
        "unknown": 0,
        "needs_review": 0,
    }
    assert {row["outcome"] for row in body["requirements"]} == {"met"}


@pytest.mark.asyncio
async def test_not_eligible_result_is_exposed(client: AsyncClient, db_session: Session):
    profile, opportunity, _ = seed(db_session)
    profile.citizenships = ["Kenya"]
    db_session.flush()

    body = (await client.post(match_path(profile.id, opportunity.id))).json()

    assert body["status"] == "not_eligible"
    assert body["facts"] == {
        "total": 5,
        "met": 4,
        "not_met": 1,
        "unknown": 0,
        "needs_review": 0,
    }


@pytest.mark.asyncio
async def test_potential_match_result_is_exposed(client: AsyncClient, db_session: Session):
    profile, opportunity, requirements = seed(db_session, education=False)

    body = (await client.post(match_path(profile.id, opportunity.id))).json()

    assert body["status"] == "potential_match"
    assert body["facts"] == {
        "total": 5,
        "met": 4,
        "not_met": 0,
        "unknown": 1,
        "needs_review": 0,
    }
    row = rows_by_requirement(body)[str(requirements[GPA].id)]
    assert row["outcome"] == "unknown"
    assert row["reason_code"] == "profile_fact_unavailable"
    assert row["actual"] == {"value": None}


@pytest.mark.asyncio
async def test_needs_review_result_is_exposed(client: AsyncClient, db_session: Session):
    profile, opportunity, requirements = seed(
        db_session, requirements=UNPARSED_REQUIREMENT_PAYLOADS
    )

    body = (await client.post(match_path(profile.id, opportunity.id))).json()

    assert body["status"] == "needs_review"
    assert body["facts"] == {
        "total": 1,
        "met": 0,
        "not_met": 0,
        "unknown": 0,
        "needs_review": 1,
    }
    row = rows_by_requirement(body)[str(requirements[0].id)]
    assert row["outcome"] == "needs_review"
    assert row["reason_code"] == "unsupported_requirement_kind"
    assert row["expected"] == {"kind": "unparsed"}
    assert row["actual"] == {}
    assert row["message"] == "Requirement kind 'unparsed' is not supported."


@pytest.mark.asyncio
async def test_any_of_evidence_is_exposed(client: AsyncClient, db_session: Session):
    profile, opportunity, requirements = seed(
        db_session, requirements=ANY_OF_REQUIREMENT_PAYLOADS
    )

    body = (await client.post(match_path(profile.id, opportunity.id))).json()

    assert body["status"] == "eligible"
    row = rows_by_requirement(body)[str(requirements[0].id)]
    assert row["outcome"] == "met"
    assert row["reason_code"] == "any_of_met"
    assert row["expected"]["operator"] == "any_of"
    children = row["actual"]["children"]
    assert [child["kind"] for child in children] == ["numeric_threshold", "set_membership"]
    assert [child["outcome"] for child in children] == ["met", "met"]
    assert all("requirement_id" not in child for child in children)
    assert row["message"] == "Profile satisfies at least one alternative."


@pytest.mark.asyncio
async def test_skill_set_evidence_is_exposed(client: AsyncClient, db_session: Session):
    profile, opportunity, requirements = seed(db_session)

    body = (await client.post(match_path(profile.id, opportunity.id))).json()

    row = rows_by_requirement(body)[str(requirements[SKILLS].id)]
    assert row["outcome"] == "met"
    assert row["reason_code"] == "skill_set_matches"
    assert row["expected"] == {
        "metric": "skills",
        "operator": "contains_all",
        "required": ["python", "matlab"],
    }
    assert set(row["actual"]["values"]) == {"python", "matlab"}
    assert row["message"] == "Profile satisfies the skill set requirement."
