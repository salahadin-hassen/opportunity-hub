"""Opportunity HTTP endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import OpportunityStatus, User
from app.services import audit
from app.schemas import OpportunityCreate, OpportunityDetailRead, OpportunityRead, OpportunityUpdate
from app.services.opportunities import (
    IncompleteOpportunityError,
    InvalidStatusTransitionError,
    OpportunitySlugConflictError,
    OpportunityWouldBecomeIncompleteError,
    close_opportunity,
    create_opportunity,
    get_opportunity,
    get_public_opportunity,
    list_all_opportunities,
    list_opportunities,
    publish_opportunity,
    update_opportunity,
)

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


def opp_status_for_audit(db: Session, opportunity_id: uuid.UUID) -> str | None:
    """The status left in place after a rejected lifecycle operation (for the audit entry)."""
    opp = get_opportunity(db, opportunity_id)
    return str(opp.status) if opp is not None else None


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


@curate_router.patch(
    "/{opportunity_id}",
    response_model=OpportunityRead,
    responses={409: {"description": "The edit would leave a public opportunity incomplete"}},
)
def patch_curator_opportunity(
    opportunity_id: uuid.UUID,
    payload: OpportunityUpdate,
    db: Session = Depends(get_db),
    curator: User = Depends(require_permission(Permission.OPPORTUNITY_EDIT)),
):
    """Update opportunity details and metadata.

    Edits to a published or closed opportunity are re-validated atomically; an edit that would
    leave it incomplete changes nothing, is audited as ``opportunity.update_rejected`` and
    returns 409 (returned, not raised, so the audit entry commits).
    """
    try:
        updated = update_opportunity(db, opportunity_id, payload)
    except OpportunityWouldBecomeIncompleteError as error:
        audit.record(
            db,
            action="opportunity.update_rejected",
            target_type="opportunity",
            target_id=opportunity_id,
            actor_id=curator.id,
            changes={"fields": sorted(payload.model_fields_set), "status": opp_status_for_audit(db, opportunity_id)},
            reason=str(error),
        )
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(error)})
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found.")
    audit.record(
        db,
        action="opportunity.updated",
        target_type="opportunity",
        target_id=opportunity_id,
        actor_id=curator.id,
        changes=payload.model_dump(mode="json", exclude_unset=True),
    )
    return updated


@curate_router.post(
    "/{opportunity_id}/publish",
    response_model=OpportunityRead,
    responses={400: {"description": "Publication validation failed"}, 409: {"description": "Not publishable from its status"}},
)
def publish_curator_opportunity(
    opportunity_id: uuid.UUID,
    db: Session = Depends(get_db),
    curator: User = Depends(require_permission(Permission.OPPORTUNITY_PUBLISH)),
):
    """Publish an opportunity if it passes the publication completeness checks.

    The checks are structural (an official URL, an own source record, quoted mandatory rules
    citing it); they do not establish that a source is authentic or that a quote is on the page.

    Validation runs inside a savepoint: a rejection rolls back any change to the
    opportunity, and the rejection itself is audited and committed (the error is
    returned rather than raised, so the request transaction still commits).
    """
    try:
        with db.begin_nested():
            opp = publish_opportunity(db, opportunity_id)
    except (IncompleteOpportunityError, InvalidStatusTransitionError) as error:
        code = status.HTTP_409_CONFLICT if isinstance(error, InvalidStatusTransitionError) else status.HTTP_400_BAD_REQUEST
        audit.record(
            db,
            action="opportunity.publish_rejected",
            target_type="opportunity",
            target_id=opportunity_id,
            actor_id=curator.id,
            changes={"status": opp_status_for_audit(db, opportunity_id)},
            reason=str(error),
        )
        return JSONResponse(status_code=code, content={"detail": str(error)})
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


@curate_router.post(
    "/{opportunity_id}/close",
    response_model=OpportunityRead,
    responses={409: {"description": "Only published opportunities can be closed"}},
)
def close_curator_opportunity(
    opportunity_id: uuid.UUID,
    db: Session = Depends(get_db),
    curator: User = Depends(require_permission(Permission.OPPORTUNITY_EDIT)),
):
    """Close a published opportunity cycle."""
    try:
        opp = close_opportunity(db, opportunity_id)
    except InvalidStatusTransitionError as error:
        audit.record(
            db,
            action="opportunity.close_rejected",
            target_type="opportunity",
            target_id=opportunity_id,
            actor_id=curator.id,
            changes={"status": opp_status_for_audit(db, opportunity_id)},
            reason=str(error),
        )
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(error)})
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