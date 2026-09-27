"""Integration tests for the authenticated, user-scoped Match API.

Every test runs inside the transaction provided by ``db_session`` and is
rolled back afterwards, so the dedicated test database stays clean.

Ownership is exercised with real JWT bearer authentication (test-only
secret) and real PostgreSQL rows — no part of authentication, the
matching engine or ownership is mocked:

``POST /me/opportunities/{id}/match -> evaluate_and_persist_match_for_user``
``GET  /me/opportunities/{id}/match -> persisted Match scoped to the caller``
``GET  /me/matches                  -> the caller's Matches only``
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models import Match, MatchRequirement, Opportunity, Profile, Requirement, Source
from app.schemas import MatchRead, RequirementCreate
from app.services.matching import ENGINE_VERSION
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select, update
from sqlalchemy.orm import Session

from tests.test_auth import TEST_JWT_SECRET, auth_headers, make_user
from tests.test_matches import (
    ANY_OF_REQUIREMENT_PAYLOADS,
    BOOLEAN,
    CITIZENSHIP,
    GPA,
    MIXED_REQUIREMENT_PAYLOADS,
    SKILLS,
    UNPARSED_REQUIREMENT_PAYLOADS,
    make_opportunity,
    make_profile,
    seed,
)

MATCHES_PATH = "/me/matches"


def match_path(opportunity_id: uuid.UUID) -> str:
    """Return the path of both single-match endpoints for one opportunity."""
    return f"/me/opportunities/{opportunity_id}/match"


def rows_by_requirement(body: dict) -> dict[str, dict]:
    """Index a match response body by requirement id."""
    return {row["requirement_id"]: row for row in body["requirements"]}


def count(db_session: Session, model) -> int:
    return db_session.scalar(select(func.count()).select_from(model))


def seed_owner(db_session: Session):
    """Create and persist an authenticated user with no profile yet."""
    user = make_user()
    db_session.add(user)
    db_session.flush()
    return user


def seed_owned(
    db_session: Session, user, **kwargs
) -> tuple[Profile, Opportunity, list[Requirement]]:
    """Seed an evaluator-ready profile owned by ``user`` plus an opportunity."""
    profile = make_profile()
    profile.user_id = user.id
    return seed(db_session, profile=profile, **kwargs)


def seed_extra_opportunity(
    db_session: Session, requirements: list | None = None
) -> Opportunity:
    """Seed one more shared opportunity, optionally with its requirements."""
    opportunity = make_opportunity()
    db_session.add(opportunity)
    db_session.flush()
    if requirements:
        for payload in requirements:
            requirement = Requirement(**RequirementCreate(**payload).model_dump())
            requirement.opportunity = opportunity
            db_session.add(requirement)
        db_session.flush()
    return opportunity


def seed_sourced_requirement(db_session: Session, user):
    """Seed a profile, an opportunity and one requirement carrying source metadata."""
    profile, opportunity, _ = seed_owned(db_session, user, requirements=[])
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


# --- POST /me/opportunities/{id}/match: evaluate -----------------------------------------


async def test_post_evaluate_returns_match_read_for_authenticated_user(
    client: AsyncClient, db_session: Session
):
    user = seed_owner(db_session)
    profile, opportunity, _ = seed_owned(db_session, user)

    response = await client.post(match_path(opportunity.id), headers=auth_headers(user))

    assert response.status_code == 200
    body = response.json()
    MatchRead.model_validate(body)
    assert uuid.UUID(body["profile_id"]) == profile.id
    assert uuid.UUID(body["opportunity_id"]) == opportunity.id


async def test_post_creates_the_correct_match_row(
    client: AsyncClient, db_session: Session
):
    user = seed_owner(db_session)
    profile, opportunity, _ = seed_owned(db_session, user)

    body = (await client.post(match_path(opportunity.id), headers=auth_headers(user))).json()

    rows = db_session.scalars(select(Match)).all()
    assert len(rows) == 1
    assert rows[0].id == uuid.UUID(body["id"])
    assert rows[0].profile_id == profile.id
    assert rows[0].opportunity_id == opportunity.id


async def test_post_match_belongs_to_the_authenticated_users_profile(
    client: AsyncClient, db_session: Session
):
    user = seed_owner(db_session)
    other = seed_owner(db_session)
    profile, opportunity, _ = seed_owned(db_session, user)
    other_profile, _, _ = seed_owned(db_session, other, skill_keys=())

    body = (await client.post(match_path(opportunity.id), headers=auth_headers(user))).json()

    assert uuid.UUID(body["profile_id"]) == profile.id
    match = db_session.get(Match, uuid.UUID(body["id"]))
    assert match.profile_id == profile.id
    assert match.profile_id != other_profile.id
    assert count(db_session, Match) == 1


async def test_post_without_profile_returns_404(
    client: AsyncClient, db_session: Session
):
    user = seed_owner(db_session)
    _, opportunity, _ = seed(db_session)

    response = await client.post(match_path(opportunity.id), headers=auth_headers(user))

    assert response.status_code == 404
    assert response.json()["detail"] == "Profile not found."
    assert count(db_session, Match) == 0


async def test_post_with_unknown_opportunity_returns_404(
    client: AsyncClient, db_session: Session
):
    user = seed_owner(db_session)
    seed_owned(db_session, user)

    response = await client.post(match_path(uuid.uuid4()), headers=auth_headers(user))

    assert response.status_code == 404
    assert response.json()["detail"] == "Opportunity not found."
    assert count(db_session, Match) == 0


async def test_post_requires_authentication(client: AsyncClient):
    path = match_path(uuid.uuid4())

    assert (await client.post(path)).status_code == 401
    assert (
        await client.post(path, headers={"Authorization": "Bearer not-a-token"})
    ).status_code == 401


async def test_repeated_post_keeps_a_single_match(
    client: AsyncClient, db_session: Session
):
    user = seed_owner(db_session)
    _, opportunity, _ = seed_owned(db_session, user)
    path = match_path(opportunity.id)

    first = (await client.post(path, headers=auth_headers(user))).json()
    second = (await client.post(path, headers=auth_headers(user))).json()

    assert second["id"] == first["id"]
    assert count(db_session, Match) == 1


async def test_repeated_post_replaces_evidence(
    client: AsyncClient, db_session: Session
):
    user = seed_owner(db_session)
    profile, opportunity, requirements = seed_owned(db_session, user)
    path = match_path(opportunity.id)

    first = (await client.post(path, headers=auth_headers(user))).json()
    assert first["status"] == "eligible"
    profile.citizenships = ["Kenya"]
    db_session.flush()
    second = (await client.post(path, headers=auth_headers(user))).json()

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


async def test_post_ignores_client_supplied_profile_id(
    client: AsyncClient, db_session: Session
):
    user = seed_owner(db_session)
    profile, opportunity, _ = seed_owned(db_session, user)
    other = seed_owner(db_session)
    other_profile, _, _ = seed_owned(db_session, other, skill_keys=())

    response = await client.post(
        match_path(opportunity.id),
        json={"profile_id": str(other_profile.id)},
        headers=auth_headers(user),
    )

    assert response.status_code == 200
    assert uuid.UUID(response.json()["profile_id"]) == profile.id
    assert db_session.get(Match, uuid.UUID(response.json()["id"])).profile_id == profile.id
    assert db_session.scalar(
        select(func.count())
        .select_from(Match)
        .where(Match.profile_id == other_profile.id)
    ) == 0


async def test_post_ignores_client_supplied_match_fields(
    client: AsyncClient, db_session: Session
):
    user = seed_owner(db_session)
    profile, opportunity, _ = seed_owned(db_session, user)
    profile.citizenships = ["Kenya"]
    db_session.flush()

    response = await client.post(
        match_path(opportunity.id),
        json={
            "status": "eligible",
            "engine_version": "999",
            "facts": {"total": 99, "met": 99, "not_met": 0, "unknown": 0, "needs_review": 0},
            "requirements": [],
            "outcomes": ["met"],
        },
        headers=auth_headers(user),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_eligible"
    assert body["engine_version"] == ENGINE_VERSION
    assert body["facts"]["total"] == 5
    assert len(body["requirements"]) == 5


async def test_post_preserves_the_real_matching_result(
    client: AsyncClient, db_session: Session
):
    user = seed_owner(db_session)
    _, opportunity, _ = seed_owned(db_session, user)

    body = (await client.post(match_path(opportunity.id), headers=auth_headers(user))).json()

    assert body["status"] == "eligible"
    assert body["facts"] == {
        "total": 5,
        "met": 5,
        "not_met": 0,
        "unknown": 0,
        "needs_review": 0,
    }
    assert {row["outcome"] for row in body["requirements"]} == {"met"}


async def test_post_preserves_match_requirement_evidence(
    client: AsyncClient, db_session: Session
):
    user = seed_owner(db_session)
    _, opportunity, requirements = seed_owned(db_session, user)

    body = (await client.post(match_path(opportunity.id), headers=auth_headers(user))).json()
    rows = rows_by_requirement(body)

    assert len(body["requirements"]) == 5
    assert len({row["id"] for row in body["requirements"]}) == 5

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

    skills_row = rows[str(requirements[SKILLS].id)]
    assert skills_row["outcome"] == "met"
    assert skills_row["reason_code"] == "skill_set_matches"
    assert set(skills_row["actual"]["values"]) == {"python", "matlab"}


# --- GET /me/opportunities/{id}/match: read one Match ------------------------------------


async def test_get_single_returns_the_owners_match(
    client: AsyncClient, db_session: Session
):
    user = seed_owner(db_session)
    _, opportunity, requirements = seed_owned(db_session, user)
    path = match_path(opportunity.id)
    posted = (await client.post(path, headers=auth_headers(user))).json()

    response = await client.get(path, headers=auth_headers(user))

    assert response.status_code == 200
    body = response.json()
    MatchRead.model_validate(body)
    assert body == posted
    assert [row["requirement_id"] for row in body["requirements"]] == [
        str(requirement.id) for requirement in requirements
    ]


async def test_get_single_does_not_evaluate(
    client: AsyncClient, db_session: Session
):
    user = seed_owner(db_session)
    _, opportunity, _ = seed_owned(db_session, user)

    response = await client.get(match_path(opportunity.id), headers=auth_headers(user))

    assert response.status_code == 404
    assert count(db_session, Match) == 0
    assert count(db_session, MatchRequirement) == 0


async def test_get_single_does_not_create_a_missing_match(
    client: AsyncClient, db_session: Session
):
    user = seed_owner(db_session)
    _, opportunity, _ = seed_owned(db_session, user)
    path = match_path(opportunity.id)

    first = await client.get(path, headers=auth_headers(user))
    second = await client.get(path, headers=auth_headers(user))

    assert first.status_code == 404
    assert second.status_code == 404
    assert count(db_session, Match) == 0
    assert count(db_session, MatchRequirement) == 0


async def test_get_single_does_not_update_the_match(
    client: AsyncClient, db_session: Session
):
    user = seed_owner(db_session)
    _, opportunity, _ = seed_owned(db_session, user)
    path = match_path(opportunity.id)
    posted = (await client.post(path, headers=auth_headers(user))).json()
    match = db_session.get(Match, uuid.UUID(posted["id"]))
    before = (match.evaluated_at, match.updated_at, match.status, dict(match.facts))
    evidence_before = sorted(row.id for row in match.requirement_results)

    db_session.expire_all()
    response = await client.get(path, headers=auth_headers(user))

    assert response.status_code == 200
    match = db_session.get(Match, uuid.UUID(posted["id"]))
    after = (match.evaluated_at, match.updated_at, match.status, dict(match.facts))
    assert after == before
    assert sorted(row.id for row in match.requirement_results) == evidence_before
    assert count(db_session, MatchRequirement) == 5


async def test_get_single_without_match_returns_404(
    client: AsyncClient, db_session: Session
):
    user = seed_owner(db_session)
    _, opportunity, _ = seed_owned(db_session, user)

    response = await client.get(match_path(opportunity.id), headers=auth_headers(user))

    assert response.status_code == 404
    assert response.json()["detail"] == "Match not found."


async def test_get_single_without_profile_returns_404(
    client: AsyncClient, db_session: Session
):
    user = seed_owner(db_session)
    _, opportunity, _ = seed(db_session)

    response = await client.get(match_path(opportunity.id), headers=auth_headers(user))

    assert response.status_code == 404
    assert response.json()["detail"] == "Profile not found."


async def test_get_single_requires_authentication(client: AsyncClient):
    path = match_path(uuid.uuid4())

    assert (await client.get(path)).status_code == 401
    assert (
        await client.get(path, headers={"Authorization": "Bearer not-a-token"})
    ).status_code == 401


async def test_user_cannot_read_another_users_match(
    client: AsyncClient, db_session: Session
):
    victim = seed_owner(db_session)
    _, opportunity, _ = seed_owned(db_session, victim)
    attacker = seed_owner(db_session)
    seed_owned(db_session, attacker, skill_keys=())
    assert (
        await client.post(match_path(opportunity.id), headers=auth_headers(victim))
    ).status_code == 200

    stolen = await client.get(match_path(opportunity.id), headers=auth_headers(attacker))

    assert stolen.status_code == 404
    assert stolen.json()["detail"] == "Match not found."
    assert count(db_session, Match) == 1
    own = await client.get(match_path(opportunity.id), headers=auth_headers(victim))
    assert own.status_code == 200


async def test_get_single_returns_requirement_evidence(
    client: AsyncClient, db_session: Session
):
    user = seed_owner(db_session)
    _, opportunity, _ = seed_owned(db_session, user)
    path = match_path(opportunity.id)
    assert (await client.post(path, headers=auth_headers(user))).status_code == 200

    body = (await client.get(path, headers=auth_headers(user))).json()

    assert len(body["requirements"]) == 5
    for row in body["requirements"]:
        assert row["outcome"] in {"met", "not_met", "unknown", "needs_review"}
        assert row["reason_code"]
        assert isinstance(row["expected"], dict)
        assert isinstance(row["actual"], dict)
        assert row["message"]
        assert row["requirement"]["label"]


async def test_get_single_returns_nested_requirement_metadata(
    client: AsyncClient, db_session: Session
):
    user = seed_owner(db_session)
    _, opportunity, requirement, source = seed_sourced_requirement(db_session, user)
    path = match_path(opportunity.id)
    assert (await client.post(path, headers=auth_headers(user))).status_code == 200

    response = await client.get(path, headers=auth_headers(user))

    assert response.status_code == 200
    row = response.json()["requirements"][0]
    assert row["requirement_id"] == str(requirement.id)
    assert row["requirement"] == {
        **EXPECTED_REQUIREMENT_SUMMARY,
        "source_id": str(source.id),
        "source_quote": "Applicants need a GPA of at least 3.5.",
    }


# --- GET /me/matches: the owner's collection ---------------------------------------------


async def test_list_returns_only_the_current_users_matches(
    client: AsyncClient, db_session: Session
):
    first_user = seed_owner(db_session)
    _, first_opportunity, _ = seed_owned(db_session, first_user)
    second_opportunity = seed_extra_opportunity(db_session)
    second = (await client.post(match_path(first_opportunity.id), headers=auth_headers(first_user))).json()
    third = (await client.post(match_path(second_opportunity.id), headers=auth_headers(first_user))).json()

    response = await client.get(MATCHES_PATH, headers=auth_headers(first_user))

    assert response.status_code == 200
    body = response.json()
    assert {row["id"] for row in body} == {second["id"], third["id"]}
    assert len(body) == 2


async def test_list_excludes_other_users_matches_on_a_shared_opportunity(
    client: AsyncClient, db_session: Session
):
    first_user = seed_owner(db_session)
    first_profile, opportunity, _ = seed_owned(db_session, first_user)
    second_user = seed_owner(db_session)
    second_profile = make_profile()
    second_profile.user_id = second_user.id
    db_session.add(second_profile)
    db_session.flush()

    first_match = (await client.post(match_path(opportunity.id), headers=auth_headers(first_user))).json()
    second_match = (await client.post(match_path(opportunity.id), headers=auth_headers(second_user))).json()
    assert first_match["id"] != second_match["id"]
    assert count(db_session, Match) == 2

    first_list = (await client.get(MATCHES_PATH, headers=auth_headers(first_user))).json()
    second_list = (await client.get(MATCHES_PATH, headers=auth_headers(second_user))).json()

    assert [row["id"] for row in first_list] == [first_match["id"]]
    assert [row["id"] for row in second_list] == [second_match["id"]]
    assert first_profile.id == uuid.UUID(first_match["profile_id"])
    assert second_profile.id == uuid.UUID(second_match["profile_id"])


async def test_list_ordering_is_deterministic_and_newest_first(
    client: AsyncClient, db_session: Session
):
    user = seed_owner(db_session)
    _, first_opportunity, _ = seed_owned(db_session, user)
    posted = [
        (
            await client.post(
                match_path(opportunity.id), headers=auth_headers(user)
            )
        ).json()
        for opportunity in (
            first_opportunity,
            seed_extra_opportunity(db_session),
            seed_extra_opportunity(db_session),
        )
    ]
    aged_id = uuid.UUID(posted[0]["id"])
    db_session.execute(
        update(Match)
        .where(Match.id == aged_id)
        .values(evaluated_at=datetime.now(timezone.utc) - timedelta(days=1))
    )
    db_session.flush()

    first = (await client.get(MATCHES_PATH, headers=auth_headers(user))).json()
    second = (await client.get(MATCHES_PATH, headers=auth_headers(user))).json()

    assert [row["id"] for row in second] == [row["id"] for row in first]
    assert first[-1]["id"] == str(aged_id)
    keys = [
        (datetime.fromisoformat(row["evaluated_at"]), uuid.UUID(row["id"]))
        for row in first
    ]
    assert keys == sorted(keys, reverse=True)


async def test_list_pagination_is_bounded(
    client: AsyncClient, db_session: Session
):
    user = seed_owner(db_session)
    _, first_opportunity, _ = seed_owned(db_session, user)
    for opportunity in (first_opportunity, seed_extra_opportunity(db_session), seed_extra_opportunity(db_session)):
        assert (
            await client.post(match_path(opportunity.id), headers=auth_headers(user))
        ).status_code == 200

    first_page = await client.get(f"{MATCHES_PATH}?limit=2", headers=auth_headers(user))
    second_page = await client.get(
        f"{MATCHES_PATH}?limit=2&offset=2", headers=auth_headers(user)
    )

    assert first_page.status_code == 200
    assert len(first_page.json()) == 2
    assert second_page.status_code == 200
    assert len(second_page.json()) == 1
    assert len(
        {row["id"] for row in first_page.json()} | {row["id"] for row in second_page.json()}
    ) == 3
    assert (await client.get(f"{MATCHES_PATH}?limit=101", headers=auth_headers(user))).status_code == 422
    assert (await client.get(f"{MATCHES_PATH}?limit=0", headers=auth_headers(user))).status_code == 422
    assert (await client.get(f"{MATCHES_PATH}?offset=-1", headers=auth_headers(user))).status_code == 422


async def test_list_without_profile_returns_404(
    client: AsyncClient, db_session: Session
):
    user = seed_owner(db_session)

    response = await client.get(MATCHES_PATH, headers=auth_headers(user))

    assert response.status_code == 404
    assert response.json()["detail"] == "Profile not found."


async def test_list_requires_authentication(client: AsyncClient):
    assert (await client.get(MATCHES_PATH)).status_code == 401
    assert (
        await client.get(MATCHES_PATH, headers={"Authorization": "Bearer not-a-token"})
    ).status_code == 401


async def test_list_loads_evidence_without_n_plus_one(
    client: AsyncClient, db_session: Session
):
    user = seed_owner(db_session)
    _, first_opportunity, _ = seed_owned(db_session, user)
    second_opportunity = seed_extra_opportunity(db_session, MIXED_REQUIREMENT_PAYLOADS)
    for opportunity in (first_opportunity, second_opportunity):
        assert (
            await client.post(match_path(opportunity.id), headers=auth_headers(user))
        ).status_code == 200
    db_session.expire_all()

    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    connection = db_session.connection()
    event.listen(connection, "before_cursor_execute", record)
    try:
        response = await client.get(MATCHES_PATH, headers=auth_headers(user))
    finally:
        event.remove(connection, "before_cursor_execute", record)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert all(len(match["requirements"]) == 5 for match in body)

    def occurrences(fragment: str) -> int:
        return sum(fragment in statement for statement in statements)

    # One query for ALL evidence rows and at most one for ALL requirement
    # metadata — never one query per MatchRequirement — and no writes.
    assert occurrences("FROM match_requirements") == 1
    assert occurrences("FROM requirements") <= 1
    assert occurrences("INSERT") == 0
    assert occurrences("UPDATE") == 0
    assert len(statements) <= 10


async def test_list_is_an_empty_collection_without_matches(
    client: AsyncClient, db_session: Session
):
    user = seed_owner(db_session)
    seed_owned(db_session, user)

    response = await client.get(MATCHES_PATH, headers=auth_headers(user))

    assert response.status_code == 200
    assert response.json() == []


# --- OpenAPI / security contract ----------------------------------------------------------


async def test_openapi_documents_the_supported_me_matching_routes():
    paths = app.openapi()["paths"]

    single = paths.get("/me/opportunities/{opportunity_id}/match", {})
    assert set(single) == {"post", "get"}
    assert "get" in paths.get("/me/matches", {})


async def test_openapi_declares_bearer_security_on_all_three_routes():
    paths = app.openapi()["paths"]

    for path in ("/me/opportunities/{opportunity_id}/match", "/me/matches"):
        for operation in paths[path].values():
            assert {"HTTPBearer": []} in operation.get("security", [])


async def test_openapi_does_not_expose_the_old_arbitrary_profile_routes():
    paths = app.openapi()["paths"]

    assert "/profiles/{profile_id}/opportunities/{opportunity_id}/match" not in paths
    assert not any(
        "profile_id" in path and "match" in path for path in paths
    ), paths


async def test_post_request_contract_has_no_client_controlled_profile_id():
    operation = app.openapi()["paths"]["/me/opportunities/{opportunity_id}/match"]["post"]

    assert "requestBody" not in operation
    parameter_names = {parameter["name"] for parameter in operation.get("parameters", [])}
    assert parameter_names == {"opportunity_id"}
    assert "profile_id" not in json.dumps(operation)


# --- Evaluator outcomes exposed through the authenticated API ----------------------------


async def test_potential_match_unknown_outcome_is_exposed(
    client: AsyncClient, db_session: Session
):
    user = seed_owner(db_session)
    _, opportunity, requirements = seed_owned(db_session, user, education=False)

    body = (await client.post(match_path(opportunity.id), headers=auth_headers(user))).json()

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


async def test_needs_review_outcome_is_exposed(
    client: AsyncClient, db_session: Session
):
    user = seed_owner(db_session)
    _, opportunity, requirements = seed_owned(
        db_session, user, requirements=UNPARSED_REQUIREMENT_PAYLOADS
    )

    body = (await client.post(match_path(opportunity.id), headers=auth_headers(user))).json()

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


async def test_any_of_nested_evidence_is_exposed(
    client: AsyncClient, db_session: Session
):
    user = seed_owner(db_session)
    _, opportunity, requirements = seed_owned(
        db_session, user, requirements=ANY_OF_REQUIREMENT_PAYLOADS
    )

    body = (await client.post(match_path(opportunity.id), headers=auth_headers(user))).json()

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
