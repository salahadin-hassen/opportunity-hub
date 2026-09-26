"""Small dispatcher for supported deterministic requirement evaluators."""
from __future__ import annotations

from typing import Any, Callable

from app.services.matching.boolean_flag import evaluate_boolean_flag
from app.services.matching.date_gate import evaluate_date_gate
from app.services.matching.equality import evaluate_equality
from app.services.matching.numeric_threshold import evaluate_numeric_threshold
from app.services.matching.set_membership import evaluate_set_membership
from app.services.matching.skill_set import evaluate_skill_set
from app.services.matching.result import RequirementOutcome, RequirementResult

Evaluator = Callable[[Any, Any], RequirementResult]

EVALUATORS: dict[str, Evaluator] = {
    "boolean_flag": evaluate_boolean_flag,
    "numeric_threshold": evaluate_numeric_threshold,
    "set_membership": evaluate_set_membership,
    "equality": evaluate_equality,
    "date_gate": evaluate_date_gate,
    "skill_set": evaluate_skill_set,
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