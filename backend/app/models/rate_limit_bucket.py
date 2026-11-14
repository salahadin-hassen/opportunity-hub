"""Shared fixed-window counters for credential endpoints.

One row per (endpoint scope, hashed subject, window start). Subjects (a
client address bucket or an account email) are stored only as keyed
HMAC digests, so the table never holds addresses or emails. Rows are
written outside request transactions (see ``app.core.rate_limit``) so a
failed login still counts, and expired windows are pruned.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, PrimaryKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RateLimitBucket(Base):
    __tablename__ = "rate_limit_buckets"

    scope: Mapped[str] = mapped_column(String(100), nullable=False)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("scope", "key", "window_start", name="pk_rate_limit_buckets"),
        CheckConstraint("count >= 1", name="ck_rate_limit_buckets_count_positive"),
        CheckConstraint("char_length(key) = 64", name="ck_rate_limit_buckets_key_digest"),
        Index("ix_rate_limit_buckets_window_start", "window_start"),
    )
