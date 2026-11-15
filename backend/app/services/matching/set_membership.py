"""Evaluator for exact (non-)membership in the profile citizenship collection."""
from __future__ import annotations

from typing import Any

from app.services.matching.result import RequirementOutcome, RequirementResult

SUPPORTED_METRIC = "citizenship"
#: ``in``: holds one required citizenship; ``not_in``: holds none of the excluded one.
SUPPORTED_OPERATORS = ("in", "not_in")


def _needs_review(reason_code: str, expected: dict[str, Any], message: str) -> RequirementResult:
    return RequirementResult(
        outcome=RequirementOutcome.NEEDS_REVIEW,
        reason_code=reason_code,
        expected=expected,
        actual={},
        message=message,
    )


def evaluate_set_membership(profile: Any, requirement: Any) -> RequirementResult:
    """Evaluate exact membership (or exclusion) of one citizenship value."""
    if getattr(requirement, "is_ambiguous", False):
        return _needs_review(
            "ambiguous_requirement",
            {},
            "Requirement is ambiguous and needs review.",
        )

    params = getattr(requirement, "params", {})
    if not isinstance(params, dict):
        return _needs_review(
            "invalid_set_membership",
            {},
            "Set membership parameters need review.",
        )

    metric = params.get("metric")
    operator = params.get("operator")
    allowed = params.get("allowed")
    required_value = allowed[0] if isinstance(allowed, list) and len(allowed) == 1 else None
    expected = {"metric": metric, "operator": operator, "value": required_value}

    if metric != SUPPORTED_METRIC:
        return _needs_review(
            "unsupported_set_metric",
            expected,
            f"Set membership metric '{metric}' is not supported.",
        )
    if operator not in SUPPORTED_OPERATORS:
        return _needs_review(
            "unsupported_set_operator",
            expected,
            f"Set membership operator '{operator}' is not supported.",
        )
    if not isinstance(allowed, list) or len(allowed) != 1 or not isinstance(required_value, str) or not required_value:
        return _needs_review(
            "invalid_set_membership",
            expected,
            "Set membership parameters need review.",
        )

    citizenships = getattr(profile, "citizenships", None)
    if citizenships is None:
        return RequirementResult(
            outcome=RequirementOutcome.UNKNOWN,
            reason_code="profile_fact_unavailable",
            expected=expected,
            actual={},
            message="Profile does not contain citizenship data.",
        )
    if not isinstance(citizenships, list) or not all(isinstance(value, str) for value in citizenships):
        return RequirementResult(
            outcome=RequirementOutcome.UNKNOWN,
            reason_code="profile_fact_unavailable",
            expected=expected,
            actual={},
            message="Profile citizenship data is unavailable.",
        )

    actual = {"values": list(citizenships)}
    if (required_value in citizenships) == (operator == "in"):
        return RequirementResult(
            outcome=RequirementOutcome.MET,
            reason_code="set_membership_matches",
            expected=expected,
            actual=actual,
            message="Profile satisfies the set membership requirement.",
        )

    return RequirementResult(
        outcome=RequirementOutcome.NOT_MET,
        reason_code="set_membership_does_not_match",
        expected=expected,
        actual=actual,
        message="Profile does not satisfy the set membership requirement.",
    )