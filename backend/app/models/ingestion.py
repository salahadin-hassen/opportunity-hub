"""Ingestion runs and candidates: what the pipeline found, kept apart from published opportunities.

A candidate is one page discovered on an approved (or testing) acquisition source. The pipeline fetches
it, extracts fields with evidence, normalises, validates and de-duplicates it, then stops at
``needs_review``. Only a curator's approval turns a candidate into a **draft** opportunity, and only the
existing ``publish_opportunity`` path (with its own checks, triggered by a person) publishes it. Nothing
here can publish.

Concurrency and retries: candidates are leased with ``FOR UPDATE SKIP LOCKED`` and a ``lease_until``
timestamp, so two workers never process the same row and a crashed worker's lease simply expires.
``candidate_key`` (source + canonical URL) makes discovery idempotent.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import enum_check_constraint

MAX_ERROR_LENGTH = 500


class CandidateState(StrEnum):
    """Where a candidate is in the pipeline."""

    #: Found by discovery (or re-queued); waiting to be fetched and extracted.
    DISCOVERED = "discovered"
    #: A fetch or processing attempt failed; retried after ``next_attempt_at``.
    RETRY = "retry"
    #: Gave up after the maximum number of attempts.
    FAILED = "failed"
    #: Extracted and validated; waiting for a curator.
    NEEDS_REVIEW = "needs_review"
    #: The extracted deadline has passed; kept for the record, not offered for review.
    EXPIRED = "expired"
    #: Same page content or same opportunity as an existing candidate or opportunity.
    DUPLICATE = "duplicate"
    #: Not an opportunity page, or otherwise unsuitable (by the pipeline or a curator).
    REJECTED = "rejected"
    #: A curator asked for a correction; re-processing puts it back to ``discovered``.
    CHANGES_REQUESTED = "changes_requested"
    #: A curator approved it: a draft opportunity exists (``opportunity_id``). Publishing is separate.
    APPROVED = "approved"


#: States the processing worker may pick up.
PROCESSABLE_STATES = (CandidateState.DISCOVERED, CandidateState.RETRY)


class RunKind(StrEnum):
    DISCOVER = "discover"
    PROCESS = "process"


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class IngestionRun(Base):
    """One execution of discovery or processing, with its counts and any error."""

    __tablename__ = "ingestion_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("acquisition_sources.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=RunStatus.RUNNING)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    stats: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    error: Mapped[str | None] = mapped_column(String(MAX_ERROR_LENGTH), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        enum_check_constraint("ingestion_runs", "kind", RunKind),
        enum_check_constraint("ingestion_runs", "status", RunStatus),
        Index("ix_ingestion_runs_started_at", "started_at"),
    )


class IngestionCandidate(Base):
    """One discovered page and everything the pipeline learned about it."""

    __tablename__ = "ingestion_candidates"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("acquisition_sources.id", ondelete="CASCADE"), nullable=False
    )
    #: sha256 of ``source_id`` and the canonical URL: discovery of the same page is a no-op.
    candidate_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default=CandidateState.DISCOVERED)

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(MAX_ERROR_LENGTH), nullable=True)

    #: What the fetch returned. ``page_text`` is the normalised visible text that evidence quotes
    #: must be substrings of; it is never rendered or served as HTML.
    final_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    page_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: ``{field: {status, value, evidence}}`` (see ``app.intelligence.extract``).
    extraction: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    extractor_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: ``{"problems": [...], "warnings": [...], "validator_version": ...}``.
    validation: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    #: 0-100, to order the review queue. Never a substitute for a person checking the page.
    quality_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    duplicate_of_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ingestion_candidates.id", ondelete="SET NULL"), nullable=True
    )
    duplicate_of_opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True
    )
    #: The draft opportunity created when a curator approved this candidate.
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True
    )

    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    discovery_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ingestion_runs.id", ondelete="SET NULL"), nullable=True
    )
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        enum_check_constraint("ingestion_candidates", "state", CandidateState),
        CheckConstraint("attempts >= 0", name="ck_ingestion_candidates_attempts_nonnegative"),
        CheckConstraint(
            "quality_score IS NULL OR quality_score BETWEEN 0 AND 100",
            name="ck_ingestion_candidates_quality_score_range",
        ),
        # An approved candidate always points at the draft it produced.
        CheckConstraint(
            "state <> 'approved' OR opportunity_id IS NOT NULL",
            name="ck_ingestion_candidates_approved_has_opportunity",
        ),
        Index("ix_ingestion_candidates_queue", "state", "next_attempt_at"),
        Index("ix_ingestion_candidates_source_id", "source_id"),
        Index("ix_ingestion_candidates_content_hash", "content_hash"),
    )

    def __repr__(self) -> str:
        return f"<IngestionCandidate {self.state} {self.url!r}>"


__all__ = [
    "CandidateState",
    "IngestionCandidate",
    "IngestionRun",
    "PROCESSABLE_STATES",
    "RunKind",
    "RunStatus",
]
