"""Evaluator for exact canonical skill key coverage."""
from __future__ import annotations

from typing import Any

from app.services.matching.result import RequirementOutcome, RequirementResult

SUPPORTED_METRIC = "skills"
SUPPORTED_OPERATORS = ("contains_any", "contains_all")


def _needs_review(reason_code: str, expected: dict[str, Any], message: str) -> RequirementResult:
    return RequirementResult(
        outcome=RequirementOutcome.NEEDS_REVIEW,
        reason_code=reason_code,
        expected=expected,
        actual={},
        message=message,
    )


def _profile_fact_unavailable(expected: dict[str, Any], message: str) -> RequirementResult:
    return RequirementResult(
        outcome=RequirementOutcome.UNKNOWN,
        reason_code="profile_fact_unavailable",
        expected=expected,
        actual={"values": None},
        message=message,
    )


def _canonical_skill_keys(profile: Any) -> list[str] | None:
    """Read canonical ``Skill.key`` values from ``profile.skills``.

    Returns ``None`` when the profile-side fact is unavailable; an empty list
    is known data meaning the profile holds no skills.
    """
    skills = getattr(profile, "skills", None)
    if skills is None or isinstance(skills, (str, bytes, dict)):
        return None
    try:
        items = list(skills)
    except TypeError:
        return None

    keys = []
    for item in items:
        if isinstance(item, str):
            keys.append(item)
            continue
        key = getattr(item, "key", None)
        if not isinstance(key, str):
            return None
        keys.append(key)
    return keys


def evaluate_skill_set(profile: Any, requirement: Any) -> RequirementResult:
    """Evaluate exact canonical skill key coverage for one skill set."""
    if getattr(requirement, "is_ambiguous", False):
        return _needs_review(
            "ambiguous_requirement",
            {},
            "Requirement is ambiguous and needs review.",
        )

    params = getattr(requirement, "params", {})
    if not isinstance(params, dict):
        return _needs_review(
            "invalid_skill_set",
            {},
            "Skill set parameters need review.",
        )

    metric = params.get("metric")
    operator = params.get("operator")
    required = params.get("required")
    expected = {
        "metric": metric,
        "operator": operator,
        "required": list(required) if isinstance(required, list) else required,
    }

    if metric != SUPPORTED_METRIC:
        return _needs_review(
            "unsupported_skill_set_metric",
            expected,
            f"Skill set metric '{metric}' is not supported.",
        )
    if operator not in SUPPORTED_OPERATORS:
        return _needs_review(
            "unsupported_skill_set_operator",
            expected,
            f"Skill set operator '{operator}' is not supported.",
        )
    if (
        not isinstance(required, list)
        or not required
        or not all(isinstance(value, str) and value for value in required)
    ):
        return _needs_review(
            "invalid_skill_set",
            expected,
            "Skill set parameters need review.",
        )

    keys = _canonical_skill_keys(profile)
    if keys is None:
        return _profile_fact_unavailable(expected, "Profile skill data is unavailable.")

    actual = {"values": list(keys)}
    known_keys = set(keys)
    if operator == "contains_any":
        satisfied = any(value in known_keys for value in required)
    else:
        satisfied = all(value in known_keys for value in required)

    if satisfied:
        return RequirementResult(
            outcome=RequirementOutcome.MET,
            reason_code="skill_set_matches",
            expected=expected,
            actual=actual,
            message="Profile satisfies the skill set requirement.",
        )

    return RequirementResult(
        outcome=RequirementOutcome.NOT_MET,
        reason_code="skill_set_does_not_match",
        expected=expected,
        actual=actual,
        message="Profile does not satisfy the skill set requirement.",
    )
