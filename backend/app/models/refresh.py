"""Refresh checks: what re-reading a published opportunity's official page found.

One row per check, kept as history. A check never changes the opportunity: the approved title,
deadline, requirements and the snapshot they were quoted from stay exactly as the curator left them.
Anything that differs is recorded here with ``review_state = 'pending'`` for a curator to act on.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import enum_check_constraint
from app.models.ingestion import MAX_ERROR_LENGTH


class RefreshOutcome(StrEnum):
    """What a refresh check concluded. Exactly one per check."""

    #: 304, identical content, or new content that still states the approved deadline and every
    #: approved eligibility quote. Nothing for a curator to do.
    UNCHANGED = "unchanged"
    #: The page no longer contains an approved eligibility quote, or states new eligibility rules.
    MATERIAL_UPDATE = "material_update"
    #: The page states a different deadline for what looks like the same application cycle.
    DEADLINE_CHANGED = "deadline_changed"
    #: The page says applications are closed, or the approved deadline has passed.
    CLOSED = "closed"
    #: The page states a deadline far enough after the approved one to be the next cycle.
    NEW_CYCLE = "new_cycle"
    #: The page could not be read (dead link, access denied, robots.txt, timeout, server error).
    SOURCE_UNAVAILABLE = "source_unavailable"
    #: The page changed and the pipeline cannot tell what it means (deadline gone or ambiguous, page
    #: no longer looks like an opportunity page, earlier deadline than the approved one).
    REVIEW_REQUIRED = "review_required"


class RefreshReviewState(StrEnum):
    #: Nothing to review (unchanged, or the same finding is already recorded on an earlier check).
    NONE = "none"
    PENDING = "pending"
    #: A curator handled it (edited, closed or re-approved the opportunity by the normal routes).
    ACKNOWLEDGED = "acknowledged"
    #: A curator decided the finding is not a real change.
    DISMISSED = "dismissed"


class OpportunityRefreshCheck(Base):
    __tablename__ = "opportunity_refresh_checks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    #: The approved acquisition source whose allow-list and robots rules the fetch ran under.
    acquisition_source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("acquisition_sources.id", ondelete="SET NULL"), nullable=True
    )
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)

    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Whether this check received content that differs from the last content held for the page.
    content_changed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    #: sha256 of the page text this check stands for (carried forward on a 304 or a failed request).
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Validators for the next conditional request (carried forward on a 304 or a failed request).
    etag: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(512), nullable=True)
    #: The page text, stored only when ``content_changed``: together with the opportunity's original
    #: source snapshot these rows are the page's history.
    page_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    #: What differs from the approved opportunity, with the quotes that show it.
    findings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    error: Mapped[str | None] = mapped_column(String(MAX_ERROR_LENGTH), nullable=True)
    #: Failed checks in a row up to and including this one (0 after any successful read).
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))

    #: sha256 of the outcome and its key facts: the same finding is put in front of a curator once.
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    review_state: Mapped[str] = mapped_column(String(16), nullable=False, default=RefreshReviewState.NONE)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: For ``new_cycle``: the candidate put in the review queue for the next cycle.
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ingestion_candidates.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        enum_check_constraint("opportunity_refresh_checks", "outcome", RefreshOutcome),
        enum_check_constraint("opportunity_refresh_checks", "review_state", RefreshReviewState),
        CheckConstraint("consecutive_failures >= 0", name="ck_opportunity_refresh_checks_failures_nonnegative"),
        Index("ix_opportunity_refresh_checks_opportunity", "opportunity_id", "checked_at"),
        Index("ix_opportunity_refresh_checks_review_state", "review_state"),
    )

    def __repr__(self) -> str:
        return f"<OpportunityRefreshCheck {self.outcome} {self.url!r}>"


__all__ = ["OpportunityRefreshCheck", "RefreshOutcome", "RefreshReviewState"]
