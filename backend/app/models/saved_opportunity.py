"""Saved / bookmarked opportunities for applicants (plan §C.2, M3)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.opportunity import Opportunity
    from app.models.profile import Profile


class SavedOpportunity(Base):
    """An opportunity pinned/bookmarked by an applicant profile."""

    __tablename__ = "saved_opportunities"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        primary_key=True,
    )
    confirmations: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    reminders_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    profile: Mapped[Profile] = relationship()
    opportunity: Mapped[Opportunity] = relationship()

    __table_args__ = (
        Index("ix_saved_opportunities_profile_created", "profile_id", "created_at"),
    )

