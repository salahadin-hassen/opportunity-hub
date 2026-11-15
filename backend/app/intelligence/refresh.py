"""Refresh: re-read the official page of a published (or closed) opportunity and report what changed.

Guarantees:

* **Read-only towards the opportunity.** A refresh never edits an opportunity, its requirements or the
  source snapshot they were quoted from. It writes one ``OpportunityRefreshCheck`` row per check; a
  finding waits there (``review_state = 'pending'``) for a curator, who changes the opportunity by the
  normal curator routes if it is real.
* **History is kept.** Each check that received new content stores that page text; with the original
  snapshot on the opportunity's source these rows are the page's history.
* **Same access rules as ingestion.** A page is fetched only when an *approved* acquisition source
  covers its host, through that source's reader (robots.txt, host allow-list on every redirect, SSRF
  guard). An opportunity no approved source covers is skipped and reported, never fetched.
* **Conditional requests.** The validators of the last successful read are sent; a 304 costs no
  download and no extraction. A failed request keeps the validators and the content hash.
* **No duplicates.** A new application cycle becomes one review *candidate* per cycle year (its own
  ``candidate_key``); approving it creates a separate draft. A finding is raised once: the same
  finding on a later check is recorded without asking for review again.

Outcomes (``RefreshOutcome``), decided in this order once a page has been read:

1. the page no longer looks like an opportunity page, or it carries none of the approved eligibility
   quotes and states no deadline or eligibility of its own → ``review_required`` (the page was
   probably replaced or moved);
2. it states a deadline at least ``NEW_CYCLE_MIN_DAYS`` after the approved one → ``new_cycle``;
3. it says applications are closed → ``closed``;
4. it states a different deadline closer than that → ``deadline_changed`` (a much *earlier* one is
   ``review_required``: the page may be showing an older cycle);
5. an approved eligibility quote is gone, or the page states rules it did not state before
   → ``material_update``;
6. the approved deadline can no longer be found on the page → ``review_required``;
7. otherwise ``unchanged`` — and, whatever the page says, a published opportunity whose approved
   fixed deadline has passed is ``closed`` (an expired cycle).

A page that could not be read is ``source_unavailable``; it asks for review at once when the link is
dead (404/410) and after ``UNAVAILABLE_REVIEW_AFTER`` failures in a row otherwise.

For an opportunity that is already closed, only ``new_cycle`` asks for review.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.intelligence import pipeline, registry
from app.intelligence.connectors.base import PageContent, PageReader
from app.intelligence.discovery import OutOfScopeURLError, check_in_scope
from app.intelligence.extract import DeterministicExtractor, Extraction, Extractor
from app.intelligence.fetcher import FetchError
from app.intelligence.normalize import canonical_url, find_dates
from app.intelligence.reader import HTTPStatusError, read_page
from app.intelligence.source_test import classify_failure
from app.models import AcquisitionSource, IngestionCandidate, IngestionRun, Opportunity, Requirement, Source
from app.models.enums import DeadlineType, OpportunityStatus, SourceStatus
from app.models.ingestion import CandidateState, RunKind, RunStatus
from app.models.refresh import OpportunityRefreshCheck, RefreshOutcome, RefreshReviewState
from app.services import audit

#: A stated deadline this many days after the approved one is the next cycle, not a correction.
NEW_CYCLE_MIN_DAYS = 180
#: Transient failures in a row before an unreadable page is put in front of a curator.
UNAVAILABLE_REVIEW_AFTER = 3
#: A refresh run older than this is assumed dead and no longer blocks a new one.
RUN_LEASE = timedelta(minutes=60)
DEFAULT_MIN_INTERVAL = timedelta(hours=24)
MAX_QUOTES_REPORTED = 20
_HTML_TYPES = ("text/html", "application/xhtml+xml")
_REFRESHABLE = (OpportunityStatus.PUBLISHED, OpportunityStatus.CLOSED)

ReaderFactory = pipeline.ReaderFactory


class RefreshError(Exception):
    """A request the refresh refuses (unknown check, already reviewed...)."""


@dataclass
class RefreshResult:
    opportunity_id: uuid.UUID
    title: str
    outcome: str
    review_state: str
    check_id: uuid.UUID
    summary: str = ""


@dataclass
class SkippedOpportunity:
    opportunity_id: uuid.UUID
    title: str
    reason: str


@dataclass
class RefreshReport:
    run_id: uuid.UUID | None = None
    #: True when another refresh run was already in progress; nothing was checked.
    busy: bool = False
    checked: int = 0
    by_outcome: dict[str, int] = field(default_factory=dict)
    pending_review: int = 0
    results: list[RefreshResult] = field(default_factory=list)
    skipped: list[SkippedOpportunity] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _utc_date(value: datetime | None) -> date | None:
    return value.astimezone(timezone.utc).date() if value is not None else None


def _fingerprint(outcome: str, facts: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps({"outcome": outcome, **facts}, sort_keys=True, default=str).encode()).hexdigest()


# --- comparison (pure) ---------------------------------------------------------------------------------


@dataclass
class Comparison:
    outcome: RefreshOutcome
    findings: dict[str, Any]
    #: The facts that identify this finding, for ``fingerprint``.
    facts: dict[str, Any]
    #: The deadline that marks a new cycle, when ``outcome`` is ``new_cycle``.
    new_cycle_deadline: date | None = None


def compare_page(
    *,
    status: str,
    deadline_type: str,
    approved_deadline: date | None,
    approved_quotes: list[str],
    text: str,
    baseline_text: str | None,
    extraction: Extraction,
    irrelevant: bool,
    today: date,
    newer_cycle_listed: bool = False,
) -> Comparison:
    """What a freshly read page means for an approved opportunity. No database, no network.

    ``baseline_text`` is the page text last held for this opportunity (None when there is none): a
    rule counts as *new* only if the page states it now and did not then.
    ``newer_cycle_listed`` says another opportunity already covers the later deadline on this page.
    """
    findings: dict[str, Any] = {}
    page = _norm(text)

    if irrelevant:
        findings["not_an_opportunity_page"] = {
            "relevance": extraction.relevance, "signals": extraction.relevance_signals,
        }
        return Comparison(RefreshOutcome.REVIEW_REQUIRED, findings, {"reason": "not_an_opportunity_page"})

    # --- deadline
    deadline = extraction.deadline
    stated: date | None = None
    if deadline.status == "explicit" and isinstance(deadline.value, str):
        try:
            stated = date.fromisoformat(deadline.value[:10])
        except ValueError:
            stated = None
    quote = deadline.evidence[0].quote if deadline.evidence else None
    new_cycle: date | None = None
    changed_to: date | None = None
    earlier: date | None = None
    deadline_missing = False
    if stated is not None:
        if approved_deadline is None:
            if deadline_type != DeadlineType.FIXED:
                changed_to = stated
                findings["deadline"] = {"approved": None, "approved_type": deadline_type, "page_states": stated.isoformat(), "quote": quote}
        elif stated != approved_deadline:
            delta = (stated - approved_deadline).days
            detail = {"approved": approved_deadline.isoformat(), "page_states": stated.isoformat(), "days_later": delta, "quote": quote}
            if delta >= NEW_CYCLE_MIN_DAYS:
                if newer_cycle_listed:
                    findings["new_cycle_already_listed"] = detail
                else:
                    new_cycle = stated
                    findings["new_cycle"] = detail
            elif delta <= -NEW_CYCLE_MIN_DAYS:
                earlier = stated
                findings["earlier_deadline"] = detail
            else:
                changed_to = stated
                findings["deadline"] = detail
    elif approved_deadline is not None:
        mentioned = {mention.value for mention in find_dates(text) if mention.value is not None}
        if approved_deadline not in mentioned:
            deadline_missing = True
            findings["deadline_not_found"] = {
                "approved": approved_deadline.isoformat(), "extractor_status": deadline.status,
                "note": deadline.note, "page_dates": sorted(value.isoformat() for value in mentioned)[:10],
            }

    # --- closed in words
    application = extraction.application_status
    closed_quote: str | None = None
    if application.status == "explicit" and application.value == "closed":
        closed_quote = application.evidence[0].quote if application.evidence else ""
        findings["closed_on_page"] = {"quote": closed_quote}

    # --- eligibility
    missing = [quote_ for quote_ in approved_quotes if _norm(quote_) not in page]
    approved = {_norm(quote_) for quote_ in approved_quotes}
    added: list[str] = []
    if baseline_text is not None and extraction.eligibility.status == "explicit":
        baseline = _norm(baseline_text)
        added = [
            statement for statement in (extraction.eligibility.value or [])
            if _norm(statement) not in approved and _norm(statement) not in baseline
        ]
    if missing or added:
        findings["eligibility"] = {
            "approved_quotes_missing": missing[:MAX_QUOTES_REPORTED],
            "new_statements": added[:MAX_QUOTES_REPORTED],
        }

    # Nothing that was approved is on the page and it states no opportunity facts of its own: this
    # is a replaced or emptied page, not an update to the opportunity.
    if (
        approved_quotes and len(missing) == len(approved_quotes) and stated is None and closed_quote is None
        and extraction.eligibility.status != "explicit"
    ):
        findings["opportunity_content_missing"] = {"approved_quotes_missing": len(missing)}
        return Comparison(RefreshOutcome.REVIEW_REQUIRED, findings, {"reason": "opportunity_content_missing"})

    expired = (
        status == OpportunityStatus.PUBLISHED and deadline_type == DeadlineType.FIXED
        and approved_deadline is not None and approved_deadline < today
    )
    if expired:
        findings["deadline_passed"] = {"approved": approved_deadline.isoformat(), "today": today.isoformat()}

    if new_cycle is not None:
        return Comparison(RefreshOutcome.NEW_CYCLE, findings,
                          {"approved": str(approved_deadline), "cycle_year": new_cycle.year}, new_cycle)
    if closed_quote is not None:
        return Comparison(RefreshOutcome.CLOSED, findings, {"reason": "closed_on_page"})
    if changed_to is not None and not (expired and changed_to < today):
        return Comparison(RefreshOutcome.DEADLINE_CHANGED, findings,
                          {"approved": str(approved_deadline), "page_states": changed_to.isoformat()})
    if expired:
        return Comparison(RefreshOutcome.CLOSED, findings, {"reason": "deadline_passed", "approved": str(approved_deadline)})
    if missing or added:
        return Comparison(RefreshOutcome.MATERIAL_UPDATE, findings,
                          {"missing": sorted(_norm(item) for item in missing), "added": sorted(_norm(item) for item in added)})
    if earlier is not None:
        return Comparison(RefreshOutcome.REVIEW_REQUIRED, findings,
                          {"reason": "earlier_deadline", "page_states": earlier.isoformat()})
    if deadline_missing:
        return Comparison(RefreshOutcome.REVIEW_REQUIRED, findings,
                          {"reason": "deadline_not_found", "approved": str(approved_deadline)})
    return Comparison(RefreshOutcome.UNCHANGED, findings, {})


# --- one opportunity -----------------------------------------------------------------------------------


def _latest_check(db: Session, opportunity_id: uuid.UUID) -> OpportunityRefreshCheck | None:
    return db.scalar(
        select(OpportunityRefreshCheck)
        .where(OpportunityRefreshCheck.opportunity_id == opportunity_id)
        .order_by(OpportunityRefreshCheck.checked_at.desc(), OpportunityRefreshCheck.id.desc())
        .limit(1)
    )


def _baseline_text(db: Session, opportunity_id: uuid.UUID, primary: Source | None) -> str | None:
    """The page text last held: the newest check that stored one, else the original snapshot."""
    stored = db.scalar(
        select(OpportunityRefreshCheck.page_text)
        .where(OpportunityRefreshCheck.opportunity_id == opportunity_id, OpportunityRefreshCheck.page_text.is_not(None))
        .order_by(OpportunityRefreshCheck.checked_at.desc(), OpportunityRefreshCheck.id.desc())
        .limit(1)
    )
    if stored is not None:
        return stored
    snapshot = primary.raw_snapshot if primary is not None else None
    if isinstance(snapshot, dict) and isinstance(snapshot.get("text"), str):
        return snapshot["text"]
    return snapshot if isinstance(snapshot, str) else None


def _acquisition_source(db: Session, opportunity: Opportunity, url: str) -> tuple[AcquisitionSource | None, str | None]:
    """The approved source whose rules cover ``url``, or the reason there is none."""
    source = db.scalar(
        select(AcquisitionSource)
        .join(IngestionCandidate, IngestionCandidate.source_id == AcquisitionSource.id)
        .where(IngestionCandidate.opportunity_id == opportunity.id)
        .limit(1)
    )
    host = (urlsplit(url).hostname or "").lower()
    if source is None or host not in registry.allowed_hosts(source):
        source = registry.find_source_for_host(db, host)
    if source is None:
        return None, f"no acquisition source covers {host or 'this URL'}"
    if SourceStatus(source.status) != SourceStatus.APPROVED:
        return None, f"source {source.name!r} is {source.status}, not approved"
    try:
        check_in_scope(url, registry.allowed_hosts(source))
    except OutOfScopeURLError as error:
        return None, f"URL is outside the source's rules: {error}"
    return source, None


def _raised_before(db: Session, opportunity_id: uuid.UUID, fingerprint: str) -> bool:
    return db.scalar(
        select(OpportunityRefreshCheck.id).where(
            OpportunityRefreshCheck.opportunity_id == opportunity_id,
            OpportunityRefreshCheck.fingerprint == fingerprint,
            OpportunityRefreshCheck.review_state != RefreshReviewState.NONE,
        ).limit(1)
    ) is not None


def _newer_cycle_listed(db: Session, opportunity: Opportunity, url: str, year: int) -> bool:
    """Whether another opportunity for the same page already has a deadline in ``year``."""
    target = canonical_url(url)
    rows = db.execute(
        select(Opportunity.official_url, Opportunity.deadline_at).where(
            Opportunity.id != opportunity.id,
            Opportunity.status != OpportunityStatus.ARCHIVED,
            Opportunity.official_url.is_not(None),
            Opportunity.deadline_at.is_not(None),
        )
    ).all()
    return any(
        canonical_url(row.official_url) == target and _utc_date(row.deadline_at).year == year for row in rows
    )


def _new_cycle_candidate(
    db: Session, *, opportunity: Opportunity, source: AcquisitionSource, url: str, page: PageContent, text: str,
    content_hash: str, extraction: Extraction, validation: Any, extractor: Extractor, cycle: date,
    run_id: uuid.UUID | None, now: datetime,
) -> uuid.UUID:
    """Put the next cycle in the curator's candidate queue, once per cycle year."""
    key = hashlib.sha256(f"{source.id}|{canonical_url(url)}|cycle:{cycle.year}".encode()).hexdigest()
    result = validation.as_dict()
    result["warnings"].append(f"possible new cycle of existing opportunity {opportunity.title!r} (found by refresh)")
    statement = (
        insert(IngestionCandidate)
        .values(
            id=uuid.uuid4(), source_id=source.id, candidate_key=key, url=canonical_url(url),
            state=CandidateState.EXPIRED if validation.expired else CandidateState.NEEDS_REVIEW,
            final_url=canonical_url(page.final_url or url), http_status=page.status_code,
            content_hash=content_hash, page_text=text, fetched_at=now, etag=page.etag,
            last_modified=page.last_modified, extraction=extraction.model_dump(mode="json"),
            extractor_version=extractor.version, validation=result, quality_score=validation.quality_score,
            duplicate_of_opportunity_id=opportunity.id, discovery_run_id=run_id,
            discovered_at=now, last_seen_at=now, next_attempt_at=now,
        )
        .on_conflict_do_nothing(index_elements=["candidate_key"])
    )
    db.execute(statement)
    return db.scalar(select(IngestionCandidate.id).where(IngestionCandidate.candidate_key == key))


