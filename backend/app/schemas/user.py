"""Pydantic schemas for authenticated users."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class UserRead(BaseModel):
    """Public identity of one user.

    Deliberately excludes ``password_hash``: no response schema in the
    project ever carries password material.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    is_active: bool
    created_at: datetime
    updated_at: datetime


__all__ = ["UserRead"]
