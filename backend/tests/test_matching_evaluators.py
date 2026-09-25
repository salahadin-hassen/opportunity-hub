"""Unit tests for the first deterministic matching evaluator slice."""
from types import SimpleNamespace

import pytest

from app.services.matching import RequirementOutcome, RequirementResult, evaluate_requirement
from app.services.matching.boolean_flag import evaluate_boolean_flag


def make_profile(**overrides):
    values = {"is_currently_enrolled": True}
    values.update(overrides)
    return SimpleNamespace(**values)


def make_requirement(**overrides):
    values = {
        "kind": "boolean_flag",
        "params": {"metric": "is_currently_enrolled", "expected": True},
        "is_ambiguous": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_boolean_flag_is_met():
    result = evaluate_boolean_flag(make_profile(is_currently_enrolled=True), make_requirement())

    assert result.outcome == RequirementOutcome.MET


def test_boolean_flag_is_not_met():
    result = evaluate_boolean_flag(make_profile(is_currently_enrolled=False), make_requirement())

    assert result.outcome == RequirementOutcome.NOT_MET


def test_registry_dispatches_boolean_flag_evaluator():
    result = evaluate_requirement(
        make_profile(is_currently_enrolled=True),
        make_requirement(),
    )

    assert result.outcome == RequirementOutcome.MET
    assert result.reason_code == "boolean_flag_matches"


def test_missing_profile_fact_is_unknown():
    result = evaluate_boolean_flag(SimpleNamespace(), make_requirement())

    assert result.outcome == RequirementOutcome.UNKNOWN
    assert result.reason_code == "profile_fact_unavailable"


def test_ambiguous_requirement_needs_review():
    result = evaluate_boolean_flag(make_profile(), make_requirement(is_ambiguous=True))

    assert result.outcome == RequirementOutcome.NEEDS_REVIEW
    assert result.reason_code == "ambiguous_requirement"


def test_unsupported_boolean_metric_needs_review():
    requirement = make_requirement(
        params={"metric": "some_future_metric", "expected": True}
    )

    result = evaluate_boolean_flag(make_profile(), requirement)

    assert result.outcome == RequirementOutcome.NEEDS_REVIEW
    assert result.reason_code == "unsupported_boolean_metric"


def test_unsupported_requirement_kind_needs_review():
    result = evaluate_requirement(make_profile(), make_requirement(kind="numeric_threshold"))

    assert result.outcome == RequirementOutcome.NEEDS_REVIEW
    assert result.reason_code == "unsupported_requirement_kind"


def test_result_contains_expected_and_actual_evidence():
    result = evaluate_requirement(make_profile(is_currently_enrolled=True), make_requirement())

    assert result.expected == {"metric": "is_currently_enrolled", "value": True}
    assert result.actual == {"value": True}


def test_result_is_serializable_and_messages_are_deterministic():
    result = evaluate_requirement(make_profile(), make_requirement())

    assert isinstance(result, RequirementResult)
    assert result.model_dump(mode="json") == {
        "outcome": "met",
        "reason_code": "boolean_flag_matches",
        "expected": {"metric": "is_currently_enrolled", "value": True},
        "actual": {"value": True},
        "message": "Profile satisfies the requirement.",
    }