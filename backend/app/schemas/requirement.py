"""Pydantic schemas for Requirement, including per-kind ``params`` validation.

The database stores ``params`` as flexible JSONB; validation happens once
on write through a ``kind`` -> params-model registry so bad payloads fail
fast while already-persisted rows are always readable.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.models.enums import RequirementCategory, RequirementKind

MetricName = Annotated[str, Field(min_length=1, max_length=100)]
SkillName = Annotated[str, Field(min_length=1, max_length=100)]


class NumericThresholdParams(BaseModel):
    """Numeric comparison such as ``gpa >= 3.0`` on a ``4.0`` scale."""

    model_config = ConfigDict(extra="forbid")

    metric: MetricName
    operator: Literal[">=", "<=", ">", "<", "==", "!="]
    value: float
    scale: float | None = Field(default=None, gt=0)


class SetMembershipParams(BaseModel):
    """Value-membership test such as ``field_of_study within {engineering}``."""

    model_config = ConfigDict(extra="forbid")

    metric: MetricName
    operator: Literal["in", "not_in", "within_taxonomy"] = "in"
    allowed: list[SkillName] = Field(min_length=1)


class EqualityParams(BaseModel):
    """Exact (in)equality against a scalar value."""

    model_config = ConfigDict(extra="forbid")

    metric: MetricName
    operator: Literal["==", "!="] = "=="
    value: str | int | float | bool


class BooleanFlagParams(BaseModel):
    """Binary profile fact such as ``is_currently_enrolled == true``."""

    model_config = ConfigDict(extra="forbid")

    metric: MetricName
    expected: bool


class DateGateParams(BaseModel):
    """Date comparison such as ``application_date <= 2026-12-01``."""

    model_config = ConfigDict(extra="forbid")

    metric: MetricName
    operator: Literal["<=", "<", ">=", ">", "==", "!="]
    value: date


class SkillSetParams(BaseModel):
    """Skill vocabulary test such as ``required skills include python``."""

    model_config = ConfigDict(extra="forbid")

    metric: MetricName = "skills"
    operator: Literal["contains_any", "contains_all"] = "contains_any"
    required: list[SkillName] = Field(min_length=1)


class UnparsedParams(BaseModel):
    """Free-form payload kept for requirements that could not be structured."""

    model_config = ConfigDict(extra="allow")

    reason: str = Field(min_length=1, max_length=255)
    raw: str | None = None


def _params_error_message(exc: ValidationError) -> str:
    """Render a nested ValidationError as one concise, single-line message."""
    parts = [
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
        for error in exc.errors()
    ]
    return " | ".join(parts) if parts else str(exc)


def validate_params_for_kind(kind: RequirementKind, params: dict[str, Any]) -> dict[str, Any]:
    """Validate ``params`` against the model registered for ``kind``.

    Returns the normalized payload (JSON-safe values) or raises
    ``ValueError`` with one message per failing field.
    """
    params_model = PARAMS_MODELS[kind]
    try:
        validated = params_model.model_validate(params)
    except ValidationError as exc:
        raise ValueError(_params_error_message(exc)) from exc
    return validated.model_dump(mode="json", exclude_none=True)


class RequirementCondition(BaseModel):
    """A validated ``kind`` + ``params`` pair (also used inside ``any_of``)."""

    model_config = ConfigDict(extra="forbid")

    kind: RequirementKind
    params: dict[str, Any]

    @model_validator(mode="after")
    def validate_params(self) -> RequirementCondition:
        self.params = validate_params_for_kind(self.kind, self.params)
        return self


class AnyOfParams(BaseModel):
    """Disjunction: satisfied when at least one child condition holds."""

    model_config = ConfigDict(extra="forbid")

    any_of: list[RequirementCondition] = Field(min_length=1)


PARAMS_MODELS: dict[RequirementKind, type[BaseModel]] = {
    RequirementKind.NUMERIC_THRESHOLD: NumericThresholdParams,
    RequirementKind.SET_MEMBERSHIP: SetMembershipParams,
    RequirementKind.EQUALITY: EqualityParams,
    RequirementKind.BOOLEAN_FLAG: BooleanFlagParams,
    RequirementKind.DATE_GATE: DateGateParams,
    RequirementKind.SKILL_SET: SkillSetParams,
    RequirementKind.ANY_OF: AnyOfParams,
    RequirementKind.UNPARSED: UnparsedParams,
}


class RequirementCreate(BaseModel):
    """Payload for creating one requirement under an opportunity."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=500)
    kind: RequirementKind
    params: dict[str, Any]
    order_index: int = Field(default=0, ge=0)
    is_mandatory: bool = True
    category: RequirementCategory = RequirementCategory.OTHER
    source_id: uuid.UUID | None = None
    source_quote: str | None = None
    is_ambiguous: bool = False
    notes: str | None = None

    @model_validator(mode="after")
    def validate_condition(self) -> RequirementCreate:
        self.params = validate_params_for_kind(self.kind, self.params)
        return self


class RequirementRead(BaseModel):
    """A persisted requirement as returned to clients."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    opportunity_id: uuid.UUID
    order_index: int
    label: str
    kind: RequirementKind
    params: dict[str, Any]
    is_mandatory: bool
    category: RequirementCategory
    source_id: uuid.UUID | None
    source_quote: str | None
    is_ambiguous: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime


__all__ = [
    "NumericThresholdParams",
    "SetMembershipParams",
    "EqualityParams",
    "BooleanFlagParams",
    "DateGateParams",
    "SkillSetParams",
    "UnparsedParams",
    "AnyOfParams",
    "RequirementCondition",
    "RequirementCreate",
    "RequirementRead",
    "PARAMS_MODELS",
    "validate_params_for_kind",
]
