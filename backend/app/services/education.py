"""Education services scoped to one authenticated owner's profile."""
from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Education
from app.schemas import EducationCreate, EducationUpdate


class PrimaryEducationConflictError(Exception):
    """Raised when the profile already has a primary education."""


class EducationValidationError(Exception):
    """Raised when a merged partial update would break a cross-field rule."""


def _has_primary(db: Session, profile_id: uuid.UUID, exclude_id: uuid.UUID | None = None) -> bool:
    statement = select(Education.id).where(
        Education.profile_id == profile_id,
        Education.is_primary.is_(True),
    )
    if exclude_id is not None:
        statement = statement.where(Education.id != exclude_id)
    return db.scalar(statement) is not None


def list_education(db: Session, profile_id: uuid.UUID) -> list[Education]:
    """Return one profile's education records in a deterministic order.

    Primary first, then in-progress records, then by creation time and id —
    never relying on physical row order.
    """
    statement = (
        select(Education)
        .where(Education.profile_id == profile_id)
        .order_by(
            Education.is_primary.desc(),
            Education.is_current.desc(),
            Education.created_at.asc(),
            Education.id.asc(),
        )
    )
    return list(db.scalars(statement).all())


def get_education(
    db: Session, profile_id: uuid.UUID, education_id: uuid.UUID
) -> Education | None:
    """Return one education record only when it belongs to ``profile_id``.

    Records owned by any other profile are indistinguishable from missing
    ids, so callers answer with one uniform 404 and learn nothing about
    whose record it was.
    """
    statement = select(Education).where(
        Education.id == education_id,
        Education.profile_id == profile_id,
    )
    return db.scalar(statement)


def create_education(
    db: Session, profile_id: uuid.UUID, payload: EducationCreate
) -> Education:
    """Attach one education record to the owned profile.

    The request body was already validated by ``EducationCreate``; the
    primary pre-check gives the deterministic conflict and a savepoint
    backstops the partial unique index so no partial row survives a failure.
    """
    if payload.is_primary and _has_primary(db, profile_id):
        raise PrimaryEducationConflictError
    education = Education(profile_id=profile_id, **payload.model_dump())
    try:
        with db.begin_nested():
            db.add(education)
            db.flush()
    except IntegrityError as error:
        raise PrimaryEducationConflictError from error
    db.refresh(education)
    return education


def _validate_merged(education: Education, changes: dict) -> None:
    """Re-run the GPA/scale and date-range rules on the record as a PATCH would leave it."""
    merged = {name: getattr(education, name) for name in EducationCreate.model_fields}
    merged.update(changes)
    for name in ("gpa", "gpa_scale"):
        if isinstance(merged[name], Decimal):
            merged[name] = float(merged[name])
    try:
        EducationCreate(**merged)
    except ValidationError as error:
        messages = "; ".join(entry["msg"] for entry in error.errors())
        raise EducationValidationError(messages) from error


def update_education(
    db: Session, education: Education, payload: EducationUpdate
) -> Education:
    """Apply only the fields the client sent, after merged-state validation."""
    changes = {name: getattr(payload, name) for name in payload.model_fields_set}
    _validate_merged(education, changes)
    if changes.get("is_primary") is True and _has_primary(
        db, education.profile_id, exclude_id=education.id
    ):
        raise PrimaryEducationConflictError
    for name, value in changes.items():
        setattr(education, name, value)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as error:
        raise PrimaryEducationConflictError from error
    return education


def delete_education(db: Session, education: Education) -> None:
    """Remove one education record; it has no children, so nothing is orphaned."""
    db.delete(education)
    db.flush()
