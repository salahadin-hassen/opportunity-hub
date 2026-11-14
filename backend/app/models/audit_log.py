"""Append-only record of privileged and automated actions (M2-T2).

Entries are written in the same transaction as the change they describe,
so the two cannot diverge. ``actor_user_id`` deliberately has no foreign
key: entries outlive the accounts that made them. Updates and deletes are
refused by the ORM (below) and by a database trigger (see the migration).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Identity, Index, String, Text, Uuid, event, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ACTOR_KINDS = ("user", "system", "cli")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    changes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    __table_args__ = (
        CheckConstraint(f"actor_kind IN ({', '.join(repr(kind) for kind in ACTOR_KINDS)})", name="ck_audit_log_actor_kind"),
        CheckConstraint(
            "actor_kind <> 'user' OR actor_user_id IS NOT NULL", name="ck_audit_log_user_actor_has_id"
        ),
        Index("ix_audit_log_target", "target_type", "target_id", "occurred_at"),
        Index("ix_audit_log_actor", "actor_user_id", "occurred_at"),
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} {self.target_type}:{self.target_id}>"


class AuditLogImmutableError(RuntimeError):
    """Audit entries are append-only."""


@event.listens_for(AuditLog, "before_update")
def _refuse_update(mapper, connection, target) -> None:  # pragma: no cover - exercised in tests
    raise AuditLogImmutableError("Audit entries cannot be modified.")


@event.listens_for(AuditLog, "before_delete")
def _refuse_delete(mapper, connection, target) -> None:  # pragma: no cover - exercised in tests
    raise AuditLogImmutableError("Audit entries cannot be deleted.")
