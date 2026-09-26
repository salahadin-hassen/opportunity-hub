"""Persisted evaluation of one profile against one opportunity."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import MatchStatus, enum_check_constraint

if TYPE_CHECKING:
    from app.models.match_requirement import MatchRequirement
    from app.models.opportunity import Opportunity
    from app.models.profile import Profile


class Match(Base):
    """The current verdict of one Profile x Opportunity evaluation.

    Exactly one Match may exist per pair, so re-evaluating updates this
    row instead of appending history. ``facts`` carries aggregate counts
    only; the normalized ``match_requirements`` rows remain the source of
    detailed evidence.
    """

    __tablename__ = "matches"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(16), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    facts: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    profile: Mapped[Profile] = relationship(back_populates="matches")
    opportunity: Mapped[Opportunity] = relationship(back_populates="matches")
    requirement_results: Mapped[list[MatchRequirement]] = relationship(
        back_populates="match",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        enum_check_constraint("matches", "status", MatchStatus),
        UniqueConstraint(
            "profile_id",
            "opportunity_id",
            name="uq_matches_profile_opportunity",
        ),
        Index("ix_matches_opportunity_id", "opportunity_id"),
    )

    def __repr__(self) -> str:
        return f"<Match {self.status} profile={self.profile_id} opportunity={self.opportunity_id}>"
