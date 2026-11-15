"""Persistence services for opportunities."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models import Opportunity, OpportunityStatus
from app.schemas import OpportunityCreate, OpportunityUpdate

#: Statuses anyone may read one opportunity in. Closed calls stay readable
#: so links and past matches keep resolving; drafts and archived rows never
#: leave the curator side.
PUBLIC_STATUSES = (OpportunityStatus.PUBLISHED, OpportunityStatus.CLOSED)


class OpportunitySlugConflictError(Exception):
    """Raised when an opportunity slug is already in use."""


class IncompleteOpportunityError(ValueError):
    """Raised when attempting to publish an opportunity that lacks required verification."""


class InvalidStatusTransitionError(ValueError):
    """Raised when a lifecycle operation is not allowed from the opportunity's current status."""


#: Lifecycle fields only ``publish_opportunity`` and ``close_opportunity`` may write.
LIFECYCLE_FIELDS = frozenset({"status", "published_at"})
#: Statuses an opportunity may be published from.
PUBLISHABLE_FROM = (OpportunityStatus.DRAFT, OpportunityStatus.CLOSED)


def is_public(opportunity: Opportunity) -> bool:
    """Return whether ``opportunity`` may be shown outside the curator side."""
    return opportunity.status in PUBLIC_STATUSES


def create_opportunity(db: Session, payload: OpportunityCreate) -> Opportunity:
    """Persist a new opportunity as a draft and return its refreshed database record.

    The status is forced here as well as by the schema, so no caller can create a
    published (or publicly readable closed) row without ``publish_opportunity``.
    """
    data = payload.model_dump()
    if LIFECYCLE_FIELDS & data.keys():
        raise ValueError("Lifecycle fields cannot be set on create.")
    opportunity = Opportunity(**data, status=OpportunityStatus.DRAFT, published_at=None)
    try:
        with db.begin_nested():
            db.add(opportunity)
            db.flush()
    except IntegrityError as error:
        raise OpportunitySlugConflictError from error
    db.refresh(opportunity)
    return opportunity


def list_opportunities(db: Session, limit: int, offset: int) -> list[Opportunity]:
    """Return a deterministic page of published opportunities."""
    statement = (
        select(Opportunity)
        .where(Opportunity.status == OpportunityStatus.PUBLISHED)
        .order_by(Opportunity.created_at.desc(), Opportunity.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement).all())


def get_opportunity(db: Session, opportunity_id: uuid.UUID) -> Opportunity | None:
    """Return one opportunity by ID, if it exists."""
    return db.get(Opportunity, opportunity_id)


def get_public_opportunity(db: Session, opportunity_id: uuid.UUID) -> Opportunity | None:
    """Return one publicly readable opportunity with its rules and sources.

    Both collections are eager-loaded (in their relationship order) so the
    detail response never issues one query per requirement. Non-public rows
    are reported exactly like missing ones.
    """
    return db.scalar(
        select(Opportunity)
        .where(
            Opportunity.id == opportunity_id,
            Opportunity.status.in_(PUBLIC_STATUSES),
        )
        .options(
            selectinload(Opportunity.requirements),
            selectinload(Opportunity.sources),
        )
    )


def list_all_opportunities(
    db: Session,
    status: OpportunityStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Opportunity]:
    """Return a list of opportunities for curators, optionally filtered by status."""
    statement = select(Opportunity)
    if status is not None:
        statement = statement.where(Opportunity.status == status)
    statement = statement.order_by(Opportunity.created_at.desc(), Opportunity.id.desc()).offset(offset).limit(limit)
    return list(db.scalars(statement).all())


