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


__all__ = ["TestScoreCreate", "TestScoreRead"]
