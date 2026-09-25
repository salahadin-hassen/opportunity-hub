"""Evaluator for boolean profile facts."""
from __future__ import annotations

from typing import Any

from app.services.matching.result import RequirementOutcome, RequirementResult

SUPPORTED_METRIC = "is_currently_enrolled"


def evaluate_boolean_flag(profile: Any, requirement: Any) -> RequirementResult:
    """Evaluate the supported boolean profile fact without guessing missing data."""
    if getattr(requirement, "is_ambiguous", False):
        return RequirementResult(
            outcome=RequirementOutcome.NEEDS_REVIEW,
            reason_code="ambiguous_requirement",
            expected={},
            actual={},
            message="Requirement is ambiguous and needs review.",
        )

    params = getattr(requirement, "params", {}) or {}
    metric = params.get("metric")
    expected = params.get("expected")
    expected_evidence = {"metric": metric, "value": expected}

    if metric != SUPPORTED_METRIC:
        return RequirementResult(
            outcome=RequirementOutcome.NEEDS_REVIEW,
            reason_code="unsupported_boolean_metric",
            expected=expected_evidence,
            actual={},
            message=f"Boolean metric '{metric}' is not supported.",
        )

    if not isinstance(expected, bool):
        return RequirementResult(
            outcome=RequirementOutcome.NEEDS_REVIEW,
            reason_code="invalid_boolean_expectation",
            expected=expected_evidence,
            actual={},
            message="Boolean requirement expectation needs review.",
        )

    actual = getattr(profile, SUPPORTED_METRIC, None)
    actual_evidence = {"value": actual}
    if actual is None:
        return RequirementResult(
            outcome=RequirementOutcome.UNKNOWN,
            reason_code="profile_fact_unavailable",
            expected=expected_evidence,
            actual=actual_evidence,
            message="Profile does not contain the required fact.",
        )

    if actual == expected:
        return RequirementResult(
            outcome=RequirementOutcome.MET,
            reason_code="boolean_flag_matches",
            expected=expected_evidence,
            actual=actual_evidence,
            message="Profile satisfies the requirement.",
        )

    return RequirementResult(
        outcome=RequirementOutcome.NOT_MET,
        reason_code="boolean_flag_does_not_match",
        expected=expected_evidence,
        actual=actual_evidence,
        message="Profile does not satisfy the requirement.",
    )