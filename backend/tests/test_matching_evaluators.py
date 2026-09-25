"""Unit tests for the first deterministic matching evaluator slice."""
from types import SimpleNamespace
from datetime import date, datetime, timezone
from decimal import Decimal
import uuid

import pytest

from app.services.matching import (
    MatchEvaluationResult,
    OpportunityMatchStatus,
    RequirementOutcome,
    RequirementResult,
    evaluate_requirement,
    evaluate_requirements,
)
from app.services.matching.boolean_flag import evaluate_boolean_flag
from app.services.matching.date_gate import evaluate_date_gate
from app.services.matching.equality import evaluate_equality
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


def make_equality_requirement(**overrides):
    values = {
        "kind": "equality",
        "params": {"metric": "degree_level", "operator": "==", "value": "bachelor"},
        "is_ambiguous": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def make_date_gate_requirement(**overrides):
    values = {
        "kind": "date_gate",
        "params": {"metric": "date_of_birth", "operator": "<=", "value": "2000-01-01"},
        "is_ambiguous": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def make_orchestration_requirement(kind="boolean_flag", is_mandatory=True, order_index=0, **overrides):
    values = {
        "id": uuid.uuid4(),
        "kind": kind,
        "is_mandatory": is_mandatory,
        "order_index": order_index,
        "is_ambiguous": False,
        "params": {"metric": "is_currently_enrolled", "expected": True},
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
    result = evaluate_requirement(make_profile(), make_requirement(kind="skill_set"))

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
        "requirement_id": None,
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


def test_all_mandatory_requirements_met_are_eligible():
    result = evaluate_requirements(
        make_profile(is_currently_enrolled=True),
        [make_orchestration_requirement(), make_orchestration_requirement(order_index=1)],
    )

    assert result.status == OpportunityMatchStatus.ELIGIBLE


def test_mandatory_requirement_not_met_is_not_eligible():
    result = evaluate_requirements(
        make_profile(is_currently_enrolled=False), [make_orchestration_requirement()]
    )

    assert result.status == OpportunityMatchStatus.NOT_ELIGIBLE


def test_unknown_without_not_met_is_potential_match():
    result = evaluate_requirements(
        SimpleNamespace(), [make_orchestration_requirement()]
    )

    assert result.status == OpportunityMatchStatus.POTENTIAL_MATCH


def test_needs_review_without_not_met_needs_review():
    result = evaluate_requirements(
        make_profile(), [make_orchestration_requirement(kind="equality")]
    )

    assert result.status == OpportunityMatchStatus.NEEDS_REVIEW


def test_mandatory_not_met_precedes_unknown():
    result = evaluate_requirements(
        SimpleNamespace(is_currently_enrolled=False),
        [
            make_orchestration_requirement(),
            make_orchestration_requirement(order_index=1, kind="equality"),
        ],
    )

    assert result.status == OpportunityMatchStatus.NOT_ELIGIBLE


def test_mandatory_not_met_precedes_needs_review():
    result = evaluate_requirements(
        make_profile(is_currently_enrolled=False),
        [
            make_orchestration_requirement(),
            make_orchestration_requirement(order_index=1, kind="equality"),
        ],
    )

    assert result.status == OpportunityMatchStatus.NOT_ELIGIBLE


def test_optional_not_met_does_not_make_result_not_eligible():
    result = evaluate_requirements(
        make_profile(is_currently_enrolled=False),
        [make_orchestration_requirement(is_mandatory=False)],
    )

    assert result.status == OpportunityMatchStatus.ELIGIBLE


def test_optional_unknown_can_make_result_potential_match():
    result = evaluate_requirements(
        SimpleNamespace(), [make_orchestration_requirement(is_mandatory=False)]
    )

    assert result.status == OpportunityMatchStatus.POTENTIAL_MATCH


def test_requirements_are_ordered_by_order_index_and_evaluated_once():
    result = evaluate_requirements(
        make_profile(is_currently_enrolled=True),
        [
            make_orchestration_requirement(order_index=2),
            make_orchestration_requirement(order_index=1),
        ],
    )

    assert len(result.requirement_results) == 2
    assert [item.reason_code for item in result.requirement_results] == [
        "boolean_flag_matches",
        "boolean_flag_matches",
    ]


def test_individual_requirement_results_are_preserved():
    result = evaluate_requirements(
        make_profile(is_currently_enrolled=True), [make_orchestration_requirement()]
    )

    assert isinstance(result, MatchEvaluationResult)
    assert result.requirement_results[0].model_dump() == {
        "requirement_id": result.requirement_results[0].requirement_id,
        "outcome": RequirementOutcome.MET,
        "reason_code": "boolean_flag_matches",
        "expected": {"metric": "is_currently_enrolled", "value": True},
        "actual": {"value": True},
        "message": "Profile satisfies the requirement.",
    }


def test_no_requirements_are_eligible():
    result = evaluate_requirements(make_profile(), [])

    assert result.status == OpportunityMatchStatus.ELIGIBLE
    assert result.requirement_results == []


def test_only_optional_requirements_follow_rollup_rules():
    result = evaluate_requirements(
        make_profile(is_currently_enrolled=False),
        [make_orchestration_requirement(is_mandatory=False)],
    )

    assert result.status == OpportunityMatchStatus.ELIGIBLE


def test_orchestrated_boolean_result_contains_requirement_id():
    requirement = make_orchestration_requirement()

    result = evaluate_requirements(make_profile(), [requirement])

    assert result.requirement_results[0].requirement_id == requirement.id


def test_orchestrated_numeric_result_contains_requirement_id():
    requirement = make_orchestration_requirement(
        kind="numeric_threshold",
        params={"metric": "gpa", "operator": ">=", "value": 3.5},
    )

    result = evaluate_requirements(
        make_profile(education=[make_education()]), [requirement]
    )

    assert result.requirement_results[0].requirement_id == requirement.id


def test_orchestrated_set_membership_result_contains_requirement_id():
    requirement = make_orchestration_requirement(
        kind="set_membership",
        params={"metric": "citizenship", "operator": "in", "allowed": ["Ethiopia"]},
    )

    result = evaluate_requirements(make_profile(citizenships=["Ethiopia"]), [requirement])

    assert result.requirement_results[0].requirement_id == requirement.id


def test_orchestrated_requirement_ids_follow_deterministic_order():
    later = make_orchestration_requirement(order_index=2)
    earlier = make_orchestration_requirement(order_index=1)

    result = evaluate_requirements(make_profile(), [later, earlier])

    assert [item.requirement_id for item in result.requirement_results] == [
        earlier.id,
        later.id,
    ]


def test_orchestrated_result_preserves_evidence_and_serializes_requirement_id():
    requirement = make_orchestration_requirement()

    result = evaluate_requirements(make_profile(), [requirement])
    requirement_result = result.requirement_results[0]

    assert requirement_result.outcome == RequirementOutcome.MET
    assert requirement_result.reason_code == "boolean_flag_matches"
    assert requirement_result.expected == {"metric": "is_currently_enrolled", "value": True}
    assert requirement_result.actual == {"value": True}
    assert requirement_result.message == "Profile satisfies the requirement."
    assert requirement_result.model_dump(mode="json")["requirement_id"] == str(requirement.id)


def test_repeated_orchestration_preserves_requirement_ids_and_results():
    requirement = make_orchestration_requirement()

    first = evaluate_requirements(make_profile(), [requirement])
    second = evaluate_requirements(make_profile(), [requirement])

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_equality_degree_level_is_met():
    result = evaluate_equality(
        make_profile(degree_level="bachelor"), make_equality_requirement()
    )

    assert result.outcome == RequirementOutcome.MET


def test_equality_degree_level_is_not_met():
    result = evaluate_equality(
        make_profile(degree_level="master"), make_equality_requirement()
    )

    assert result.outcome == RequirementOutcome.NOT_MET


def test_equality_is_exact_and_does_not_fold_case():
    result = evaluate_equality(
        make_profile(degree_level="BACHELOR"), make_equality_requirement()
    )

    assert result.outcome == RequirementOutcome.NOT_MET


def test_equality_missing_profile_value_is_unknown():
    result = evaluate_equality(SimpleNamespace(), make_equality_requirement())

    assert result.outcome == RequirementOutcome.UNKNOWN
    assert result.reason_code == "profile_fact_unavailable"


def test_equality_none_profile_value_is_unknown():
    result = evaluate_equality(
        make_profile(degree_level=None), make_equality_requirement()
    )

    assert result.outcome == RequirementOutcome.UNKNOWN


def test_equality_ambiguous_requirement_needs_review():
    result = evaluate_equality(
        make_profile(degree_level="bachelor"), make_equality_requirement(is_ambiguous=True)
    )

    assert result.outcome == RequirementOutcome.NEEDS_REVIEW
    assert result.reason_code == "ambiguous_requirement"


def test_equality_unsupported_metric_needs_review():
    result = evaluate_equality(
        make_profile(degree_level="bachelor"),
        make_equality_requirement(params={"metric": "field_of_study", "operator": "==", "value": "biology"}),
    )

    assert result.outcome == RequirementOutcome.NEEDS_REVIEW
    assert result.reason_code == "unsupported_equality_metric"


@pytest.mark.parametrize(
    "params",
    [
        {"metric": "degree_level", "operator": "=="},
        {"metric": "degree_level", "operator": "==", "value": None},
        {"metric": "degree_level", "operator": "==", "value": ["bachelor"]},
        {"metric": "degree_level", "operator": "==", "value": {"level": "bachelor"}},
        {"metric": "degree_level", "operator": "==", "value": (1, 2)},
    ],
)
def test_equality_missing_or_malformed_expected_value_needs_review(params):
    result = evaluate_equality(
        make_profile(degree_level="bachelor"), make_equality_requirement(params=params)
    )

    assert result.outcome == RequirementOutcome.NEEDS_REVIEW
    assert result.reason_code == "invalid_equality_value"


def test_equality_non_dict_params_need_review():
    result = evaluate_equality(
        make_profile(degree_level="bachelor"), make_equality_requirement(params="degree_level=bachelor")
    )

    assert result.outcome == RequirementOutcome.NEEDS_REVIEW
    assert result.reason_code == "invalid_equality_value"


def test_equality_unsupported_operator_needs_review():
    result = evaluate_equality(
        make_profile(degree_level="bachelor"),
        make_equality_requirement(params={"metric": "degree_level", "operator": "!=", "value": "bachelor"}),
    )

    assert result.outcome == RequirementOutcome.NEEDS_REVIEW
    assert result.reason_code == "unsupported_equality_operator"


def test_equality_contains_expected_evidence():
    result = evaluate_equality(
        make_profile(degree_level="bachelor"), make_equality_requirement()
    )

    assert result.expected == {"metric": "degree_level", "operator": "==", "value": "bachelor"}


def test_equality_contains_actual_evidence():
    result = evaluate_equality(
        make_profile(degree_level="bachelor"), make_equality_requirement()
    )

    assert result.actual == {"value": "bachelor"}


def test_equality_missing_profile_fact_contains_none_evidence():
    result = evaluate_equality(SimpleNamespace(), make_equality_requirement())

    assert result.expected == {"metric": "degree_level", "operator": "==", "value": "bachelor"}
    assert result.actual == {"value": None}


def test_registry_dispatches_equality_evaluator():
    result = evaluate_requirement(
        make_profile(degree_level="bachelor"), make_equality_requirement()
    )

    assert result.outcome == RequirementOutcome.MET
    assert result.reason_code == "equality_matches"


def test_equality_reason_code_and_message_are_deterministic():
    result = evaluate_equality(
        make_profile(degree_level="bachelor"), make_equality_requirement()
    )

    assert result.reason_code == "equality_matches"
    assert result.message == "Profile satisfies the equality requirement."


def test_equality_result_serializes_to_stable_evidence():
    result = evaluate_equality(
        make_profile(degree_level="bachelor"), make_equality_requirement()
    )

    assert result.model_dump(mode="json") == {
        "requirement_id": None,
        "outcome": "met",
        "reason_code": "equality_matches",
        "expected": {"metric": "degree_level", "operator": "==", "value": "bachelor"},
        "actual": {"value": "bachelor"},
        "message": "Profile satisfies the equality requirement.",
    }


def test_equality_not_met_reason_code_and_message_are_deterministic():
    result = evaluate_equality(
        make_profile(degree_level="master"), make_equality_requirement()
    )

    assert result.model_dump(mode="json") == {
        "requirement_id": None,
        "outcome": "not_met",
        "reason_code": "equality_does_not_match",
        "expected": {"metric": "degree_level", "operator": "==", "value": "bachelor"},
        "actual": {"value": "master"},
        "message": "Profile does not satisfy the equality requirement.",
    }


def test_orchestrated_equality_result_contains_requirement_id():
    requirement = make_orchestration_requirement(
        kind="equality",
        params={"metric": "degree_level", "operator": "==", "value": "bachelor"},
    )

    result = evaluate_requirements(make_profile(degree_level="bachelor"), [requirement])

    assert result.requirement_results[0].requirement_id == requirement.id
    assert result.requirement_results[0].reason_code == "equality_matches"


def test_equality_met_requirement_keeps_rollup_eligible():
    result = evaluate_requirements(
        make_profile(degree_level="bachelor"),
        [
            make_orchestration_requirement(),
            make_orchestration_requirement(
                order_index=1,
                kind="equality",
                params={"metric": "degree_level", "operator": "==", "value": "bachelor"},
            ),
        ],
    )

    assert result.status == OpportunityMatchStatus.ELIGIBLE
    assert [item.reason_code for item in result.requirement_results] == [
        "boolean_flag_matches",
        "equality_matches",
    ]


def test_equality_not_met_mandatory_requirement_keeps_rollup_not_eligible():
    result = evaluate_requirements(
        make_profile(degree_level="master"),
        [
            make_orchestration_requirement(
                kind="equality",
                params={"metric": "degree_level", "operator": "==", "value": "bachelor"},
            ),
        ],
    )

    assert result.status == OpportunityMatchStatus.NOT_ELIGIBLE


def test_equality_unknown_requirement_keeps_rollup_potential_match():
    result = evaluate_requirements(
        SimpleNamespace(),
        [
            make_orchestration_requirement(
                kind="equality",
                params={"metric": "degree_level", "operator": "==", "value": "bachelor"},
            ),
        ],
    )

    assert result.status == OpportunityMatchStatus.POTENTIAL_MATCH


def test_repeated_equality_evaluation_is_deterministic():
    requirement = make_equality_requirement()
    profile = make_profile(degree_level="bachelor")

    first = evaluate_equality(profile, requirement)
    second = evaluate_equality(profile, requirement)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_date_gate_birth_date_on_or_before_cutoff_is_met():
    result = evaluate_date_gate(
        make_profile(date_of_birth=date(1998, 5, 15)), make_date_gate_requirement()
    )

    assert result.outcome == RequirementOutcome.MET


def test_date_gate_birth_date_after_cutoff_is_not_met():
    result = evaluate_date_gate(
        make_profile(date_of_birth=date(2001, 3, 1)), make_date_gate_requirement()
    )

    assert result.outcome == RequirementOutcome.NOT_MET


def test_date_gate_birth_date_equal_to_cutoff_is_met():
    result = evaluate_date_gate(
        make_profile(date_of_birth=date(2000, 1, 1)), make_date_gate_requirement()
    )

    assert result.outcome == RequirementOutcome.MET
    assert result.reason_code == "date_gate_met"


def test_date_gate_missing_profile_date_is_unknown():
    result = evaluate_date_gate(SimpleNamespace(), make_date_gate_requirement())

    assert result.outcome == RequirementOutcome.UNKNOWN
    assert result.reason_code == "profile_fact_unavailable"


def test_date_gate_none_profile_date_is_unknown():
    result = evaluate_date_gate(
        make_profile(date_of_birth=None), make_date_gate_requirement()
    )

    assert result.outcome == RequirementOutcome.UNKNOWN
    assert result.reason_code == "profile_fact_unavailable"


def test_date_gate_ambiguous_requirement_needs_review():
    result = evaluate_date_gate(
        make_profile(date_of_birth=date(1998, 5, 15)),
        make_date_gate_requirement(is_ambiguous=True),
    )

    assert result.outcome == RequirementOutcome.NEEDS_REVIEW
    assert result.reason_code == "ambiguous_requirement"


def test_date_gate_unsupported_metric_needs_review():
    result = evaluate_date_gate(
        make_profile(date_of_birth=date(1998, 5, 15)),
        make_date_gate_requirement(
            params={"metric": "graduation_date", "operator": "<=", "value": "2000-01-01"}
        ),
    )

    assert result.outcome == RequirementOutcome.NEEDS_REVIEW
    assert result.reason_code == "unsupported_date_metric"


@pytest.mark.parametrize("operator", ["<", ">=", ">", "==", "!="])
def test_date_gate_unsupported_operator_needs_review(operator):
    result = evaluate_date_gate(
        make_profile(date_of_birth=date(1998, 5, 15)),
        make_date_gate_requirement(
            params={"metric": "date_of_birth", "operator": operator, "value": "2000-01-01"}
        ),
    )

    assert result.outcome == RequirementOutcome.NEEDS_REVIEW
    assert result.reason_code == "unsupported_date_operator"


def test_date_gate_missing_expected_date_needs_review():
    result = evaluate_date_gate(
        make_profile(date_of_birth=date(1998, 5, 15)),
        make_date_gate_requirement(params={"metric": "date_of_birth", "operator": "<="}),
    )

    assert result.outcome == RequirementOutcome.NEEDS_REVIEW
    assert result.reason_code == "invalid_date_gate_value"


@pytest.mark.parametrize(
    "value",
    [
        None,
        "not-a-date",
        "01/01/2000",
        "20000101",
        "2000-01-01T00:00:00",
        20000101,
        ["2000-01-01"],
        {"year": 2000},
        datetime(2000, 1, 1),
        datetime(2000, 1, 1, tzinfo=timezone.utc),
    ],
)
def test_date_gate_malformed_expected_date_needs_review(value):
    result = evaluate_date_gate(
        make_profile(date_of_birth=date(1998, 5, 15)),
        make_date_gate_requirement(
            params={"metric": "date_of_birth", "operator": "<=", "value": value}
        ),
    )

    assert result.outcome == RequirementOutcome.NEEDS_REVIEW
    assert result.reason_code == "invalid_date_gate_value"


def test_date_gate_non_dict_params_need_review():
    result = evaluate_date_gate(
        make_profile(date_of_birth=date(1998, 5, 15)),
        make_date_gate_requirement(params="date_of_birth<=2000-01-01"),
    )

    assert result.outcome == RequirementOutcome.NEEDS_REVIEW
    assert result.reason_code == "invalid_date_gate_value"


def test_date_gate_accepts_structured_date_value():
    result = evaluate_date_gate(
        make_profile(date_of_birth=date(1998, 5, 15)),
        make_date_gate_requirement(
            params={"metric": "date_of_birth", "operator": "<=", "value": date(2000, 1, 1)}
        ),
    )

    assert result.outcome == RequirementOutcome.MET
    assert result.expected == {"metric": "date_of_birth", "operator": "<=", "value": "2000-01-01"}


@pytest.mark.parametrize(
    "birth_date",
    [
        datetime(1998, 5, 15),
        datetime(1998, 5, 15, tzinfo=timezone.utc),
    ],
)
def test_date_gate_datetime_profile_value_needs_review(birth_date):
    result = evaluate_date_gate(
        make_profile(date_of_birth=birth_date), make_date_gate_requirement()
    )

    assert result.outcome == RequirementOutcome.NEEDS_REVIEW
    assert result.reason_code == "incompatible_date_fact"


def test_date_gate_non_date_profile_value_needs_review():
    result = evaluate_date_gate(
        make_profile(date_of_birth="1998-05-15"), make_date_gate_requirement()
    )

    assert result.outcome == RequirementOutcome.NEEDS_REVIEW
    assert result.reason_code == "incompatible_date_fact"


def test_date_gate_contains_expected_evidence():
    result = evaluate_date_gate(
        make_profile(date_of_birth=date(1998, 5, 15)), make_date_gate_requirement()
    )

    assert result.expected == {"metric": "date_of_birth", "operator": "<=", "value": "2000-01-01"}


def test_date_gate_contains_actual_evidence():
    result = evaluate_date_gate(
        make_profile(date_of_birth=date(1998, 5, 15)), make_date_gate_requirement()
    )

    assert result.actual == {"value": "1998-05-15"}


def test_date_gate_missing_profile_fact_contains_none_evidence():
    result = evaluate_date_gate(SimpleNamespace(), make_date_gate_requirement())

    assert result.expected == {"metric": "date_of_birth", "operator": "<=", "value": "2000-01-01"}
    assert result.actual == {"value": None}


def test_registry_dispatches_date_gate_evaluator():
    result = evaluate_requirement(
        make_profile(date_of_birth=date(1998, 5, 15)), make_date_gate_requirement()
    )

    assert result.outcome == RequirementOutcome.MET
    assert result.reason_code == "date_gate_met"


def test_date_gate_met_reason_code_and_message_are_deterministic():
    result = evaluate_date_gate(
        make_profile(date_of_birth=date(1998, 5, 15)), make_date_gate_requirement()
    )

    assert result.model_dump(mode="json") == {
        "requirement_id": None,
        "outcome": "met",
        "reason_code": "date_gate_met",
        "expected": {"metric": "date_of_birth", "operator": "<=", "value": "2000-01-01"},
        "actual": {"value": "1998-05-15"},
        "message": "Profile satisfies the date gate requirement.",
    }


def test_date_gate_not_met_reason_code_and_message_are_deterministic():
    result = evaluate_date_gate(
        make_profile(date_of_birth=date(2001, 3, 1)), make_date_gate_requirement()
    )

    assert result.model_dump(mode="json") == {
        "requirement_id": None,
        "outcome": "not_met",
        "reason_code": "date_gate_not_met",
        "expected": {"metric": "date_of_birth", "operator": "<=", "value": "2000-01-01"},
        "actual": {"value": "2001-03-01"},
        "message": "Profile does not satisfy the date gate requirement.",
    }


def test_orchestrated_date_gate_result_contains_requirement_id():
    requirement = make_orchestration_requirement(
        kind="date_gate",
        params={"metric": "date_of_birth", "operator": "<=", "value": "2000-01-01"},
    )

    result = evaluate_requirements(
        make_profile(date_of_birth=date(1998, 5, 15)), [requirement]
    )

    assert result.requirement_results[0].requirement_id == requirement.id
    assert result.requirement_results[0].reason_code == "date_gate_met"


def test_date_gate_participates_in_opportunity_rollup():
    result = evaluate_requirements(
        make_profile(is_currently_enrolled=True, date_of_birth=date(1998, 5, 15)),
        [
            make_orchestration_requirement(),
            make_orchestration_requirement(
                order_index=1,
                kind="date_gate",
                params={"metric": "date_of_birth", "operator": "<=", "value": "2000-01-01"},
            ),
        ],
    )

    assert result.status == OpportunityMatchStatus.ELIGIBLE
    assert [item.reason_code for item in result.requirement_results] == [
        "boolean_flag_matches",
        "date_gate_met",
    ]


def test_date_gate_not_met_mandatory_requirement_keeps_rollup_not_eligible():
    result = evaluate_requirements(
        make_profile(date_of_birth=date(2001, 3, 1)),
        [
            make_orchestration_requirement(
                kind="date_gate",
                params={"metric": "date_of_birth", "operator": "<=", "value": "2000-01-01"},
            ),
        ],
    )

    assert result.status == OpportunityMatchStatus.NOT_ELIGIBLE


def test_repeated_date_gate_evaluation_is_deterministic():
    requirement = make_date_gate_requirement()
    profile = make_profile(date_of_birth=date(1998, 5, 15))

    first = evaluate_date_gate(profile, requirement)
    second = evaluate_date_gate(profile, requirement)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
