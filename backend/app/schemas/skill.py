"""Pydantic schemas for canonical skills."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.skill import SKILL_KEY_PATTERN


class SkillCreate(BaseModel):
    """Payload for creating a canonical skill.

    ``key`` is accepted verbatim: it must already be a lowercase slug and is
    never generated, normalized or case-folded by this schema.
    """

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=255, pattern=SKILL_KEY_PATTERN)
    name: str = Field(min_length=1, max_length=255)


class SkillRead(BaseModel):
    """A persisted skill as returned to clients."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    name: str
    created_at: datetime


class ProfileSkillCreate(BaseModel):
    """Payload for attaching one existing canonical skill to a profile.

    Only the skill identifier is accepted: the profile comes from
    authentication, and no new skill vocabulary can be created here.
    """

    model_config = ConfigDict(extra="forbid")

    skill_id: uuid.UUID


__all__ = ["ProfileSkillCreate", "SkillCreate", "SkillRead", "SKILL_KEY_PATTERN"]
