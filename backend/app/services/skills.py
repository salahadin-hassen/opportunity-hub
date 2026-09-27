"""Profile-skill association services scoped to one authenticated owner."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ProfileSkill, Skill
from app.schemas import ProfileSkillCreate

DUPLICATE_ASSOCIATION_CONSTRAINT = "uq_profile_skills_profile_skill"


class SkillNotFoundError(Exception):
    """Raised when the referenced canonical skill does not exist."""


class SkillNotAttachedError(Exception):
    """Raised when the owned profile does not have the skill attached."""


class SkillAlreadyAttachedError(Exception):
    """Raised when the owned profile already has the skill attached."""


def _constraint_name(error: IntegrityError) -> str | None:
    diagnostic = getattr(error.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None)


def list_profile_skills(db: Session, profile_id: uuid.UUID) -> list[Skill]:
    """Return the profile's skills ordered by canonical key.

    One explicit join answers the whole list — no N+1 loads and no
    dependence on relationship or physical row order.
    """
    statement = (
        select(Skill)
        .join(ProfileSkill, ProfileSkill.skill_id == Skill.id)
        .where(ProfileSkill.profile_id == profile_id)
        .order_by(Skill.key.asc())
    )
    return list(db.scalars(statement).all())


def attach_skill(
    db: Session, profile_id: uuid.UUID, payload: ProfileSkillCreate
) -> Skill:
    """Attach an existing canonical skill to the owned profile.

    The friendly pre-check gives the deterministic conflict; the insert
    itself runs in a savepoint so a concurrent request still surfaces as
    the same conflict — but only when the duplicate constraint is what
    actually fired, never for unrelated database failures.
    """
    skill = db.get(Skill, payload.skill_id)
    if skill is None:
        raise SkillNotFoundError
    attached = db.scalar(
        select(ProfileSkill.id).where(
            ProfileSkill.profile_id == profile_id,
            ProfileSkill.skill_id == skill.id,
        )
    )
    if attached is not None:
        raise SkillAlreadyAttachedError
    association = ProfileSkill(profile_id=profile_id, skill_id=skill.id)
    try:
        with db.begin_nested():
            db.add(association)
            db.flush()
    except IntegrityError as error:
        if _constraint_name(error) == DUPLICATE_ASSOCIATION_CONSTRAINT:
            raise SkillAlreadyAttachedError from error
        raise
    return skill


def detach_skill(db: Session, profile_id: uuid.UUID, skill_id: uuid.UUID) -> None:
    """Remove one association row; the shared skill and profile stay intact."""
    association = db.scalar(
        select(ProfileSkill).where(
            ProfileSkill.profile_id == profile_id,
            ProfileSkill.skill_id == skill_id,
        )
    )
    if association is None:
        raise SkillNotAttachedError
    db.delete(association)
    db.flush()
