"""Pydantic schemas for test score records."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TestScoreCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_type: str = Field(min_length=1, max_length=100)
    overall_score: float = Field(ge=0)
    sub_scores: dict[str, Any] | list[Any] | None = None
    test_date: date | None = None
    expires_at: date | None = None
    report_number: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        if self.test_date and self.expires_at and self.expires_at < self.test_date:
            raise ValueError("expires_at must be on or after test_date")
        return self


class TestScoreRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    profile_id: uuid.UUID
    test_type: str
    overall_score: float
    sub_scores: dict[str, Any] | list[Any] | None
    test_date: date | None
    expires_at: date | None
    report_number: str | None
    created_at: datetime


class TestScoreUpdate(BaseModel):
    """Partial update for one owned test score.

    Non-nullable columns declare a ``None`` default they can never receive:
    an omitted field keeps its stored value (it is not in
    ``model_fields_set`` and therefore never applied), while an explicit
    ``null`` on such a field fails validation with a 422 instead of reaching
    the database. The cross-field ``expires_at >= test_date`` rule spans the
    stored record plus the submitted fields, so it is re-checked against the
    merged state in the service — this schema only validates what the client
    actually sends.
    """

    model_config = ConfigDict(extra="forbid")

    test_type: str = Field(default=None, min_length=1, max_length=100)
    overall_score: float = Field(default=None, ge=0)
    sub_scores: dict[str, Any] | list[Any] | None = None
    test_date: date | None = None
    expires_at: date | None = None
    report_number: str | None = Field(default=None, max_length=100)


__all__ = ["TestScoreCreate", "TestScoreRead", "TestScoreUpdate"]
