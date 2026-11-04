"""Persistence service for the acquisition source registry.

All writes to ``acquisition_sources`` go through these functions, which
apply the pure rules in ``app.intelligence.lifecycle`` and the connector
contract, then flush (the caller owns the transaction, as elsewhere in
the codebase). Anything that weakens trust fails closed:

* editing an approved source sends it back to ``testing`` with publication ``off``;
* terms no longer acceptable, or robots.txt no longer allowing crawling,
  pauses an approved source;
* repeated run failures pause it automatically.

Every change is written to the audit log in the same transaction
(``app.services.audit``), with the acting user or ``system``. Rejecting
a source (back to ``proposed``) and retiring it require a reason.
Permission checks belong to the HTTP layer (``app.api.routers.curate``).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.intelligence.connectors.base import Connector, SourceView, UnknownConnectorError, get_connector
from app.intelligence.definitions import CrawlPolicy, SourceDefinition
from app.intelligence.hosts import InvalidHostError, normalize_host
from app.intelligence.lifecycle import (
    ApprovalFacts,
    LifecycleError,
    approval_problems,
    check_publish_mode_change,
    check_transition,
    is_discoverable,
    publish_mode_after_status,
)
from app.models import AcquisitionSource, AcquisitionSourceHost
from app.models.acquisition_source import MAX_ERROR_LENGTH
from app.models.enums import (
    AuthorityLevel,
    DiscoveryMethod,
    PublishMode,
    RobotsStatus,
    SourceHostKind,
    SourceStatus,
    TermsStatus,
)
from app.services import audit

#: Consecutive failed runs after which an approved source pauses itself.
AUTO_PAUSE_AFTER_FAILURES = 5

TARGET_TYPE = "acquisition_source"

#: Audit action per status a source moves to.
STATUS_ACTIONS: dict[SourceStatus, str] = {
    SourceStatus.TESTING: "source.testing_started",
    SourceStatus.APPROVED: "source.approved",
    SourceStatus.PROPOSED: "source.rejected",
    SourceStatus.PAUSED: "source.paused",
    SourceStatus.RETIRED: "source.retired",
}
#: Moves that undo or end a source's standing need a recorded reason.
REASON_REQUIRED = frozenset({SourceStatus.PROPOSED, SourceStatus.RETIRED})


class SourceRegistryError(Exception):
    """Base class for registry errors the API layer maps to 4xx responses."""


class SourceConfigurationError(SourceRegistryError):
    """The connector is unknown, does not match the discovery method, or rejects the config."""


class SourceConflictError(SourceRegistryError):
    """The name is taken or an allowed host already belongs to another source."""


class SourceStateError(SourceRegistryError):
    """The requested change is not allowed in the source's current state."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def allowed_hosts(source: AcquisitionSource) -> frozenset[str]:
    return frozenset(row.host for row in source.hosts if row.kind == SourceHostKind.ALLOWED)


def application_hosts(source: AcquisitionSource) -> frozenset[str]:
    return frozenset(row.host for row in source.hosts if row.kind == SourceHostKind.APPLICATION)


def snapshot(source: AcquisitionSource) -> dict[str, Any]:
    """The audited facts about a source (no personal data; timestamps reduced to booleans)."""
    return {
        "name": source.name,
        "base_domain": source.base_domain,
        "allowed_hosts": sorted(allowed_hosts(source)),
        "application_hosts": sorted(application_hosts(source)),
        "category": str(source.category),
        "authority_level": str(source.authority_level),
        "provider_name": source.provider_name,
        "provider_aliases": list(source.provider_aliases or []),
        "discovery_method": str(source.discovery_method),
        "connector_key": source.connector_key,
        "connector_config": source.connector_config,
        "crawl_policy": source.crawl_policy,
        "status": str(source.status),
        "publish_mode": str(source.publish_mode),
        "terms_status": str(source.terms_status),
        "terms_notes": source.terms_notes,
        "robots_status": str(source.robots_status),
        "test_run_passed": source.test_run_passed_at is not None,
    }


