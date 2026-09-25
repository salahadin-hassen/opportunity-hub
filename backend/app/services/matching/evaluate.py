"""Requirement orchestration and opportunity-level verdict rollup."""
from __future__ import annotations

from enum import StrEnum
import uuid
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict

from app.services.matching.registry import evaluate_requirement
from app.services.matching.result import RequirementOutcome, RequirementResult


class OpportunityMatchStatus(StrEnum):
    """Overall status for an in-memory opportunity evaluation."""

    ELIGIBLE = "eligible"
    POTENTIAL_MATCH = "potential_match"
    NOT_ELIGIBLE = "not_eligible"
    NEEDS_REVIEW = "needs_review"


class MatchEvaluationResult(BaseModel):
    """A deterministic opportunity verdict with its individual evidence."""

    model_config = ConfigDict(extra="forbid")

    status: OpportunityMatchStatus
    requirement_results: list[RequirementResult]


def _ordered_requirements(requirements: Iterable[Any]) -> list[Any]:
    """Preserve input order, using order_index when the domain provides it."""
    items = list(requirements)
    if not items or not all(hasattr(requirement, "order_index") for requirement in items):
        return items
    return [
        requirement
        for _, requirement in sorted(
            enumerate(items), key=lambda item: (item[1].order_index, item[0])
        )
    ]


def evaluate_requirements(profile: Any, requirements: Iterable[Any]) -> MatchEvaluationResult:
    """Evaluate each requirement once and roll results into an opportunity verdict."""
    ordered_requirements = _ordered_requirements(requirements)
    evaluated = []
    for requirement in ordered_requirements:
        requirement_id = getattr(requirement, "id", None)
        if not isinstance(requirement_id, uuid.UUID):
            raise ValueError("Each requirement must have a UUID before evaluation.")
        result = evaluate_requirement(profile, requirement)
        evaluated.append(
            (requirement, result.model_copy(update={"requirement_id": requirement_id}))
        )
    requirement_results = [result for _, result in evaluated]

    if any(
        getattr(requirement, "is_mandatory", True)
        and result.outcome == RequirementOutcome.NOT_MET
        for requirement, result in evaluated
    ):
        status = OpportunityMatchStatus.NOT_ELIGIBLE
    elif any(result.outcome == RequirementOutcome.NEEDS_REVIEW for result in requirement_results):
        status = OpportunityMatchStatus.NEEDS_REVIEW
    elif any(result.outcome == RequirementOutcome.UNKNOWN for result in requirement_results):
        status = OpportunityMatchStatus.POTENTIAL_MATCH
    else:
        status = OpportunityMatchStatus.ELIGIBLE

    return MatchEvaluationResult(status=status, requirement_results=requirement_results)