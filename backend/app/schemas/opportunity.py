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


__all__ = ["OpportunityCreate", "OpportunityRead"]
