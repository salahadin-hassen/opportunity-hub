"""Authenticated education endpoints under the current user's profile."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_my_profile
from app.db.session import get_db
from app.models import Education, Profile
from app.schemas import EducationCreate, EducationRead, EducationUpdate
from app.services.education import (
    EducationValidationError,
    PrimaryEducationConflictError,
    create_education,
    delete_education,
    get_education,
    list_education,
    update_education,
)

router = APIRouter(prefix="/me/profile/education", tags=["education"])

PRIMARY_EDUCATION_CONFLICT_DETAIL = "The profile already has a primary education."


def _education_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Education not found."
    )


@router.get("", response_model=list[EducationRead])
def list_my_education(
    profile: Profile = Depends(get_my_profile),
    db: Session = Depends(get_db),
) -> list[EducationRead]:
    """Return the owned profile's education records in deterministic order."""
    return list_education(db, profile.id)


@router.post(
    "", response_model=EducationRead, status_code=status.HTTP_201_CREATED
)
def create_my_education(
    payload: EducationCreate,
    profile: Profile = Depends(get_my_profile),
    db: Session = Depends(get_db),
) -> EducationRead:
    """Add one education record to the owned profile."""
    try:
        return create_education(db, profile.id, payload)
    except PrimaryEducationConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=PRIMARY_EDUCATION_CONFLICT_DETAIL,
        ) from error


@router.patch("/{education_id}", response_model=EducationRead)
def patch_my_education(
    education_id: uuid.UUID,
    payload: EducationUpdate,
    profile: Profile = Depends(get_my_profile),
    db: Session = Depends(get_db),
) -> EducationRead:
    """Apply a partial update to one owned education record."""
    education = get_education(db, profile.id, education_id)
    if education is None:
        raise _education_not_found()
    try:
        return update_education(db, education, payload)
    except PrimaryEducationConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=PRIMARY_EDUCATION_CONFLICT_DETAIL,
        ) from error
    except EducationValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error


@router.delete("/{education_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_education(
    education_id: uuid.UUID,
    profile: Profile = Depends(get_my_profile),
    db: Session = Depends(get_db),
) -> Response:
    """Delete one owned education record."""
    education = get_education(db, profile.id, education_id)
    if education is None:
        raise _education_not_found()
    delete_education(db, education)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
