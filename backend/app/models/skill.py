"""Canonical skill vocabulary shared by profiles and matching."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.profile import Profile
    from app.models.profile_skill import ProfileSkill

#: Canonical machine identity format for ``Skill.key``. The value is used
#: verbatim by both the Pydantic schemas and the database CHECK constraint;
#: nothing ever rewrites, slugs, case-folds or aliases it.
SKILL_KEY_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class Skill(Base):
    """A canonical skill whose lowercase ``key`` is its machine identity."""

    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    profiles: Mapped[list[Profile]] = relationship(
        secondary="profile_skills",
        back_populates="skills",
        overlaps="skills,profile,skill",
    )
    profile_skills: Mapped[list[ProfileSkill]] = relationship(
        back_populates="skill",
        order_by="ProfileSkill.created_at",
        viewonly=True,
    )

    __table_args__ = (
        CheckConstraint(f"key ~ '{SKILL_KEY_PATTERN}'", name="ck_skills_key_format"),
    )

    def __repr__(self) -> str:
        return f"<Skill {self.key!r}>"