def _summary(outcome: str, findings: dict[str, Any], error: str | None) -> str:
    if outcome == RefreshOutcome.SOURCE_UNAVAILABLE:
        return error or "page could not be read"
    parts = []
    for key in ("new_cycle", "deadline", "earlier_deadline"):
        if key in findings:
            parts.append(f"deadline {findings[key].get('approved')} → {findings[key].get('page_states')}")
    if "closed_on_page" in findings:
        parts.append("page says applications are closed")
    if "deadline_passed" in findings:
        parts.append(f"approved deadline {findings['deadline_passed']['approved']} has passed")
    if "eligibility" in findings:
        parts.append(f"{len(findings['eligibility']['approved_quotes_missing'])} approved quote(s) missing, "
                     f"{len(findings['eligibility']['new_statements'])} new statement(s)")
    if "deadline_not_found" in findings:
        parts.append("approved deadline no longer found on the page")
    if "not_an_opportunity_page" in findings or "opportunity_content_missing" in findings:
        parts.append("page no longer describes the opportunity")
    return "; ".join(parts)


def refresh_one(
    db: Session,
    opportunity: Opportunity,
    *,
    readers: dict[uuid.UUID, PageReader],
    reader_factory: ReaderFactory,
    extractor: Extractor,
    now: datetime,
    run_id: uuid.UUID | None = None,
) -> RefreshResult | SkippedOpportunity:
    """Check one opportunity and record the result. Never modifies the opportunity."""
    primary = db.scalar(select(Source).where(Source.opportunity_id == opportunity.id, Source.is_primary))
    url = (primary.url if primary is not None else None) or opportunity.official_url
    if not url:
        return SkippedOpportunity(opportunity.id, opportunity.title, "no official URL")
    source, reason = _acquisition_source(db, opportunity, url)
    if source is None:
        return SkippedOpportunity(opportunity.id, opportunity.title, reason or "no approved source")

    previous = _latest_check(db, opportunity.id)
    baseline_hash = (previous.content_hash if previous is not None else None) or (primary.content_hash if primary else None)
    etag = previous.etag if previous is not None and baseline_hash else None
    last_modified = previous.last_modified if previous is not None and baseline_hash else None
    published = opportunity.status == OpportunityStatus.PUBLISHED
    approved_deadline = _utc_date(opportunity.deadline_at)
    today = now.date()

    check = OpportunityRefreshCheck(
        opportunity_id=opportunity.id, acquisition_source_id=source.id, url=url, checked_at=now,
        content_hash=baseline_hash, etag=etag, last_modified=last_modified,
    )
    reader = readers.get(source.id)
    if reader is None:
        reader = readers[source.id] = reader_factory(source)

    page: PageContent | None = None
    try:
        page = read_page(reader, url, etag=etag, last_modified=last_modified)
        if page.status_code != 304 and page.content_type not in _HTML_TYPES:
            raise FetchError(f"not an HTML page ({page.content_type})")
        if page.status_code == 304 and not baseline_hash:
            raise FetchError("HTTP 304 for a page that has no stored content")
    except (FetchError, OutOfScopeURLError) as error:
        # The validators and the content hash carried over above are left as they were.
        kind, status_code = classify_failure(error)
        permanent = isinstance(error, HTTPStatusError) and error.permanent
        check.outcome = RefreshOutcome.SOURCE_UNAVAILABLE
        check.http_status = status_code
        check.error = registry.sanitize_error(f"{kind}: {error}")[:500]
        check.consecutive_failures = (previous.consecutive_failures if previous is not None else 0) + 1
        check.findings = {"source_unavailable": {"kind": kind, "permanent": permanent, "failures_in_a_row": check.consecutive_failures}}
        last_ok = db.scalar(
            select(OpportunityRefreshCheck.id).where(
                OpportunityRefreshCheck.opportunity_id == opportunity.id,
                OpportunityRefreshCheck.outcome != RefreshOutcome.SOURCE_UNAVAILABLE,
            ).order_by(OpportunityRefreshCheck.checked_at.desc(), OpportunityRefreshCheck.id.desc()).limit(1)
        )
        facts = {"episode_after": str(last_ok)}
        wants_review = published and (permanent or check.consecutive_failures >= UNAVAILABLE_REVIEW_AFTER)
        return _record(db, opportunity, check, facts, wants_review)

    check.http_status = page.status_code
    comparison: Comparison
    if page.status_code == 304:
        if page.etag:
            check.etag = page.etag
        if page.last_modified:
            check.last_modified = page.last_modified
        comparison = _unchanged(opportunity, approved_deadline, today)
    else:
        text, extraction, validation = pipeline.analyse_page(source, page, extractor, today)
        content_hash = hashlib.sha256(text.encode()).hexdigest()
        check.etag, check.last_modified = page.etag, page.last_modified
        if content_hash == baseline_hash:
            comparison = _unchanged(opportunity, approved_deadline, today)
        else:
            quotes = list(db.scalars(
                select(Requirement.source_quote)
                .where(Requirement.opportunity_id == opportunity.id, Requirement.source_quote.is_not(None))
                .order_by(Requirement.order_index)
            ))
            stated = extraction.deadline.value if extraction.deadline.status == "explicit" else None
            listed = False
            if isinstance(stated, str) and stated[:4].isdigit():
                listed = _newer_cycle_listed(db, opportunity, url, int(stated[:4]))
            comparison = compare_page(
                status=opportunity.status, deadline_type=opportunity.deadline_type,
                approved_deadline=approved_deadline, approved_quotes=[quote for quote in quotes if quote],
                text=text, baseline_text=_baseline_text(db, opportunity.id, primary), extraction=extraction,
                irrelevant=validation.irrelevant, today=today, newer_cycle_listed=listed,
            )
            check.content_changed = True
            check.content_hash = content_hash
            check.page_text = text
            check.extraction = extraction.model_dump(mode="json")
            if comparison.outcome == RefreshOutcome.NEW_CYCLE and comparison.new_cycle_deadline is not None:
                check.candidate_id = _new_cycle_candidate(
                    db, opportunity=opportunity, source=source, url=url, page=page, text=text,
                    content_hash=content_hash, extraction=extraction, validation=validation,
                    extractor=extractor, cycle=comparison.new_cycle_deadline, run_id=run_id, now=now,
                )

    check.outcome = comparison.outcome
    check.findings = comparison.findings
    wants_review = comparison.outcome != RefreshOutcome.UNCHANGED and (
        published or comparison.outcome == RefreshOutcome.NEW_CYCLE
    )
    return _record(db, opportunity, check, comparison.facts, wants_review)


