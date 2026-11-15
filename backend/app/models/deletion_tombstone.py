"""Deletion tombstones for GDPR and account erasure audit."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DeletionTombstone(Base):
    """Immutable record that an account was permanently purged.
    
    Contains NO personal data or identifiers other than the purged UUID.
    Used to reconcile backups and prevent resurrection of deleted data.
    """

    __tablename__ = "deletion_tombstones"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    purged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

