"""Opportunity HTTP endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import User
from app.services import audit
from app.schemas import OpportunityCreate, OpportunityDetailRead, OpportunityRead
from app.services.opportunities import (
    OpportunitySlugConflictError,
    create_opportunity,
    get_public_opportunity,
    list_opportunities,
)

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


@router.post(
    "",
    response_model=OpportunityRead,
    status_code=status.HTTP_201_CREATED,
)
def create(
    payload: OpportunityCreate,
    db: Session = Depends(get_db),
    curator: User = Depends(require_permission(Permission.OPPORTUNITY_CREATE)),
) -> OpportunityRead:
    """Create an opportunity (curators and admins only); audited in the same transaction."""
    try:
        opportunity = create_opportunity(db, payload)
    except OpportunitySlugConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An opportunity with this slug already exists.",
        ) from error
    audit.record(
        db,
        action="opportunity.created",
        target_type="opportunity",
        target_id=opportunity.id,
        actor_id=curator.id,
        changes={"slug": opportunity.slug, "status": opportunity.status, "title": opportunity.title},
    )
    return opportunity


@router.get("", response_model=list[OpportunityRead])
def list_all(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[OpportunityRead]:
    """List published opportunities with simple offset pagination."""
    return list_opportunities(db, limit, offset)


@router.get("/{opportunity_id}", response_model=OpportunityDetailRead)
def get_one(opportunity_id: uuid.UUID, db: Session = Depends(get_db)) -> OpportunityDetailRead:
    """Return one public opportunity with its eligibility rules and sources."""
    opportunity = get_public_opportunity(db, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found.")
    return opportunity