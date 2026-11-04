"""Acquisition source registry: definitions, persistence, lifecycle and database invariants.

Every test runs inside the ``db_session`` transaction and is rolled back.
A scripted test connector is registered for the module; no network is used.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterable

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.intelligence import registry
from app.intelligence.connectors.base import (
    Connector,
    Lead,
    PageReader,
    SourceView,
    register_connector,
    unregister_connector,
)
from app.intelligence.definitions import SourceDefinition
from app.models import AcquisitionSource, AcquisitionSourceHost, User
from app.models.enums import (
    AuthorityLevel,
    DiscoveryMethod,
    PublishMode,
    RobotsStatus,
    SourceHostKind,
    SourceStatus,
    TermsStatus,
)


class UrlListConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    urls: list[str] = []


class UrlListTestConnector(Connector):
    key = "url_list_registry_test"
    discovery_method = DiscoveryMethod.URL_LIST
    config_model = UrlListConfig

    def discover(self, source: SourceView, pages: PageReader) -> Iterable[Lead]:
        return [Lead(url=url) for url in source.config.urls]


@pytest.fixture(autouse=True)
def test_connector():
    register_connector(UrlListTestConnector)
    yield
    unregister_connector(UrlListTestConnector.key)


def definition(**overrides) -> SourceDefinition:
    values = {
        "name": f"CERN careers {uuid.uuid4().hex[:6]}",
        "base_domain": "careers.cern",
        "allowed_hosts": ["careers.cern"],
        "application_hosts": ["smartrecruiters.com"],
        "category": "research_institution",
        "authority_level": "official",
        "provider": {"name": "CERN", "aliases": ["European Organization for Nuclear Research"]},
        "discovery_method": "url_list",
        "connector_key": UrlListTestConnector.key,
        "connector_config": {"urls": ["https://careers.cern/programmes/summer-studentship/"]},
    }
    values.update(overrides)
    return SourceDefinition.model_validate(values)


def approved_source(db: Session, **overrides) -> AcquisitionSource:
    source = registry.create_source(db, definition(**overrides))
    registry.change_status(db, source, SourceStatus.TESTING)
    registry.record_terms_review(db, source, status=TermsStatus.ACCEPTABLE, reviewer_id=None, notes="ok")
    registry.record_test_run(db, source, passed=True, robots_status=RobotsStatus.ALLOWED)
    registry.change_status(db, source, SourceStatus.APPROVED)
    return source


# --- Definitions ----------------------------------------------------------------------------------


def test_definition_canonicalises_hosts():
    item = definition(base_domain="CAREERS.cern", allowed_hosts=[" Careers.CERN "])
    assert item.base_domain == "careers.cern"
    assert item.allowed_hosts == ["careers.cern"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"allowed_hosts": []},
        {"allowed_hosts": ["evil.org"]},
        {"allowed_hosts": ["careers.cern.evil.org"]},
        {"allowed_hosts": ["careers.cern", "careers.cern"]},
        {"allowed_hosts": ["*.careers.cern"]},
        {"base_domain": "localhost"},
        {"application_hosts": ["careers.cern"]},
        {"provider": {"name": " "}},
        {"provider": {"name": "CERN", "aliases": ["cern"]}},
        {"provider": {"name": "CERN", "aliases": ["A", "a"]}},
        {"connector_key": "Bad Key"},
        {"crawl_policy": {"min_delay_seconds": 0.1}},
        {"crawl_policy": {"discovery_interval_hours": 0}},
        {"crawl_policy": {"max_pages_per_run": 10_000}},
        {"crawl_policy": {"unknown": 1}},
        {"category": "blog"},
        {"surprise": True},
    ],
)
def test_invalid_definitions_are_rejected(overrides):
    with pytest.raises(ValidationError):
        definition(**overrides)


# --- Creation and configuration -------------------------------------------------------------------


def test_new_source_is_proposed_with_publication_off(db_session):
    source = registry.create_source(db_session, definition())
    assert source.status == SourceStatus.PROPOSED
    assert source.publish_mode == PublishMode.OFF
    assert registry.allowed_hosts(source) == frozenset({"careers.cern"})
    assert registry.application_hosts(source) == frozenset({"smartrecruiters.com"})
    assert source.provider_aliases == ["European Organization for Nuclear Research"]
    assert source.crawl_policy == {"discovery_interval_hours": 24, "max_pages_per_run": 50, "min_delay_seconds": 5.0}


def test_unknown_connector_is_refused(db_session):
    with pytest.raises(registry.SourceConfigurationError):
        registry.create_source(db_session, definition(connector_key="not_registered"))


def test_connector_and_discovery_method_must_agree(db_session):
    with pytest.raises(registry.SourceConfigurationError):
        registry.create_source(db_session, definition(discovery_method="sitemap"))


def test_connector_config_is_validated_by_the_connector(db_session):
    with pytest.raises(registry.SourceConfigurationError):
        registry.create_source(db_session, definition(connector_config={"urls": "not-a-list"}))
    with pytest.raises(registry.SourceConfigurationError):
        registry.create_source(db_session, definition(connector_config={"surprise": 1}))


def test_an_allowed_host_belongs_to_one_source_only(db_session):
    registry.create_source(db_session, definition())
    with pytest.raises(registry.SourceConflictError):
        registry.create_source(db_session, definition())


def test_application_hosts_may_be_shared(db_session):
    registry.create_source(db_session, definition())
    other = registry.create_source(
        db_session, definition(base_domain="kaust.edu.sa", allowed_hosts=["admissions.kaust.edu.sa"])
    )
    assert registry.application_hosts(other) == frozenset({"smartrecruiters.com"})


def test_names_are_unique(db_session):
    registry.create_source(db_session, definition(name="Same name"))
    with pytest.raises(registry.SourceConflictError):
        registry.create_source(
            db_session, definition(name="Same name", base_domain="kaust.edu.sa", allowed_hosts=["kaust.edu.sa"])
        )


def test_a_conflict_leaves_the_session_usable(db_session):
    registry.create_source(db_session, definition())
    with pytest.raises(registry.SourceConflictError):
        registry.create_source(db_session, definition())
    assert db_session.scalar(select(AcquisitionSource).limit(1)) is not None


def test_find_source_for_host_uses_exact_allowed_hosts(db_session):
    source = registry.create_source(db_session, definition())
    assert registry.find_source_for_host(db_session, "CAREERS.cern") is source
    assert registry.find_source_for_host(db_session, "www.careers.cern") is None
    assert registry.find_source_for_host(db_session, "smartrecruiters.com") is None
    assert registry.find_source_for_host(db_session, "not a host") is None


# --- Lifecycle ------------------------------------------------------------------------------------


def test_full_approval_path(db_session):
    source = approved_source(db_session)
    assert source.status == SourceStatus.APPROVED
    assert source.publish_mode == PublishMode.OFF
    assert source.test_run_passed_at is not None


def test_approval_requires_every_prerequisite(db_session):
    source = registry.create_source(db_session, definition())
    registry.change_status(db_session, source, SourceStatus.TESTING)
    with pytest.raises(registry.SourceStateError) as error:
        registry.change_status(db_session, source, SourceStatus.APPROVED)
    assert "terms" in str(error.value) and "robots" in str(error.value) and "test run" in str(error.value)


def test_failed_test_run_blocks_approval(db_session):
    source = registry.create_source(db_session, definition())
    registry.change_status(db_session, source, SourceStatus.TESTING)
    registry.record_terms_review(db_session, source, status=TermsStatus.ACCEPTABLE, reviewer_id=None)
    registry.record_test_run(db_session, source, passed=False, robots_status=RobotsStatus.ALLOWED)
    with pytest.raises(registry.SourceStateError):
        registry.change_status(db_session, source, SourceStatus.APPROVED)


def test_a_passing_run_does_not_count_when_robots_disallow(db_session):
    source = registry.create_source(db_session, definition())
    registry.change_status(db_session, source, SourceStatus.TESTING)
    registry.record_test_run(db_session, source, passed=True, robots_status=RobotsStatus.DISALLOWED)
    assert source.test_run_passed_at is None


def test_test_runs_only_while_testing(db_session):
    source = registry.create_source(db_session, definition())
    with pytest.raises(registry.SourceStateError):
        registry.record_test_run(db_session, source, passed=True, robots_status=RobotsStatus.ALLOWED)


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_rejecting_or_retiring_requires_a_reason(db_session, reason):
    source = registry.create_source(db_session, definition())
    with pytest.raises(registry.SourceStateError):
        registry.change_status(db_session, source, SourceStatus.RETIRED, reason=reason)
    registry.change_status(db_session, source, SourceStatus.TESTING)
    with pytest.raises(registry.SourceStateError):
        registry.change_status(db_session, source, SourceStatus.PROPOSED, reason=reason)
    assert source.status == SourceStatus.TESTING


def test_invalid_transition_is_refused(db_session):
    source = registry.create_source(db_session, definition())
    with pytest.raises(registry.SourceStateError):
        registry.change_status(db_session, source, SourceStatus.APPROVED)


def test_pausing_turns_publication_off_and_retest_is_required(db_session):
    source = approved_source(db_session)
    registry.set_publish_mode(db_session, source, PublishMode.SHADOW)
    registry.change_status(db_session, source, SourceStatus.PAUSED)
    assert source.publish_mode == PublishMode.OFF
    registry.change_status(db_session, source, SourceStatus.TESTING)
    assert source.test_run_passed_at is None
    with pytest.raises(registry.SourceStateError):
        registry.change_status(db_session, source, SourceStatus.APPROVED)


def test_retired_source_cannot_be_edited_or_revived(db_session):
    source = registry.create_source(db_session, definition())
    registry.change_status(db_session, source, SourceStatus.RETIRED, reason="Provider closed the programme")
    with pytest.raises(registry.SourceStateError):
        registry.update_definition(db_session, source, definition())
    with pytest.raises(registry.SourceStateError):
        registry.change_status(db_session, source, SourceStatus.TESTING)


def test_status_changes_record_the_actor(db_session):
    actor = User(email=f"curator-{uuid.uuid4().hex[:8]}@example.org", password_hash="x")
    db_session.add(actor)
    db_session.flush()
    source = registry.create_source(db_session, definition(), actor_id=actor.id)
    assert source.status_changed_by == actor.id
    registry.change_status(db_session, source, SourceStatus.TESTING, actor_id=actor.id)
    assert source.status_changed_at is not None


# --- Publication mode -----------------------------------------------------------------------------


def test_publication_rises_one_step_at_a_time(db_session):
    source = approved_source(db_session)
    with pytest.raises(registry.SourceStateError):
        registry.set_publish_mode(db_session, source, PublishMode.FULL)
    for mode in (PublishMode.SHADOW, PublishMode.LISTING_ONLY, PublishMode.FULL):
        registry.set_publish_mode(db_session, source, mode)
    assert source.publish_mode == PublishMode.FULL
    registry.set_publish_mode(db_session, source, PublishMode.OFF)
    assert source.publish_mode == PublishMode.OFF


def test_unapproved_source_cannot_publish(db_session):
    source = registry.create_source(db_session, definition())
    with pytest.raises(registry.SourceStateError):
        registry.set_publish_mode(db_session, source, PublishMode.SHADOW)


def test_secondary_source_can_be_approved_but_never_publish(db_session):
    source = approved_source(
        db_session, authority_level=AuthorityLevel.SECONDARY, category="aggregator"
    )
    with pytest.raises(registry.SourceStateError):
        registry.set_publish_mode(db_session, source, PublishMode.SHADOW)


# --- Fail-closed events ---------------------------------------------------------------------------


def test_editing_an_approved_source_sends_it_back_to_testing(db_session):
    source = approved_source(db_session)
    registry.set_publish_mode(db_session, source, PublishMode.SHADOW)
    registry.update_definition(
        db_session, source, definition(name=source.name, allowed_hosts=["careers.cern", "jobs.careers.cern"])
    )
    assert source.status == SourceStatus.TESTING
    assert source.publish_mode == PublishMode.OFF
    assert source.test_run_passed_at is None
    assert registry.allowed_hosts(source) == frozenset({"careers.cern", "jobs.careers.cern"})


def test_editing_keeps_unchanged_hosts_without_conflict(db_session):
    source = registry.create_source(db_session, definition())
    registry.update_definition(db_session, source, definition(name=source.name))
    assert registry.allowed_hosts(source) == frozenset({"careers.cern"})


def test_editing_cannot_claim_another_sources_host(db_session):
    registry.create_source(db_session, definition(base_domain="kaust.edu.sa", allowed_hosts=["kaust.edu.sa"]))
    source = registry.create_source(db_session, definition())
    with pytest.raises(registry.SourceConflictError):
        registry.update_definition(
            db_session,
            source,
            definition(name=source.name, base_domain="kaust.edu.sa", allowed_hosts=["kaust.edu.sa"]),
        )


def test_restricted_terms_pause_an_approved_source(db_session):
    source = approved_source(db_session)
    registry.set_publish_mode(db_session, source, PublishMode.SHADOW)
    registry.record_terms_review(db_session, source, status=TermsStatus.RESTRICTED, reviewer_id=None)
    assert source.status == SourceStatus.PAUSED
    assert source.publish_mode == PublishMode.OFF


def test_a_review_must_reach_a_conclusion(db_session):
    source = registry.create_source(db_session, definition())
    with pytest.raises(registry.SourceStateError):
        registry.record_terms_review(db_session, source, status=TermsStatus.NOT_REVIEWED, reviewer_id=None)


@pytest.mark.parametrize("status", [RobotsStatus.DISALLOWED, RobotsStatus.UNREACHABLE, RobotsStatus.UNKNOWN])
def test_robots_no_longer_allowing_pauses_an_approved_source(db_session, status):
    source = approved_source(db_session)
    registry.record_robots_status(db_session, source, status)
    assert source.status == SourceStatus.PAUSED
    assert source.publish_mode == PublishMode.OFF


def test_repeated_failures_pause_an_approved_source(db_session):
    source = approved_source(db_session)
    results = [registry.record_run_failure(db_session, source, "timeout", pause_after=3) for _ in range(3)]
    assert results == [False, False, True]
    assert source.status == SourceStatus.PAUSED
    assert source.consecutive_failures == 3


def test_success_resets_the_failure_count(db_session):
    source = approved_source(db_session)
    registry.record_run_failure(db_session, source, "timeout")
    registry.record_run_success(db_session, source)
    assert source.consecutive_failures == 0
    assert source.last_success_at is not None


def test_failures_while_not_approved_never_pause_anything(db_session):
    source = registry.create_source(db_session, definition())
    registry.change_status(db_session, source, SourceStatus.TESTING)
    assert registry.record_run_failure(db_session, source, "x", pause_after=1) is False
    assert source.status == SourceStatus.TESTING


def test_stored_errors_are_one_bounded_printable_line(db_session):
    source = registry.create_source(db_session, definition())
    registry.record_run_failure(db_session, source, "line one\nline\x00two\t" + "x" * 1000)
    assert "\n" not in source.last_error and "\x00" not in source.last_error
    assert source.last_error.startswith("line one line two")
    assert len(source.last_error) == 500


# --- Source view for connectors --------------------------------------------------------------------


def test_source_view_carries_validated_config_and_exact_hosts(db_session):
    source = approved_source(db_session)
    view = registry.source_view(source)
    assert view.allowed_hosts == frozenset({"careers.cern"})
    assert isinstance(view.config, UrlListConfig)
    assert view.config.urls == ["https://careers.cern/programmes/summer-studentship/"]


@pytest.mark.parametrize("status", [SourceStatus.PROPOSED, SourceStatus.PAUSED, SourceStatus.RETIRED])
def test_no_view_for_sources_that_may_not_run(db_session, status):
    source = registry.create_source(db_session, definition())
    source.status = status
    with pytest.raises(registry.SourceStateError):
        registry.source_view(source)


def test_view_refuses_a_tampered_stored_config(db_session):
    source = approved_source(db_session)
    source.connector_config = {"urls": "tampered"}
    with pytest.raises(registry.SourceConfigurationError):
        registry.source_view(source)


# --- Database invariants (bypassing the service) ---------------------------------------------------


def _insert_raw(db: Session, **columns) -> None:
    values = {
        "id": uuid.uuid4(),
        "name": f"raw {uuid.uuid4().hex[:8]}",
        "base_domain": "raw.example-uni.edu",
        "category": "university",
        "authority_level": "official",
        "provider_name": "Raw",
        "discovery_method": "url_list",
        "connector_key": "url_list",
        "status": "proposed",
        "publish_mode": "off",
    }
    values.update(columns)
    names = ", ".join(values)
    params = ", ".join(f":{key}" for key in values)
    with db.begin_nested():
        db.execute(text(f"INSERT INTO acquisition_sources ({names}) VALUES ({params})"), values)


def test_database_accepts_a_plain_proposed_row(db_session):
    _insert_raw(db_session)


@pytest.mark.parametrize(
    "columns",
    [
        {"publish_mode": "shadow"},  # not approved
        {"status": "approved"},  # approval prerequisites missing
        {"status": "testing", "publish_mode": "full"},
        {"base_domain": "Raw.Example-Uni.edu"},
        {"consecutive_failures": -1},
        {"status": "live"},
        {"publish_mode": "everything"},
        {"authority_level": "trusted"},
    ],
)
def test_database_rejects_unsafe_rows(db_session, columns):
    with pytest.raises(IntegrityError):
        _insert_raw(db_session, **columns)


def test_database_rejects_publication_by_a_secondary_source(db_session):
    with pytest.raises(IntegrityError):
        _insert_raw(
            db_session,
            authority_level="secondary",
            status="approved",
            publish_mode="shadow",
            terms_status="acceptable",
            terms_reviewed_at="2026-11-01T00:00:00Z",
            robots_status="allowed",
            test_run_passed_at="2026-11-01T00:00:00Z",
        )


def test_database_enforces_one_owner_per_allowed_host(db_session):
    first = registry.create_source(db_session, definition())
    second = registry.create_source(
        db_session, definition(base_domain="kaust.edu.sa", allowed_hosts=["kaust.edu.sa"])
    )
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(AcquisitionSourceHost(source_id=second.id, host="careers.cern", kind=SourceHostKind.ALLOWED))
            db_session.flush()
    assert registry.allowed_hosts(first) == frozenset({"careers.cern"})


def test_database_rejects_upper_case_hosts(db_session):
    source = registry.create_source(db_session, definition())
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(AcquisitionSourceHost(source_id=source.id, host="Upper.Careers.cern", kind="allowed"))
            db_session.flush()


def test_deleting_a_source_removes_its_hosts(db_session):
    source = registry.create_source(db_session, definition())
    db_session.delete(source)
    db_session.flush()
    remaining = db_session.scalar(
        select(AcquisitionSourceHost).where(AcquisitionSourceHost.host == "careers.cern")
    )
    assert remaining is None
