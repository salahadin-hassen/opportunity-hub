"""Authenticated test score endpoints under the current user's profile."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_my_profile
from app.db.session import get_db
from app.models import Profile, TestScore
from app.schemas import TestScoreCreate, TestScoreRead, TestScoreUpdate
from app.services.test_scores import (
    TestScoreValidationError,
    create_test_score,
    delete_test_score,
    get_test_score,
    list_test_scores,
    update_test_score,
)

router = APIRouter(prefix="/me/profile/test-scores", tags=["test-scores"])


def _test_score_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Test score not found."
    )


@router.get("", response_model=list[TestScoreRead])
def list_my_test_scores(
    profile: Profile = Depends(get_my_profile),
    db: Session = Depends(get_db),
) -> list[TestScoreRead]:
    """Return the owned profile's test scores in deterministic order."""
    return list_test_scores(db, profile.id)


@router.post(
    "", response_model=TestScoreRead, status_code=status.HTTP_201_CREATED
)
def create_my_test_score(
    payload: TestScoreCreate,
    profile: Profile = Depends(get_my_profile),
    db: Session = Depends(get_db),
) -> TestScoreRead:
    """Add one test score to the owned profile."""
    return create_test_score(db, profile.id, payload)


@router.patch("/{test_score_id}", response_model=TestScoreRead)
def patch_my_test_score(
    test_score_id: uuid.UUID,
    payload: TestScoreUpdate,
    profile: Profile = Depends(get_my_profile),
    db: Session = Depends(get_db),
) -> TestScoreRead:
    """Apply a partial update to one owned test score."""
    score = get_test_score(db, profile.id, test_score_id)
    if score is None:
        raise _test_score_not_found()
    try:
        return update_test_score(db, score, payload)
    except TestScoreValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error


@router.delete("/{test_score_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_test_score(
    test_score_id: uuid.UUID,
    profile: Profile = Depends(get_my_profile),
    db: Session = Depends(get_db),
) -> Response:
    """Delete one owned test score."""
    score = get_test_score(db, profile.id, test_score_id)
    if score is None:
        raise _test_score_not_found()
    delete_test_score(db, score)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
