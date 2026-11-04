"""Pure lifecycle and publication-mode rules for acquisition sources."""
from __future__ import annotations

import itertools

import pytest

from app.intelligence.lifecycle import (
    PUBLISH_ORDER,
    TRANSITIONS,
    ApprovalFacts,
    LifecycleError,
    approval_problems,
    check_publish_mode_change,
    check_transition,
    is_discoverable,
    publish_mode_after_status,
)
from app.models.enums import AuthorityLevel, PublishMode, RobotsStatus, SourceStatus, TermsStatus

ALLOWED_MOVES = {
    (SourceStatus.PROPOSED, SourceStatus.TESTING),
    (SourceStatus.PROPOSED, SourceStatus.RETIRED),
    (SourceStatus.TESTING, SourceStatus.APPROVED),
    (SourceStatus.TESTING, SourceStatus.PROPOSED),
    (SourceStatus.TESTING, SourceStatus.RETIRED),
    (SourceStatus.APPROVED, SourceStatus.PAUSED),
    (SourceStatus.APPROVED, SourceStatus.RETIRED),
    (SourceStatus.PAUSED, SourceStatus.TESTING),
    (SourceStatus.PAUSED, SourceStatus.RETIRED),
}


def test_transition_table_covers_every_status():
    assert set(TRANSITIONS) == set(SourceStatus)


@pytest.mark.parametrize(("current", "target"), list(itertools.product(SourceStatus, SourceStatus)))
def test_every_status_pair(current, target):
    if (current, target) in ALLOWED_MOVES:
        check_transition(current, target)
    else:
        with pytest.raises(LifecycleError):
            check_transition(current, target)


def test_paused_source_cannot_be_reapproved_without_testing_again():
    with pytest.raises(LifecycleError):
        check_transition(SourceStatus.PAUSED, SourceStatus.APPROVED)


def test_retired_is_terminal():
    for target in SourceStatus:
        with pytest.raises(LifecycleError):
            check_transition(SourceStatus.RETIRED, target)


def _facts(**overrides) -> ApprovalFacts:
    values = {
        "terms_status": TermsStatus.ACCEPTABLE,
        "terms_reviewed": True,
        "robots_status": RobotsStatus.ALLOWED,
        "test_run_passed": True,
    }
    values.update(overrides)
    return ApprovalFacts(**values)


def test_approval_has_no_problems_when_every_prerequisite_holds():
    assert approval_problems(_facts()) == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"terms_status": TermsStatus.NOT_REVIEWED},
        {"terms_status": TermsStatus.RESTRICTED},
        {"terms_reviewed": False},
        {"robots_status": RobotsStatus.UNKNOWN},
        {"robots_status": RobotsStatus.DISALLOWED},
        {"robots_status": RobotsStatus.UNREACHABLE},
        {"test_run_passed": False},
    ],
)
def test_each_missing_prerequisite_blocks_approval(overrides):
    assert len(approval_problems(_facts(**overrides))) == 1


def test_all_problems_are_reported_together():
    facts = _facts(terms_status=TermsStatus.NOT_REVIEWED, robots_status=RobotsStatus.UNKNOWN, test_run_passed=False)
    assert len(approval_problems(facts)) == 3


@pytest.mark.parametrize("mode", list(PublishMode))
def test_leaving_approved_always_turns_publication_off(mode):
    for target in (SourceStatus.PAUSED, SourceStatus.RETIRED, SourceStatus.TESTING):
        assert publish_mode_after_status(target, mode) == PublishMode.OFF


def test_approval_itself_never_raises_publication():
    assert publish_mode_after_status(SourceStatus.APPROVED, PublishMode.OFF) == PublishMode.OFF


def _change(current, target, *, status=SourceStatus.APPROVED, authority=AuthorityLevel.OFFICIAL):
    check_publish_mode_change(status=status, authority_level=authority, current=current, target=target)


@pytest.mark.parametrize(("current", "target"), list(zip(PUBLISH_ORDER, PUBLISH_ORDER[1:])))
def test_publication_can_be_raised_one_step(current, target):
    _change(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [(PublishMode.OFF, PublishMode.LISTING_ONLY), (PublishMode.OFF, PublishMode.FULL), (PublishMode.SHADOW, PublishMode.FULL)],
)
def test_publication_cannot_skip_steps(current, target):
    with pytest.raises(LifecycleError):
        _change(current, target)


@pytest.mark.parametrize("current", [PublishMode.SHADOW, PublishMode.LISTING_ONLY, PublishMode.FULL])
def test_publication_can_always_be_lowered_to_off(current):
    _change(current, PublishMode.OFF, status=SourceStatus.PAUSED)


@pytest.mark.parametrize("status", [s for s in SourceStatus if s != SourceStatus.APPROVED])
def test_publication_cannot_be_raised_unless_approved(status):
    with pytest.raises(LifecycleError):
        _change(PublishMode.OFF, PublishMode.SHADOW, status=status)


@pytest.mark.parametrize("authority", [AuthorityLevel.SECONDARY, AuthorityLevel.COMMUNITY])
def test_non_official_sources_never_publish(authority):
    with pytest.raises(LifecycleError):
        _change(PublishMode.OFF, PublishMode.SHADOW, authority=authority)


def test_only_testing_and_approved_sources_are_discoverable():
    assert {status for status in SourceStatus if is_discoverable(status)} == {
        SourceStatus.TESTING,
        SourceStatus.APPROVED,
    }
