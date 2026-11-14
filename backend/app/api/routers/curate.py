"""Curator API for the acquisition source registry (M2-T6 routes).

Every route requires a signed-in account whose stored role grants the
permission for that specific action (``app.core.permissions``): reading
is checked before anything is looked up, so students learn nothing about
which sources exist. All rules stay in ``app.intelligence.registry`` and
every change is audited there, in the request's transaction.

There is deliberately no route to record a test run: that is the
fetcher's job (M2-T7). Until it exists, no source can be approved.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.permissions import Permission, has_permission
from app.db.session import get_db
from app.intelligence import registry
from app.intelligence.definitions import SourceDefinition
from app.intelligence.lifecycle import PUBLISH_ORDER
from app.models import AcquisitionSource, AuditLog, User
from app.models.enums import PublishMode, SourceStatus
from app.schemas.acquisition_source import (
    AuditEntryRead,
    ProviderRead,
    PublishModeChange,
    SourceRead,
    StatusChange,
    TermsReview,
)

router = APIRouter(prefix="/curate/sources", tags=["curate"])

#: The permission each target status needs.
STATUS_PERMISSIONS: dict[SourceStatus, Permission] = {
    SourceStatus.TESTING: Permission.SOURCE_TEST,
    SourceStatus.PROPOSED: Permission.SOURCE_TEST,
    SourceStatus.PAUSED: Permission.SOURCE_PAUSE,
    SourceStatus.APPROVED: Permission.SOURCE_APPROVE,
    SourceStatus.RETIRED: Permission.SOURCE_RETIRE,
}

FORBIDDEN = "You do not have permission for this action."


def _read(source: AcquisitionSource) -> SourceRead:
    return SourceRead(
        id=source.id,
        name=source.name,
        base_domain=source.base_domain,
        allowed_hosts=sorted(registry.allowed_hosts(source)),
        application_hosts=sorted(registry.application_hosts(source)),
        category=source.category,
        authority_level=source.authority_level,
        provider=ProviderRead(name=source.provider_name, aliases=list(source.provider_aliases or [])),
        discovery_method=source.discovery_method,
        connector_key=source.connector_key,
        connector_config=source.connector_config,
        crawl_policy=source.crawl_policy,
        robots_status=source.robots_status,
        robots_checked_at=source.robots_checked_at,
        terms_status=source.terms_status,
        terms_reviewed_at=source.terms_reviewed_at,
        terms_notes=source.terms_notes,
        test_run_passed_at=source.test_run_passed_at,
        status=source.status,
        publish_mode=source.publish_mode,
        status_changed_at=source.status_changed_at,
        last_success_at=source.last_success_at,
        last_failure_at=source.last_failure_at,
        last_error=source.last_error,
        consecutive_failures=source.consecutive_failures,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


def _load(db: Session, source_id: uuid.UUID) -> AcquisitionSource:
    source = db.get(AcquisitionSource, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found.")
    return source


def _require(user: User, permission: Permission) -> None:
    if not has_permission(user.role, permission):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=FORBIDDEN)


def _registry_error(error: registry.SourceRegistryError) -> HTTPException:
    if isinstance(error, registry.SourceConfigurationError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))


@router.get("", response_model=list[SourceRead])
def list_sources(
    status_filter: SourceStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.SOURCE_READ)),
) -> list[SourceRead]:
    statement = select(AcquisitionSource).order_by(AcquisitionSource.created_at, AcquisitionSource.id)
    if status_filter is not None:
        statement = statement.where(AcquisitionSource.status == status_filter)
    return [_read(source) for source in db.scalars(statement.offset(offset).limit(limit))]


@router.post("", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
def propose_source(
    definition: SourceDefinition,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.SOURCE_PROPOSE)),
) -> SourceRead:
    try:
        return _read(registry.create_source(db, definition, actor_id=user.id))
    except registry.SourceRegistryError as error:
        raise _registry_error(error) from error


@router.get("/{source_id}", response_model=SourceRead)
def get_source(
    source_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.SOURCE_READ)),
) -> SourceRead:
    return _read(_load(db, source_id))


@router.put("/{source_id}", response_model=SourceRead)
def edit_source(
    source_id: uuid.UUID,
    definition: SourceDefinition,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.SOURCE_EDIT)),
) -> SourceRead:
    source = _load(db, source_id)
    try:
        return _read(registry.update_definition(db, source, definition, actor_id=user.id))
    except registry.SourceRegistryError as error:
        raise _registry_error(error) from error


@router.post("/{source_id}/terms-review", response_model=SourceRead)
def review_terms(
    source_id: uuid.UUID,
    review: TermsReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.SOURCE_REVIEW)),
) -> SourceRead:
    source = _load(db, source_id)
    try:
        return _read(registry.record_terms_review(db, source, status=review.status, reviewer_id=user.id, notes=review.notes))
    except registry.SourceRegistryError as error:
        raise _registry_error(error) from error


@router.post("/{source_id}/status", response_model=SourceRead)
def change_status(
    source_id: uuid.UUID,
    change: StatusChange,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.SOURCE_READ)),
) -> SourceRead:
    _require(user, STATUS_PERMISSIONS[change.status])
    source = _load(db, source_id)
    try:
        return _read(registry.change_status(db, source, change.status, actor_id=user.id, reason=change.reason))
    except registry.SourceRegistryError as error:
        raise _registry_error(error) from error


@router.post("/{source_id}/publish-mode", response_model=SourceRead)
def change_publish_mode(
    source_id: uuid.UUID,
    change: PublishModeChange,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.SOURCE_READ)),
) -> SourceRead:
    source = _load(db, source_id)
    raising = PUBLISH_ORDER.index(change.mode) > PUBLISH_ORDER.index(PublishMode(source.publish_mode))
    _require(user, Permission.SOURCE_PUBLISH_RAISE if raising else Permission.SOURCE_PUBLISH_LOWER)
    try:
        return _read(registry.set_publish_mode(db, source, change.mode, actor_id=user.id, reason=change.reason))
    except registry.SourceRegistryError as error:
        raise _registry_error(error) from error


@router.get("/{source_id}/history", response_model=list[AuditEntryRead])
def source_history(
    source_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.SOURCE_READ)),
) -> list[AuditLog]:
    _load(db, source_id)
    return list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.target_type == registry.TARGET_TYPE, AuditLog.target_id == str(source_id))
            .order_by(AuditLog.id)
            .limit(limit)
        )
    )


admin_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_router.get("/audit", response_model=list[AuditEntryRead])
def read_audit(
    target_type: str | None = Query(default=None, max_length=32),
    target_id: str | None = Query(default=None, max_length=64),
    action: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=100),
    before_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.AUDIT_READ)),
) -> list[AuditLog]:
    """Newest first; page with ``before_id``."""
    statement = select(AuditLog).order_by(AuditLog.id.desc())
    if target_type:
        statement = statement.where(AuditLog.target_type == target_type)
    if target_id:
        statement = statement.where(AuditLog.target_id == target_id)
    if action:
        statement = statement.where(AuditLog.action == action)
    if before_id:
        statement = statement.where(AuditLog.id < before_id)
    return list(db.scalars(statement.limit(limit)))


__all__ = ["admin_router", "router"]
