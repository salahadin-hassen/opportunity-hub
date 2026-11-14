"""Authenticated applicant endpoints for saved opportunities and applications (M3)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_my_profile
from app.db.session import get_db
from app.models.profile import Profile
from app.schemas.tracking import (
    ApplicationCreate,
    ApplicationItemCreate,
    ApplicationItemRead,
    ApplicationItemUpdate,
    ApplicationRead,
    ApplicationUpdate,
    SavedOpportunityCreate,
    SavedOpportunityRead,
)
from app.services import tracking

router = APIRouter(prefix="/me", tags=["tracking"])


@router.get("/saved-opportunities", response_model=list[SavedOpportunityRead])
def list_saved(
    profile: Profile = Depends(get_my_profile),
    db: Session = Depends(get_db),
) -> list[SavedOpportunityRead]:
    """List all saved/bookmarked opportunities for the current user."""
    return tracking.list_saved_opportunities(db, profile.id)


@router.post(
    "/saved-opportunities",
    response_model=SavedOpportunityRead,
    status_code=status.HTTP_201_CREATED,
)
def save(
    payload: SavedOpportunityCreate,
    profile: Profile = Depends(get_my_profile),
    db: Session = Depends(get_db),
) -> SavedOpportunityRead:
    """Save or update reminder settings for an opportunity."""
    saved = tracking.save_opportunity(
        db, profile.id, payload.opportunity_id, payload.reminders_enabled
    )
    if saved is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opportunity not found.",
        )
    return saved


@router.delete(
    "/saved-opportunities/{opportunity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def unsave(
    opportunity_id: uuid.UUID,
    profile: Profile = Depends(get_my_profile),
    db: Session = Depends(get_db),
) -> Response:
    """Remove a saved opportunity."""
    if not tracking.unsave_opportunity(db, profile.id, opportunity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved opportunity not found.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/applications", response_model=list[ApplicationRead])
def list_apps(
    profile: Profile = Depends(get_my_profile),
    db: Session = Depends(get_db),
) -> list[ApplicationRead]:
    """List tracked applications for the current profile."""
    return tracking.list_applications(db, profile.id)


@router.post(
    "/applications",
    response_model=ApplicationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_app(
    payload: ApplicationCreate,
    profile: Profile = Depends(get_my_profile),
    db: Session = Depends(get_db),
) -> ApplicationRead:
    """Start tracking an application."""
    app = tracking.create_application(db, profile.id, payload)
    if app is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opportunity not found.",
        )
    return app


@router.get("/applications/{application_id}", response_model=ApplicationRead)
def get_app(
    application_id: uuid.UUID,
    profile: Profile = Depends(get_my_profile),
    db: Session = Depends(get_db),
) -> ApplicationRead:
    """Get application details and checklist items."""
    app = tracking.get_application(db, profile.id, application_id)
    if app is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found.",
        )
    return app


@router.patch("/applications/{application_id}", response_model=ApplicationRead)
def update_app(
    application_id: uuid.UUID,
    payload: ApplicationUpdate,
    profile: Profile = Depends(get_my_profile),
    db: Session = Depends(get_db),
) -> ApplicationRead:
    """Update application status, notes, or outcome."""
    app = tracking.update_application(db, profile.id, application_id, payload)
    if app is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found.",
        )
    return app


@router.post(
    "/applications/{application_id}/items",
    response_model=ApplicationItemRead,
    status_code=status.HTTP_201_CREATED,
)
def add_item(
    application_id: uuid.UUID,
    payload: ApplicationItemCreate,
    profile: Profile = Depends(get_my_profile),
    db: Session = Depends(get_db),
) -> ApplicationItemRead:
    """Add a checklist item to an application."""
    item = tracking.add_application_item(db, profile.id, application_id, payload)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found.",
        )
    return item


@router.patch(
    "/applications/{application_id}/items/{item_id}",
    response_model=ApplicationItemRead,
)
def update_item(
    application_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ApplicationItemUpdate,
    profile: Profile = Depends(get_my_profile),
    db: Session = Depends(get_db),
) -> ApplicationItemRead:
    """Update status or notes for an application checklist item."""
    item = tracking.update_application_item(db, profile.id, application_id, item_id, payload)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application item not found.",
        )
    return item


@router.delete(
    "/applications/{application_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_app(
    application_id: uuid.UUID,
    profile: Profile = Depends(get_my_profile),
    db: Session = Depends(get_db),
) -> Response:
    """Delete a tracked application."""
    if not tracking.delete_application(db, profile.id, application_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/applications/{application_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_item(
    application_id: uuid.UUID,
    item_id: uuid.UUID,
    profile: Profile = Depends(get_my_profile),
    db: Session = Depends(get_db),
) -> Response:
    """Delete a checklist item from an application."""
    if not tracking.delete_application_item(db, profile.id, application_id, item_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application item not found.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