def _audit(
    db: Session,
    source: AcquisitionSource,
    action: str,
    before: dict[str, Any],
    *,
    actor_id: uuid.UUID | None,
    reason: str | None = None,
) -> None:
    audit.record(
        db,
        action=action,
        target_type=TARGET_TYPE,
        target_id=source.id,
        actor_id=actor_id,
        changes=audit.diff(before, snapshot(source)),
        reason=reason,
    )


def _resolve_connector(definition: SourceDefinition) -> tuple[type[Connector], BaseModel]:
    try:
        connector = get_connector(definition.connector_key)
    except UnknownConnectorError as error:
        raise SourceConfigurationError(f"No connector is registered as {definition.connector_key!r}.") from error
    if connector.discovery_method != definition.discovery_method:
        raise SourceConfigurationError(
            f"Connector {connector.key!r} implements {connector.discovery_method}, "
            f"not {definition.discovery_method}."
        )
    try:
        config = connector.config_model.model_validate(definition.connector_config)
    except ValidationError as error:
        raise SourceConfigurationError(f"Invalid {connector.key} configuration: {error}") from error
    return connector, config


def _apply_definition(source: AcquisitionSource, definition: SourceDefinition, config: BaseModel) -> None:
    source.name = definition.name
    source.base_domain = definition.base_domain
    source.category = definition.category
    source.authority_level = definition.authority_level
    source.provider_name = definition.provider.name
    source.provider_aliases = list(definition.provider.aliases)
    source.discovery_method = definition.discovery_method
    source.connector_key = definition.connector_key
    source.connector_config = config.model_dump(mode="json")
    source.crawl_policy = definition.crawl_policy.model_dump(mode="json")


def _host_rows(definition: SourceDefinition) -> list[AcquisitionSourceHost]:
    return [AcquisitionSourceHost(host=host, kind=SourceHostKind.ALLOWED) for host in definition.allowed_hosts] + [
        AcquisitionSourceHost(host=host, kind=SourceHostKind.APPLICATION) for host in definition.application_hosts
    ]


CONFLICT_MESSAGE = "Another source already uses this name or claims one of these allowed hosts."


def create_source(db: Session, definition: SourceDefinition, *, actor_id: uuid.UUID | None = None) -> AcquisitionSource:
    """Register a new source in ``proposed`` status with publication ``off``."""
    _, config = _resolve_connector(definition)
    source = AcquisitionSource(
        status=SourceStatus.PROPOSED,
        publish_mode=PublishMode.OFF,
        robots_status=RobotsStatus.UNKNOWN,
        terms_status=TermsStatus.NOT_REVIEWED,
        status_changed_at=_now(),
        status_changed_by=actor_id,
    )
    _apply_definition(source, definition, config)
    source.hosts = _host_rows(definition)
    try:
        with db.begin_nested():
            db.add(source)
            db.flush()
    except IntegrityError as error:
        raise SourceConflictError(CONFLICT_MESSAGE) from error
    _audit(db, source, "source.created", {}, actor_id=actor_id)
    return source


def update_definition(
    db: Session, source: AcquisitionSource, definition: SourceDefinition, *, actor_id: uuid.UUID | None = None
) -> AcquisitionSource:
    """Replace what a source declares; an approved or tested source must be tested again."""
    status = SourceStatus(source.status)
    if status == SourceStatus.RETIRED:
        raise SourceStateError("A retired source cannot be edited.")
    _, config = _resolve_connector(definition)
    before = snapshot(source)
    try:
        with db.begin_nested():
            _apply_definition(source, definition, config)
            # Delete the old host rows before inserting the new ones, so an
            # unchanged host never collides with itself on the unique index.
            source.hosts.clear()
            db.flush()
            source.hosts.extend(_host_rows(definition))
            source.test_run_passed_at = None
            if status in (SourceStatus.APPROVED, SourceStatus.PAUSED):
                _set_status(source, SourceStatus.TESTING, actor_id=actor_id)
            db.flush()
    except IntegrityError as error:
        raise SourceConflictError(CONFLICT_MESSAGE) from error
    _audit(db, source, "source.updated", before, actor_id=actor_id)
    return source


