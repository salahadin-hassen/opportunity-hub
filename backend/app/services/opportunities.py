"""Persistence services for opportunities."""
from __future__ import annotations

import uuid

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


def is_public(opportunity: Opportunity) -> bool:
    """Return whether ``opportunity`` may be shown outside the curator side."""
    return opportunity.status in PUBLIC_STATUSES


def create_opportunity(db: Session, payload: OpportunityCreate) -> Opportunity:
    """Persist an opportunity and return its refreshed database record."""
    opportunity = Opportunity(**payload.model_dump())
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


def update_opportunity(
    db: Session,
    opportunity_id: uuid.UUID,
    payload: OpportunityUpdate,
) -> Opportunity | None:
    """Update editable fields of an opportunity."""
    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        return None

    update_data = payload.model_dump(exclude_unset=True)
    if "official_url" in update_data and update_data["official_url"] is not None:
        update_data["official_url"] = str(update_data["official_url"])

    for field, value in update_data.items():
        setattr(opp, field, value)

    db.flush()
    db.refresh(opp)
    return opp


def publish_opportunity(db: Session, opportunity_id: uuid.UUID) -> Opportunity:
    """Publish a draft or closed opportunity after validating completeness and quotes."""
    opp = db.scalar(
        select(Opportunity)
        .where(Opportunity.id == opportunity_id)
        .options(
            selectinload(Opportunity.requirements),
            selectinload(Opportunity.sources),
        )
    )
    if opp is None:
        raise ValueError("Opportunity not found.")

    # Guard: Avoid accidentally publishing stale, incomplete or unverified opportunities
    if not opp.sources:
        raise IncompleteOpportunityError("Opportunity must have at least one verified source before publishing.")
    if not opp.requirements:
        raise IncompleteOpportunityError("Opportunity must have at least one eligibility rule before publishing.")

    has_quoted_req = any(bool(req.source_quote and req.source_quote.strip()) for req in opp.requirements)
    if not has_quoted_req:
        raise IncompleteOpportunityError("At least one requirement must have a verified verbatim source quote.")

    from datetime import datetime, timezone
    opp.status = OpportunityStatus.PUBLISHED
    opp.published_at = datetime.now(timezone.utc)
    db.flush()
    db.refresh(opp)
    return opp


def close_opportunity(db: Session, opportunity_id: uuid.UUID) -> Opportunity:
    """Transition an opportunity to closed."""
    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        raise ValueError("Opportunity not found.")

    opp.status = OpportunityStatus.CLOSED
    db.flush()
    db.refresh(opp)
    return opp
