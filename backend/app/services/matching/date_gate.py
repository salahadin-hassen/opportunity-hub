"""Evaluator for a date gate on the profile date of birth."""
from __future__ import annotations

import operator as op
from datetime import date, datetime
from typing import Any, Callable

from app.services.matching.result import RequirementOutcome, RequirementResult

SUPPORTED_METRIC = "date_of_birth"
#: Every comparison the requirement schema allows: ``date_of_birth <= D``
#: reads "born on or before D" (old enough), ``> D`` "born after D" (young enough).
OPERATORS: dict[str, Callable[[date, date], bool]] = {
    "<=": op.le,
    "<": op.lt,
    ">=": op.ge,
    ">": op.gt,
    "==": op.eq,
    "!=": op.ne,
}


def _needs_review(
    reason_code: str,
    expected: dict[str, Any],
    message: str,
    actual: dict[str, Any] | None = None,
) -> RequirementResult:
    return RequirementResult(
        outcome=RequirementOutcome.NEEDS_REVIEW,
        reason_code=reason_code,
        expected=expected,
        actual=actual if actual is not None else {},
        message=message,
    )


def _serialize(value: Any) -> Any:
    """Render dates in their canonical ISO representation for evidence."""
    if isinstance(value, date):
        return value.isoformat()
    return value


def _parse_expected_date(value: Any) -> date | None:
    """Accept an already-validated date or its canonical ISO form only."""
    if isinstance(value, datetime):
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.isoformat() == value else None
    return None


def evaluate_date_gate(profile: Any, requirement: Any) -> RequirementResult:
    """Compare the profile date of birth to a required date without guessing missing data."""
    if getattr(requirement, "is_ambiguous", False):
        return _needs_review(
            "ambiguous_requirement",
            {},
            "Requirement is ambiguous and needs review.",
        )

    params = getattr(requirement, "params", {})
    if not isinstance(params, dict):
        return _needs_review(
            "invalid_date_gate_value",
            {},
            "Date gate parameters need review.",
        )

    metric = params.get("metric")
    operator = params.get("operator")
    value = params.get("value")
    expected = {"metric": metric, "operator": operator, "value": _serialize(value)}

    if metric != SUPPORTED_METRIC:
        return _needs_review(
            "unsupported_date_metric",
            expected,
            f"Date metric '{metric}' is not supported.",
        )
    if operator not in OPERATORS:
        return _needs_review(
            "unsupported_date_operator",
            expected,
            f"Date operator '{operator}' is not supported.",
        )

    required_date = _parse_expected_date(value)
    if required_date is None:
        return _needs_review(
            "invalid_date_gate_value",
            expected,
            "Date gate parameters need review.",
        )

    actual_value = getattr(profile, SUPPORTED_METRIC, None)
    actual = {"value": _serialize(actual_value)}
    if actual_value is None:
        return RequirementResult(
            outcome=RequirementOutcome.UNKNOWN,
            reason_code="profile_fact_unavailable",
            expected=expected,
            actual=actual,
            message="Profile does not contain a date of birth.",
        )
    if isinstance(actual_value, datetime) or not isinstance(actual_value, date):
        return _needs_review(
            "incompatible_date_fact",
            expected,
            "Profile date fact is not comparable to the required date.",
            actual,
        )

    if OPERATORS[operator](actual_value, required_date):
        return RequirementResult(
            outcome=RequirementOutcome.MET,
            reason_code="date_gate_met",
            expected=expected,
            actual=actual,
            message="Profile satisfies the date gate requirement.",
        )

    return RequirementResult(
        outcome=RequirementOutcome.NOT_MET,
        reason_code="date_gate_not_met",
        expected=expected,
        actual=actual,
        message="Profile does not satisfy the date gate requirement.",
    )
