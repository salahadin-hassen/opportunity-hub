"""Opportunity HTTP endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import OpportunityCreate, OpportunityRead
from app.services.opportunities import (
    OpportunitySlugConflictError,
    create_opportunity,
    get_opportunity,
    list_opportunities,
)

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


@router.post("", response_model=OpportunityRead, status_code=status.HTTP_201_CREATED)
def create(payload: OpportunityCreate, db: Session = Depends(get_db)) -> OpportunityRead:
    """Create an opportunity."""
    try:
        return create_opportunity(db, payload)
    except OpportunitySlugConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An opportunity with this slug already exists.",
        ) from error


@router.get("", response_model=list[OpportunityRead])
def list_all(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[OpportunityRead]:
    """List opportunities with simple offset pagination."""
    return list_opportunities(db, limit, offset)


@router.get("/{opportunity_id}", response_model=OpportunityRead)
def get_one(opportunity_id: uuid.UUID, db: Session = Depends(get_db)) -> OpportunityRead:
    """Return one opportunity by ID."""
    opportunity = get_opportunity(db, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found.")
    return opportunity