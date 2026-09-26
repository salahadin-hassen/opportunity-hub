"""Persistence mapping from matching engine results to Match rows."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Match,
    MatchOutcome,
    MatchRequirement,
    MatchStatus,
    Opportunity,
    Profile,
)
from app.services.matching import ENGINE_VERSION, MatchEvaluationResult, RequirementResult


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
