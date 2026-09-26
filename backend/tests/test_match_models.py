"""Persistence tests for Match and MatchRequirement.

Every test runs inside the transaction provided by ``db_session`` and is
rolled back afterwards, so the dedicated test database stays clean.
"""
from __future__ import annotations

import uuid
import warnings

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SAWarning

from app.models import (
    Match,
    MatchOutcome,
    MatchRequirement,
    MatchStatus,
    Opportunity,
    Profile,
    Requirement,
)
from app.schemas import OpportunityCreate, ProfileCreate, RequirementCreate
from app.services.matching import (
    ENGINE_VERSION,
    MatchEvaluationResult,
    OpportunityMatchStatus,
    RequirementOutcome,
    RequirementResult,
    evaluate_requirements,
)
from app.services.matches import MatchPersistenceError, persist_match_evaluation


def make_profile(**overrides) -> Profile:
    payload = {
        "full_name": "Sara Bekele",
        "email": f"sara-{uuid.uuid4().hex[:10]}@example.org",
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


def make_requirement(**overrides) -> Requirement:
    payload = {
        "label": "Currently enrolled",
        "kind": "boolean_flag",
        "params": {"metric": "is_currently_enrolled", "expected": True},
        "order_index": 0,
        "category": "other",
    }
    payload.update(overrides)
    return Requirement(**RequirementCreate(**payload).model_dump())


def default_requirements() -> list[Requirement]:
    """Three requirements that all hold for :func:`make_profile`."""
    return [
        make_requirement(
            label="Currently enrolled",
            kind="boolean_flag",
            params={"metric": "is_currently_enrolled", "expected": True},
            order_index=0,
        ),
        make_requirement(
            label="Bachelor's degree",
            kind="equality",
            params={"metric": "degree_level", "operator": "==", "value": "bachelor"},
            order_index=1,
        ),
        make_requirement(
            label="Ethiopian citizenship",
            kind="set_membership",
            params={"metric": "citizenship", "operator": "in", "allowed": ["Ethiopia"]},
            order_index=2,
        ),
    ]


def seed(db_session, requirements=None):
    """Persist a profile, an opportunity and its requirements."""
    profile = make_profile()
    opportunity = make_opportunity()
    db_session.add_all([profile, opportunity])
    db_session.flush()

    seeded = list(default_requirements() if requirements is None else requirements)
    for requirement in seeded:
        requirement.opportunity = opportunity
        db_session.add(requirement)
    db_session.flush()
    return profile, opportunity, seeded


def seed_match(db_session, requirements=None):
    """Seed a domain plus an empty Match row for it."""
    profile, opportunity, seeded = seed(db_session, requirements)
    match = Match(
        profile_id=profile.id,
        opportunity_id=opportunity.id,
        status=MatchStatus.ELIGIBLE,
        engine_version=ENGINE_VERSION,
        facts={"total": 0, "met": 0, "not_met": 0, "unknown": 0, "needs_review": 0},
    )
    db_session.add(match)
    db_session.flush()
    return profile, opportunity, seeded, match


def evaluation_for(profile, requirements) -> MatchEvaluationResult:
    return evaluate_requirements(profile, requirements)


def evaluation_with_unknown_requirement() -> MatchEvaluationResult:
    return MatchEvaluationResult(
        status=OpportunityMatchStatus.ELIGIBLE,
        requirement_results=[
            RequirementResult(
                requirement_id=uuid.uuid4(),
                outcome=RequirementOutcome.MET,
                reason_code="boolean_flag_matches",
                expected={"metric": "is_currently_enrolled", "value": True},
                actual={"value": True},
                message="Profile satisfies the requirement.",
            )
        ],
    )


def count(db_session, model) -> int:
    return db_session.scalar(select(func.count()).select_from(model))


def reload(db_session, model, entity_id):
    db_session.expire_all()
    return db_session.get(model, entity_id)


# --- Match -------------------------------------------------------------------------


def test_match_can_be_created(db_session):
    profile, opportunity, _ = seed(db_session, requirements=[])

    match = Match(
        profile_id=profile.id,
        opportunity_id=opportunity.id,
        status=MatchStatus.ELIGIBLE,
        engine_version=ENGINE_VERSION,
        facts={"total": 0, "met": 0, "not_met": 0, "unknown": 0, "needs_review": 0},
    )
    db_session.add(match)
    db_session.flush()
    db_session.refresh(match)

    assert isinstance(match.id, uuid.UUID)
    assert match.profile_id == profile.id
    assert match.opportunity_id == opportunity.id


def test_match_status_persists(db_session):
    profile, opportunity, _ = seed(db_session, requirements=[])

    match = Match(
        profile_id=profile.id,
        opportunity_id=opportunity.id,
        status=MatchStatus.POTENTIAL_MATCH,
        engine_version=ENGINE_VERSION,
        facts={},
    )
    db_session.add(match)
    db_session.flush()

    reloaded = reload(db_session, Match, match.id)

    assert reloaded.status == "potential_match"
    assert reloaded.status == OpportunityMatchStatus.POTENTIAL_MATCH


def test_match_rejects_unknown_status(db_session):
    profile, opportunity, _ = seed(db_session, requirements=[])

    match = Match(
        profile_id=profile.id,
        opportunity_id=opportunity.id,
        status="almost_eligible",
        engine_version=ENGINE_VERSION,
        facts={},
    )
    db_session.add(match)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_match_engine_version_persists(db_session):
    profile, opportunity, _ = seed(db_session, requirements=[])

    match = Match(
        profile_id=profile.id,
        opportunity_id=opportunity.id,
        status=MatchStatus.NOT_ELIGIBLE,
        engine_version="7",
        facts={},
    )
    db_session.add(match)
    db_session.flush()

    assert reload(db_session, Match, match.id).engine_version == "7"


def test_match_evaluated_at_persists_and_is_timezone_aware(db_session):
    profile, opportunity, _ = seed(db_session, requirements=[])

    match = Match(
        profile_id=profile.id,
        opportunity_id=opportunity.id,
        status=MatchStatus.ELIGIBLE,
        engine_version=ENGINE_VERSION,
        facts={},
    )
    db_session.add(match)
    db_session.flush()

    reloaded = reload(db_session, Match, match.id)

    assert reloaded.evaluated_at is not None
    assert reloaded.evaluated_at.tzinfo is not None


def test_match_facts_jsonb_persists(db_session):
    profile, opportunity, _ = seed(db_session, requirements=[])
    facts = {"total": 5, "met": 4, "not_met": 0, "unknown": 1, "needs_review": 0}

    match = Match(
        profile_id=profile.id,
        opportunity_id=opportunity.id,
        status=MatchStatus.POTENTIAL_MATCH,
        engine_version=ENGINE_VERSION,
        facts=facts,
    )
    db_session.add(match)
    db_session.flush()

    assert reload(db_session, Match, match.id).facts == facts


def test_match_profile_opportunity_pair_is_unique(db_session):
    profile, opportunity, _ = seed(db_session, requirements=[])
    db_session.add(
        Match(
            profile_id=profile.id,
            opportunity_id=opportunity.id,
            status=MatchStatus.ELIGIBLE,
            engine_version=ENGINE_VERSION,
            facts={},
        )
    )
    db_session.flush()

    db_session.add(
        Match(
            profile_id=profile.id,
            opportunity_id=opportunity.id,
            status=MatchStatus.NOT_ELIGIBLE,
            engine_version=ENGINE_VERSION,
            facts={},
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_match_profile_relationship(db_session):
    profile, opportunity, _ = seed(db_session, requirements=[])
    match = Match(
        profile_id=profile.id,
        opportunity_id=opportunity.id,
        status=MatchStatus.ELIGIBLE,
        engine_version=ENGINE_VERSION,
        facts={},
    )
    db_session.add(match)
    db_session.flush()

    assert match.profile.email == profile.email
    assert match.profile.id == profile.id


def test_match_opportunity_relationship(db_session):
    profile, opportunity, _ = seed(db_session, requirements=[])
    match = Match(
        profile_id=profile.id,
        opportunity_id=opportunity.id,
        status=MatchStatus.ELIGIBLE,
        engine_version=ENGINE_VERSION,
        facts={},
    )
    db_session.add(match)
    db_session.flush()

    assert match.opportunity.slug == opportunity.slug
    assert match.opportunity.id == opportunity.id


# --- MatchRequirement ---------------------------------------------------------------


def make_match_requirement(match, requirement, **overrides) -> MatchRequirement:
    payload = {
        "match": match,
        "requirement_id": requirement.id,
        "outcome": MatchOutcome.MET,
        "reason_code": "boolean_flag_matches",
        "expected": {"metric": "is_currently_enrolled", "value": True},
        "actual": {"value": True},
        "message": "Profile satisfies the requirement.",
    }
    payload.update(overrides)
    return MatchRequirement(**payload)


def test_match_requirement_persists(db_session):
    _, _, requirements, match = seed_match(db_session)
    row = make_match_requirement(match, requirements[0])
    db_session.add(row)
    db_session.flush()

    reloaded = reload(db_session, MatchRequirement, row.id)

    assert isinstance(reloaded.id, uuid.UUID)
    assert reloaded.match_id == match.id


def test_match_requirement_outcome_persists(db_session):
    _, _, requirements, match = seed_match(db_session)
    row = make_match_requirement(match, requirements[0], outcome=MatchOutcome.UNKNOWN)
    db_session.add(row)
    db_session.flush()

    reloaded = reload(db_session, MatchRequirement, row.id)

    assert reloaded.outcome == "unknown"
    assert reloaded.outcome == RequirementOutcome.UNKNOWN.value


def test_match_requirement_rejects_unknown_outcome(db_session):
    _, _, requirements, match = seed_match(db_session)
    db_session.add(make_match_requirement(match, requirements[0], outcome="maybe"))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_match_requirement_reason_code_persists(db_session):
    _, _, requirements, match = seed_match(db_session)
    row = make_match_requirement(
        match, requirements[0], reason_code="set_membership_does_not_match"
    )
    db_session.add(row)
    db_session.flush()

    assert reload(db_session, MatchRequirement, row.id).reason_code == (
        "set_membership_does_not_match"
    )


def test_match_requirement_expected_jsonb_persists(db_session):
    _, _, requirements, match = seed_match(db_session)
    expected = {
        "operator": "any_of",
        "children": [{"kind": "equality", "params": {"metric": "degree_level"}}],
    }
    row = make_match_requirement(match, requirements[0], expected=expected)
    db_session.add(row)
    db_session.flush()

    assert reload(db_session, MatchRequirement, row.id).expected == expected


def test_match_requirement_actual_jsonb_persists(db_session):
    _, _, requirements, match = seed_match(db_session)
    actual = {"values": ["python", "sql"], "nested": {"depth": 1}}
    row = make_match_requirement(match, requirements[0], actual=actual)
    db_session.add(row)
    db_session.flush()

    assert reload(db_session, MatchRequirement, row.id).actual == actual


def test_match_requirement_message_persists(db_session):
    _, _, requirements, match = seed_match(db_session)
    row = make_match_requirement(
        match, requirements[0], message="Profile does not satisfy the requirement."
    )
    db_session.add(row)
    db_session.flush()

    assert reload(db_session, MatchRequirement, row.id).message == (
        "Profile does not satisfy the requirement."
    )


def test_match_requirement_links_correct_requirement(db_session):
    _, _, requirements, match = seed_match(db_session)
    row = make_match_requirement(match, requirements[1])
    db_session.add(row)
    db_session.flush()

    reloaded = reload(db_session, MatchRequirement, row.id)

    assert reloaded.requirement_id == requirements[1].id
    assert reloaded.requirement.label == "Bachelor's degree"


def test_match_requirement_duplicate_pair_is_rejected(db_session):
    _, _, requirements, match = seed_match(db_session)
    db_session.add(make_match_requirement(match, requirements[0]))
    db_session.flush()

    db_session.add(make_match_requirement(match, requirements[0]))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_match_requirement_requires_existing_match(db_session):
    _, _, requirements, _ = seed_match(db_session)
    orphan = MatchRequirement(
        match_id=uuid.uuid4(),
        requirement_id=requirements[0].id,
        outcome=MatchOutcome.MET,
        reason_code="boolean_flag_matches",
        expected={},
        actual={},
        message="Profile satisfies the requirement.",
    )
    db_session.add(orphan)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_match_requirement_requires_existing_requirement(db_session):
    _, _, _, match = seed_match(db_session)
    orphan = MatchRequirement(
        match_id=match.id,
        requirement_id=uuid.uuid4(),
        outcome=MatchOutcome.MET,
        reason_code="boolean_flag_matches",
        expected={},
        actual={},
        message="Profile satisfies the requirement.",
    )
    db_session.add(orphan)

    with pytest.raises(IntegrityError):
        db_session.flush()


# --- Full evaluation persistence -----------------------------------------------------


def test_persist_match_evaluation_maps_status_and_facts(db_session):
    profile, opportunity, requirements = seed(db_session)
    evaluation = evaluation_for(profile, requirements)

    match = persist_match_evaluation(db_session, profile, opportunity, evaluation)

    assert match.status == str(evaluation.status)
    assert match.status == MatchStatus.ELIGIBLE
    assert match.facts == {
        "total": 3,
        "met": 3,
        "not_met": 0,
        "unknown": 0,
        "needs_review": 0,
    }
    assert match.engine_version == ENGINE_VERSION
    assert reload(db_session, Match, match.id).status == "eligible"


def test_persist_match_evaluation_creates_one_row_per_result(db_session):
    profile, opportunity, requirements = seed(db_session)
    evaluation = evaluation_for(profile, requirements)

    match = persist_match_evaluation(db_session, profile, opportunity, evaluation)

    assert count(db_session, Match) == 1
    assert count(db_session, MatchRequirement) == len(evaluation.requirement_results)
    assert len(match.requirement_results) == len(evaluation.requirement_results)


def test_persist_match_evaluation_preserves_requirement_ids(db_session):
    profile, opportunity, requirements = seed(db_session)
    evaluation = evaluation_for(profile, requirements)

    match = persist_match_evaluation(db_session, profile, opportunity, evaluation)

    persisted_ids = {row.requirement_id for row in match.requirement_results}
    evaluated_ids = {result.requirement_id for result in evaluation.requirement_results}
    assert persisted_ids == evaluated_ids == {requirement.id for requirement in requirements}


def test_persist_match_evaluation_preserves_evidence(db_session):
    profile, opportunity, requirements = seed(db_session)
    evaluation = evaluation_for(profile, requirements)

    match = persist_match_evaluation(db_session, profile, opportunity, evaluation)
    rows = {row.requirement_id: row for row in match.requirement_results}

    for result in evaluation.requirement_results:
        row = rows[result.requirement_id]
        assert row.outcome == str(result.outcome)
        assert row.reason_code == result.reason_code
        assert row.expected == result.expected
        assert row.actual == result.actual
        assert row.message == result.message


def test_persist_match_evaluation_facts_are_deterministic(db_session):
    profile, opportunity, requirements = seed(db_session)
    evaluation = evaluation_for(profile, requirements)

    first = persist_match_evaluation(db_session, profile, opportunity, evaluation)
    second = persist_match_evaluation(db_session, profile, opportunity, evaluation)

    assert first.facts == second.facts
    assert sorted(first.facts) == sorted(
        ["total", "met", "not_met", "unknown", "needs_review"]
    )


def test_repeated_persistence_updates_single_match(db_session):
    profile, opportunity, requirements = seed(db_session)
    first_evaluation = evaluation_for(profile, requirements)
    first_match = persist_match_evaluation(db_session, profile, opportunity, first_evaluation)
    first_row_ids = {row.id for row in first_match.requirement_results}

    profile.citizenships = ["Kenya"]
    second_evaluation = evaluation_for(profile, requirements)
    second_match = persist_match_evaluation(db_session, profile, opportunity, second_evaluation)

    assert second_match.id == first_match.id
    assert count(db_session, Match) == 1
    assert count(db_session, MatchRequirement) == len(second_evaluation.requirement_results)
    assert second_match.status == OpportunityMatchStatus.NOT_ELIGIBLE
    assert second_match.facts == {
        "total": 3,
        "met": 2,
        "not_met": 1,
        "unknown": 0,
        "needs_review": 0,
    }
    second_row_ids = {row.id for row in second_match.requirement_results}
    assert first_row_ids.isdisjoint(second_row_ids)
    outcomes = {row.requirement_id: row.outcome for row in second_match.requirement_results}
    assert outcomes[requirements[2].id] == "not_met"


def test_failed_persistence_leaves_no_partial_match(db_session):
    profile, opportunity, _ = seed(db_session)

    with pytest.raises(MatchPersistenceError):
        persist_match_evaluation(
            db_session, profile, opportunity, evaluation_with_unknown_requirement()
        )

    assert count(db_session, Match) == 0
    assert count(db_session, MatchRequirement) == 0


def test_failed_re_evaluation_keeps_existing_match_intact(db_session):
    profile, opportunity, requirements = seed(db_session)
    evaluation = evaluation_for(profile, requirements)
    match = persist_match_evaluation(db_session, profile, opportunity, evaluation)
    original_row_ids = {row.id for row in match.requirement_results}

    with pytest.raises(MatchPersistenceError):
        persist_match_evaluation(
            db_session, profile, opportunity, evaluation_with_unknown_requirement()
        )

    assert count(db_session, Match) == 1
    assert count(db_session, MatchRequirement) == len(original_row_ids)
    persisted = reload(db_session, Match, match.id)
    assert persisted.status == OpportunityMatchStatus.ELIGIBLE
    assert {row.id for row in persisted.requirement_results} == original_row_ids


def test_persist_match_evaluation_emits_no_orm_warnings(db_session):
    profile, opportunity, requirements = seed(db_session)
    evaluation = evaluation_for(profile, requirements)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        persist_match_evaluation(db_session, profile, opportunity, evaluation)
        db_session.flush()

    assert not [w for w in caught if issubclass(w.category, SAWarning)]


# --- Cascades and integrity ----------------------------------------------------------


def test_deleting_profile_cascades_match_and_evidence(db_session):
    profile, opportunity, requirements = seed(db_session)
    evaluation = evaluation_for(profile, requirements)
    persist_match_evaluation(db_session, profile, opportunity, evaluation)

    db_session.delete(profile)
    db_session.flush()

    assert count(db_session, Match) == 0
    assert count(db_session, MatchRequirement) == 0
    assert db_session.get(Opportunity, opportunity.id) is not None
    assert count(db_session, Requirement) == len(requirements)


def test_deleting_opportunity_cascades_match_and_evidence(db_session):
    profile, opportunity, requirements = seed(db_session)
    evaluation = evaluation_for(profile, requirements)
    persist_match_evaluation(db_session, profile, opportunity, evaluation)

    db_session.delete(opportunity)
    db_session.flush()

    assert count(db_session, Match) == 0
    assert count(db_session, MatchRequirement) == 0
    assert db_session.get(Profile, profile.id) is not None


def test_deleting_requirement_with_evidence_is_restricted(db_session):
    profile, opportunity, requirements = seed(db_session)
    evaluation = evaluation_for(profile, requirements)
    persist_match_evaluation(db_session, profile, opportunity, evaluation)

    db_session.delete(requirements[0])

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_deleting_requirement_without_evidence_is_allowed(db_session):
    profile, opportunity, requirements = seed(db_session)
    evaluation = evaluation_for(profile, requirements)
    match = persist_match_evaluation(db_session, profile, opportunity, evaluation)
    # Only the first requirement carries evidence in this scenario.
    for row in list(match.requirement_results):
        if row.requirement_id != requirements[0].id:
            db_session.delete(row)
    db_session.flush()

    db_session.delete(requirements[1])
    db_session.flush()

    assert db_session.get(Requirement, requirements[1].id) is None
    assert db_session.get(Requirement, requirements[0].id) is not None


# --- Vocabulary guard -----------------------------------------------------------------


def test_match_enums_mirror_matching_engine_vocabulary():
    assert [status.value for status in MatchStatus] == [
        status.value for status in OpportunityMatchStatus
    ]
    assert [outcome.value for outcome in MatchOutcome] == [
        outcome.value for outcome in RequirementOutcome
    ]
    assert MatchStatus.ELIGIBLE == OpportunityMatchStatus.ELIGIBLE
    assert MatchOutcome.MET == RequirementOutcome.MET
