"""The ingestion pipeline: approved source → discovery → candidates → fetch → extract → validate →
de-duplicate → curator review → draft opportunity.

Guarantees:

* **Nothing is published here.** Approval creates a *draft* opportunity (with its source record, page
  snapshot and quoted rules); a curator publishes it through ``publish_opportunity``, which runs the
  publication checks. Pipeline code never writes an existing opportunity.
* **Idempotent discovery.** ``candidate_key`` = sha256(source id, canonical URL); re-discovering a page
  only refreshes ``last_seen_at``.
* **Safe concurrency and retries.** Candidates are leased with ``FOR UPDATE SKIP LOCKED`` and a lease
  timestamp, each candidate is committed on its own, a crashed worker's lease expires, and failures
  back off exponentially up to ``MAX_ATTEMPTS`` before the candidate is marked ``failed``.
* **Evidence first.** Every extracted claim carries a quote that must be on the fetched page
  (``validate.enforce_evidence``); missing or uncertain values stay missing or uncertain.
* **Conditional re-fetches.** A candidate keeps the ``ETag`` / ``Last-Modified`` of the response its
  page text came from and sends them on the next fetch. A 304 keeps the stored text, hash, extraction
  and validators, and returns the candidate to the state it was re-queued from; a failed request
  changes none of them.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.intelligence import registry
from app.intelligence.connectors import get_connector
from app.intelligence.connectors.base import PageContent, PageReader
from app.intelligence.discovery import OutOfScopeURLError, RejectedLead, collect_leads
from app.intelligence.extract import DeterministicExtractor, Extraction, Extractor, PageInput
from app.intelligence.fetcher import FetchError, OffAllowListError, SSRFBlockedError
from app.intelligence.lifecycle import is_discoverable
from app.intelligence.normalize import canonical_url, normalise_title
from app.intelligence.reader import (
    HTTPStatusError,
    RobotsDisallowedError,
    SafePageReader,
    UnsupportedContentTypeError,
    read_page,
)
from app.intelligence.text import parse_html
from app.intelligence.validate import validate
from app.models import AcquisitionSource, Opportunity, Requirement, Source
from app.models.enums import (
    AuthorityLevel,
    DeadlineType,
    LocationMode,
    OpportunityType,
    RequirementCategory,
    RequirementKind,
    SourceStatus,
    SourceType,
)
from app.models.ingestion import (
    MAX_ERROR_LENGTH,
    PROCESSABLE_STATES,
    CandidateState,
    IngestionCandidate,
    IngestionRun,
    RunKind,
    RunStatus,
)
from app.schemas import OpportunityCreate
from app.services import audit
from app.services.opportunities import create_opportunity

MAX_ATTEMPTS = 5
LEASE_DURATION = timedelta(minutes=10)
BASE_BACKOFF = timedelta(minutes=15)
_HTML_TYPES = ("text/html", "application/xhtml+xml")

ReaderFactory = Callable[[AcquisitionSource], PageReader]


class PipelineError(Exception):
    """A request the pipeline refuses (wrong state, missing curator input...)."""


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def default_reader(source: AcquisitionSource) -> SafePageReader:
    policy = source.crawl_policy or {}
    return SafePageReader(
        registry.allowed_hosts(source),
        min_delay_seconds=float(policy.get("min_delay_seconds", 5.0)),
    )


def candidate_key(source_id: uuid.UUID, url: str) -> str:
    return hashlib.sha256(f"{source_id}|{canonical_url(url)}".encode()).hexdigest()


def _error(text: str) -> str:
    return registry.sanitize_error(text)[:MAX_ERROR_LENGTH]


# --- discovery -----------------------------------------------------------------------------------------


@dataclass
class DiscoveryReport:
    run_id: uuid.UUID | None
    accepted: list[str] = field(default_factory=list)
    rejected: list[tuple[str, str]] = field(default_factory=list)
    new: int = 0
    seen_again: int = 0
    pages_read: int = 0
    error: str | None = None


def run_discovery(
    db: Session,
    source: AcquisitionSource,
    *,
    reader: PageReader | None = None,
    dry_run: bool = False,
    now: datetime | None = None,
) -> DiscoveryReport:
    """Collect leads from ``source``; unless ``dry_run``, record them as candidates (idempotently)."""
    now = now or now_utc()
    if not is_discoverable(SourceStatus(source.status)):
        raise PipelineError(f"Source {source.name!r} is {source.status}; discovery runs only while testing or approved.")
    reader = reader or default_reader(source)
    run: IngestionRun | None = None
    if not dry_run:
        run = IngestionRun(kind=RunKind.DISCOVER, source_id=source.id, dry_run=False, status=RunStatus.RUNNING)
        db.add(run)
        db.commit()
    report = DiscoveryReport(run_id=run.id if run else None)
    connector = get_connector(source.connector_key)()
    try:
        result = collect_leads(connector, registry.source_view(source), reader)
    except Exception as exc:  # noqa: BLE001 - recorded on the run and the source, never swallowed silently
        report.error = _error(f"{type(exc).__name__}: {exc}")
        if run is not None:
            run.status, run.error, run.finished_at = RunStatus.FAILED, report.error, now_utc()
            registry.record_run_failure(db, source, report.error)
            _record_robots(db, source, reader)
            db.commit()
        return report

    # Leads must also be allowed by robots.txt (a connector like url_list reads no page itself).
    allowed_by_robots = getattr(reader, "allowed_by_robots", None)
    if allowed_by_robots is not None:
        kept = []
        for lead in result.accepted:
            if allowed_by_robots(lead.url):
                kept.append(lead)
            else:
                result.rejected.append(RejectedLead(url=lead.url, reason="disallowed by robots.txt (or robots.txt unreachable)"))
        result.accepted = kept
    report.accepted = [lead.url for lead in result.accepted]
    report.rejected = [(item.url, item.reason) for item in result.rejected]
    report.pages_read = result.pages_read
    if run is None:
        return report

    for lead in result.accepted:
        statement = (
            insert(IngestionCandidate)
            .values(
                id=uuid.uuid4(),
                source_id=source.id,
                candidate_key=candidate_key(source.id, lead.url),
                url=canonical_url(lead.url),
                external_id=lead.external_id,
                state=CandidateState.DISCOVERED,
                discovery_run_id=run.id,
                discovered_at=now,
                last_seen_at=now,
                next_attempt_at=now,
            )
            .on_conflict_do_update(index_elements=["candidate_key"], set_={"last_seen_at": now})
            .returning(IngestionCandidate.discovery_run_id)
        )
        created_by = db.execute(statement).scalar_one()
        if created_by == run.id:
            report.new += 1
        else:
            report.seen_again += 1
    registry.record_run_success(db, source)
    _record_robots(db, source, reader)
    run.status = RunStatus.SUCCEEDED
    run.finished_at = now_utc()
    run.stats = {
        "accepted": len(report.accepted), "rejected": len(report.rejected), "new": report.new,
        "seen_again": report.seen_again, "pages_read": report.pages_read,
        "rejected_examples": [{"url": url, "reason": reason} for url, reason in report.rejected[:10]],
    }
    db.commit()
    return report


def robots_status_for(source: AcquisitionSource, reader: Any):
    """The robots.txt status of the source's primary host (its first allowed host), if it was read."""
    statuses = getattr(reader, "robots_status", {}) or {}
    for host in sorted(registry.allowed_hosts(source), key=lambda host: (host != source.base_domain, host)):
        if host in statuses:
            return statuses[host]
    return None