def change_status(
    db: Session,
    source: AcquisitionSource,
    target: SourceStatus,
    *,
    actor_id: uuid.UUID | None = None,
    reason: str | None = None,
) -> AcquisitionSource:
    """Move a source through its lifecycle, enforcing transitions, approval prerequisites and reasons."""
    current = SourceStatus(source.status)
    try:
        check_transition(current, target)
    except LifecycleError as error:
        raise SourceStateError(str(error)) from error
    if target in REASON_REQUIRED and not (reason or "").strip():
        raise SourceStateError(f"Moving a source to {target} requires a reason.")
    if target == SourceStatus.APPROVED:
        problems = approval_problems(
            ApprovalFacts(
                terms_status=TermsStatus(source.terms_status),
                terms_reviewed=source.terms_reviewed_at is not None,
                robots_status=RobotsStatus(source.robots_status),
                test_run_passed=source.test_run_passed_at is not None,
            )
        )
        if problems:
            raise SourceStateError("Cannot approve this source: " + "; ".join(problems) + ".")
    before = snapshot(source)
    _set_status(source, target, actor_id=actor_id)
    db.flush()
    _audit(db, source, STATUS_ACTIONS[target], before, actor_id=actor_id, reason=reason)
    return source


def _set_status(source: AcquisitionSource, target: SourceStatus, *, actor_id: uuid.UUID | None) -> None:
    source.publish_mode = publish_mode_after_status(target, PublishMode(source.publish_mode))
    if target == SourceStatus.TESTING:
        source.test_run_passed_at = None  # every (re-)test starts from scratch
    source.status = target
    source.status_changed_at = _now()
    source.status_changed_by = actor_id


def set_publish_mode(
    db: Session,
    source: AcquisitionSource,
    target: PublishMode,
    *,
    actor_id: uuid.UUID | None = None,
    reason: str | None = None,
) -> AcquisitionSource:
    """Raise publication one step on an approved official source, or lower it at once."""
    try:
        check_publish_mode_change(
            status=SourceStatus(source.status),
            authority_level=AuthorityLevel(source.authority_level),
            current=PublishMode(source.publish_mode),
            target=target,
        )
    except LifecycleError as error:
        raise SourceStateError(str(error)) from error
    if PublishMode(source.publish_mode) == target:
        return source
    before = snapshot(source)
    source.publish_mode = target
    db.flush()
    _audit(db, source, "source.publish_mode_changed", before, actor_id=actor_id, reason=reason)
    return source


def record_terms_review(
    db: Session,
    source: AcquisitionSource,
    *,
    status: TermsStatus,
    reviewer_id: uuid.UUID | None,
    notes: str | None = None,
) -> AcquisitionSource:
    """Record a person's review of the source's terms of use."""
    if SourceStatus(source.status) == SourceStatus.RETIRED:
        raise SourceStateError("A retired source cannot be reviewed.")
    if status == TermsStatus.NOT_REVIEWED:
        raise SourceStateError("A review must conclude acceptable or restricted.")
    before = snapshot(source)
    source.terms_status = status
    source.terms_reviewed_at = _now()
    source.terms_reviewed_by = reviewer_id
    source.terms_notes = notes
    if status != TermsStatus.ACCEPTABLE and SourceStatus(source.status) == SourceStatus.APPROVED:
        _set_status(source, SourceStatus.PAUSED, actor_id=reviewer_id)
    db.flush()
    _audit(db, source, "source.terms_reviewed", before, actor_id=reviewer_id)
    return source


def record_robots_status(db: Session, source: AcquisitionSource, status: RobotsStatus) -> AcquisitionSource:
    """Record the latest robots.txt verdict; anything but ``allowed`` pauses an approved source."""
    before = snapshot(source)
    source.robots_status = status
    source.robots_checked_at = _now()
    if status != RobotsStatus.ALLOWED and SourceStatus(source.status) == SourceStatus.APPROVED:
        _set_status(source, SourceStatus.PAUSED, actor_id=None)
    db.flush()
    if audit.diff(before, snapshot(source)):
        _audit(db, source, "source.robots_status_changed", before, actor_id=None)
    return source


