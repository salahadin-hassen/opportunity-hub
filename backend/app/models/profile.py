"""Canonical student profile used by future matching."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Index, String, Text, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import DegreeLevel, enum_check_constraint

if TYPE_CHECKING:
    from app.models.education import Education
    from app.models.match import Match
    from app.models.profile_skill import ProfileSkill
    from app.models.skill import Skill
    from app.models.test_score import TestScore


class Profile(Base):
    """Matchable person profile; education-specific GPA lives on Education."""

    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    citizenships: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    country_of_residence: Mapped[str | None] = mapped_column(String(2), nullable=True)
    degree_level: Mapped[str] = mapped_column(String(32), nullable=False)
    is_currently_enrolled: Mapped[bool] = mapped_column(nullable=False, default=False, server_default=text("false"))
    languages: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    links: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    interests: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    education: Mapped[list[Education]] = relationship(back_populates="profile", cascade="all, delete-orphan", passive_deletes=True, order_by="Education.created_at")
    test_scores: Mapped[list[TestScore]] = relationship(back_populates="profile", cascade="all, delete-orphan", passive_deletes=True, order_by="TestScore.test_date.desc()")
    profile_skills: Mapped[list[ProfileSkill]] = relationship(
        back_populates="profile",
        order_by="ProfileSkill.created_at",
        viewonly=True,
    )
    skills: Mapped[list[Skill]] = relationship(
        secondary="profile_skills",
        back_populates="profiles",
        overlaps="profiles,profile,skill",
    )
    matches: Mapped[list[Match]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        enum_check_constraint("profiles", "degree_level", DegreeLevel),
        Index("ix_profiles_country_of_residence", "country_of_residence"),
        Index("ix_profiles_degree_level", "degree_level"),
    )

    def __repr__(self) -> str:
        return f"<Profile {self.email!r}>"
