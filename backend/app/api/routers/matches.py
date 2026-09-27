"""Authenticated, user-scoped match endpoints.

The supported production contract addresses matches only through the
authenticated user's own profile::

    POST /me/opportunities/{opportunity_id}/match   evaluate (idempotent)
    GET  /me/opportunities/{opportunity_id}/match   read one Match
    GET  /me/matches                               list the profile's Matches

The client never supplies a ``profile_id``: the profile is derived from
the JWT via ``get_my_profile``, so one user can only ever read or
evaluate their own Matches. Opportunities are shared domain objects —
their existence is public, and using one grants no access to anyone
else's stored Match.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_my_profile
from app.db.session import get_db
from app.models import Opportunity, Profile
from app.schemas import MatchRead
from app.services.matches import (
    evaluate_and_persist_match_for_user,
    get_match_for_user,
    list_matches_for_user,
)

router = APIRouter(prefix="/me", tags=["matches"])


def _opportunity_or_match_not_found(db: Session, opportunity_id: uuid.UUID) -> HTTPException:
    """Build the read-only 404 for a Match lookup.

    Opportunities are shared, so their existence is not a secret and the
    existing ``Opportunity not found.`` convention applies. A Match that
    belongs to someone else is reported exactly like one that does not
    exist — the query is scoped to the caller's profile, so there is
    nothing further to reveal.
    """
    if db.get(Opportunity, opportunity_id) is None:
        detail = "Opportunity not found."
    else:
        detail = "Match not found."
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


@router.post(
    "/opportunities/{opportunity_id}/match",
    response_model=MatchRead,
    status_code=status.HTTP_200_OK,
)
def evaluate_for_me(
    opportunity_id: uuid.UUID,
    profile: Profile = Depends(get_my_profile),
    db: Session = Depends(get_db),
) -> MatchRead:
    """Evaluate the owned profile against one shared opportunity.

    The request carries only ``opportunity_id`` — the profile comes from
    the JWT and every verdict, fact and evidence row is server-generated
    by the matching engine. Idempotent for the Profile x Opportunity
    pair: re-evaluating updates the single existing Match and replaces
    its evidence instead of appending history.
    """
    match = evaluate_and_persist_match_for_user(db, profile, opportunity_id)
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found."
        )
    return match


@router.get("/opportunities/{opportunity_id}/match", response_model=MatchRead)
def get_one_for_me(
    opportunity_id: uuid.UUID,
    profile: Profile = Depends(get_my_profile),
    db: Session = Depends(get_db),
) -> MatchRead:
    """Return the owned profile's persisted Match for one opportunity.

    Read-only: this never evaluates, creates or updates anything. The
    lookup is scoped to the caller's profile inside the query, so another
    user's Match is indistinguishable from a missing one (404).
    """
    match = get_match_for_user(db, profile, opportunity_id)
    if match is None:
        raise _opportunity_or_match_not_found(db, opportunity_id)
    return match


@router.get("/matches", response_model=list[MatchRead])
def list_my_matches(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    profile: Profile = Depends(get_my_profile),
    db: Session = Depends(get_db),
) -> list[MatchRead]:
    """List the owned profile's Matches, newest evaluation first.

    Offset pagination is bounded server-side (1-100 rows per request), so
    no request can return the whole table. Only the caller's own Matches
    are ever selected.
    """
    return list_matches_for_user(db, profile, limit, offset)
