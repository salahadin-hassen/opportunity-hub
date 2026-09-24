"""Education history attached to a profile."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import DegreeLevel, enum_check_constraint

if TYPE_CHECKING:
    from app.models.profile import Profile


class Education(Base):
    """A profile's education record, including GPA on its reported scale."""

    __tablename__ = "education"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    institution_name: Mapped[str] = mapped_column(String(255), nullable=False)
    degree_level: Mapped[str] = mapped_column(String(32), nullable=False)
    field_of_study: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(nullable=False, default=False, server_default=text("false"))
    gpa: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    gpa_scale: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    is_primary: Mapped[bool] = mapped_column(nullable=False, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    profile: Mapped[Profile] = relationship(back_populates="education")

    __table_args__ = (
        enum_check_constraint("education", "degree_level", DegreeLevel),
        CheckConstraint("(gpa IS NULL) = (gpa_scale IS NULL)", name="ck_education_gpa_scale_pair"),
        CheckConstraint("gpa IS NULL OR gpa >= 0", name="ck_education_gpa_nonnegative"),
        CheckConstraint("gpa_scale IS NULL OR gpa_scale IN (4, 5, 10, 100)", name="ck_education_gpa_scale_supported"),
        CheckConstraint("gpa IS NULL OR gpa <= gpa_scale", name="ck_education_gpa_within_scale"),
        CheckConstraint("start_date IS NULL OR end_date IS NULL OR end_date >= start_date", name="ck_education_date_range"),
        Index("ix_education_profile_id", "profile_id"),
        Index("uq_education_primary_per_profile", "profile_id", unique=True, postgresql_where=text("is_primary")),
    )

    def __repr__(self) -> str:
        return f"<Education {self.institution_name!r} ({self.degree_level})>"
