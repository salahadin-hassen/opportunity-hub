"""Test score services scoped to one authenticated owner's profile."""
from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TestScore
from app.schemas import TestScoreCreate, TestScoreUpdate


class TestScoreValidationError(Exception):
    """Raised when a merged partial update would break a cross-field rule."""


def list_test_scores(db: Session, profile_id: uuid.UUID) -> list[TestScore]:
    """Return one profile's test scores in a deterministic order.

    Most recent ``test_date`` first (PostgreSQL puts undated scores ahead of
    dated ones under ``DESC``, matching the ``Profile.test_scores``
    relationship), then ``created_at`` and ``id`` as stable tiebreaks —
    never relying on physical row order.
    """
    statement = (
        select(TestScore)
        .where(TestScore.profile_id == profile_id)
        .order_by(
            TestScore.test_date.desc(),
            TestScore.created_at.asc(),
            TestScore.id.asc(),
        )
    )
    return list(db.scalars(statement).all())


def get_test_score(
    db: Session, profile_id: uuid.UUID, test_score_id: uuid.UUID
) -> TestScore | None:
    """Return one test score only when it belongs to ``profile_id``.

    Records owned by any other profile are indistinguishable from missing
    ids, so callers answer with one uniform 404 and learn nothing about
    whose record it was.
    """
    statement = select(TestScore).where(
        TestScore.id == test_score_id,
        TestScore.profile_id == profile_id,
    )
    return db.scalar(statement)


def create_test_score(
    db: Session, profile_id: uuid.UUID, payload: TestScoreCreate
) -> TestScore:
    """Attach one test score to the owned profile.

    The request body was already validated by ``TestScoreCreate`` and the
    domain enforces no uniqueness, so a plain flush is sufficient — the
    caller owns the transaction as usual.
    """
    score = TestScore(profile_id=profile_id, **payload.model_dump())
    db.add(score)
    db.flush()
    db.refresh(score)
    return score


def _validate_merged(score: TestScore, changes: dict) -> None:
    """Re-run the date-range rule on the record as a PATCH would leave it."""
    merged = {name: getattr(score, name) for name in TestScoreCreate.model_fields}
    merged.update(changes)
    if isinstance(merged["overall_score"], Decimal):
        merged["overall_score"] = float(merged["overall_score"])
    try:
        TestScoreCreate(**merged)
    except ValidationError as error:
        messages = "; ".join(entry["msg"] for entry in error.errors())
        raise TestScoreValidationError(messages) from error


def update_test_score(
    db: Session, score: TestScore, payload: TestScoreUpdate
) -> TestScore:
    """Apply only the fields the client sent, after merged-state validation."""
    changes = {name: getattr(payload, name) for name in payload.model_fields_set}
    _validate_merged(score, changes)
    for name, value in changes.items():
        setattr(score, name, value)
    db.flush()
    return score


def delete_test_score(db: Session, score: TestScore) -> None:
    """Remove one test score; it has no children, so nothing is orphaned."""
    db.delete(score)
    db.flush()
