"""Unit tests for the first deterministic matching evaluator slice."""
from types import SimpleNamespace
from decimal import Decimal

import pytest

from app.services.matching import RequirementOutcome, RequirementResult, evaluate_requirement
from app.services.matching.boolean_flag import evaluate_boolean_flag
from app.services.matching.numeric_threshold import evaluate_numeric_threshold
from app.services.matching.set_membership import evaluate_set_membership


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


def make_numeric_requirement(**overrides):
    values = {
        "kind": "numeric_threshold",
        "params": {"metric": "gpa", "operator": ">=", "value": 3.5},
        "is_ambiguous": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def make_education(gpa=Decimal("3.7"), is_primary=True):
    return SimpleNamespace(gpa=gpa, is_primary=is_primary)


def make_set_membership_requirement(**overrides):
    values = {
        "kind": "set_membership",
        "params": {"metric": "citizenship", "operator": "in", "allowed": ["Ethiopia"]},
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
    result = evaluate_requirement(make_profile(), make_requirement(kind="equality"))

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


def test_numeric_threshold_gpa_is_met():
    result = evaluate_numeric_threshold(
        make_profile(education=[make_education()]), make_numeric_requirement()
    )

    assert result.outcome == RequirementOutcome.MET


def test_numeric_threshold_gpa_is_below_threshold():
    result = evaluate_numeric_threshold(
        make_profile(education=[make_education(Decimal("3.2"))]), make_numeric_requirement()
    )

    assert result.outcome == RequirementOutcome.NOT_MET


def test_numeric_threshold_missing_gpa_is_unknown():
    result = evaluate_numeric_threshold(
        make_profile(education=[make_education(None)]), make_numeric_requirement()
    )

    assert result.outcome == RequirementOutcome.UNKNOWN


def test_numeric_threshold_ambiguous_requirement_needs_review():
    result = evaluate_numeric_threshold(
        make_profile(education=[make_education()]), make_numeric_requirement(is_ambiguous=True)
    )

    assert result.outcome == RequirementOutcome.NEEDS_REVIEW


def test_numeric_threshold_unsupported_metric_needs_review():
    result = evaluate_numeric_threshold(
        make_profile(education=[make_education()]),
        make_numeric_requirement(params={"metric": "degree_level", "operator": ">=", "value": 3.5}),
    )

    assert result.outcome == RequirementOutcome.NEEDS_REVIEW
    assert result.reason_code == "unsupported_numeric_metric"


@pytest.mark.parametrize(
    "params",
    [
        {"metric": "gpa", "operator": ">="},
        {"metric": "gpa", "operator": ">=", "value": "not-a-number"},
    ],
)
def test_numeric_threshold_malformed_parameters_need_review(params):
    result = evaluate_numeric_threshold(
        make_profile(education=[make_education()]), make_numeric_requirement(params=params)
    )

    assert result.outcome == RequirementOutcome.NEEDS_REVIEW
    assert result.reason_code == "invalid_numeric_threshold"


def test_numeric_threshold_contains_expected_and_actual_evidence():
    result = evaluate_numeric_threshold(
        make_profile(education=[make_education(Decimal("3.7"))]), make_numeric_requirement()
    )

    assert result.expected == {"metric": "gpa", "operator": ">=", "value": 3.5}
    assert result.actual == {"value": 3.7}


def test_registry_dispatches_numeric_threshold_evaluator():
    result = evaluate_requirement(
        make_profile(education=[make_education()]), make_numeric_requirement()
    )

    assert result.outcome == RequirementOutcome.MET
    assert result.reason_code == "numeric_threshold_met"


def test_numeric_threshold_reason_code_and_message_are_deterministic():
    result = evaluate_numeric_threshold(
        make_profile(education=[make_education()]), make_numeric_requirement()
    )

    assert result.reason_code == "numeric_threshold_met"
    assert result.message == "Profile satisfies the numeric threshold requirement."


def test_set_membership_citizenship_is_present():
    result = evaluate_set_membership(
        make_profile(citizenships=["Ethiopia", "Kenya"]), make_set_membership_requirement()
    )

    assert result.outcome == RequirementOutcome.MET


def test_set_membership_citizenship_is_absent():
    result = evaluate_set_membership(
        make_profile(citizenships=["Kenya"]), make_set_membership_requirement()
    )

    assert result.outcome == RequirementOutcome.NOT_MET


def test_set_membership_missing_citizenship_data_is_unknown():
    result = evaluate_set_membership(SimpleNamespace(), make_set_membership_requirement())

    assert result.outcome == RequirementOutcome.UNKNOWN


def test_set_membership_empty_citizenship_collection_is_not_met():
    result = evaluate_set_membership(
        make_profile(citizenships=[]), make_set_membership_requirement()
    )

    assert result.outcome == RequirementOutcome.NOT_MET


def test_set_membership_ambiguous_requirement_needs_review():
    result = evaluate_set_membership(
        make_profile(citizenships=["Ethiopia"]),
        make_set_membership_requirement(is_ambiguous=True),
    )

    assert result.outcome == RequirementOutcome.NEEDS_REVIEW


def test_set_membership_unsupported_metric_needs_review():
    result = evaluate_set_membership(
        make_profile(citizenships=["Ethiopia"]),
        make_set_membership_requirement(
            params={"metric": "language", "operator": "in", "allowed": ["English"]}
        ),
    )

    assert result.outcome == RequirementOutcome.NEEDS_REVIEW
    assert result.reason_code == "unsupported_set_metric"


@pytest.mark.parametrize(
    "params",
    [
        {"metric": "citizenship", "operator": "in"},
        {"metric": "citizenship", "operator": "in", "allowed": []},
        {"metric": "citizenship", "operator": "in", "allowed": ["Ethiopia", "Kenya"]},
        {"metric": "citizenship", "operator": "in", "allowed": [42]},
    ],
)
def test_set_membership_malformed_expected_value_needs_review(params):
    result = evaluate_set_membership(
        make_profile(citizenships=["Ethiopia"]),
        make_set_membership_requirement(params=params),
    )

    assert result.outcome == RequirementOutcome.NEEDS_REVIEW
    assert result.reason_code == "invalid_set_membership"


def test_set_membership_contains_expected_and_actual_evidence():
    result = evaluate_set_membership(
        make_profile(citizenships=["Ethiopia", "Kenya"]), make_set_membership_requirement()
    )

    assert result.expected == {"metric": "citizenship", "value": "Ethiopia"}
    assert result.actual == {"values": ["Ethiopia", "Kenya"]}


def test_registry_dispatches_set_membership_evaluator():
    result = evaluate_requirement(
        make_profile(citizenships=["Ethiopia"]), make_set_membership_requirement()
    )

    assert result.outcome == RequirementOutcome.MET
    assert result.reason_code == "set_membership_matches"


def test_set_membership_reason_code_and_message_are_deterministic():
    result = evaluate_set_membership(
        make_profile(citizenships=["Ethiopia"]), make_set_membership_requirement()
    )

    assert result.reason_code == "set_membership_matches"
    assert result.message == "Profile satisfies the set membership requirement."