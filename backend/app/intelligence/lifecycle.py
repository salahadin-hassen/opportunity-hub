"""Lifecycle and publication-mode rules for acquisition sources (pure, no database).

Status::

    proposed → testing → approved → paused → testing → approved …
         ↘          ↘          ↘        ↘
                         retired (terminal)

Publication mode can only be raised on an approved, official source and
only one step at a time (off → shadow → listing_only → full); it can be
lowered to any level at once. Every status change away from ``approved``
forces the mode back to ``off``, so automation fails closed.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import AuthorityLevel, PublishMode, RobotsStatus, SourceStatus, TermsStatus

TRANSITIONS: dict[SourceStatus, frozenset[SourceStatus]] = {
    SourceStatus.PROPOSED: frozenset({SourceStatus.TESTING, SourceStatus.RETIRED}),
    SourceStatus.TESTING: frozenset({SourceStatus.APPROVED, SourceStatus.PROPOSED, SourceStatus.RETIRED}),
    SourceStatus.APPROVED: frozenset({SourceStatus.PAUSED, SourceStatus.RETIRED}),
    SourceStatus.PAUSED: frozenset({SourceStatus.TESTING, SourceStatus.RETIRED}),
    SourceStatus.RETIRED: frozenset(),
}

PUBLISH_ORDER: tuple[PublishMode, ...] = (
    PublishMode.OFF,
    PublishMode.SHADOW,
    PublishMode.LISTING_ONLY,
    PublishMode.FULL,
)

#: Statuses in which a connector may run discovery: a dry run while testing, real runs once approved.
DISCOVERABLE_STATUSES = frozenset({SourceStatus.TESTING, SourceStatus.APPROVED})


class LifecycleError(ValueError):
    """Raised when a requested status or publication-mode change is not allowed."""


@dataclass(frozen=True)
class ApprovalFacts:
    """The recorded facts approval depends on.

    Secondary and community sources can be approved too (for leads); what
    keeps them from publishing is ``check_publish_mode_change``.
    """

    terms_status: TermsStatus
    terms_reviewed: bool
    robots_status: RobotsStatus
    test_run_passed: bool


def check_transition(current: SourceStatus, target: SourceStatus) -> None:
    """Raise ``LifecycleError`` unless ``current → target`` is a permitted move."""
    if target not in TRANSITIONS[current]:
        allowed = ", ".join(sorted(TRANSITIONS[current])) or "none (terminal)"
        raise LifecycleError(f"Cannot move a source from {current} to {target}; allowed: {allowed}.")


def approval_problems(facts: ApprovalFacts) -> list[str]:
    """List every unmet prerequisite for approval (empty when approval may proceed)."""
    problems = []
    if facts.terms_status != TermsStatus.ACCEPTABLE or not facts.terms_reviewed:
        problems.append("terms of use have not been reviewed as acceptable")
    if facts.robots_status != RobotsStatus.ALLOWED:
        problems.append(f"robots.txt status is {facts.robots_status}, not allowed")
    if not facts.test_run_passed:
        problems.append("no passing test run is recorded")
    return problems


def publish_mode_after_status(target: SourceStatus, current_mode: PublishMode) -> PublishMode:
    """The publication mode a source has after moving to ``target``.

    Approval never raises the mode by itself; leaving ``approved`` resets it to ``off``.
    """
    return current_mode if target == SourceStatus.APPROVED else PublishMode.OFF


def check_publish_mode_change(
    *,
    status: SourceStatus,
    authority_level: AuthorityLevel,
    current: PublishMode,
    target: PublishMode,
) -> None:
    """Raise ``LifecycleError`` unless the publication mode may change from ``current`` to ``target``."""
    if target == current:
        return
    if PUBLISH_ORDER.index(target) < PUBLISH_ORDER.index(current):
        return  # lowering is always allowed and takes effect at once
    if status != SourceStatus.APPROVED:
        raise LifecycleError(f"Publication can be raised only on an approved source (status is {status}).")
    if authority_level != AuthorityLevel.OFFICIAL:
        raise LifecycleError("Only official sources can publish; secondary and community sources produce leads only.")
    if PUBLISH_ORDER.index(target) - PUBLISH_ORDER.index(current) != 1:
        next_mode = PUBLISH_ORDER[PUBLISH_ORDER.index(current) + 1]
        raise LifecycleError(f"Raise publication one step at a time: from {current} the next step is {next_mode}.")


def is_discoverable(status: SourceStatus) -> bool:
    """Whether a connector may run for a source in ``status``."""
    return status in DISCOVERABLE_STATUSES


__all__ = [
    "ApprovalFacts",
    "DISCOVERABLE_STATUSES",
    "LifecycleError",
    "PUBLISH_ORDER",
    "TRANSITIONS",
    "approval_problems",
    "check_publish_mode_change",
    "check_transition",
    "is_discoverable",
    "publish_mode_after_status",
]
