"""Profile HTTP endpoints: the owned collection and the current user's profile."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_profile
from app.db.session import get_db
from app.models import Profile, User
from app.schemas import ProfileCreate, ProfileRead, ProfileUpdate
from app.services import audit
from app.services.profiles import (
    ProfileAlreadyExistsError,
    ProfileEmailConflictError,
    create_profile_for_user,
    get_profile_for_user,
    update_profile,
)
from app.services.sessions import revoke_all_user_sessions

router = APIRouter(prefix="/profiles", tags=["profiles"])
me_router = APIRouter(prefix="/me", tags=["profiles"])


def _profile_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found."
    )


@router.get("/{profile_id}", response_model=ProfileRead)
def get_one(profile: Profile = Depends(get_owned_profile)) -> ProfileRead:
    """Return one profile owned by the authenticated user."""
    return profile


@me_router.get("/profile", response_model=ProfileRead)
def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProfileRead:
    """Return the authenticated user's profile, or 404 when none exists yet."""
    profile = get_profile_for_user(db, current_user.id)
    if profile is None:
        raise _profile_not_found()
    return profile


@me_router.post(
    "/profile", response_model=ProfileRead, status_code=status.HTTP_201_CREATED
)
def create_my_profile(
    payload: ProfileCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProfileRead:
    """Create the authenticated user's single profile."""
    try:
        return create_profile_for_user(db, current_user.id, payload)
    except ProfileAlreadyExistsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The user already has a profile.",
        ) from error
    except ProfileEmailConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A profile with this email already exists.",
        ) from error


@me_router.patch("/profile", response_model=ProfileRead)
def patch_my_profile(
    payload: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProfileRead:
    """Apply a partial update to the authenticated user's profile."""
    profile = get_profile_for_user(db, current_user.id)
    if profile is None:
        raise _profile_not_found()
    return update_profile(db, profile, payload)


@me_router.post("/account/request-deletion", status_code=status.HTTP_200_OK)
def request_deletion(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Request scheduled account deletion with a 30-day recovery window (plan §C.2)."""
    now = datetime.now(timezone.utc)
    current_user.deletion_requested_at = now
    current_user.deletion_due_at = now + timedelta(days=30)
    revoke_all_user_sessions(db, current_user.id)
    audit.record(
        db,
        action="user.deletion_requested",
        target_type="user",
        target_id=current_user.id,
        actor_id=current_user.id,
    )
    db.flush()
    return {"status": "ok", "deletion_due_at": current_user.deletion_due_at.isoformat()}


@me_router.post("/account/cancel-deletion", status_code=status.HTTP_200_OK)
def cancel_deletion(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Cancel a pending account deletion request."""
    current_user.deletion_requested_at = None
    current_user.deletion_due_at = None
    audit.record(
        db,
        action="user.deletion_cancelled",
        target_type="user",
        target_id=current_user.id,
        actor_id=current_user.id,
    )
    db.flush()
    return {"status": "ok"}
