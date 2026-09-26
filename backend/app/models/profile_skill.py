"""Association object joining a profile to a canonical skill."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.profile import Profile
    from app.models.skill import Skill


class ProfileSkill(Base):
    """One profile's membership in one skill, unique on (profile, skill)."""

    __tablename__ = "profile_skills"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    skill_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    profile: Mapped[Profile] = relationship(back_populates="profile_skills")
    skill: Mapped[Skill] = relationship(back_populates="profile_skills")

    __table_args__ = (
        UniqueConstraint("profile_id", "skill_id", name="uq_profile_skills_profile_skill"),
        Index("ix_profile_skills_profile_id", "profile_id"),
        Index("ix_profile_skills_skill_id", "skill_id"),
    )

    def __repr__(self) -> str:
        return f"<ProfileSkill profile_id={self.profile_id!r} skill_id={self.skill_id!r}>"
