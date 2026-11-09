"""Opportunity HTTP endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import OpportunityStatus, User
from app.services import audit
from app.schemas import OpportunityCreate, OpportunityDetailRead, OpportunityRead, OpportunityUpdate
from app.services.opportunities import (
    IncompleteOpportunityError,
    OpportunitySlugConflictError,
    close_opportunity,
    create_opportunity,
    get_public_opportunity,
    list_all_opportunities,
    list_opportunities,
    publish_opportunity,
    update_opportunity,
)

router = APIRouter(prefix="/opportunities", tags=["opportunities"])
curate_router = APIRouter(prefix="/curate/opportunities", tags=["curate"])


@curate_router.get("", response_model=list[OpportunityRead])
def list_curator_opportunities(
    status: OpportunityStatus | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.OPPORTUNITY_CREATE)),
) -> list[OpportunityRead]:
    """List opportunities across all statuses for curators."""
    return list_all_opportunities(db, status=status, limit=limit, offset=offset)


@curate_router.patch("/{opportunity_id}", response_model=OpportunityRead)
def patch_curator_opportunity(
    opportunity_id: uuid.UUID,
    payload: OpportunityUpdate,
    db: Session = Depends(get_db),
    curator: User = Depends(require_permission(Permission.OPPORTUNITY_EDIT)),
) -> OpportunityRead:
    """Update opportunity details and metadata."""
    updated = update_opportunity(db, opportunity_id, payload)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found.")
    audit.record(
        db,
        action="opportunity.updated",
        target_type="opportunity",
        target_id=opportunity_id,
        actor_id=curator.id,
        changes=payload.model_dump(exclude_unset=True),
    )
    return updated


@curate_router.post("/{opportunity_id}/publish", response_model=OpportunityRead)
def publish_curator_opportunity(
    opportunity_id: uuid.UUID,
    db: Session = Depends(get_db),
    curator: User = Depends(require_permission(Permission.OPPORTUNITY_PUBLISH)),
) -> OpportunityRead:
    """Publish an opportunity after checking source and rule verification."""
    try:
        opp = publish_opportunity(db, opportunity_id)
    except IncompleteOpportunityError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    audit.record(
        db,
        action="opportunity.published",
        target_type="opportunity",
        target_id=opportunity_id,
        actor_id=curator.id,
        changes={"status": opp.status, "published_at": opp.published_at.isoformat() if opp.published_at else None},
    )
    return opp


@curate_router.post("/{opportunity_id}/close", response_model=OpportunityRead)
def close_curator_opportunity(
    opportunity_id: uuid.UUID,
    db: Session = Depends(get_db),
    curator: User = Depends(require_permission(Permission.OPPORTUNITY_EDIT)),
) -> OpportunityRead:
    """Close an opportunity cycle."""
    try:
        opp = close_opportunity(db, opportunity_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    audit.record(
        db,
        action="opportunity.closed",
        target_type="opportunity",
        target_id=opportunity_id,
        actor_id=curator.id,
        changes={"status": opp.status},
    )
    return opp


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