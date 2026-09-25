"""Result contract for deterministic requirement evaluation."""
from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class RequirementOutcome(StrEnum):
    """Possible outcomes for one requirement evaluation."""

    MET = "met"
    NOT_MET = "not_met"
    UNKNOWN = "unknown"
    NEEDS_REVIEW = "needs_review"


class RequirementResult(BaseModel):
    """Deterministic, serializable evidence for one evaluation."""

    model_config = ConfigDict(extra="forbid")

    outcome: RequirementOutcome
    reason_code: str
    expected: dict[str, Any]
    actual: dict[str, Any]
    message: str