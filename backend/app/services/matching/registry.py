"""Small dispatcher for supported deterministic requirement evaluators."""
from __future__ import annotations

from typing import Any, Callable

from app.services.matching.boolean_flag import evaluate_boolean_flag
from app.services.matching.result import RequirementOutcome, RequirementResult

Evaluator = Callable[[Any, Any], RequirementResult]

EVALUATORS: dict[str, Evaluator] = {
    "boolean_flag": evaluate_boolean_flag,
}


def evaluate_requirement(profile: Any, requirement: Any) -> RequirementResult:
    """Dispatch a requirement to its evaluator or request manual review."""
    kind = getattr(requirement, "kind", None)
    evaluator = EVALUATORS.get(kind)
    if evaluator is None:
        return RequirementResult(
            outcome=RequirementOutcome.NEEDS_REVIEW,
            reason_code="unsupported_requirement_kind",
            expected={"kind": kind},
            actual={},
            message=f"Requirement kind '{kind}' is not supported.",
        )
    return evaluator(profile, requirement)