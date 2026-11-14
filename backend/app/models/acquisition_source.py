"""Acquisition source registry: where the ingestion pipeline may look, and how far it may go.

A source is approved by a person once (provider identity, terms of use,
robots.txt) and then drives discovery and publication for its exact,
listed hostnames only. The invariants that keep an unapproved or
non-official source from ever publishing are enforced here as database
constraints, not just in the service layer.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    AuthorityLevel,
    DiscoveryMethod,
    PublishMode,
    RobotsStatus,
    SourceCategory,
    SourceHostKind,
    SourceStatus,
    TermsStatus,
    enum_check_constraint,
)

MAX_HOSTNAME_LENGTH = 253
MAX_ERROR_LENGTH = 500


class AcquisitionSource(Base):
    """One approved-or-pending place the pipeline may discover opportunities from."""

    __tablename__ = "acquisition_sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    base_domain: Mapped[str] = mapped_column(String(MAX_HOSTNAME_LENGTH), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    authority_level: Mapped[str] = mapped_column(String(16), nullable=False)

    provider_name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_aliases: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )

    discovery_method: Mapped[str] = mapped_column(String(32), nullable=False)
    connector_key: Mapped[str] = mapped_column(String(64), nullable=False)
    connector_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    crawl_policy: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    robots_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=RobotsStatus.UNKNOWN, server_default=RobotsStatus.UNKNOWN.value
    )
    robots_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terms_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=TermsStatus.NOT_REVIEWED, server_default=TermsStatus.NOT_REVIEWED.value
    )
    terms_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terms_reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    terms_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Set only by a successful dry run of the connector against the live source.
    test_run_passed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=SourceStatus.PROPOSED, server_default=SourceStatus.PROPOSED.value
    )
    publish_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default=PublishMode.OFF, server_default=PublishMode.OFF.value
    )
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status_changed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(MAX_ERROR_LENGTH), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    hosts: Mapped[list[AcquisitionSourceHost]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="(AcquisitionSourceHost.kind, AcquisitionSourceHost.host)",
    )

    __table_args__ = (
        enum_check_constraint("acquisition_sources", "category", SourceCategory),
        enum_check_constraint("acquisition_sources", "authority_level", AuthorityLevel),
        enum_check_constraint("acquisition_sources", "discovery_method", DiscoveryMethod),
        enum_check_constraint("acquisition_sources", "robots_status", RobotsStatus),
        enum_check_constraint("acquisition_sources", "terms_status", TermsStatus),
        enum_check_constraint("acquisition_sources", "status", SourceStatus),
        enum_check_constraint("acquisition_sources", "publish_mode", PublishMode),
        CheckConstraint("base_domain = lower(base_domain)", name="ck_acquisition_sources_base_domain_lower"),
        CheckConstraint("consecutive_failures >= 0", name="ck_acquisition_sources_failures_nonnegative"),
        # Only an approved source may run with publication beyond "off".
        CheckConstraint(
            "publish_mode = 'off' OR status = 'approved'",
            name="ck_acquisition_sources_publish_requires_approval",
        ),
        # Secondary and community sources produce leads only; they never publish.
        CheckConstraint(
            "publish_mode = 'off' OR authority_level = 'official'",
            name="ck_acquisition_sources_publish_requires_official",
        ),
        # Approval needs an accepted terms review, permissive robots.txt and a passed test run.
        CheckConstraint(
            "status <> 'approved' OR ("
            "terms_status = 'acceptable' AND terms_reviewed_at IS NOT NULL "
            "AND robots_status = 'allowed' AND test_run_passed_at IS NOT NULL)",
            name="ck_acquisition_sources_approval_prerequisites",
        ),
        Index("ix_acquisition_sources_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<AcquisitionSource {self.name!r} ({self.status}, {self.publish_mode})>"


class AcquisitionSourceHost(Base):
    """One exact hostname a source may fetch from (``allowed``) or link applicants to (``application``).

    Hostnames are exact: no wildcards, no ports, lower-case ASCII (IDNA).
    An ``allowed`` host belongs to at most one source, so two registry
    entries can never both claim authority over the same site.
    """

    __tablename__ = "acquisition_source_hosts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("acquisition_sources.id", ondelete="CASCADE"), nullable=False
    )
    host: Mapped[str] = mapped_column(String(MAX_HOSTNAME_LENGTH), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    source: Mapped[AcquisitionSource] = relationship(back_populates="hosts")

    __table_args__ = (
        enum_check_constraint("acquisition_source_hosts", "kind", SourceHostKind),
        CheckConstraint("host = lower(host)", name="ck_acquisition_source_hosts_host_lower"),
        UniqueConstraint("source_id", "host", "kind", name="uq_acquisition_source_hosts_source_host_kind"),
        Index(
            "uq_acquisition_source_hosts_allowed_host",
            "host",
            unique=True,
            postgresql_where=text("kind = 'allowed'"),
        ),
        Index("ix_acquisition_source_hosts_host", "host"),
    )

    def __repr__(self) -> str:
        return f"<AcquisitionSourceHost {self.kind} {self.host!r}>"
