"""Source health: what is actually known about each registered source, from recorded evidence only.

Registration is not evidence. A source is counted at a stage only when something recorded proves it:

* ``tested``       a source test ran (``last_test_at``);
* ``test_passed``  that test fetched its pages successfully;
* ``fetchable``    a test passed, or the pipeline fetched at least one of its pages (HTTP 2xx, from a
                   candidate created by a real discovery or refresh run);
* ``parsed``       at least one fetched page was recognised as an opportunity page;
* ``producing``    at least one candidate has no validation problem and is awaiting review or approved;
* ``failed``       the last test failed, the last runs failed, or candidates exist and none was fetched;
* ``needs_review`` candidates are waiting for a curator.

The stages are cumulative facts, not exclusive states; ``stage`` is the furthest one reached, or
``failed``. Candidates without a discovery run (rows written straight into the table) are ignored.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.models import AcquisitionSource, IngestionCandidate
from app.models.ingestion import CandidateState

STAGES = ("registered", "tested", "fetchable", "parsed", "producing")


@dataclass
class SourceHealth:
    id: uuid.UUID
    name: str
    status: str
    connector_key: str
    robots_status: str
    tested: bool = False
    test_passed: bool = False
    fetchable: bool = False
    parsed: bool = False
    producing: bool = False
    failed: bool = False
    needs_review: bool = False
    #: The furthest stage reached (``registered`` … ``producing``), or ``failed``.
    stage: str = "registered"
    candidates: int = 0
    fetched: int = 0
    valid: int = 0
    awaiting_review: int = 0
    untraceable_candidates: int = 0
    problem: str | None = None


@dataclass
class HealthReport:
    registered: int = 0
    tested: int = 0
    test_passed: int = 0
    fetchable: int = 0
    parsed: int = 0
    producing: int = 0
    failed: int = 0
    needs_review: int = 0
    never_tested: int = 0
    by_stage: dict[str, int] = field(default_factory=dict)
    by_status: dict[str, int] = field(default_factory=dict)
    by_connector: dict[str, int] = field(default_factory=dict)
    untraceable_candidates: int = 0
    sources: list[SourceHealth] = field(default_factory=list)

    def as_dict(self, *, with_sources: bool = True) -> dict[str, Any]:
        data = asdict(self)
        if not with_sources:
            data.pop("sources")
        return data


def _test_problem(report: dict[str, Any] | None) -> str | None:
    problems = (report or {}).get("problems") or []
    return str(problems[0])[:300] if problems else None


def source_health(db: Session) -> HealthReport:
    report = HealthReport()
    rows: dict[uuid.UUID, SourceHealth] = {}
    bind = db.get_bind()
    insp = inspect(bind)
    cols = {c["name"] for c in insp.get_columns("acquisition_sources")}
    has_test_cols = "last_test_at" in cols

    if has_test_cols:
        for source in db.scalars(select(AcquisitionSource).order_by(AcquisitionSource.name)):
            item = SourceHealth(
                id=source.id, name=source.name, status=str(source.status), connector_key=source.connector_key,
                robots_status=str(source.robots_status),
                tested=source.last_test_at is not None, test_passed=bool(source.last_test_passed),
            )
            if source.last_test_at is not None and not source.last_test_passed:
                item.failed = True
                item.problem = _test_problem(source.last_test_report) or "the last source test failed"
            elif source.consecutive_failures > 0:
                item.failed = True
                item.problem = source.last_error or f"{source.consecutive_failures} failed run(s) in a row"
            rows[source.id] = item
    else:
        stmt = select(
            AcquisitionSource.id,
            AcquisitionSource.name,
            AcquisitionSource.status,
            AcquisitionSource.connector_key,
            AcquisitionSource.robots_status,
            AcquisitionSource.consecutive_failures,
            AcquisitionSource.last_error,
        ).order_by(AcquisitionSource.name)
        for r in db.execute(stmt):
            item = SourceHealth(
                id=r.id, name=r.name, status=str(r.status), connector_key=r.connector_key,
                robots_status=str(r.robots_status),
                tested=False, test_passed=False,
            )
            if r.consecutive_failures > 0:
                item.failed = True
                item.problem = r.last_error or f"{r.consecutive_failures} failed run(s) in a row"
            rows[r.id] = item

    candidates = db.execute(
        select(
            IngestionCandidate.source_id, IngestionCandidate.state, IngestionCandidate.http_status,
            IngestionCandidate.fetched_at, IngestionCandidate.validation, IngestionCandidate.extraction,
            IngestionCandidate.discovery_run_id, IngestionCandidate.last_error,
        )
    ).all()
    last_error: dict[uuid.UUID, str] = {}
    for row in candidates:
        item = rows.get(row.source_id)
        if item is None:
            continue
        if row.discovery_run_id is None:
            item.untraceable_candidates += 1
            continue
        item.candidates += 1
        fetched = row.fetched_at is not None and row.http_status is not None and 200 <= row.http_status < 300
        validation = row.validation or {}
        if fetched:
            item.fetched += 1
            if row.extraction and not validation.get("irrelevant"):
                item.parsed = True
        if row.state in (CandidateState.NEEDS_REVIEW, CandidateState.CHANGES_REQUESTED):
            item.awaiting_review += 1
        if fetched and row.state in (CandidateState.NEEDS_REVIEW, CandidateState.APPROVED) and not validation.get("problems"):
            item.valid += 1
        if row.last_error:
            last_error[row.source_id] = row.last_error

    for item in rows.values():
        item.fetchable = item.test_passed or item.fetched > 0
        item.producing = item.valid > 0
        item.needs_review = item.awaiting_review > 0
        if item.candidates and not item.fetched and not item.failed:
            item.failed = True
            item.problem = last_error.get(item.id) or "candidates exist but no page has been fetched"
        if item.failed:
            item.stage = "failed"
        elif item.producing:
            item.stage = "producing"
        elif item.parsed:
            item.stage = "parsed"
        elif item.fetchable:
            item.stage = "fetchable"
        elif item.tested:
            item.stage = "tested"
        report.registered += 1
        for name in ("tested", "test_passed", "fetchable", "parsed", "producing", "failed", "needs_review"):
            if getattr(item, name):
                setattr(report, name, getattr(report, name) + 1)
        report.never_tested += 0 if item.tested else 1
        report.by_stage[item.stage] = report.by_stage.get(item.stage, 0) + 1
        report.by_status[item.status] = report.by_status.get(item.status, 0) + 1
        report.by_connector[item.connector_key] = report.by_connector.get(item.connector_key, 0) + 1
        report.untraceable_candidates += item.untraceable_candidates
        report.sources.append(item)
    return report


__all__ = ["HealthReport", "STAGES", "SourceHealth", "source_health"]
