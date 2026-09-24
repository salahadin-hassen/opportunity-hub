"""Standardized and language test results attached to a profile."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.profile import Profile


class TestScore(Base):
    """One attempt at a standardized or language test."""

    __tablename__ = "test_scores"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    test_type: Mapped[str] = mapped_column(String(100), nullable=False)
    overall_score: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    sub_scores: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSONB, nullable=True)
    test_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    report_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    profile: Mapped[Profile] = relationship(back_populates="test_scores")

    __table_args__ = (
        CheckConstraint("overall_score >= 0", name="ck_test_scores_overall_score_nonnegative"),
        CheckConstraint("test_date IS NULL OR expires_at IS NULL OR expires_at >= test_date", name="ck_test_scores_date_range"),
        Index("ix_test_scores_profile_id", "profile_id"),
        Index("ix_test_scores_profile_test_type", "profile_id", "test_type"),
    )

    def __repr__(self) -> str:
        return f"<TestScore {self.test_type!r} ({self.overall_score})>"
