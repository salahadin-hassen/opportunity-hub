"""Run the ingestion pipeline from the site: test a source, run discovery and processing, import the starter list.

These are the only web requests that make the server fetch other websites, so they are deliberately
narrow:

- **Admins only** to start anything (``Permission.SOURCE_APPROVE``, which only the admin role holds);
  curators can watch progress (``source.read``).
- **No URLs come from the request.** A run fetches only what approved sources already define (a test
  fetches what the source being tested defines), through the same reader as the command line: allowed
  hosts on every redirect, SSRF-safe sockets, robots.txt, per-host politeness and page budgets.
- **One job at a time** per API process. A second start while one runs gets 409.
- **Bounded:** processing takes at most ``limit`` candidates per run (default 50, at most 100).
- **Audited:** every start is written to the audit log with the admin who started it.

Jobs run on a background thread with their own database session and call exactly the functions the
command line uses (``run_source_test``, ``run_discovery``, ``process_candidates``), which commit their
own work as they go. Live status is kept in memory; the durable record is ``ingestion_runs`` and the
audit log. Nothing is ever published: processing only produces candidates for curator review.
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.permissions import Permission
from app.db.session import SessionLocal, get_db
from app.intelligence import ai_review, autonomy, pipeline, registry
from app.intelligence.definitions import SourceDefinition
from app.models import AcquisitionSource, User
from app.models.enums import SourceStatus
from app.services import audit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/curate/ingestion/jobs", tags=["curate"])

#: The reviewed starter list that ships with the code (see vetted_sources.md); never a user-supplied file.
#: Found next to the source tree, or under the working directory (the API runs from ``backend/``).
STARTER_SOURCES = next(
    (path for path in (Path(__file__).resolve().parents[3] / "data" / "ingestion" / "vetted_sources.json", Path.cwd() / "data" / "ingestion" / "vetted_sources.json") if path.exists()),
    Path(__file__).resolve().parents[3] / "data" / "ingestion" / "vetted_sources.json",
)


# ---------------------------------------------------------------------------
# Job registry (in memory; one job at a time)
# ---------------------------------------------------------------------------


@dataclass
class Job:
    id: str
    kind: str  # "pipeline" | "source_test"
    label: str
    started_by: str
    started_at: datetime
    status: str = "running"  # running | succeeded | failed
    finished_at: datetime | None = None
    summary: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


_lock = threading.Lock()
_current: Job | None = None
_recent: deque[Job] = deque(maxlen=10)


def _spawn(target: Callable[[], None]) -> None:
    """Start the job's thread (replaced in tests to run inline)."""
    threading.Thread(target=target, name="ingestion-job", daemon=True).start()


def _session_factory() -> Session:
    """The job's own session: the request's session closes when the response is sent (replaced in tests)."""
    return SessionLocal()


def _claim(kind: str, label: str, actor: User) -> Job:
    global _current
    with _lock:
        if _current is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"“{_current.label}” is still running. Wait for it to finish.")
        _current = Job(id=uuid.uuid4().hex, kind=kind, label=label, started_by=actor.email, started_at=datetime.now(timezone.utc))
        return _current


def _run(job: Job, work: Callable[[Session], dict[str, Any]]) -> None:
    global _current
    db = _session_factory()
    try:
        job.summary = work(db)
        job.status = "succeeded"
    except Exception as error:  # a failed job is reported, never raised into the server
        db.rollback()
        job.status = "failed"
        job.error = f"{type(error).__name__}: {error}"[:500]
        logger.exception("ingestion job %s failed", job.id)
    finally:
        db.close()
        job.finished_at = datetime.now(timezone.utc)
        with _lock:
            _current = None
            _recent.appendleft(job)


# ---------------------------------------------------------------------------
# Work
# ---------------------------------------------------------------------------


def _pipeline_work(source_id: uuid.UUID | None, limit: int) -> Callable[[Session], dict[str, Any]]:
    def work(db: Session) -> dict[str, Any]:
        query = select(AcquisitionSource).where(AcquisitionSource.status == SourceStatus.APPROVED)
        if source_id is not None:
            query = query.where(AcquisitionSource.id == source_id)
        sources = list(db.scalars(query.order_by(AcquisitionSource.name)))
        discovered = []
        for source in sources:
            report = pipeline.run_discovery(db, source)
            discovered.append({"source": source.name, "new": report.new, "seen_again": report.seen_again, "rejected": len(report.rejected), "error": report.error})
        processed = pipeline.process_candidates(db, limit=limit, source_id=source_id)
        # Autonomy: decide reviewable candidates of sources above "off" (see app.intelligence.autonomy),
        # then retire what has passed its deadline.
        today = datetime.now(timezone.utc).date()
        automatic = autonomy.run(db, today=today, limit=limit)
        expired = pipeline.expire_candidates(db, today=today)
        db.commit()
        closed = autonomy.close_past_deadline(db)
        return {
            "sources": len(sources),
            "new_leads": sum(item["new"] for item in discovered),
            "discovery": discovered,
            "processed": processed.processed,
            "by_state": processed.by_state,
            "automatic": automatic,
            "ai_review": ai_review.enabled(),
            "expired_candidates": expired,
            "closed_opportunities": closed,
            "errors": processed.errors[:10],
        }

    return work


