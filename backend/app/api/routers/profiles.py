"""Profile HTTP endpoints, scoped to the authenticated owner."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_owned_profile
from app.models import Profile
from app.schemas import ProfileRead

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("/{profile_id}", response_model=ProfileRead)
def get_one(profile: Profile = Depends(get_owned_profile)) -> ProfileRead:
    """Return one profile owned by the authenticated user."""
    return profile
