"""Evaluator for ``any_of`` composite requirements (logical OR).

Children are inline ``kind`` + ``params`` pairs, so they are evaluated
through the shared registry dispatch instead of calling primitive
evaluators directly.

Outcome policy for the OR:

* ``met`` wins immediately — one satisfied alternative is enough.
* otherwise ``unknown`` outranks ``needs_review`` — while any branch is
  missing data we cannot claim every alternative fails, and an
  unexamined branch may still succeed.
* otherwise ``needs_review`` outranks ``not_met`` — unresolved children
  must stay visible.
* ``not_met`` only when every child is known to fail.

Nested ``any_of`` children are allowed by the schema; evaluation stops
requesting review beyond ``MAX_ANY_OF_DEPTH`` so the dispatcher stays
bounded. Cycles are impossible because children are inline JSON.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.services.matching.result import RequirementOutcome, RequirementResult

#: Logical operator implemented by this composite.
SUPPORTED_OPERATOR = "any_of"

#: Maximum ``any_of`` nesting depth before requesting review.
MAX_ANY_OF_DEPTH = 5

_REASON_CODES: dict[RequirementOutcome, str] = {
    RequirementOutcome.MET: "any_of_met",
    RequirementOutcome.NOT_MET: "any_of_not_met",
    RequirementOutcome.UNKNOWN: "any_of_unknown",
    RequirementOutcome.NEEDS_REVIEW: "any_of_needs_review",
}

_MESSAGES: dict[RequirementOutcome, str] = {
    RequirementOutcome.MET: "Profile satisfies at least one alternative.",
    RequirementOutcome.NOT_MET: "Profile satisfies none of the alternatives.",
    RequirementOutcome.UNKNOWN: "At least one alternative could not be evaluated.",
    RequirementOutcome.NEEDS_REVIEW: "At least one alternative needs review.",
}


def _needs_review(reason_code: str, expected: dict[str, Any], message: str) -> RequirementResult:
    return RequirementResult(
        outcome=RequirementOutcome.NEEDS_REVIEW,
        reason_code=reason_code,
        expected=expected,
        actual={},
        message=message,
    )


def _is_malformed(children: Any) -> bool:
    """Return whether the ``any_of`` child list cannot be evaluated as stored."""
    if not isinstance(children, list) or not children:
        return True
    for child in children:
        if not isinstance(child, dict) or not isinstance(child.get("params", {}), dict):
            return True
    return False


def _as_requirement(child: dict[str, Any], depth: int) -> SimpleNamespace:
    """Wrap one inline child condition for registry dispatch.

    Children are not persisted ``Requirement`` rows, so they carry no id.
    """
    return SimpleNamespace(
        kind=child.get("kind"),
        params=child.get("params", {}),
        is_ambiguous=bool(child.get("is_ambiguous", False)),
        any_of_depth=depth,
    )


def _combine(child_outcomes: list[RequirementOutcome]) -> RequirementOutcome:
    """Combine child outcomes for a logical OR (see module docstring)."""
    if RequirementOutcome.MET in child_outcomes:
        return RequirementOutcome.MET
    if RequirementOutcome.UNKNOWN in child_outcomes:
        return RequirementOutcome.UNKNOWN
    if RequirementOutcome.NEEDS_REVIEW in child_outcomes:
        return RequirementOutcome.NEEDS_REVIEW
    return RequirementOutcome.NOT_MET


def evaluate_any_of(profile: Any, requirement: Any) -> RequirementResult:
    """Evaluate ``any_of`` as a deterministic OR over dispatched children."""
    # Deferred import: the registry imports this module, so the dispatcher
    # is resolved at call time instead of module load time.
    from app.services.matching.registry import evaluate_requirement

    if getattr(requirement, "is_ambiguous", False):
        return _needs_review(
            "ambiguous_requirement",
            {},
            "Requirement is ambiguous and needs review.",
        )

    params = getattr(requirement, "params", {})
    if not isinstance(params, dict):
        return _needs_review(
            "invalid_any_of",
            {},
            "Any of parameters need review.",
        )

    children = params.get("any_of")
    expected = {"operator": SUPPORTED_OPERATOR, "children": children}
    if _is_malformed(children):
        return _needs_review(
            "invalid_any_of",
            expected,
            "Any of parameters need review.",
        )

    depth = getattr(requirement, "any_of_depth", 1)
    if depth > MAX_ANY_OF_DEPTH:
        return _needs_review(
            "any_of_depth_exceeded",
            expected,
            "Any of nesting depth is not supported.",
        )

    child_results = [
        evaluate_requirement(profile, _as_requirement(child, depth + 1))
        for child in children
    ]
    actual = {
        "children": [
            {
                "kind": child.get("kind"),
                "outcome": child_result.outcome,
                "reason_code": child_result.reason_code,
                "expected": child_result.expected,
                "actual": child_result.actual,
                "message": child_result.message,
            }
            for child, child_result in zip(children, child_results)
        ]
    }

    outcome = _combine([child_result.outcome for child_result in child_results])
    return RequirementResult(
        outcome=outcome,
        reason_code=_REASON_CODES[outcome],
        expected=expected,
        actual=actual,
        message=_MESSAGES[outcome],
    )