def _record_robots(db: Session, source: AcquisitionSource, reader: Any) -> None:
    status = robots_status_for(source, reader)
    if status is not None and status != source.robots_status:
        registry.record_robots_status(db, source, status)


# --- processing ----------------------------------------------------------------------------------------


@dataclass
class ProcessReport:
    run_id: uuid.UUID | None = None
    processed: int = 0
    by_state: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def lease_candidates(db: Session, *, limit: int, now: datetime, source_id: uuid.UUID | None = None) -> list[uuid.UUID]:
    """Claim up to ``limit`` due candidates for this worker; another worker skips them."""
    statement = (
        select(IngestionCandidate.id)
        .where(
            IngestionCandidate.state.in_([state.value for state in PROCESSABLE_STATES]),
            IngestionCandidate.next_attempt_at <= now,
            (IngestionCandidate.lease_until.is_(None)) | (IngestionCandidate.lease_until < now),
        )
        .order_by(IngestionCandidate.next_attempt_at, IngestionCandidate.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    if source_id is not None:
        statement = statement.where(IngestionCandidate.source_id == source_id)
    ids = list(db.scalars(statement))
    if ids:
        db.execute(
            update(IngestionCandidate)
            .where(IngestionCandidate.id.in_(ids))
            .values(lease_until=now + LEASE_DURATION)
            .execution_options(synchronize_session=False)
        )
    db.commit()
    return ids


def process_candidates(
    db: Session,
    *,
    limit: int = 20,
    reader_factory: ReaderFactory = default_reader,
    extractor: Extractor | None = None,
    now: datetime | None = None,
    source_id: uuid.UUID | None = None,
) -> ProcessReport:
    now = now or now_utc()
    extractor = extractor or DeterministicExtractor()
    run = IngestionRun(kind=RunKind.PROCESS, source_id=source_id, status=RunStatus.RUNNING)
    db.add(run)
    db.commit()
    report = ProcessReport(run_id=run.id)
    readers: dict[uuid.UUID, PageReader] = {}
    for candidate_id in lease_candidates(db, limit=limit, now=now, source_id=source_id):
        # Each candidate runs in a savepoint: a crash undoes only that candidate's partial work, then
        # the failure is recorded and committed on its own. Other candidates are unaffected.
        try:
            with db.begin_nested():
                state = _process_one(db, candidate_id, readers, reader_factory, extractor, now)
        except Exception as exc:  # noqa: BLE001 - one bad candidate must not stop the batch
            candidate = db.get(IngestionCandidate, candidate_id, with_for_update=True, populate_existing=True)
            state = _apply_failure(candidate, f"{type(exc).__name__}: {exc}", now) if candidate else "missing"
            report.errors.append(f"{candidate_id}: {type(exc).__name__}")
        db.commit()
        report.processed += 1
        report.by_state[str(state)] = report.by_state.get(str(state), 0) + 1
    run.status = RunStatus.SUCCEEDED
    run.finished_at = now_utc()
    run.stats = {"processed": report.processed, "by_state": report.by_state, "errors": report.errors[:20]}
    db.commit()
    return report


def _apply_failure(candidate: IngestionCandidate, message: str, now: datetime) -> str:
    """Count a failed attempt: retry later with exponential backoff, or give up after ``MAX_ATTEMPTS``."""
    candidate.attempts += 1
    candidate.last_error = _error(message)
    candidate.lease_until = None
    if candidate.attempts >= MAX_ATTEMPTS:
        candidate.state = CandidateState.FAILED
    else:
        candidate.state = CandidateState.RETRY
        candidate.next_attempt_at = now + BASE_BACKOFF * (2 ** (candidate.attempts - 1))
    return candidate.state


def _finish(db: Session, candidate: IngestionCandidate, state: CandidateState, *, error: str | None = None) -> str:
    candidate.state = state
    candidate.lease_until = None
    candidate.last_error = _error(error) if error else None
    db.flush()
    return state


def _process_one(
    db: Session,
    candidate_id: uuid.UUID,
    readers: dict[uuid.UUID, PageReader],
    reader_factory: ReaderFactory,
    extractor: Extractor,
    now: datetime,
) -> str:
    candidate = db.get(IngestionCandidate, candidate_id, with_for_update=True)
    if candidate is None or candidate.state not in PROCESSABLE_STATES:
        return "skipped"
    source = db.get(AcquisitionSource, candidate.source_id)
    if source is None or not is_discoverable(SourceStatus(source.status)):
        candidate.lease_until = None
        return "skipped"
    reader = readers.get(source.id)
    if reader is None:
        reader = readers[source.id] = reader_factory(source)

    # Validators are only meaningful for the page text we still hold.
    conditional = bool(candidate.page_text)
    try:
        page = read_page(
            reader, candidate.url,
            etag=candidate.etag if conditional else None,
            last_modified=candidate.last_modified if conditional else None,
        )
    except HTTPStatusError as exc:
        if exc.permanent:
            return _finish(db, candidate, CandidateState.REJECTED, error=f"page gone: HTTP {exc.status_code}")
        return _apply_failure(candidate, str(exc), now)
    except (RobotsDisallowedError, OffAllowListError, OutOfScopeURLError, SSRFBlockedError, UnsupportedContentTypeError) as exc:
        return _finish(db, candidate, CandidateState.REJECTED, error=f"not fetchable: {exc}")
    except FetchError as exc:
        return _apply_failure(candidate, str(exc), now)

    return _store_page(db, candidate, source, page, extractor, now)


def analyse_page(
    source: AcquisitionSource, page: PageContent, extractor: Extractor, today: date
) -> tuple[str, Extraction, Any]:
    """Pure part of processing: page → (text, extraction, validation). Used by preview and processing."""
    html = page.body.decode("utf-8", errors="replace")
    parsed = parse_html(html)
    final_url = page.final_url or page.url
    extraction = extractor.extract(PageInput(url=final_url, page=parsed, provider_name=source.provider_name))
    hosts = registry.allowed_hosts(source)
    validation = validate(extraction, parsed.text, allowed_hosts=hosts, today=today)
    return parsed.text, extraction, validation


def _store_page(
    db: Session, candidate: IngestionCandidate, source: AcquisitionSource, page: PageContent,
    extractor: Extractor, now: datetime,
) -> str:
    if page.status_code == 304:
        if not candidate.page_text:
            # A 304 with nothing stored to stand for it: treat as a failed fetch, never as content.
            return _apply_failure(candidate, "HTTP 304 for a page that has no stored content", now)
        return _not_modified(db, candidate, page, now)
    if page.content_type not in _HTML_TYPES:
        return _finish(db, candidate, CandidateState.REJECTED, error=f"not an HTML page ({page.content_type})")
    previous = candidate.extraction
    text, extraction, validation = analyse_page(source, page, extractor, now.date())
    candidate.final_url = canonical_url(page.final_url or page.url)
    candidate.http_status = page.status_code
    candidate.content_hash = hashlib.sha256(text.encode()).hexdigest()
    candidate.page_text = text
    candidate.fetched_at = now
    candidate.last_seen_at = now
    # The validators belong to this response; a server that stops sending them clears ours.
    candidate.etag = page.etag
    candidate.last_modified = page.last_modified
    candidate.resume_state = None
    candidate.extractor_version = extractor.version
    candidate.attempts = 0
    candidate.extraction = extraction.model_dump(mode="json")
    result = validation.as_dict()
    if previous:
        weakened = [
            name for name, item in previous.items()
            if isinstance(item, dict) and item.get("status") == "explicit"
            and candidate.extraction.get(name, {}).get("status") != "explicit"
        ]
        if weakened:
            result["warnings"].append(
                "re-fetched page no longer states: " + ", ".join(weakened) + " (previous values kept in 'previous')"
            )
            result["previous"] = {name: previous[name] for name in weakened}
    candidate.quality_score = validation.quality_score

    if validation.irrelevant:
        candidate.validation = result
        return _finish(db, candidate, CandidateState.REJECTED, error="not an opportunity page")

    duplicate = find_duplicate(db, candidate, extraction)
    candidate.duplicate_of_candidate_id = duplicate.candidate_id
    candidate.duplicate_of_opportunity_id = duplicate.opportunity_id
    if duplicate.note:
        result["warnings"].append(duplicate.note)
    candidate.validation = result
    if duplicate.is_duplicate:
        return _finish(db, candidate, CandidateState.DUPLICATE)
    if validation.expired:
        return _finish(db, candidate, CandidateState.EXPIRED)
    return _finish(db, candidate, CandidateState.NEEDS_REVIEW)


#: Outcomes that stand when a re-queued candidate's page turns out to be unchanged.
_RESUMABLE = (CandidateState.REJECTED, CandidateState.DUPLICATE)


def _not_modified(db: Session, candidate: IngestionCandidate, page: PageContent, now: datetime) -> str:
    """The server confirmed the stored page is current: keep everything, leave the processing queue.

    The stored text, hash, extraction and validation are untouched. A candidate that was rejected or
    marked duplicate before it was re-queued stays so; otherwise the stored validation decides, and a
    deadline that has passed in the meantime expires it.
    """
    candidate.last_seen_at = now
    candidate.attempts = 0
    if page.etag:
        candidate.etag = page.etag
    if page.last_modified:
        candidate.last_modified = page.last_modified
    previous, candidate.resume_state = candidate.resume_state, None
    validation = candidate.validation or {}
    deadline = (candidate.extraction or {}).get("deadline") or {}
    passed = (
        deadline.get("status") == "explicit" and isinstance(deadline.get("value"), str)
        and deadline["value"] < now.date().isoformat()
    )
    if previous in _RESUMABLE:
        return _finish(db, candidate, CandidateState(previous), error=candidate.last_error)
    if validation.get("irrelevant"):
        return _finish(db, candidate, CandidateState.REJECTED, error="not an opportunity page")
    if passed or validation.get("expired"):
        return _finish(db, candidate, CandidateState.EXPIRED)
    return _finish(db, candidate, CandidateState.NEEDS_REVIEW)


# --- de-duplication ------------------------------------------------------------------------------------


@dataclass
class DuplicateMatch:
    is_duplicate: bool = False
    candidate_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None
    note: str | None = None


def _deadline_year(value: Any) -> int | None:
    if isinstance(value, str) and len(value) >= 4 and value[:4].isdigit():
        return int(value[:4])
    if isinstance(value, datetime):
        return value.year
    return None


def _same_cycle(year_a: int | None, year_b: int | None) -> bool:
    """Unknown years can't prove a new cycle, so they count as the same one (the curator decides)."""
    return year_a is None or year_b is None or year_a == year_b


def find_duplicate(db: Session, candidate: IngestionCandidate, extraction: Extraction) -> DuplicateMatch:
    """Same page content, same official page, or same title from the same provider.

    A matching record whose deadline is in a different year is reported as a possible **new cycle**
    (not a duplicate), so next year's call reaches review instead of being dropped.
    """
    deadline_year = _deadline_year(extraction.deadline.value if extraction.deadline.status == "explicit" else None)
    open_states = [CandidateState.NEEDS_REVIEW, CandidateState.APPROVED, CandidateState.EXPIRED,
                   CandidateState.CHANGES_REQUESTED]

    same_content = db.scalar(
        select(IngestionCandidate.id).where(
            IngestionCandidate.content_hash == candidate.content_hash,
            IngestionCandidate.id != candidate.id,
            IngestionCandidate.state.in_(open_states),
        ).limit(1)
    )
    if same_content is not None:
        return DuplicateMatch(True, candidate_id=same_content, note="same page content as another candidate")

    url = candidate.final_url or candidate.url
    title_key = normalise_title(str(extraction.title.value or "")) if extraction.title.status == "explicit" else ""
    opportunities = db.execute(
        select(Opportunity.id, Opportunity.title, Opportunity.official_url, Opportunity.deadline_at, Opportunity.host_name)
    ).all()
    source_urls = {
        canonical_url(row.url): row.opportunity_id
        for row in db.execute(select(Source.url, Source.opportunity_id))
    }
    provider = (db.scalar(select(AcquisitionSource.provider_name).where(AcquisitionSource.id == candidate.source_id)) or "").casefold()
    for opportunity in opportunities:
        same_url = (opportunity.official_url and canonical_url(opportunity.official_url) == url) or source_urls.get(url) == opportunity.id
        same_title = bool(title_key) and normalise_title(opportunity.title) == title_key and (
            not opportunity.host_name or opportunity.host_name.casefold() == provider
        )
        if not (same_url or same_title):
            continue
        if _same_cycle(deadline_year, _deadline_year(opportunity.deadline_at)):
            return DuplicateMatch(True, opportunity_id=opportunity.id,
                                  note=f"matches existing opportunity {opportunity.title!r}")
        return DuplicateMatch(False, opportunity_id=opportunity.id,
                              note=f"possible new cycle of existing opportunity {opportunity.title!r}")

    if title_key:
        rows = db.execute(
            select(IngestionCandidate.id, IngestionCandidate.extraction).where(
                IngestionCandidate.source_id == candidate.source_id,
                IngestionCandidate.id != candidate.id,
                IngestionCandidate.state.in_(open_states),
            )
        ).all()
        for row in rows:
            other = row.extraction or {}
            other_title = (other.get("title") or {}).get("value")
            if not isinstance(other_title, str) or normalise_title(other_title) != title_key:
                continue
            other_deadline = other.get("deadline") or {}
            other_year = _deadline_year(other_deadline.get("value") if other_deadline.get("status") == "explicit" else None)
            if _same_cycle(deadline_year, other_year):
                return DuplicateMatch(True, candidate_id=row.id, note="same title as another candidate from this source")
            return DuplicateMatch(False, candidate_id=row.id, note="possible new cycle of another candidate")
    return DuplicateMatch()


# --- review --------------------------------------------------------------------------------------------


@dataclass
class ApprovalInput:
    """What a curator confirms or corrects when approving. ``None`` keeps the extracted value."""

    title: str | None = None
    opportunity_type: str | None = None
    deadline: date | None = None
    deadline_type: str | None = None
    description: str | None = None
    #: Indexes into the extracted eligibility statements to keep; None keeps all.
    statements: list[int] | None = None
    countries: list[str] | None = None
    notes: str | None = None
    #: Required to approve a candidate the pipeline marked expired or duplicate.
    force: bool = False


_MANDATORY = re.compile(r"\b(must|required|requires|only|eligible|open to|not eligible|ineligible|need to|may not|cannot|must not)\b", re.IGNORECASE)
_CATEGORY_HINTS = (
    (RequirementCategory.LANGUAGE, re.compile(r"\b(english|ielts|toefl|language|german|french)\b", re.IGNORECASE)),
    (RequirementCategory.ACADEMIC, re.compile(r"\b(gpa|grades?|degrees?|bachelor\w*|master\w*|phd|doctora\w*|enrol\w*|students?|post-?doctoral|universit\w*|colleges?|year of study|transcripts?|graduates?)\b", re.IGNORECASE)),
    (RequirementCategory.DEMOGRAPHIC, re.compile(r"\b(citizen|national|resident|age|years old|born|women|gender)\b", re.IGNORECASE)),
    (RequirementCategory.DOCUMENT, re.compile(r"\b(letter|cv|curriculum vitae|statement|essay|portfolio)\b", re.IGNORECASE)),
    (RequirementCategory.TIMING, re.compile(r"\b(deadline|available|duration|weeks|months|start)\b", re.IGNORECASE)),
)


def _requirement_category(statement: str) -> RequirementCategory:
    for category, pattern in _CATEGORY_HINTS:
        if pattern.search(statement):
            return category
    return RequirementCategory.OTHER


def _slug(title: str, deadline: date | None) -> str:
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")[:80] or "opportunity"
    suffix = f"-{deadline.year}" if deadline and str(deadline.year) not in base else ""
    return f"{base}{suffix}-{uuid.uuid4().hex[:6]}"


def _lock_candidate(db: Session, candidate_id: uuid.UUID) -> IngestionCandidate:
    candidate = db.scalar(
        select(IngestionCandidate).where(IngestionCandidate.id == candidate_id)
        .with_for_update().execution_options(populate_existing=True)
    )
    if candidate is None:
        raise PipelineError("Candidate not found.")
    return candidate


def approve_candidate(db: Session, candidate_id: uuid.UUID, *, actor_id: uuid.UUID, decision: ApprovalInput) -> Opportunity:
    """Create a draft opportunity from a reviewed candidate. Publication remains a separate, checked step."""
    candidate = _lock_candidate(db, candidate_id)
    if candidate.state == CandidateState.APPROVED:
        raise PipelineError("Candidate is already approved.")
    if candidate.state in (CandidateState.EXPIRED, CandidateState.DUPLICATE):
        if not decision.force:
            raise PipelineError(f"Candidate is {candidate.state}; approving it needs an explicit override.")
    elif candidate.state != CandidateState.NEEDS_REVIEW:
        raise PipelineError(f"Candidate is {candidate.state}; only reviewable candidates can be approved.")
    extraction = Extraction.model_validate(candidate.extraction or {})
    source = db.get(AcquisitionSource, candidate.source_id)
    if source is None or not candidate.page_text or not candidate.final_url:
        raise PipelineError("Candidate has no fetched page to publish from.")

    title = (decision.title or (extraction.title.value if extraction.title.status == "explicit" else "") or "").strip()
    if not title:
        raise PipelineError("A title is required (none was extracted).")
    category = decision.opportunity_type or (extraction.opportunity_type.value if extraction.opportunity_type.status != "not_found" else None)
    if category not in {item.value for item in OpportunityType}:
        raise PipelineError("Choose an opportunity type (none was recognised).")

    deadline_type = decision.deadline_type or (extraction.deadline_type.value if extraction.deadline_type.status == "explicit" else None)
    deadline_value = decision.deadline
    if deadline_value is None and extraction.deadline.status == "explicit" and decision.deadline_type in (None, "fixed"):
        deadline_value = date.fromisoformat(extraction.deadline.value)
    if deadline_type is None and deadline_value is not None:
        deadline_type = DeadlineType.FIXED.value
    if deadline_type not in {item.value for item in DeadlineType}:
        raise PipelineError("Confirm the deadline: give a date, or a deadline type of rolling or none.")
    if deadline_type == DeadlineType.FIXED and deadline_value is None:
        raise PipelineError("A fixed deadline needs a date.")

    statements: list[str] = list(extraction.eligibility.value or []) if extraction.eligibility.status == "explicit" else []
    if decision.statements is not None:
        try:
            statements = [statements[index] for index in decision.statements]
        except IndexError:
            raise PipelineError("A selected statement index does not exist.") from None
    statements = [statement for statement in statements if statement in candidate.page_text]
    if not statements:
        raise PipelineError("Keep at least one quoted eligibility statement (publication requires one).")

    description = decision.description or (extraction.description.value if extraction.description.status == "explicit" else None)
    countries = decision.countries if decision.countries is not None else (getattr(extraction, "countries", None) or [])
    payload = OpportunityCreate(
        slug=_slug(title, deadline_value),
        title=title[:255],
        description=description,
        host_name=source.provider_name,
        official_url=candidate.final_url,
        opportunity_type=category,
        # The page gives a date, not a time or zone: stored as the end of that day in UTC (documented).
        deadline_at=datetime.combine(deadline_value, time(23, 59), tzinfo=timezone.utc) if deadline_value else None,
        deadline_type=deadline_type,
        location_mode=LocationMode.UNKNOWN,
        countries=list(countries),
    )
    opportunity = create_opportunity(db, payload)
    snapshot_source = Source(
        opportunity_id=opportunity.id,
        source_type=SourceType.OFFICIAL_PAGE if source.authority_level == AuthorityLevel.OFFICIAL else SourceType.SCRAPED,
        url=candidate.final_url,
        publisher=source.provider_name,
        retrieved_at=candidate.fetched_at or now_utc(),
        content_hash=candidate.content_hash,
        raw_snapshot={"text": candidate.page_text, "extractor_version": candidate.extractor_version,
                      "candidate_id": str(candidate.id)},
        is_primary=True,
        notes="Created from ingestion candidate after curator review.",
    )
    db.add(snapshot_source)
    db.flush()
    for index, statement in enumerate(statements):
        db.add(Requirement(
            opportunity_id=opportunity.id,
            order_index=index,
            label=statement[:500],
            kind=RequirementKind.UNPARSED,
            params={},
            is_mandatory=bool(_MANDATORY.search(statement)),
            category=_requirement_category(statement),
            source_id=snapshot_source.id,
            source_quote=statement,
            is_ambiguous=True,
            notes="Quoted from the source page; not converted to a structured rule.",
        ))
    candidate.state = CandidateState.APPROVED
    candidate.opportunity_id = opportunity.id
    candidate.reviewed_by = actor_id
    candidate.reviewed_at = now_utc()
    candidate.review_notes = decision.notes
    overrides = {name: str(getattr(decision, name)) for name in ("title", "opportunity_type", "deadline", "deadline_type", "description")
                 if getattr(decision, name) is not None}
    audit.record(
        db, action="ingestion.candidate_approved", target_type="ingestion_candidate", target_id=candidate.id,
        actor_id=actor_id,
        changes={"opportunity_id": str(opportunity.id), "curator_overrides": overrides,
                 "statements_kept": len(statements), "forced": decision.force},
        reason=decision.notes,
    )
    db.flush()
    return opportunity


def decide_candidate(db: Session, candidate_id: uuid.UUID, *, actor_id: uuid.UUID, decision: str, notes: str | None) -> IngestionCandidate:
    """``reject`` or ``request_changes``. Both keep the candidate and its evidence for the record."""
    targets = {"reject": CandidateState.REJECTED, "request_changes": CandidateState.CHANGES_REQUESTED}
    if decision not in targets:
        raise PipelineError("Decision must be reject or request_changes.")
    candidate = _lock_candidate(db, candidate_id)
    if candidate.state == CandidateState.APPROVED:
        raise PipelineError("An approved candidate already has a draft opportunity; edit or close that instead.")
    if decision == "request_changes" and not (notes or "").strip():
        raise PipelineError("Say what needs correcting.")
    before = candidate.state
    candidate.state = targets[decision]
    candidate.reviewed_by = actor_id
    candidate.reviewed_at = now_utc()
    candidate.review_notes = notes
    audit.record(
        db, action=f"ingestion.candidate_{'rejected' if decision == 'reject' else 'changes_requested'}",
        target_type="ingestion_candidate", target_id=candidate.id, actor_id=actor_id,
        changes={"state": {"from": before, "to": candidate.state}}, reason=notes,
    )
    db.flush()
    return candidate


REQUEUEABLE = (
    CandidateState.FAILED, CandidateState.RETRY, CandidateState.CHANGES_REQUESTED, CandidateState.NEEDS_REVIEW,
    CandidateState.EXPIRED, CandidateState.DUPLICATE, CandidateState.REJECTED,
)


def requeue_candidate(db: Session, candidate_id: uuid.UUID, *, actor_id: uuid.UUID | None, now: datetime | None = None) -> IngestionCandidate:
    """Put a candidate back in the queue for a fresh fetch and extraction. Approved ones are never touched."""
    candidate = _lock_candidate(db, candidate_id)
    if candidate.state not in REQUEUEABLE:
        raise PipelineError(f"A {candidate.state} candidate cannot be re-queued.")
    before = candidate.state
    # Re-queueing twice in a row must not forget where the candidate originally was.
    if before not in PROCESSABLE_STATES:
        candidate.resume_state = before
    candidate.state = CandidateState.DISCOVERED
    candidate.attempts = 0
    candidate.next_attempt_at = now or now_utc()
    candidate.lease_until = None
    audit.record(db, action="ingestion.candidate_requeued", target_type="ingestion_candidate",
                 target_id=candidate.id, actor_id=actor_id, changes={"state": {"from": before, "to": "discovered"}})
    db.flush()
    return candidate


# --- expiry --------------------------------------------------------------------------------------------


def expire_candidates(db: Session, *, today: date) -> int:
    """Move needs-review candidates whose explicit deadline has passed to ``expired``."""
    rows = db.scalars(
        select(IngestionCandidate).where(IngestionCandidate.state == CandidateState.NEEDS_REVIEW).with_for_update(skip_locked=True)
    ).all()
    expired = 0
    for candidate in rows:
        deadline = (candidate.extraction or {}).get("deadline") or {}
        if deadline.get("status") == "explicit" and isinstance(deadline.get("value"), str) and deadline["value"] < today.isoformat():
            candidate.state = CandidateState.EXPIRED
            expired += 1
    db.flush()
    return expired


def stats(db: Session) -> dict[str, int]:
    rows = db.execute(select(IngestionCandidate.state, func.count()).group_by(IngestionCandidate.state)).all()
    return {state: count for state, count in rows}


__all__ = [
    "ApprovalInput",
    "DiscoveryReport",
    "MAX_ATTEMPTS",
    "PipelineError",
    "ProcessReport",
    "analyse_page",
    "approve_candidate",
    "candidate_key",
    "decide_candidate",
    "default_reader",
    "expire_candidates",
    "find_duplicate",
    "lease_candidates",
    "process_candidates",
    "requeue_candidate",
    "run_discovery",
    "stats",
]
