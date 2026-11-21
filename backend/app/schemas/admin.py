"""Schemas for the admin console (``/admin``).

Nothing here ever carries password hashes, session tokens or full client IP
addresses: the console shows who is on the platform and what they do, not the
secrets that would let anyone act as them.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.acquisition_source import AuditEntryRead


class DayCount(BaseModel):
    day: date
    count: int


class NamedCount(BaseModel):
    key: str
    count: int


class TopOpportunity(BaseModel):
    id: uuid.UUID
    title: str
    count: int


class UsersOverview(BaseModel):
    total: int
    active: int
    suspended: int
    pending_deletion: int
    verified_email: int
    with_google: int
    with_profile: int
    new_7d: int
    new_30d: int
    by_role: list[NamedCount]


class ActivityOverview(BaseModel):
    """People with session activity in each window (sessions refresh ``last_seen_at`` as they're used)."""

    active_1d: int
    active_7d: int
    active_30d: int
    open_sessions: int
    signups_30d: list[DayCount]


class EngagementOverview(BaseModel):
    eligibility_checks: int
    profiles_checked: int
    verdicts: list[NamedCount]
    saved: int
    profiles_saving: int
    applications: int
    applications_by_status: list[NamedCount]
    most_saved: list[TopOpportunity]
    most_tracked: list[TopOpportunity]


class CatalogueOverview(BaseModel):
    opportunities_by_status: list[NamedCount]
    candidates_by_state: list[NamedCount]
    sources_by_status: list[NamedCount]


class EmailOverview(BaseModel):
    by_status: list[NamedCount]
    oldest_pending: datetime | None


class SystemOverview(BaseModel):
    environment: str
    schema_revision: str | None
    database_time: datetime
    #: Whether candidates get an AI review (a GROQ_API_KEY is set), and with which model.
    ai_review: bool = False
    ai_model: str | None = None


class AdminOverview(BaseModel):
    generated_at: datetime
    users: UsersOverview
    activity: ActivityOverview
    engagement: EngagementOverview
    catalogue: CatalogueOverview
    email: EmailOverview
    system: SystemOverview


class AdminUserRow(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    role: str
    is_active: bool
    email_verified: bool
    has_password: bool
    google_linked: bool
    has_profile: bool
    created_at: datetime
    last_active_at: datetime | None
    deletion_due_at: datetime | None
    saved_count: int
    applications_count: int


class AdminUserPage(BaseModel):
    items: list[AdminUserRow]
    total: int
    limit: int
    offset: int


class AdminSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    last_seen_at: datetime | None
    expires_at: datetime
    device: str | None
    network: str | None


class AdminUserDetail(AdminUserRow):
    email_verified_at: datetime | None
    deletion_requested_at: datetime | None
    google_email: str | None
    matches_count: int
    sessions: list[AdminSessionRead]
    history: list[AuditEntryRead]


class AccountRoleChange(BaseModel):
    role: Literal["student", "curator", "admin"]
    reason: str = Field(min_length=3, max_length=500)


class AccountStatusChange(BaseModel):
    active: bool
    reason: str = Field(min_length=3, max_length=500)


class AccountActionReason(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


__all__ = [
    "ActivityOverview",
    "AdminOverview",
    "AdminSessionRead",
    "AdminUserDetail",
    "AdminUserPage",
    "AdminUserRow",
    "CatalogueOverview",
    "DayCount",
    "EmailOverview",
    "EngagementOverview",
    "NamedCount",
    "AccountActionReason",
    "AccountRoleChange",
    "AccountStatusChange",
    "SystemOverview",
    "TopOpportunity",
    "UsersOverview",
]
