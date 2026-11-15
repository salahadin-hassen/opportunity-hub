"""Evaluator for numeric thresholds backed by primary education GPA.

GPA comparison strategy: a threshold is only meaningful on the grading scale
it was published on, so a rule must declare ``params.scale`` and the
profile's primary education must report its GPA on that same scale. Scales
are never converted — a 3.5/4.0 and an 8.75/10 are not interchangeable
across institutions — so a missing threshold scale or a scale mismatch is
sent to human review rather than guessed. A missing GPA stays ``unknown``,
which the profile owner can resolve by adding it.
"""
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
    scale = params.get("scale")
    expected = {"metric": metric, "operator": operator, "value": value, "scale": scale}

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

    threshold_scale = _decimal_or_none(scale)
    if threshold_scale is None or threshold_scale <= 0:
        return _needs_review(
            "gpa_threshold_scale_unspecified",
            expected,
            "The GPA threshold does not state its grading scale, so it cannot be compared.",
        )

    education_records = getattr(profile, "education", None)
    primary_education = next(
        (education for education in (education_records or []) if getattr(education, "is_primary", False)),
        None,
    )
    actual_gpa = getattr(primary_education, "gpa", None)
    actual_scale = getattr(primary_education, "gpa_scale", None)
    actual = {
        "value": float(actual_gpa) if actual_gpa is not None else None,
        "scale": float(actual_scale) if actual_scale is not None else None,
    }
    if actual_gpa is None:
        return RequirementResult(
            outcome=RequirementOutcome.UNKNOWN,
            reason_code="profile_fact_unavailable",
            expected=expected,
            actual=actual,
            message="Profile does not contain a primary education GPA.",
        )

    if actual_scale is None or Decimal(str(actual_scale)) != threshold_scale:
        return RequirementResult(
            outcome=RequirementOutcome.NEEDS_REVIEW,
            reason_code="gpa_scale_mismatch",
            expected=expected,
            actual=actual,
            message="Profile GPA is on a different grading scale than the threshold.",
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


def _decimal_or_none(value: Any) -> Decimal | None:
    """Parse a finite numeric parameter, treating anything else as absent."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None
