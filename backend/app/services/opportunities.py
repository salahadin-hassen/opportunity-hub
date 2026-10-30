"""Persistence services for opportunities."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models import Opportunity, OpportunityStatus
from app.schemas import OpportunityCreate

#: Statuses anyone may read one opportunity in. Closed calls stay readable
#: so links and past matches keep resolving; drafts and archived rows never
#: leave the curator side.
PUBLIC_STATUSES = (OpportunityStatus.PUBLISHED, OpportunityStatus.CLOSED)


class OpportunitySlugConflictError(Exception):
    """Raised when an opportunity slug is already in use."""


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
