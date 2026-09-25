"""Evaluator for exact equality against the profile degree level."""
from __future__ import annotations

from typing import Any

from app.services.matching.result import RequirementOutcome, RequirementResult

SUPPORTED_METRIC = "degree_level"
SUPPORTED_OPERATOR = "=="


def _needs_review(reason_code: str, expected: dict[str, Any], message: str) -> RequirementResult:
    return RequirementResult(
        outcome=RequirementOutcome.NEEDS_REVIEW,
        reason_code=reason_code,
        expected=expected,
        actual={},
        message=message,
    )


def evaluate_equality(profile: Any, requirement: Any) -> RequirementResult:
    """Evaluate exact equality on the one supported profile degree level fact."""
    if getattr(requirement, "is_ambiguous", False):
        return _needs_review(
            "ambiguous_requirement",
            {},
            "Requirement is ambiguous and needs review.",
        )

    params = getattr(requirement, "params", {})
    if not isinstance(params, dict):
        return _needs_review(
            "invalid_equality_value",
            {},
            "Equality parameters need review.",
        )

    metric = params.get("metric")
    operator = params.get("operator")
    value = params.get("value")
    expected = {"metric": metric, "operator": operator, "value": value}

    if metric != SUPPORTED_METRIC:
        return _needs_review(
            "unsupported_equality_metric",
            expected,
            f"Equality metric '{metric}' is not supported.",
        )
    if operator != SUPPORTED_OPERATOR:
        return _needs_review(
            "unsupported_equality_operator",
            expected,
            f"Equality operator '{operator}' is not supported.",
        )
    if value is None or not isinstance(value, (str, int, float, bool)):
        return _needs_review(
            "invalid_equality_value",
            expected,
            "Equality parameters need review.",
        )

    actual_value = getattr(profile, SUPPORTED_METRIC, None)
    actual = {"value": actual_value}
    if actual_value is None:
        return RequirementResult(
            outcome=RequirementOutcome.UNKNOWN,
            reason_code="profile_fact_unavailable",
            expected=expected,
            actual=actual,
            message="Profile does not contain the required fact.",
        )

    if actual_value == value:
        return RequirementResult(
            outcome=RequirementOutcome.MET,
            reason_code="equality_matches",
            expected=expected,
            actual=actual,
            message="Profile satisfies the equality requirement.",
        )

    return RequirementResult(
        outcome=RequirementOutcome.NOT_MET,
        reason_code="equality_does_not_match",
        expected=expected,
        actual=actual,
        message="Profile does not satisfy the equality requirement.",
    )
