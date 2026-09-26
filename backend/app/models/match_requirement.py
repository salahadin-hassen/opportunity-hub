"""Persisted evidence for one requirement inside a Match."""
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
from app.models.enums import MatchOutcome, enum_check_constraint

if TYPE_CHECKING:
    from app.models.match import Match
    from app.models.requirement import Requirement


class MatchRequirement(Base):
    """Evidence for exactly one requirement within one Match.

    ``requirement_id`` is deliberately RESTRICTed rather than cascaded:
    requirements disappear only together with their opportunity (which
    already deletes the whole Match), so evidence for a surviving Match
    may never be silently deleted or unlinked from its requirement.
    """

    __tablename__ = "match_requirements"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("matches.id", ondelete="CASCADE"),
        nullable=False,
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("requirements.id", ondelete="RESTRICT"),
        nullable=False,
    )
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    expected: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    actual: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    match: Mapped[Match] = relationship(back_populates="requirement_results")
    requirement: Mapped[Requirement] = relationship()

    __table_args__ = (
        enum_check_constraint("match_requirements", "outcome", MatchOutcome),
        UniqueConstraint(
            "match_id",
            "requirement_id",
            name="uq_match_requirements_match_requirement",
        ),
        Index("ix_match_requirements_match_id", "match_id"),
        Index("ix_match_requirements_requirement_id", "requirement_id"),
    )

    def __repr__(self) -> str:
        return f"<MatchRequirement {self.outcome} requirement={self.requirement_id}>"