def record_test_run(
    db: Session,
    source: AcquisitionSource,
    *,
    passed: bool,
    robots_status: RobotsStatus,
    actor_id: uuid.UUID | None = None,
) -> AcquisitionSource:
    """Record a dry run of the connector; only possible while the source is ``testing``."""
    if SourceStatus(source.status) != SourceStatus.TESTING:
        raise SourceStateError("Test runs are recorded only while a source is in testing.")
    before = snapshot(source)
    source.robots_status = robots_status
    source.robots_checked_at = _now()
    source.test_run_passed_at = _now() if passed and robots_status == RobotsStatus.ALLOWED else None
    db.flush()
    audit.record(
        db,
        action="source.test_run_recorded",
        target_type=TARGET_TYPE,
        target_id=source.id,
        actor_id=actor_id,
        changes={**audit.diff(before, snapshot(source)), "passed": passed},
    )
    return source


def record_run_success(db: Session, source: AcquisitionSource) -> AcquisitionSource:
    """Note a successful discovery or monitoring run (health only; not audited)."""
    source.last_success_at = _now()
    source.consecutive_failures = 0
    db.flush()
    return source


def record_run_failure(
    db: Session,
    source: AcquisitionSource,
    error: str,
    *,
    pause_after: int = AUTO_PAUSE_AFTER_FAILURES,
) -> bool:
    """Note a failed run; return True when this failure paused an approved source (audited)."""
    before = snapshot(source)
    source.last_failure_at = _now()
    source.last_error = sanitize_error(error)
    source.consecutive_failures += 1
    paused = (
        SourceStatus(source.status) == SourceStatus.APPROVED and source.consecutive_failures >= pause_after
    )
    if paused:
        _set_status(source, SourceStatus.PAUSED, actor_id=None)
    db.flush()
    if paused:
        _audit(
            db, source, "source.auto_paused", before, actor_id=None,
            reason=f"{source.consecutive_failures} consecutive failed runs",
        )
    return paused


def sanitize_error(error: str) -> str:
    """One line, printable, bounded: safe to store and show to a curator."""
    flattened = "".join(char if char.isprintable() else " " for char in str(error))
    collapsed = " ".join(flattened.split())
    return collapsed[:MAX_ERROR_LENGTH] or "unknown error"


def source_view(source: AcquisitionSource) -> SourceView:
    """The read-only view a connector receives; only for sources in testing or approved."""
    if not is_discoverable(SourceStatus(source.status)):
        raise SourceStateError(f"Source {source.name!r} is {source.status}; discovery is not allowed.")
    try:
        connector = get_connector(source.connector_key)
    except UnknownConnectorError as error:
        raise SourceConfigurationError(f"No connector is registered as {source.connector_key!r}.") from error
    try:
        config = connector.config_model.model_validate(source.connector_config)
        crawl_policy = CrawlPolicy.model_validate(source.crawl_policy)
    except ValidationError as error:
        raise SourceConfigurationError(f"Stored configuration for {source.name!r} is invalid: {error}") from error
    hosts = allowed_hosts(source)
    if not hosts:
        raise SourceConfigurationError(f"Source {source.name!r} has no allowed hosts.")
    return SourceView(
        id=source.id,
        name=source.name,
        base_domain=source.base_domain,
        allowed_hosts=hosts,
        discovery_method=DiscoveryMethod(source.discovery_method),
        crawl_policy=crawl_policy,
        config=config,
    )


def find_source_for_host(db: Session, host: str) -> AcquisitionSource | None:
    """The source that claims ``host`` as an allowed host, if any."""
    try:
        canonical = normalize_host(host)
    except InvalidHostError:
        return None
    return db.scalar(
        select(AcquisitionSource)
        .join(AcquisitionSourceHost)
        .where(AcquisitionSourceHost.host == canonical, AcquisitionSourceHost.kind == SourceHostKind.ALLOWED)
    )


__all__ = [
    "AUTO_PAUSE_AFTER_FAILURES",
    "SourceConfigurationError",
    "SourceConflictError",
    "SourceRegistryError",
    "SourceStateError",
    "allowed_hosts",
    "application_hosts",
    "change_status",
    "create_source",
    "find_source_for_host",
    "record_robots_status",
    "record_run_failure",
    "record_run_success",
    "record_terms_review",
    "record_test_run",
    "sanitize_error",
    "set_publish_mode",
    "snapshot",
    "source_view",
    "update_definition",
]