def _test_work(source_id: uuid.UUID, actor_id: uuid.UUID) -> Callable[[Session], dict[str, Any]]:
    def work(db: Session) -> dict[str, Any]:
        from app.intelligence.source_test import run_source_test

        source = db.get(AcquisitionSource, source_id)
        if source is None:
            raise LookupError("The source no longer exists.")
        if source.status == SourceStatus.PROPOSED:
            registry.change_status(db, source, SourceStatus.TESTING, actor_id=actor_id)
            db.commit()
        report = run_source_test(db, source)
        db.commit()
        return {
            "source": source.name,
            "passed": report.passed,
            "robots": str(report.robots_status),
            "leads": report.leads,
            "fetched_ok": report.fetched_ok,
            "fetched_failed": report.fetched_failed,
            "problems": report.problems[:5],
            "warnings": report.warnings[:5],
        }

    return work


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


class JobRead(BaseModel):
    id: str
    kind: str
    label: str
    started_by: str
    started_at: datetime
    status: str
    finished_at: datetime | None
    summary: dict[str, Any]
    error: str | None


class JobsRead(BaseModel):
    current: JobRead | None
    recent: list[JobRead]


class PipelineRunRequest(BaseModel):
    source_id: uuid.UUID | None = None
    limit: int = Field(default=50, ge=1, le=100)


class StarterImport(BaseModel):
    created: list[str]
    skipped: list[str]


def _read(job: Job | None) -> JobRead | None:
    return JobRead(**asdict(job)) if job else None


@router.get("", response_model=JobsRead)
def list_jobs(_: User = Depends(require_permission(Permission.SOURCE_READ))) -> JobsRead:
    with _lock:
        return JobsRead(current=_read(_current), recent=[_read(job) for job in _recent])  # type: ignore[misc]


@router.post("/pipeline", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
def start_pipeline(
    request: PipelineRunRequest,
    db: Session = Depends(get_db, scope="function"),
    admin: User = Depends(require_permission(Permission.SOURCE_APPROVE)),
) -> JobRead:
    if request.source_id is not None:
        source = db.get(AcquisitionSource, request.source_id)
        if source is None or source.status != SourceStatus.APPROVED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only approved sources can be run.")
        label = f"Pipeline run: {source.name}"
    else:
        count = db.scalar(select(AcquisitionSource.id).where(AcquisitionSource.status == SourceStatus.APPROVED).limit(1))
        if count is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No approved sources yet. Test a source, review its terms and approve it first.")
        label = "Pipeline run: all approved sources"
    job = _claim("pipeline", label, admin)
    audit.record(db, action="ingestion.run_started", target_type="ingestion", target_id=job.id, actor_id=admin.id,
                 changes={"source_id": str(request.source_id) if request.source_id else "all", "limit": request.limit})
    _spawn(lambda: _run(job, _pipeline_work(request.source_id, request.limit)))
    return _read(job)  # type: ignore[return-value]


@router.post("/source-test/{source_id}", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
def start_source_test(
    source_id: uuid.UUID,
    db: Session = Depends(get_db, scope="function"),
    admin: User = Depends(require_permission(Permission.SOURCE_APPROVE)),
) -> JobRead:
    source = db.get(AcquisitionSource, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No source with that id.")
    if source.status not in (SourceStatus.PROPOSED, SourceStatus.TESTING):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Only proposed or testing sources are tested (this one is {source.status}).")
    job = _claim("source_test", f"Test: {source.name}", admin)
    audit.record(db, action="source.test_started", target_type="acquisition_source", target_id=source.id, actor_id=admin.id)
    _spawn(lambda: _run(job, _test_work(source.id, admin.id)))
    return _read(job)  # type: ignore[return-value]


@router.post("/starter-sources", response_model=StarterImport)
def import_starter_sources(
    db: Session = Depends(get_db, scope="function"),
    admin: User = Depends(require_permission(Permission.SOURCE_APPROVE)),
) -> StarterImport:
    """Propose the reviewed starter list that ships with the code. Existing names are skipped; nothing is fetched."""
    if not STARTER_SOURCES.exists():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="The starter source list isn’t available on this server.")
    definitions = json.loads(STARTER_SOURCES.read_text())
    created: list[str] = []
    skipped: list[str] = []
    for raw in definitions:
        definition = SourceDefinition.model_validate(raw)
        if db.scalar(select(AcquisitionSource.id).where(AcquisitionSource.name == definition.name)):
            skipped.append(definition.name)
            continue
        registry.create_source(db, definition, actor_id=admin.id)
        created.append(definition.name)
    audit.record(db, action="ingestion.starter_imported", target_type="ingestion", target_id="starter-sources", actor_id=admin.id,
                 changes={"created": len(created), "skipped": len(skipped)})
    return StarterImport(created=created, skipped=skipped)


__all__ = ["router"]
