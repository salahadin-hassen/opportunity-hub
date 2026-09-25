"""Deterministic requirement evaluation services."""

from app.services.matching.registry import evaluate_requirement
from app.services.matching.result import RequirementOutcome, RequirementResult

__all__ = ["RequirementOutcome", "RequirementResult", "evaluate_requirement"]