"""Integration coverage for the DB-backed matching service.

Every test runs inside the transaction provided by ``db_session`` and is
rolled back afterwards, so the dedicated test database stays clean.

These tests exercise the whole service path with real PostgreSQL-backed
ORM objects:

``profile_id + opportunity_id -> load -> evaluate_requirements ->
persist_match_evaluation -> Match``

The pure evaluator semantics remain covered by
``test_matching_evaluators.py``; only loading, orchestration and
persistence through real rows are asserted here.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import event, func, select

from app.models import (
    Education,
    Match,
    MatchRequirement,
    Opportunity,
    Profile,
    Requirement,
    Skill,
)
from app.schemas import (
    EducationCreate,
    OpportunityCreate,
    ProfileCreate,
    RequirementCreate,
    SkillCreate,
)
from app.services.matching import ENGINE_VERSION
from app.services.matches import MatchPersistenceError, evaluate_and_persist_match
from tests.conftest import test_engine

#: Positions of the five mixed requirements inside ``seed``'s result.
BOOLEAN, GPA, CITIZENSHIP, DEGREE, SKILLS = range(5)

MIXED_REQUIREMENT_PAYLOADS = [
    {
        "label": "Currently enrolled",
        "kind": "boolean_flag",
        "params": {"metric": "is_currently_enrolled", "expected": True},
        "order_index": BOOLEAN,
    },
    {
        "label": "GPA at least 3.5",
        "kind": "numeric_threshold",
        "params": {"metric": "gpa", "operator": ">=", "value": 3.5, "scale": 4.0},
        "order_index": GPA,
    },
    {
        "label": "Ethiopian citizenship",
        "kind": "set_membership",
        "params": {"metric": "citizenship", "operator": "in", "allowed": ["Ethiopia"]},
        "order_index": CITIZENSHIP,
    },
    {
        "label": "Bachelor's degree",
        "kind": "equality",
        "params": {"metric": "degree_level", "operator": "==", "value": "bachelor"},
        "order_index": DEGREE,
    },
    {
        "label": "Programming skills",
        "kind": "skill_set",
        "params": {"metric": "skills", "operator": "contains_all", "required": ["python", "matlab"]},
        "order_index": SKILLS,
    },
]

UNPARSED_REQUIREMENT_PAYLOADS = [
    {
        "label": "Free-text eligibility note",
        "kind": "unparsed",
        "params": {"reason": "Extracted from a scanned flyer"},
        "order_index": 0,
    },
]

ANY_OF_REQUIREMENT_PAYLOADS = [
    {
        "label": "GPA or citizenship",
        "kind": "any_of",
        "params": {
            "any_of": [
                {"kind": "numeric_threshold", "params": {"metric": "gpa", "operator": ">=", "value": 3.5}},
                {"kind": "set_membership", "params": {"metric": "citizenship", "operator": "in", "allowed": ["Ethiopia"]}},
            ]
        },
        "order_index": 0,
    },
]

DATE_GATE_REQUIREMENT_PAYLOADS = [
    {
        "label": "Born on or before 2010",
        "kind": "date_gate",
        "params": {"metric": "date_of_birth", "operator": "<=", "value": "2010-01-01"},
        "order_index": 0,
    },
]


def make_profile(**overrides) -> Profile:
    payload = {
        "full_name": "Sara Bekele",
        "email": f"sara-{uuid.uuid4().hex[:10]}@example.org",
        "date_of_birth": "2002-05-14",
        "citizenships": ["Ethiopia"],
        "country_of_residence": "ET",
        "degree_level": "bachelor",
        "is_currently_enrolled": True,
        "languages": ["en"],
        "links": {"github": "https://github.com/sara"},
        "interests": ["aerospace"],
        "bio": "Aerospace engineering student.",
    }
    payload.update(overrides)
    return Profile(**ProfileCreate(**payload).model_dump())


def make_education(**overrides) -> Education:
    payload = {
        "institution_name": "Addis Ababa University",
        "degree_level": "bachelor",
        "field_of_study": "Aerospace Engineering",
        "country": "ET",
        "is_current": True,
        "gpa": 3.75,
        "gpa_scale": 4.0,
        "is_primary": True,
    }
    payload.update(overrides)
    return Education(**EducationCreate(**payload).model_dump())


def make_skill(key: str) -> Skill:
    return Skill(**SkillCreate(key=key, name=key.title()).model_dump())


def make_opportunity(**overrides) -> Opportunity:
    payload = {
        "slug": f"orbit-{uuid.uuid4().hex[:10]}",
        "title": "Orbital Mechanics Research Fellowship 2026",
        "opportunity_type": "research_program",
        "description": "A research fellowship for undergraduate engineers.",
        "host_name": "ESA",
        "status": "published",
    }
    payload.update(overrides)
    return Opportunity(**OpportunityCreate(**payload).model_dump())


def seed(
    db_session,
    requirements=None,
    *,
    profile: Profile | None = None,
    education: bool = True,
    skill_keys: tuple[str, ...] = ("python", "matlab"),
) -> tuple[Profile, Opportunity, list[Requirement]]:
    """Persist a realistic profile, an opportunity and its requirements."""
    profile = profile or make_profile()
    if education:
        profile.education.append(make_education())
    profile.skills.extend(make_skill(key) for key in skill_keys)
    opportunity = make_opportunity()
    db_session.add_all([profile, opportunity])
    db_session.flush()

    payloads = MIXED_REQUIREMENT_PAYLOADS if requirements is None else requirements
    seeded = []
    for payload in payloads:
        requirement = Requirement(**RequirementCreate(**payload).model_dump())
        requirement.opportunity = opportunity
        db_session.add(requirement)
        seeded.append(requirement)
    db_session.flush()
    return profile, opportunity, seeded


def rows_by_requirement(match: Match) -> dict[uuid.UUID, MatchRequirement]:
    return {row.requirement_id: row for row in match.requirement_results}


def count(db_session, model) -> int:
    return db_session.scalar(select(func.count()).select_from(model))


# --- Lookup ------------------------------------------------------------------------


def test_existing_profile_and_opportunity_produce_a_match(db_session):
    profile, opportunity, requirements = seed(db_session)

    match = evaluate_and_persist_match(db_session, profile.id, opportunity.id)

    assert match is not None
    assert isinstance(match, Match)
    assert isinstance(match.profile, Profile)
    assert isinstance(match.opportunity, Opportunity)
    assert match.profile_id == profile.id
    assert match.opportunity_id == opportunity.id
    assert match.status == "eligible"
    assert match.engine_version == ENGINE_VERSION
    assert match.facts == {
        "total": 5,
        "met": 5,
        "not_met": 0,
        "unknown": 0,
        "needs_review": 0,
    }


def test_opportunity_requirements_are_loaded_before_evaluation(db_session):
    profile, opportunity, requirements = seed(db_session)
    db_session.expire_all()

    match = evaluate_and_persist_match(db_session, profile.id, opportunity.id)

    persisted_ids = {row.requirement_id for row in match.requirement_results}
    assert persisted_ids == {requirement.id for requirement in opportunity.requirements}
    assert len(persisted_ids) == len(requirements) == 5
    assert all(isinstance(row.requirement, Requirement) for row in match.requirement_results)


def test_missing_profile_returns_none_without_persisting(db_session):
    _, opportunity, _ = seed(db_session)

    match = evaluate_and_persist_match(db_session, uuid.uuid4(), opportunity.id)

    assert match is None
    assert count(db_session, Match) == 0
    assert count(db_session, MatchRequirement) == 0


def test_missing_opportunity_returns_none_without_persisting(db_session):
    profile, _, _ = seed(db_session)

    match = evaluate_and_persist_match(db_session, profile.id, uuid.uuid4())

    assert match is None
    assert count(db_session, Match) == 0
    assert count(db_session, MatchRequirement) == 0


# --- Individual requirement persistence ---------------------------------------------


def test_boolean_requirement_persists_real_evidence(db_session):
    profile, opportunity, requirements = seed(db_session)

    match = evaluate_and_persist_match(db_session, profile.id, opportunity.id)

    row = rows_by_requirement(match)[requirements[BOOLEAN].id]
    assert isinstance(row, MatchRequirement)
    assert row.outcome == "met"
    assert row.reason_code == "boolean_flag_matches"
    assert row.expected == {"metric": "is_currently_enrolled", "value": True}
    assert row.actual == {"value": True}
    assert row.message == "Profile satisfies the requirement."


def test_gpa_requirement_persists_real_evidence(db_session):
    profile, opportunity, requirements = seed(db_session)

    match = evaluate_and_persist_match(db_session, profile.id, opportunity.id)

    row = rows_by_requirement(match)[requirements[GPA].id]
    assert row.outcome == "met"
    assert row.reason_code == "numeric_threshold_met"
    assert row.expected == {"metric": "gpa", "operator": ">=", "value": 3.5}
    assert row.actual == {"value": 3.75}
    assert row.message == "Profile satisfies the numeric threshold requirement."


def test_citizenship_requirement_persists_real_evidence(db_session):
    profile, opportunity, requirements = seed(db_session)

    match = evaluate_and_persist_match(db_session, profile.id, opportunity.id)

    row = rows_by_requirement(match)[requirements[CITIZENSHIP].id]
    assert row.outcome == "met"
    assert row.reason_code == "set_membership_matches"
    assert row.expected == {"metric": "citizenship", "value": "Ethiopia"}
    assert row.actual == {"values": ["Ethiopia"]}
    assert row.message == "Profile satisfies the set membership requirement."


def test_degree_requirement_persists_real_evidence(db_session):
    profile, opportunity, requirements = seed(db_session)

    match = evaluate_and_persist_match(db_session, profile.id, opportunity.id)

    row = rows_by_requirement(match)[requirements[DEGREE].id]
    assert row.outcome == "met"
    assert row.reason_code == "equality_matches"
    assert row.expected == {"metric": "degree_level", "operator": "==", "value": "bachelor"}
    assert row.actual == {"value": "bachelor"}
    assert row.message == "Profile satisfies the equality requirement."


def test_skill_requirement_evaluates_through_profile_skills(db_session):
    profile, opportunity, requirements = seed(db_session)
    db_session.expire_all()

    match = evaluate_and_persist_match(db_session, profile.id, opportunity.id)

    reloaded_profile = db_session.get(Profile, profile.id)
    assert [type(skill) for skill in reloaded_profile.skills] == [Skill, Skill]
    assert {skill.key for skill in reloaded_profile.skills} == {"python", "matlab"}

    row = rows_by_requirement(match)[requirements[SKILLS].id]
    assert row.outcome == "met"
    assert row.reason_code == "skill_set_matches"
    assert row.expected == {
        "metric": "skills",
        "operator": "contains_all",
        "required": ["python", "matlab"],
    }
    assert set(row.actual["values"]) == {"python", "matlab"}
    assert row.message == "Profile satisfies the skill set requirement."


def test_date_gate_requirement_persists_real_evidence(db_session):
    profile, opportunity, requirements = seed(
        db_session, requirements=DATE_GATE_REQUIREMENT_PAYLOADS
    )

    match = evaluate_and_persist_match(db_session, profile.id, opportunity.id)

    row = rows_by_requirement(match)[requirements[0].id]
    assert row.outcome == "met"
    assert row.reason_code == "date_gate_met"
    assert row.expected == {"metric": "date_of_birth", "operator": "<=", "value": "2010-01-01"}
    assert row.actual == {"value": "2002-05-14"}
    assert row.message == "Profile satisfies the date gate requirement."


# --- Verdicts -----------------------------------------------------------------------


def test_mixed_requirements_persist_one_row_each(db_session):
    profile, opportunity, requirements = seed(db_session)

    match = evaluate_and_persist_match(db_session, profile.id, opportunity.id)

    persisted = rows_by_requirement(match)
    assert set(persisted) == {requirement.id for requirement in requirements}
    assert len(persisted) == 5
    assert {row.outcome for row in persisted.values()} == {"met"}
    assert {row.reason_code for row in persisted.values()} == {
        "boolean_flag_matches",
        "numeric_threshold_met",
        "set_membership_matches",
        "equality_matches",
        "skill_set_matches",
    }


def test_not_eligible_verdict_after_profile_change(db_session):
    profile, opportunity, requirements = seed(db_session)
    first = evaluate_and_persist_match(db_session, profile.id, opportunity.id)
    assert first.status == "eligible"

    profile.citizenships = ["Kenya"]
    db_session.flush()
    second = evaluate_and_persist_match(db_session, profile.id, opportunity.id)

    assert second.id == first.id
    assert count(db_session, Match) == 1
    assert second.status == "not_eligible"
    assert second.facts == {
        "total": 5,
        "met": 4,
        "not_met": 1,
        "unknown": 0,
        "needs_review": 0,
    }
    row = rows_by_requirement(second)[requirements[CITIZENSHIP].id]
    assert row.outcome == "not_met"
    assert row.reason_code == "set_membership_does_not_match"
    assert row.actual == {"values": ["Kenya"]}


def test_potential_match_verdict_when_gpa_is_missing(db_session):
    profile, opportunity, requirements = seed(db_session, education=False)

    match = evaluate_and_persist_match(db_session, profile.id, opportunity.id)

    assert match.status == "potential_match"
    assert match.facts == {
        "total": 5,
        "met": 4,
        "not_met": 0,
        "unknown": 1,
        "needs_review": 0,
    }
    row = rows_by_requirement(match)[requirements[GPA].id]
    assert row.outcome == "unknown"
    assert row.reason_code == "profile_fact_unavailable"
    assert row.actual == {"value": None}


def test_needs_review_verdict_for_unsupported_requirement(db_session):
    profile, opportunity, requirements = seed(
        db_session, requirements=UNPARSED_REQUIREMENT_PAYLOADS
    )

    match = evaluate_and_persist_match(db_session, profile.id, opportunity.id)

    assert match.status == "needs_review"
    assert match.facts == {
        "total": 1,
        "met": 0,
        "not_met": 0,
        "unknown": 0,
        "needs_review": 1,
    }
    row = rows_by_requirement(match)[requirements[0].id]
    assert row.outcome == "needs_review"
    assert row.reason_code == "unsupported_requirement_kind"
    assert row.expected == {"kind": "unparsed"}
    assert row.actual == {}
    assert row.message == "Requirement kind 'unparsed' is not supported."


def test_all_rows_preserve_ids_evidence_and_messages(db_session):
    profile, opportunity, requirements = seed(db_session)

    match = evaluate_and_persist_match(db_session, profile.id, opportunity.id)
    persisted = rows_by_requirement(match)

    assert set(persisted) == {requirement.id for requirement in requirements}
    assert len(persisted) == 5

    expected_evidence = {
        requirements[BOOLEAN]: (
            "boolean_flag_matches",
            {"metric": "is_currently_enrolled", "value": True},
            {"value": True},
            "Profile satisfies the requirement.",
        ),
        requirements[GPA]: (
            "numeric_threshold_met",
            {"metric": "gpa", "operator": ">=", "value": 3.5},
            {"value": 3.75},
            "Profile satisfies the numeric threshold requirement.",
        ),
        requirements[CITIZENSHIP]: (
            "set_membership_matches",
            {"metric": "citizenship", "value": "Ethiopia"},
            {"values": ["Ethiopia"]},
            "Profile satisfies the set membership requirement.",
        ),
        requirements[DEGREE]: (
            "equality_matches",
            {"metric": "degree_level", "operator": "==", "value": "bachelor"},
            {"value": "bachelor"},
            "Profile satisfies the equality requirement.",
        ),
        requirements[SKILLS]: (
            "skill_set_matches",
            {"metric": "skills", "operator": "contains_all", "required": ["python", "matlab"]},
            {"values": ["python", "matlab"]},
            "Profile satisfies the skill set requirement.",
        ),
    }
    for requirement, (reason_code, expected, actual, message) in expected_evidence.items():
        row = persisted[requirement.id]
        assert row.reason_code == reason_code
        assert row.expected == expected
        if requirement is requirements[SKILLS]:
            assert set(row.actual["values"]) == set(actual["values"])
        else:
            assert row.actual == actual
        assert row.message == message


# --- any_of composite ----------------------------------------------------------------


def test_any_of_parent_persists_composite_evidence(db_session):
    profile, opportunity, requirements = seed(
        db_session, requirements=ANY_OF_REQUIREMENT_PAYLOADS
    )

    match = evaluate_and_persist_match(db_session, profile.id, opportunity.id)

    assert match.status == "eligible"
    assert match.facts == {
        "total": 1,
        "met": 1,
        "not_met": 0,
        "unknown": 0,
        "needs_review": 0,
    }
    parent_id = requirements[0].id
    persisted = rows_by_requirement(match)
    assert set(persisted) == {parent_id}

    row = persisted[parent_id]
    assert row.requirement_id == parent_id
    assert row.outcome == "met"
    assert row.reason_code == "any_of_met"
    assert row.expected["operator"] == "any_of"
    children = row.actual["children"]
    assert [child["kind"] for child in children] == ["numeric_threshold", "set_membership"]
    assert [child["outcome"] for child in children] == ["met", "met"]
    assert all("requirement_id" not in child for child in children)
    assert row.message == "Profile satisfies at least one alternative."


# --- Re-evaluation and determinism -----------------------------------------------------


def test_re_evaluation_updates_the_existing_match(db_session):
    profile, opportunity, requirements = seed(db_session)
    first = evaluate_and_persist_match(db_session, profile.id, opportunity.id)

    profile.is_currently_enrolled = False
    db_session.flush()
    second = evaluate_and_persist_match(db_session, profile.id, opportunity.id)

    assert second.id == first.id
    assert count(db_session, Match) == 1
    assert second.status == "not_eligible"
    row = rows_by_requirement(second)[requirements[BOOLEAN].id]
    assert row.outcome == "not_met"
    assert row.reason_code == "boolean_flag_does_not_match"
    assert row.actual == {"value": False}


def test_re_evaluation_replaces_old_requirement_rows(db_session):
    profile, opportunity, _ = seed(db_session)
    first = evaluate_and_persist_match(db_session, profile.id, opportunity.id)
    first_row_ids = {row.id for row in first.requirement_results}
    assert len(first_row_ids) == 5

    profile.citizenships = ["Kenya"]
    db_session.flush()
    second = evaluate_and_persist_match(db_session, profile.id, opportunity.id)

    second_row_ids = {row.id for row in second.requirement_results}
    assert len(second_row_ids) == 5
    assert first_row_ids.isdisjoint(second_row_ids)
    assert count(db_session, Match) == 1
    assert count(db_session, MatchRequirement) == 5


def test_repeated_evaluation_is_deterministic(db_session):
    profile, opportunity, _ = seed(db_session)

    first = evaluate_and_persist_match(db_session, profile.id, opportunity.id)
    first_status = first.status
    first_facts = dict(first.facts)
    first_evidence = {
        row.requirement_id: (row.outcome, row.reason_code, row.expected, row.actual, row.message)
        for row in first.requirement_results
    }

    db_session.expire_all()
    second = evaluate_and_persist_match(db_session, profile.id, opportunity.id)
    second_evidence = {
        row.requirement_id: (row.outcome, row.reason_code, row.expected, row.actual, row.message)
        for row in second.requirement_results
    }

    assert second.id == first.id
    assert second.status == first_status
    assert dict(second.facts) == first_facts
    assert second_evidence == first_evidence
    assert count(db_session, Match) == 1


# --- Transaction and failure behavior ----------------------------------------------------


def test_transaction_is_caller_owned(db_session):
    profile, opportunity, _ = seed(db_session)

    match = evaluate_and_persist_match(db_session, profile.id, opportunity.id)
    assert match is not None

    with test_engine.connect() as other_connection:
        committed = other_connection.scalar(
            select(func.count())
            .select_from(Match)
            .where(
                Match.profile_id == profile.id,
                Match.opportunity_id == opportunity.id,
            )
        )
    assert committed == 0


def test_failed_evidence_write_rolls_back_partial_match(db_session, monkeypatch):
    profile, opportunity, _ = seed(db_session)

    class _FailingEvidence:
        def __init__(self, *args, **kwargs):
            raise MatchPersistenceError("evidence write failed")

    # Fail after the Match INSERT has flushed inside the savepoint, so the
    # rollback has real partial work to undo.
    monkeypatch.setattr("app.services.matches.MatchRequirement", _FailingEvidence)

    with pytest.raises(MatchPersistenceError):
        evaluate_and_persist_match(db_session, profile.id, opportunity.id)

    assert count(db_session, Match) == 0
    assert count(db_session, MatchRequirement) == 0


# --- Query efficiency ---------------------------------------------------------------------


def test_evaluation_uses_a_fixed_number_of_queries(db_session):
    profile, opportunity, _ = seed(db_session)

    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    connection = db_session.connection()
    event.listen(connection, "before_cursor_execute", record)
    try:
        match = evaluate_and_persist_match(db_session, profile.id, opportunity.id)
    finally:
        event.remove(connection, "before_cursor_execute", record)

    assert match is not None

    def occurrences(fragment: str) -> int:
        return sum(fragment in statement for statement in statements)

    # One query per collection — never one query per skill or requirement.
    # The m2m selectin renders ``FROM profiles ... JOIN profile_skills JOIN
    # skills``; one-to-many collections render ``FROM <child> ... IN``.
    assert occurrences("FROM education") == 1
    assert occurrences("JOIN profile_skills") == 1
    assert occurrences("JOIN skills") == 1
    assert occurrences("FROM requirements") == 1
    # Loads + savepoint write + evidence + refresh stay a small constant.
    assert len(statements) <= 20
