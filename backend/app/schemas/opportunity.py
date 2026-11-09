"""Pydantic schemas for Opportunity."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_serializer, model_validator

from app.models.enums import (
    DeadlineType,
    LocationMode,
    OpportunityStatus,
    OpportunityType,
    RequirementCategory,
    RequirementKind,
    SourceType,
)


class OpportunityCreate(BaseModel):
    """Payload for creating an opportunity."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, max_length=255, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=1, max_length=500)
    opportunity_type: OpportunityType = OpportunityType.OTHER
    description: str | None = None
    host_name: str | None = Field(default=None, max_length=255)
    official_url: HttpUrl | None = Field(default=None, max_length=2000)
    deadline_at: datetime | None = None
    deadline_type: DeadlineType = DeadlineType.FIXED
    starts_at: date | None = None
    ends_at: date | None = None
    location_mode: LocationMode = LocationMode.UNKNOWN
    countries: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    status: OpportunityStatus = OpportunityStatus.DRAFT
    published_at: datetime | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> OpportunityCreate:
        if self.starts_at and self.ends_at and self.ends_at < self.starts_at:
            raise ValueError("ends_at must be on or after starts_at")
        return self

    @field_serializer("official_url")
    def serialize_official_url(self, value: HttpUrl | None) -> str | None:
        """Keep ORM payloads and serialized API output as plain strings."""
        return str(value) if value is not None else None


class OpportunityUpdate(BaseModel):
    """Payload for updating an opportunity (curators/admins)."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=500)
    opportunity_type: OpportunityType | None = None
    description: str | None = None
    host_name: str | None = Field(default=None, max_length=255)
    official_url: HttpUrl | None = Field(default=None, max_length=2000)
    deadline_at: datetime | None = None
    deadline_type: DeadlineType | None = None
    starts_at: date | None = None
    ends_at: date | None = None
    location_mode: LocationMode | None = None
    countries: list[str] | None = None
    languages: list[str] | None = None
    tags: list[str] | None = None
    status: OpportunityStatus | None = None

    @field_serializer("official_url")
    def serialize_official_url(self, value: HttpUrl | None) -> str | None:
        return str(value) if value is not None else None


class OpportunityRead(BaseModel):
    """A persisted opportunity as returned to clients."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    title: str
    opportunity_type: OpportunityType
    description: str | None
    host_name: str | None
    official_url: HttpUrl | None
    deadline_at: datetime | None
    deadline_type: DeadlineType
    starts_at: date | None
    ends_at: date | None
    location_mode: LocationMode
    countries: list[Any]
    languages: list[Any]
    tags: list[Any]
    status: OpportunityStatus
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None

    @field_serializer("official_url")
    def serialize_official_url(self, value: HttpUrl | None) -> str | None:
        return str(value) if value is not None else None


class PublicSourceRead(BaseModel):
    """Provenance a visitor can verify: where a rule came from and when.

    Curator-only fields (``raw_snapshot``, ``content_hash``, ``notes``) are
    deliberately absent.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_type: SourceType
    url: HttpUrl
    publisher: str | None
    retrieved_at: datetime
    is_primary: bool

    @field_serializer("url")
    def serialize_url(self, value: HttpUrl) -> str:
        return str(value)


class PublicRequirementRead(BaseModel):
    """One eligibility rule as published, before any profile is evaluated.

    ``kind`` + ``params`` are the rule itself, so clients can state it
    without evaluating; curator ``notes`` and timestamps are not exposed.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_index: int
    label: str
    kind: RequirementKind
    params: dict[str, Any]
    is_mandatory: bool
    category: RequirementCategory
    source_id: uuid.UUID | None
    source_quote: str | None
    is_ambiguous: bool


class OpportunityDetailRead(OpportunityRead):
    """One public opportunity with its ordered rules and their sources."""

    requirements: list[PublicRequirementRead]
    sources: list[PublicSourceRead]


__all__ = [
    "OpportunityCreate",
    "OpportunityDetailRead",
    "OpportunityRead",
    "OpportunityUpdate",
    "PublicRequirementRead",
    "PublicSourceRead",
]