def _unchanged(opportunity: Opportunity, approved_deadline: date | None, today: date) -> Comparison:
    """The page is as last read. Only the calendar can still have moved: the cycle may have expired."""
    if (
        opportunity.status == OpportunityStatus.PUBLISHED and opportunity.deadline_type == DeadlineType.FIXED
        and approved_deadline is not None and approved_deadline < today
    ):
        findings = {"deadline_passed": {"approved": approved_deadline.isoformat(), "today": today.isoformat()}}
        return Comparison(RefreshOutcome.CLOSED, findings, {"reason": "deadline_passed", "approved": str(approved_deadline)})
    return Comparison(RefreshOutcome.UNCHANGED, {}, {})


def _record(
    db: Session, opportunity: Opportunity, check: OpportunityRefreshCheck, facts: dict[str, Any], wants_review: bool,
) -> RefreshResult:
    check.fingerprint = _fingerprint(check.outcome, facts)
    pending = wants_review and not _raised_before(db, opportunity.id, check.fingerprint)
    check.review_state = RefreshReviewState.PENDING if pending else RefreshReviewState.NONE
    db.add(check)
    db.flush()
    if pending:
        audit.record(
            db, action="opportunity.refresh_finding", target_type="opportunity", target_id=opportunity.id,
            actor_kind="system", changes={"check_id": str(check.id), "outcome": str(check.outcome)},
        )
    return RefreshResult(
        opportunity_id=opportunity.id, title=opportunity.title, outcome=str(check.outcome),
        review_state=str(check.review_state), check_id=check.id,
        summary=_summary(check.outcome, check.findings or {}, check.error),
    )


