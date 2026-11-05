"""Schemas for saved opportunities and application tracking (M3)."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.opportunity import OpportunityRead


class SavedOpportunityCreate(BaseModel):
    opportunity_id: uuid.UUID
    reminders_enabled: bool = True


class SavedOpportunityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    profile_id: uuid.UUID
    opportunity_id: uuid.UUID
    confirmations: dict[str, Any] = Field(default_factory=dict)
    reminders_enabled: bool = True
    created_at: datetime
    opportunity: OpportunityRead


class ApplicationItemCreate(BaseModel):
    label: str = Field(min_length=1, max_length=255)
    requirement_id: uuid.UUID | None = None
    due_date: date | None = None
    note: str | None = None
    order_index: int = 0


class ApplicationItemUpdate(BaseModel):
    status: str | None = None
    note: str | None = None
    due_date: date | None = None


class ApplicationItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    requirement_id: uuid.UUID | None = None
    label: str
    status: str
    due_date: date | None = None
    note: str | None = None
    order_index: int


class ApplicationCreate(BaseModel):
    opportunity_id: uuid.UUID
    notes: str | None = None
    target_date: date | None = None
    initial_items: list[ApplicationItemCreate] = Field(default_factory=list)


class ApplicationUpdate(BaseModel):
    status: str | None = None
    outcome: str | None = None
    notes: str | None = None
    target_date: date | None = None


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    profile_id: uuid.UUID
    opportunity_id: uuid.UUID
    status: str
    outcome: str | None = None
    notes: str | None = None
    target_date: date | None = None
    submitted_at: datetime | None = None
    outcome_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    items: list[ApplicationItemRead] = Field(default_factory=list)
    opportunity: OpportunityRead


__all__ = [
    "SavedOpportunityCreate",
    "SavedOpportunityRead",
    "ApplicationItemCreate",
    "ApplicationItemUpdate",
    "ApplicationItemRead",
    "ApplicationCreate",
    "ApplicationUpdate",
    "ApplicationRead",
]

