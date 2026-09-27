"""Pydantic schemas for a persisted Profile x Opportunity match.

The response mirrors the persisted ``matches`` + ``match_requirements``
rows so the frontend can render an explanation UI from one request: the
aggregate facts live on ``Match``, the per-requirement evidence on each
``MatchRequirement``, and the ``requirement`` sub-object carries the
requirement metadata (label, kind, category, source quote) that would
otherwise need one extra lookup per row.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    MatchOutcome,
    MatchStatus,
    RequirementCategory,
    RequirementKind,
)


class MatchFacts(BaseModel):
    """Aggregate outcome counts stored on the ``matches`` row."""

    total: int
    met: int
    not_met: int
    unknown: int
    needs_review: int


class RequirementSummary(BaseModel):
    """Requirement metadata embedded in each requirement result."""

    model_config = ConfigDict(from_attributes=True)

    label: str
    kind: RequirementKind
    category: RequirementCategory
    is_mandatory: bool
    source_id: uuid.UUID | None
    source_quote: str | None


class MatchRequirementRead(BaseModel):
    """Persisted evidence for one requirement inside a Match."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    requirement_id: uuid.UUID
    outcome: MatchOutcome
    reason_code: str
    expected: dict[str, Any]
    actual: dict[str, Any]
    message: str
    requirement: RequirementSummary


class MatchRead(BaseModel):
    """A persisted evaluation of one profile against one opportunity."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    profile_id: uuid.UUID
    opportunity_id: uuid.UUID
    status: MatchStatus
    engine_version: str
    evaluated_at: datetime
    facts: MatchFacts
    #: The persisted ``match_requirements`` rows, in their domain order.
    requirements: list[MatchRequirementRead] = Field(
        default_factory=list, validation_alias="requirement_results"
    )


__all__ = ["MatchFacts", "MatchRead", "MatchRequirementRead", "RequirementSummary"]
