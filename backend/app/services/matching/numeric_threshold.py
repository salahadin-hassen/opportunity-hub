"""Evaluator for numeric thresholds backed by primary education GPA."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.matching.result import RequirementOutcome, RequirementResult

SUPPORTED_METRIC = "gpa"
SUPPORTED_OPERATOR = ">="


def _needs_review(reason_code: str, expected: dict[str, Any], message: str) -> RequirementResult:
    return RequirementResult(
        outcome=RequirementOutcome.NEEDS_REVIEW,
        reason_code=reason_code,
        expected=expected,
        actual={},
        message=message,
    )


def evaluate_numeric_threshold(profile: Any, requirement: Any) -> RequirementResult:
    """Evaluate a GPA threshold using the profile's primary education record."""
    if getattr(requirement, "is_ambiguous", False):
        return _needs_review(
            "ambiguous_requirement",
            {},
            "Requirement is ambiguous and needs review.",
        )

    params = getattr(requirement, "params", {})
    if not isinstance(params, dict):
        return _needs_review(
            "invalid_numeric_threshold",
            {},
            "Numeric threshold parameters need review.",
        )

    metric = params.get("metric")
    operator = params.get("operator")
    value = params.get("value")
    expected = {"metric": metric, "operator": operator, "value": value}

    if metric != SUPPORTED_METRIC:
        return _needs_review(
            "unsupported_numeric_metric",
            expected,
            f"Numeric metric '{metric}' is not supported.",
        )
    if operator != SUPPORTED_OPERATOR:
        return _needs_review(
            "unsupported_numeric_operator",
            expected,
            f"Numeric operator '{operator}' is not supported.",
        )
    if isinstance(value, bool) or value is None:
        return _needs_review(
            "invalid_numeric_threshold",
            expected,
            "Numeric threshold parameters need review.",
        )

    try:
        threshold = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return _needs_review(
            "invalid_numeric_threshold",
            expected,
            "Numeric threshold parameters need review.",
        )
    if not threshold.is_finite():
        return _needs_review(
            "invalid_numeric_threshold",
            expected,
            "Numeric threshold parameters need review.",
        )

    education_records = getattr(profile, "education", None)
    primary_education = next(
        (education for education in (education_records or []) if getattr(education, "is_primary", False)),
        None,
    )
    actual_gpa = getattr(primary_education, "gpa", None)
    actual = {"value": float(actual_gpa) if actual_gpa is not None else None}
    if actual_gpa is None:
        return RequirementResult(
            outcome=RequirementOutcome.UNKNOWN,
            reason_code="profile_fact_unavailable",
            expected=expected,
            actual=actual,
            message="Profile does not contain a primary education GPA.",
        )

    actual_decimal = Decimal(str(actual_gpa))
    if actual_decimal >= threshold:
        return RequirementResult(
            outcome=RequirementOutcome.MET,
            reason_code="numeric_threshold_met",
            expected=expected,
            actual=actual,
            message="Profile satisfies the numeric threshold requirement.",
        )

    return RequirementResult(
        outcome=RequirementOutcome.NOT_MET,
        reason_code="numeric_threshold_not_met",
        expected=expected,
        actual=actual,
        message="Profile does not satisfy the numeric threshold requirement.",
    )