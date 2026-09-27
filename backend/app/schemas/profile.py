"""Pydantic schemas for profiles."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import DegreeLevel


class ProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    date_of_birth: date | None = None
    citizenships: list[str] = Field(default_factory=list)
    country_of_residence: str | None = Field(default=None, min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")
    degree_level: DegreeLevel
    is_currently_enrolled: bool = False
    languages: list[str] = Field(default_factory=list)
    links: dict[str, str] = Field(default_factory=dict)
    interests: list[str] = Field(default_factory=list)
    bio: str | None = None

    @field_validator("date_of_birth")
    @classmethod
    def date_of_birth_not_future(cls, value: date | None) -> date | None:
        if value and value > datetime.now(timezone.utc).date():
            raise ValueError("date_of_birth cannot be in the future")
        return value


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: EmailStr
    date_of_birth: date | None
    citizenships: list[str]
    country_of_residence: str | None
    degree_level: DegreeLevel
    is_currently_enrolled: bool
    languages: list[str]
    links: dict[str, str]
    interests: list[str]
    bio: str | None
    created_at: datetime
    updated_at: datetime


class ProfileUpdate(BaseModel):
    """Partial update for one owned profile.

    Non-nullable columns declare a ``None`` default they can never receive:
    an omitted field keeps its stored value (it is not in ``model_fields_set``
    and therefore never applied), while an explicit ``null`` on such a field
    fails validation with a 422 instead of reaching the database. Nullable
    columns accept ``null`` to clear the value. Server-managed fields
    (``id``, ``user_id``, timestamps) are absent and rejected as unknown.
    """

    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(default=None, min_length=1, max_length=255)
    email: EmailStr = Field(default=None)
    date_of_birth: date | None = None
    citizenships: list[str] = Field(default=None)
    country_of_residence: str | None = Field(default=None, min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")
    degree_level: DegreeLevel = Field(default=None)
    is_currently_enrolled: bool = Field(default=None)
    languages: list[str] = Field(default=None)
    links: dict[str, str] = Field(default=None)
    interests: list[str] = Field(default=None)
    bio: str | None = None

    @field_validator("date_of_birth")
    @classmethod
    def date_of_birth_not_future(cls, value: date | None) -> date | None:
        if value and value > datetime.now(timezone.utc).date():
            raise ValueError("date_of_birth cannot be in the future")
        return value


__all__ = ["ProfileCreate", "ProfileRead", "ProfileUpdate"]
