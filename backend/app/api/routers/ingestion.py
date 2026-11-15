"""Curator review of ingestion candidates, refresh findings and source health.

Candidates are what the pipeline found; nothing here publishes. Approval creates a **draft**
opportunity, which a curator then publishes through ``POST /curate/opportunities/{id}/publish`` (with
its publication checks). Discovery, processing, source tests and refreshes are operator commands
(``python -m app.cli ingest-*``), not API calls, so a web request can never trigger outbound fetching.

Refresh findings (``/curate/ingestion/refresh-checks``) are what re-reading a published opportunity's
page found. Resolving one only records the curator's decision; it never edits the opportunity.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.permissions import Permission
from app.db.session import get_db
from app.intelligence import pipeline, refresh
from app.intelligence.health import source_health
from app.models import AcquisitionSource, IngestionCandidate, IngestionRun, Opportunity, OpportunityRefreshCheck, User
from app.models.ingestion import CandidateState
from app.models.refresh import RefreshOutcome, RefreshReviewState

router = APIRouter(prefix="/curate/candidates", tags=["curate"])
operations_router = APIRouter(prefix="/curate/ingestion", tags=["curate"])


class CandidateSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    source_name: str | None = None
    url: str
    final_url: str | None
    state: str
    quality_score: int | None
    title: str | None = None
    deadline: Any = None
    problems: list[str] = Field(default_factory=list)
    attempts: int
    last_error: str | None
    opportunity_id: uuid.UUID | None
    duplicate_of_candidate_id: uuid.UUID | None
    duplicate_of_opportunity_id: uuid.UUID | None
    fetched_at: datetime | None
    discovered_at: datetime
    updated_at: datetime


class CandidateDetail(CandidateSummary):
    extraction: dict[str, Any] | None
    validation: dict[str, Any] | None
    extractor_version: str | None
    content_hash: str | None
    http_status: int | None
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    review_notes: str | None
    #: When the page was last confirmed (a 200 or a 304), and the validators held for the next fetch.
    last_seen_at: datetime
    etag: str | None
    last_modified: str | None


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject", "request_changes"]
    notes: str | None = Field(default=None, max_length=2000)
    #: Approval only: corrections a curator confirms against the page. Omitted fields keep extracted values.
    title: str | None = Field(default=None, max_length=255)
    opportunity_type: str | None = None
    deadline: date | None = None
    deadline_type: Literal["fixed", "rolling", "none"] | None = None
    description: str | None = Field(default=None, max_length=5000)
    statements: list[int] | None = Field(default=None, max_length=50)
    countries: list[str] | None = Field(default=None, max_length=50)
    force: bool = False


class ReviewResult(BaseModel):
    candidate: CandidateDetail
    opportunity_id: uuid.UUID | None = None


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    source_id: uuid.UUID | None
    status: str
    dry_run: bool
    stats: dict[str, Any]
    error: str | None
    started_at: datetime
    finished_at: datetime | None


def _summary_fields(candidate: IngestionCandidate, source_name: str | None) -> dict[str, Any]:
    extraction = candidate.extraction or {}
    validation = candidate.validation or {}
    return {
        "source_name": source_name,
        "title": (extraction.get("title") or {}).get("value"),
        "deadline": (extraction.get("deadline") or {}).get("value"),
        "problems": validation.get("problems") or [],
    }


def _detail(db: Session, candidate: IngestionCandidate) -> CandidateDetail:
    name = db.scalar(select(AcquisitionSource.name).where(AcquisitionSource.id == candidate.source_id))
    return CandidateDetail.model_validate(candidate, from_attributes=True).model_copy(update=_summary_fields(candidate, name))


@router.get("", response_model=list[CandidateSummary])
def list_candidates(
    state: CandidateState | None = Query(default=None),
    source_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db, scope="function"),
    _: User = Depends(require_permission(Permission.SOURCE_READ)),
) -> list[CandidateSummary]:
    """The review queue: highest quality score first within a state."""
    statement = (
        select(IngestionCandidate, AcquisitionSource.name)
        .join(AcquisitionSource, AcquisitionSource.id == IngestionCandidate.source_id)
        .order_by(IngestionCandidate.quality_score.desc().nulls_last(), IngestionCandidate.discovered_at)
        .limit(limit)
        .offset(offset)
    )
    if state is not None:
        statement = statement.where(IngestionCandidate.state == state)
    if source_id is not None:
        statement = statement.where(IngestionCandidate.source_id == source_id)
    return [
        CandidateSummary.model_validate(candidate, from_attributes=True).model_copy(update=_summary_fields(candidate, name))
        for candidate, name in db.execute(statement).all()
    ]


@router.get("/runs", response_model=list[RunRead])
def list_runs(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db, scope="function"),
    _: User = Depends(require_permission(Permission.SOURCE_READ)),
) -> list[IngestionRun]:
    return list(db.scalars(select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(limit)))


@router.get("/{candidate_id}", response_model=CandidateDetail)
def get_candidate(
    candidate_id: uuid.UUID,
    db: Session = Depends(get_db, scope="function"),
    _: User = Depends(require_permission(Permission.SOURCE_READ)),
) -> CandidateDetail:
    candidate = db.get(IngestionCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found.")
    return _detail(db, candidate)


@router.post("/{candidate_id}/review", response_model=ReviewResult)
def review_candidate(
    candidate_id: uuid.UUID,
    payload: ReviewRequest,
    db: Session = Depends(get_db, scope="function"),
    curator: User = Depends(require_permission(Permission.OPPORTUNITY_CREATE)),
) -> ReviewResult:
    """Approve (creates a draft opportunity, never publishes), reject, or request a correction."""
    try:
        if payload.decision == "approve":
            opportunity = pipeline.approve_candidate(
                db, candidate_id, actor_id=curator.id,
                decision=pipeline.ApprovalInput(
                    title=payload.title, opportunity_type=payload.opportunity_type, deadline=payload.deadline,
                    deadline_type=payload.deadline_type, description=payload.description,
                    statements=payload.statements, countries=payload.countries, notes=payload.notes, force=payload.force,
                ),
            )
            opportunity_id = opportunity.id
        else:
            pipeline.decide_candidate(db, candidate_id, actor_id=curator.id, decision=payload.decision, notes=payload.notes)
            opportunity_id = None
    except pipeline.PipelineError as error:
        code = status.HTTP_404_NOT_FOUND if str(error) == "Candidate not found." else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=str(error)) from None
    candidate = db.get(IngestionCandidate, candidate_id)
    return ReviewResult(candidate=_detail(db, candidate), opportunity_id=opportunity_id)


@router.post("/{candidate_id}/requeue", response_model=CandidateDetail)
def requeue(
    candidate_id: uuid.UUID,
    db: Session = Depends(get_db, scope="function"),
    curator: User = Depends(require_permission(Permission.SOURCE_TEST)),
) -> CandidateDetail:
    """Queue a fresh fetch and extraction (the next ``ingest-process`` run picks it up)."""
    try:
        candidate = pipeline.requeue_candidate(db, candidate_id, actor_id=curator.id)
    except pipeline.PipelineError as error:
        code = status.HTTP_404_NOT_FOUND if str(error) == "Candidate not found." else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=str(error)) from None
    return _detail(db, candidate)


# --- source health ---------------------------------------------------------------------------------------


class SourceHealthRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: str
    connector_key: str
    robots_status: str
    tested: bool
    test_passed: bool
    fetchable: bool
    parsed: bool
    producing: bool
    failed: bool
    needs_review: bool
    stage: str
    candidates: int
    fetched: int
    valid: int
    awaiting_review: int
    untraceable_candidates: int
    problem: str | None


class SourceHealthReport(BaseModel):
    """Counts of sources by what recorded evidence proves. Registration alone counts for nothing."""

    model_config = ConfigDict(from_attributes=True)

    registered: int
    tested: int
    test_passed: int
    never_tested: int
    fetchable: int
    parsed: int
    producing: int
    failed: int
    needs_review: int
    by_stage: dict[str, int]
    by_status: dict[str, int]
    by_connector: dict[str, int]
    untraceable_candidates: int
    sources: list[SourceHealthRead]


@operations_router.get("/source-health", response_model=SourceHealthReport)
def read_source_health(
    db: Session = Depends(get_db, scope="function"),
    _: User = Depends(require_permission(Permission.SOURCE_READ)),
) -> SourceHealthReport:
    return SourceHealthReport.model_validate(source_health(db), from_attributes=True)


# --- refresh findings ------------------------------------------------------------------------------------


class RefreshCheckSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    opportunity_id: uuid.UUID
    opportunity_title: str | None = None
    url: str
    checked_at: datetime
    outcome: str
    review_state: str
    http_status: int | None
    content_changed: bool
    findings: dict[str, Any]
    error: str | None
    consecutive_failures: int
    candidate_id: uuid.UUID | None


class RefreshCheckDetail(RefreshCheckSummary):
    content_hash: str | None
    etag: str | None
    last_modified: str | None
    extraction: dict[str, Any] | None
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    review_notes: str | None


class RefreshResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["acknowledge", "dismiss"]
    notes: str | None = Field(default=None, max_length=2000)


def _check_detail(db: Session, check: OpportunityRefreshCheck) -> RefreshCheckDetail:
    title = db.scalar(select(Opportunity.title).where(Opportunity.id == check.opportunity_id))
    return RefreshCheckDetail.model_validate(check, from_attributes=True).model_copy(update={"opportunity_title": title})


@operations_router.get("/refresh-checks", response_model=list[RefreshCheckSummary])
def list_refresh_checks(
    review_state: RefreshReviewState | None = Query(default=RefreshReviewState.PENDING),
    outcome: RefreshOutcome | None = Query(default=None),
    opportunity_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db, scope="function"),
    _: User = Depends(require_permission(Permission.SOURCE_READ)),
) -> list[RefreshCheckSummary]:
    """Refresh checks, newest first. By default only the findings waiting for a curator."""
    statement = (
        select(OpportunityRefreshCheck, Opportunity.title)
        .join(Opportunity, Opportunity.id == OpportunityRefreshCheck.opportunity_id)
        .order_by(OpportunityRefreshCheck.checked_at.desc(), OpportunityRefreshCheck.id)
        .limit(limit)
        .offset(offset)
    )
    if review_state is not None:
        statement = statement.where(OpportunityRefreshCheck.review_state == review_state)
    if outcome is not None:
        statement = statement.where(OpportunityRefreshCheck.outcome == outcome)
    if opportunity_id is not None:
        statement = statement.where(OpportunityRefreshCheck.opportunity_id == opportunity_id)
    return [
        RefreshCheckSummary.model_validate(check, from_attributes=True).model_copy(update={"opportunity_title": title})
        for check, title in db.execute(statement).all()
    ]


@operations_router.get("/refresh-checks/{check_id}", response_model=RefreshCheckDetail)
def get_refresh_check(
    check_id: uuid.UUID,
    db: Session = Depends(get_db, scope="function"),
    _: User = Depends(require_permission(Permission.SOURCE_READ)),
) -> RefreshCheckDetail:
    check = db.get(OpportunityRefreshCheck, check_id)
    if check is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Refresh check not found.")
    return _check_detail(db, check)


@operations_router.post("/refresh-checks/{check_id}/resolve", response_model=RefreshCheckDetail)
def resolve_refresh_check(
    check_id: uuid.UUID,
    payload: RefreshResolveRequest,
    db: Session = Depends(get_db, scope="function"),
    curator: User = Depends(require_permission(Permission.OPPORTUNITY_EDIT)),
) -> RefreshCheckDetail:
    """Record that a finding was handled or is not a real change. Never edits the opportunity."""
    try:
        check = refresh.resolve_check(db, check_id, actor_id=curator.id, decision=payload.decision, notes=payload.notes)
    except refresh.RefreshError as error:
        code = status.HTTP_404_NOT_FOUND if str(error) == "Refresh check not found." else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=str(error)) from None
    return _check_detail(db, check)
