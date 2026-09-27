"""Authenticated profile skill endpoints under the current user's profile."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_my_profile
from app.db.session import get_db
from app.models import Profile, Skill
from app.schemas import ProfileSkillCreate, SkillRead
from app.services.skills import (
    SkillAlreadyAttachedError,
    SkillNotAttachedError,
    SkillNotFoundError,
    attach_skill,
    detach_skill,
    list_profile_skills,
)

router = APIRouter(prefix="/me/profile/skills", tags=["skills"])


def _skill_not_attached() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Skill is not attached to this profile.",
    )


@router.get("", response_model=list[SkillRead])
def list_my_skills(
    profile: Profile = Depends(get_my_profile),
    db: Session = Depends(get_db),
) -> list[SkillRead]:
    """Return the owned profile's canonical skills ordered by key."""
    return list_profile_skills(db, profile.id)


@router.post("", response_model=SkillRead, status_code=status.HTTP_201_CREATED)
def attach_my_skill(
    payload: ProfileSkillCreate,
    profile: Profile = Depends(get_my_profile),
    db: Session = Depends(get_db),
) -> SkillRead:
    """Attach one existing canonical skill to the owned profile."""
    try:
        return attach_skill(db, profile.id, payload)
    except SkillNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found."
        ) from error
    except SkillAlreadyAttachedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The profile already has this skill.",
        ) from error


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def detach_my_skill(
    skill_id: uuid.UUID,
    profile: Profile = Depends(get_my_profile),
    db: Session = Depends(get_db),
) -> Response:
    """Remove one skill association; the canonical skill survives."""
    try:
        detach_skill(db, profile.id, skill_id)
    except SkillNotAttachedError as error:
        raise _skill_not_attached() from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