class OpportunityWouldBecomeIncompleteError(ValueError):
    """Raised when an edit would leave a publicly visible opportunity failing publication requirements."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("This edit would leave a public opportunity incomplete: " + " ".join(problems))
        self.problems = problems


def _locked_with_evidence(db: Session, opportunity_id: uuid.UUID) -> Opportunity | None:
    """The opportunity row locked ``FOR UPDATE``, with its sources and rules freshly loaded."""
    return db.scalar(
        select(Opportunity)
        .where(Opportunity.id == opportunity_id)
        .with_for_update(of=Opportunity)
        .options(selectinload(Opportunity.requirements), selectinload(Opportunity.sources))
        .execution_options(populate_existing=True)
    )


def update_opportunity(
    db: Session,
    opportunity_id: uuid.UUID,
    payload: OpportunityUpdate,
) -> Opportunity | None:
    """Update editable fields of an opportunity.

    The row is locked first. For a publicly visible opportunity (published or closed), the edited
    record is re-checked with :func:`publication_problems` before anything is kept: if the edit
    would leave it incomplete, every change is rolled back (savepoint) and
    ``OpportunityWouldBecomeIncompleteError`` is raised. Drafts may be edited freely; they are
    checked when published. Any future endpoint that changes an opportunity's sources or rules
    must make the same check (``assert_still_publishable``).
    """
    update_data = payload.model_dump(exclude_unset=True)
    if LIFECYCLE_FIELDS & update_data.keys():
        raise ValueError("Lifecycle fields cannot be changed by an update.")
    if "official_url" in update_data and update_data["official_url"] is not None:
        update_data["official_url"] = str(update_data["official_url"])

    savepoint = db.begin_nested()
    try:
        opp = _locked_with_evidence(db, opportunity_id)
        if opp is None:
            savepoint.rollback()
            return None
        for field, value in update_data.items():
            setattr(opp, field, value)
        db.flush()
        assert_still_publishable(opp)
    except BaseException:
        if savepoint.is_active:
            savepoint.rollback()
        raise
    savepoint.commit()
    db.refresh(opp)
    return opp


def assert_still_publishable(opp: Opportunity) -> None:
    """Raise ``OpportunityWouldBecomeIncompleteError`` if a public ``opp`` no longer meets requirements."""
    if opp.status in PUBLIC_STATUSES:
        problems = publication_problems(opp)
        if problems:
            raise OpportunityWouldBecomeIncompleteError(problems)


def publication_problems(opp: Opportunity) -> list[str]:
    """Every reason ``opp`` may not be (or stay) published; empty when it meets the requirements.

    These are structural completeness checks, not verification. They require:

    * a non-blank title and an official http(s) URL;
    * at least one source *record* belonging to this opportunity whose URL is http(s);
    * at least one eligibility rule, and at least one rule carrying a verbatim quote;
    * on every mandatory rule, a non-blank quote **and** a citation (``source_id``) of one of
      this opportunity's own source records.

    Nothing here proves a source is official, that its host matches the official URL, or that a
    quote really appears on the page: there is no source verification state yet (review R-5).
    """
    problems: list[str] = []
    if not (opp.title or "").strip():
        problems.append("Opportunity must have a title.")
    if not _is_http_url(opp.official_url):
        problems.append("Opportunity must have an official http(s) URL.")
    own_sources = {source.id for source in opp.sources if _is_http_url(source.url)}
    if not own_sources:
        problems.append("Opportunity must have at least one source record with an http(s) URL.")
    if not opp.requirements:
        problems.append("Opportunity must have at least one eligibility rule.")
    else:
        quoted = [req for req in opp.requirements if req.source_quote and req.source_quote.strip()]
        if not quoted:
            problems.append("At least one requirement must carry a verbatim source quote.")
        mandatory = [req for req in opp.requirements if req.is_mandatory]
        unquoted = [req for req in mandatory if req not in quoted]
        if unquoted:
            problems.append(f"{len(unquoted)} mandatory requirement(s) lack a verbatim source quote.")
        uncited = [req for req in mandatory if req in quoted and req.source_id not in own_sources]
        if uncited:
            problems.append(
                f"{len(uncited)} mandatory requirement(s) do not cite one of this opportunity's own source records."
            )
    return problems


def _is_http_url(value: str | None) -> bool:
    if not value or not value.strip():
        return False
    parts = urlsplit(value.strip())
    return parts.scheme in ("http", "https") and bool(parts.hostname)


def publish_opportunity(
    db: Session,
    opportunity_id: uuid.UUID,
    *,
    published_at: datetime | None = None,
) -> Opportunity:
    """Publish a draft or closed opportunity after validating completeness and quotes.

    This is the only code path that sets ``PUBLISHED``. The row is locked first so
    a concurrent edit or publish can't interleave with the check. On any failure
    nothing is written. ``published_at`` is for reproducible seeding only; API
    callers can't supply it.
    """
    opp = _locked_with_evidence(db, opportunity_id)
    if opp is None:
        raise ValueError("Opportunity not found.")
    if opp.status not in PUBLISHABLE_FROM:
        raise InvalidStatusTransitionError(f"An opportunity in status '{opp.status}' cannot be published.")

    problems = publication_problems(opp)
    if problems:
        raise IncompleteOpportunityError(" ".join(problems))

    opp.status = OpportunityStatus.PUBLISHED
    opp.published_at = published_at or datetime.now(timezone.utc)
    db.flush()
    db.refresh(opp)
    return opp


def close_opportunity(db: Session, opportunity_id: uuid.UUID) -> Opportunity:
    """Close a published opportunity.

    Only published rows may be closed: ``CLOSED`` is publicly readable, so closing
    a draft would expose it without ever passing publication validation.
    """
    opp = db.scalar(
        select(Opportunity).where(Opportunity.id == opportunity_id).with_for_update().execution_options(populate_existing=True)
    )
    if opp is None:
        raise ValueError("Opportunity not found.")
    if opp.status != OpportunityStatus.PUBLISHED:
        raise InvalidStatusTransitionError(f"An opportunity in status '{opp.status}' cannot be closed.")

    opp.status = OpportunityStatus.CLOSED
    db.flush()
    db.refresh(opp)
    return opp
