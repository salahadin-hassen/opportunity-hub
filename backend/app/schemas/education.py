"""Pydantic schemas for education records."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import DegreeLevel

SUPPORTED_GPA_SCALES = (4.0, 5.0, 10.0, 100.0)


class EducationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institution_name: str = Field(min_length=1, max_length=255)
    degree_level: DegreeLevel
    field_of_study: str = Field(min_length=1, max_length=255)
    country: str | None = Field(default=None, min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool = False
    gpa: float | None = Field(default=None, ge=0)
    gpa_scale: float | None = None
    is_primary: bool = False

    @model_validator(mode="after")
    def validate_education(self) -> Self:
        if (self.gpa is None) != (self.gpa_scale is None):
            raise ValueError("gpa and gpa_scale must be provided together")
        if self.gpa_scale is not None and self.gpa_scale not in SUPPORTED_GPA_SCALES:
            raise ValueError(f"gpa_scale must be one of {SUPPORTED_GPA_SCALES}")
        if self.gpa is not None and self.gpa_scale is not None and self.gpa > self.gpa_scale:
            raise ValueError("gpa cannot exceed gpa_scale")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class EducationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    profile_id: uuid.UUID
    institution_name: str
    degree_level: DegreeLevel
    field_of_study: str
    country: str | None
    start_date: date | None
    end_date: date | None
    is_current: bool
    gpa: float | None
    gpa_scale: float | None
    is_primary: bool
    created_at: datetime


class EducationUpdate(BaseModel):
    """Partial update for one owned education record.

    Non-nullable columns declare a ``None`` default they can never receive:
    an omitted field keeps its stored value (it is not in
    ``model_fields_set`` and therefore never applied), while an explicit
    ``null`` on such a field fails validation with a 422 instead of reaching
    the database. The cross-field GPA/scale and date-range rules span the
    stored record plus the submitted fields, so they are re-checked against
    the merged state in the service — this schema only validates what the
    client actually sends.
    """

    model_config = ConfigDict(extra="forbid")

    institution_name: str = Field(default=None, min_length=1, max_length=255)
    degree_level: DegreeLevel = Field(default=None)
    field_of_study: str = Field(default=None, min_length=1, max_length=255)
    country: str | None = Field(default=None, min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool = Field(default=None)
    gpa: float | None = Field(default=None, ge=0)
    gpa_scale: float | None = None
    is_primary: bool = Field(default=None)


__all__ = ["EducationCreate", "EducationRead", "EducationUpdate", "SUPPORTED_GPA_SCALES"]
