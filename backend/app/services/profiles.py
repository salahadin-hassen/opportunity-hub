"""Profile services scoped to one authenticated owner."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Profile
from app.schemas import ProfileCreate, ProfileUpdate


class ProfileAlreadyExistsError(Exception):
    """Raised when the authenticated user already owns a profile."""


class ProfileEmailConflictError(Exception):
    """Raised when another profile already uses this contact email."""


def get_profile_for_user(db: Session, user_id: uuid.UUID) -> Profile | None:
    """Return the profile owned by ``user_id``, if any.

    Ownerless legacy rows (``user_id IS NULL``) never match, so they are
    neither exposed nor claimed through this lookup.
    """
    return db.scalar(select(Profile).where(Profile.user_id == user_id))


def create_profile_for_user(db: Session, user_id: uuid.UUID, payload: ProfileCreate) -> Profile:
    """Attach exactly one new profile to the authenticated user.

    Ownership comes from ``user_id`` — never from the payload. The caller
    owns the transaction, so this only flushes: the ownership pre-check
    gives the deterministic conflict, and a savepoint backstops the unique
    constraints so a failed request leaves no partial row behind.
    """
    if get_profile_for_user(db, user_id) is not None:
        raise ProfileAlreadyExistsError
    profile = Profile(user_id=user_id, **payload.model_dump())
    try:
        with db.begin_nested():
            db.add(profile)
            db.flush()
    except IntegrityError as error:
        raise ProfileEmailConflictError from error
    db.refresh(profile)
    return profile


def update_profile(db: Session, profile: Profile, payload: ProfileUpdate) -> Profile:
    """Apply only the fields the client actually sent; everything else stays."""
    for field_name in payload.model_fields_set:
        setattr(profile, field_name, getattr(payload, field_name))
    db.flush()
    db.refresh(profile)
    return profile
