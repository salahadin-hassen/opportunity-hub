"""Persistence services for opportunities."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Opportunity
from app.schemas import OpportunityCreate


class OpportunitySlugConflictError(Exception):
    """Raised when an opportunity slug is already in use."""


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
    """Return a deterministic page of opportunities."""
    statement = (
        select(Opportunity)
        .order_by(Opportunity.created_at.desc(), Opportunity.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement).all())


def get_opportunity(db: Session, opportunity_id: uuid.UUID) -> Opportunity | None:
    """Return one opportunity by ID, if it exists."""
    return db.get(Opportunity, opportunity_id)