"""Request and response schemas for the curator source API and audit reads."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PublishMode, SourceStatus, TermsStatus


class ProviderRead(BaseModel):
    name: str
    aliases: list[str]


class SourceRead(BaseModel):
    """Everything a curator needs to judge a source; no secrets are stored on sources."""

    id: uuid.UUID
    name: str
    base_domain: str
    allowed_hosts: list[str]
    application_hosts: list[str]
    category: str
    authority_level: str
    provider: ProviderRead
    discovery_method: str
    connector_key: str
    connector_config: dict[str, Any]
    crawl_policy: dict[str, Any]
    robots_status: str
    robots_checked_at: datetime | None
    terms_status: str
    terms_reviewed_at: datetime | None
    terms_notes: str | None
    test_run_passed_at: datetime | None
    status: str
    publish_mode: str
    status_changed_at: datetime | None
    last_success_at: datetime | None
    last_failure_at: datetime | None
    last_error: str | None
    consecutive_failures: int
    created_at: datetime
    updated_at: datetime


class StatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: SourceStatus
    reason: str | None = Field(default=None, max_length=1000)


class PublishModeChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: PublishMode
    reason: str | None = Field(default=None, max_length=1000)


class TermsReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TermsStatus
    notes: str | None = Field(default=None, max_length=5000)


class AuditEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occurred_at: datetime
    actor_kind: str
    actor_user_id: uuid.UUID | None
    action: str
    target_type: str
    target_id: str
    reason: str | None
    changes: dict[str, Any]


__all__ = ["AuditEntryRead", "ProviderRead", "PublishModeChange", "SourceRead", "StatusChange", "TermsReview"]
