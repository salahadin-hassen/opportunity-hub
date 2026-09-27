"""Persistence mapping from matching engine results to Match rows."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Match,
    MatchOutcome,
    MatchRequirement,
    MatchStatus,
    Opportunity,
    Profile,
)
from app.services.matching import (
    ENGINE_VERSION,
    MatchEvaluationResult,
    RequirementResult,
    evaluate_requirements,
)


class MatchPersistenceError(Exception):
    """Raised when an evaluation cannot be persisted intact."""


def _summarize(results: list[RequirementResult]) -> dict[str, int]:
    """Aggregate deterministic counts.

    The ``match_requirements`` rows stay authoritative for detail; this
    summary only answers ``how many of each outcome``.
    """
    counts = {"total": len(results), "met": 0, "not_met": 0, "unknown": 0, "needs_review": 0}
    for result in results:
        counts[MatchOutcome(str(result.outcome)).value] += 1
    return counts


def _validated_requirement_ids(results: list[RequirementResult]) -> list[uuid.UUID]:
    """Reject results that lost their requirement identity, before any write."""
    requirement_ids = []
    for result in results:
        if not isinstance(result.requirement_id, uuid.UUID):
            raise ValueError(
                "Each requirement result must carry a requirement id before persistence."
            )
        requirement_ids.append(result.requirement_id)
    return requirement_ids


def persist_match_evaluation(
    db: Session,
    profile: Profile,
    opportunity: Opportunity,
    evaluation_result: MatchEvaluationResult,
    engine_version: str = ENGINE_VERSION,
) -> Match:
    """Persist one Profile x Opportunity evaluation.

    The caller owns the transaction (``get_db`` commits, tests roll back),
    so this only flushes — inside a savepoint, so a failure leaves neither
    a Match without evidence nor evidence without its Match.

    Re-persisting the same pair updates the existing Match and replaces
    its requirement rows; the unique ``(profile_id, opportunity_id)``
    constraint guarantees at most one current Match per pair.
    """
    results = list(evaluation_result.requirement_results)
    _validated_requirement_ids(results)

    status = MatchStatus(str(evaluation_result.status))
    facts = _summarize(results)

    match = db.scalar(
        select(Match).where(
            Match.profile_id == profile.id,
            Match.opportunity_id == opportunity.id,
        )
    )
    creating = match is None
    if creating:
        match = Match(profile_id=profile.id, opportunity_id=opportunity.id)

    try:
        with db.begin_nested():
            if creating:
                db.add(match)
            match.status = status
            match.engine_version = engine_version
            match.evaluated_at = func.now()
            match.facts = facts

            # Replace evidence: a re-evaluation never mixes with stale rows.
            # The explicit flush guarantees DELETEs before INSERTs so the
            # (match_id, requirement_id) unique constraint is never violated.
            match.requirement_results.clear()
            db.flush()
            for result in results:
                match.requirement_results.append(
                    MatchRequirement(
                        match=match,
                        requirement_id=result.requirement_id,
                        outcome=MatchOutcome(str(result.outcome)).value,
                        reason_code=result.reason_code,
                        expected=dict(result.expected),
                        actual=dict(result.actual),
                        message=result.message,
                    )
                )
            db.flush()
    except IntegrityError as error:
        raise MatchPersistenceError from error

    db.refresh(match)
    return match


def _load_evaluable_profile(db: Session, profile_id: uuid.UUID) -> Profile | None:
    """Load a profile with everything the evaluators read up front.

    Education and skills are eager-loaded so evaluation itself never
    issues SQL; the ownership decision always happens above this lookup.
    """
    return db.scalar(
        select(Profile)
        .where(Profile.id == profile_id)
        .options(selectinload(Profile.education), selectinload(Profile.skills))
    )


def _load_opportunity(db: Session, opportunity_id: uuid.UUID) -> Opportunity | None:
    """Load one opportunity with its requirements for evaluation."""
    return db.scalar(
        select(Opportunity)
        .where(Opportunity.id == opportunity_id)
        .options(selectinload(Opportunity.requirements))
    )


def _evaluate_and_persist(db: Session, profile: Profile, opportunity: Opportunity) -> Match:
    """Run the pure evaluator on pre-loaded rows and persist the verdict."""
    evaluation = evaluate_requirements(profile, opportunity.requirements)
    return persist_match_evaluation(db, profile, opportunity, evaluation)


def evaluate_and_persist_match(
    db: Session,
    profile_id: uuid.UUID,
    opportunity_id: uuid.UUID,
) -> Match | None:
    """Evaluate one Profile x Opportunity pair and persist its Match.

    This is the service-level entry point that connects the pure matching
    engine to real ORM objects: it loads everything the evaluators read
    (education, skills, requirements) up front so evaluation itself never
    issues SQL, then delegates verdict rollup to ``evaluate_requirements``
    and all Match/MatchRequirement writing to :func:`persist_match_evaluation`.

    Returns ``None`` when either parent is missing — the same not-found
    convention as ``get_opportunity`` — and never commits: the caller owns
    the transaction (``get_db`` commits, tests roll back).
    """
    profile = _load_evaluable_profile(db, profile_id)
    if profile is None:
        return None

    opportunity = _load_opportunity(db, opportunity_id)
    if opportunity is None:
        return None

    return _evaluate_and_persist(db, profile, opportunity)


def evaluate_and_persist_match_for_user(
    db: Session,
    profile: Profile,
    opportunity_id: uuid.UUID,
) -> Match | None:
    """Evaluate the authenticated user's owned Profile against an opportunity.

    The Profile row comes from the JWT ownership chain (``get_my_profile``),
    so this variant never accepts an arbitrary profile id; only the shared
    opportunity is addressed by client input. Returns ``None`` when the
    opportunity does not exist. Same engine, same persistence path — no
    second matching logic.
    """
    owned_profile = _load_evaluable_profile(db, profile.id)
    if owned_profile is None:
        return None

    opportunity = _load_opportunity(db, opportunity_id)
    if opportunity is None:
        return None

    return _evaluate_and_persist(db, owned_profile, opportunity)


def get_match(
    db: Session, profile_id: uuid.UUID, opportunity_id: uuid.UUID
) -> Match | None:
    """Load one persisted Match with everything a response needs.

    Eager-loads ``requirement_results`` and each row's ``requirement``
    metadata so serializing the Match never issues one query per
    requirement. Rows keep their persisted (domain) order; no re-sorting
    happens here. Returns ``None`` when the pair has no Match yet — the
    same not-found convention as ``get_opportunity`` — and never
    evaluates, writes or commits.
    """
    return db.scalar(
        select(Match)
        .where(
            Match.profile_id == profile_id,
            Match.opportunity_id == opportunity_id,
        )
        .options(
            selectinload(Match.requirement_results).selectinload(
                MatchRequirement.requirement
            )
        )
    )


def get_match_for_user(
    db: Session, profile: Profile, opportunity_id: uuid.UUID
) -> Match | None:
    """Read one Match for the owned Profile only.

    The ownership scope lives inside the query (``profile_id = owned
    profile``), so another user's Match is indistinguishable from an
    absent one: callers get ``None`` either way and never see a
    cross-user row. Read-only — never evaluates, creates or updates.
    """
    return get_match(db, profile.id, opportunity_id)


def list_matches_for_user(
    db: Session, profile: Profile, limit: int, offset: int
) -> list[Match]:
    """List the owned Profile's Matches newest-first with bounded pagination.

    The single query is scoped to the caller's profile and eager-loads the
    full evidence chain (``requirement_results`` then ``requirement``) with
    two ``selectinload`` queries total — serializing every row never issues
    one query per requirement. Only ``matches`` columns are selected; no
    Profile or User columns are loaded for the response.
    """
    return list(
        db.scalars(
            select(Match)
            .where(Match.profile_id == profile.id)
            .options(
                selectinload(Match.requirement_results).selectinload(
                    MatchRequirement.requirement
                )
            )
            .order_by(Match.evaluated_at.desc(), Match.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )
