"""Pydantic schemas for OpportunitySource."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_serializer

from app.models.enums import SourceType


class SourceCreate(BaseModel):
    """Payload for creating a provenance record for an opportunity."""

    model_config = ConfigDict(extra="forbid")

    source_type: SourceType = SourceType.MANUAL_ENTRY
    url: HttpUrl = Field(max_length=2000)
    publisher: str | None = Field(default=None, max_length=255)
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    content_hash: str | None = Field(default=None, max_length=128)
    raw_snapshot: dict[str, Any] | list[Any] | str | None = None
    is_primary: bool = False
    notes: str | None = None

    @field_serializer("url")
    def serialize_url(self, value: HttpUrl) -> str:
        return str(value)


class SourceRead(BaseModel):
    """A persisted source as returned to clients."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    opportunity_id: uuid.UUID
    source_type: SourceType
    url: HttpUrl
    publisher: str | None
    retrieved_at: datetime
    content_hash: str | None
    raw_snapshot: Any
    is_primary: bool
    notes: str | None

    @field_serializer("url")
    def serialize_url(self, value: HttpUrl) -> str:
        return str(value)


__all__ = ["SourceCreate", "SourceRead"]