# --- a run ---------------------------------------------------------------------------------------------


def _due(
    db: Session, *, limit: int, now: datetime, min_interval: timedelta, opportunity_id: uuid.UUID | None,
) -> list[Opportunity]:
    last = (
        select(OpportunityRefreshCheck.opportunity_id, func.max(OpportunityRefreshCheck.checked_at).label("last_checked"))
        .group_by(OpportunityRefreshCheck.opportunity_id)
        .subquery()
    )
    statement = (
        select(Opportunity)
        .outerjoin(last, last.c.opportunity_id == Opportunity.id)
        .where(Opportunity.status.in_([status.value for status in _REFRESHABLE]))
        .order_by(last.c.last_checked.asc().nulls_first(), Opportunity.id)
        .limit(limit)
    )
    if opportunity_id is not None:
        statement = statement.where(Opportunity.id == opportunity_id)
    else:
        statement = statement.where((last.c.last_checked.is_(None)) | (last.c.last_checked <= now - min_interval))
    return list(db.scalars(statement))


def refresh_opportunities(
    db: Session,
    *,
    limit: int = 20,
    reader_factory: ReaderFactory = pipeline.default_reader,
    extractor: Extractor | None = None,
    now: datetime | None = None,
    opportunity_id: uuid.UUID | None = None,
    min_interval: timedelta = DEFAULT_MIN_INTERVAL,
) -> RefreshReport:
    """Check up to ``limit`` published or closed opportunities, least recently checked first.

    One run at a time: a second caller while a run is in progress returns ``busy`` and checks nothing.
    Each opportunity is committed on its own; one that fails does not stop the rest.
    """
    now = now or pipeline.now_utc()
    extractor = extractor or DeterministicExtractor()
    run = IngestionRun(kind=RunKind.REFRESH, status=RunStatus.RUNNING)
    db.add(run)
    db.commit()
    report = RefreshReport(run_id=run.id)
    other = db.scalar(
        select(IngestionRun.id).where(
            IngestionRun.kind == RunKind.REFRESH, IngestionRun.status == RunStatus.RUNNING,
            IngestionRun.id != run.id, IngestionRun.started_at >= func.now() - RUN_LEASE,
            (IngestionRun.started_at < run.started_at)
            | ((IngestionRun.started_at == run.started_at) & (IngestionRun.id < run.id)),
        ).limit(1)
    )
    if other is not None:
        report.busy = True
        run.status, run.error, run.finished_at = RunStatus.FAILED, "another refresh run is in progress", pipeline.now_utc()
        db.commit()
        return report

    readers: dict[uuid.UUID, PageReader] = {}
    for opportunity in _due(db, limit=limit, now=now, min_interval=min_interval, opportunity_id=opportunity_id):
        opportunity_id_, title = opportunity.id, opportunity.title
        try:
            with db.begin_nested():
                result = refresh_one(
                    db, opportunity, readers=readers, reader_factory=reader_factory, extractor=extractor,
                    now=now, run_id=run.id,
                )
        except Exception as exc:  # noqa: BLE001 - one bad opportunity must not stop the run
            report.errors.append(f"{opportunity_id_}: {type(exc).__name__}: {registry.sanitize_error(str(exc))[:200]}")
            db.commit()
            continue
        db.commit()
        if isinstance(result, SkippedOpportunity):
            report.skipped.append(SkippedOpportunity(opportunity_id_, title, result.reason))
            continue
        report.checked += 1
        report.results.append(result)
        report.by_outcome[result.outcome] = report.by_outcome.get(result.outcome, 0) + 1
        if result.review_state == RefreshReviewState.PENDING:
            report.pending_review += 1
    run.status = RunStatus.SUCCEEDED
    run.finished_at = pipeline.now_utc()
    run.stats = {
        "checked": report.checked, "by_outcome": report.by_outcome, "pending_review": report.pending_review,
        "skipped": len(report.skipped), "errors": report.errors[:20],
    }
    db.commit()
    return report


# --- review --------------------------------------------------------------------------------------------


def resolve_check(
    db: Session, check_id: uuid.UUID, *, actor_id: uuid.UUID, decision: str, notes: str | None,
) -> OpportunityRefreshCheck:
    """``acknowledge`` (handled) or ``dismiss`` (not a real change) a pending finding.

    Neither changes the opportunity: a curator who agrees with a finding edits, closes or re-approves
    it through the normal curator routes, then acknowledges the check.
    """
    targets = {"acknowledge": RefreshReviewState.ACKNOWLEDGED, "dismiss": RefreshReviewState.DISMISSED}
    if decision not in targets:
        raise RefreshError("Decision must be acknowledge or dismiss.")
    check = db.scalar(
        select(OpportunityRefreshCheck).where(OpportunityRefreshCheck.id == check_id)
        .with_for_update().execution_options(populate_existing=True)
    )
    if check is None:
        raise RefreshError("Refresh check not found.")
    if check.review_state != RefreshReviewState.PENDING:
        raise RefreshError(f"This check is {check.review_state}; only a pending finding can be resolved.")
    if decision == "dismiss" and not (notes or "").strip():
        raise RefreshError("Say why the finding is not a real change.")
    check.review_state = targets[decision]
    check.reviewed_by = actor_id
    check.reviewed_at = pipeline.now_utc()
    check.review_notes = notes
    audit.record(
        db, action=f"opportunity.refresh_finding_{'acknowledged' if decision == 'acknowledge' else 'dismissed'}",
        target_type="opportunity", target_id=check.opportunity_id, actor_id=actor_id,
        changes={"check_id": str(check.id), "outcome": str(check.outcome)}, reason=notes,
    )
    db.flush()
    return check


__all__ = [
    "Comparison",
    "DEFAULT_MIN_INTERVAL",
    "NEW_CYCLE_MIN_DAYS",
    "RefreshError",
    "RefreshReport",
    "RefreshResult",
    "SkippedOpportunity",
    "UNAVAILABLE_REVIEW_AFTER",
    "compare_page",
    "refresh_one",
    "refresh_opportunities",
    "resolve_check",
]
