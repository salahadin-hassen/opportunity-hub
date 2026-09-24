"""Opportunity model: a generic scholarship/internship/fellowship/etc. record."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Index, String, Text, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    DeadlineType,
    LocationMode,
    OpportunityStatus,
    OpportunityType,
    enum_check_constraint,
)

if TYPE_CHECKING:
    from app.models.requirement import Requirement
    from app.models.source import Source


class Opportunity(Base):
    """A single discoverable opportunity of any type.

    Holds descriptive and scheduling facts only; eligibility conditions
    live on related :class:`~app.models.requirement.Requirement` rows.
    """

    __tablename__ = "opportunities"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    opportunity_type: Mapped[str] = mapped_column(String(32), nullable=False, default=OpportunityType.OTHER)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    host_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    official_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_type: Mapped[str] = mapped_column(String(16), nullable=False, default=DeadlineType.FIXED)
    starts_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    ends_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    location_mode: Mapped[str] = mapped_column(String(16), nullable=False, default=LocationMode.UNKNOWN)
    countries: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    languages: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    tags: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )

    status: Mapped[str] = mapped_column(String(16), nullable=False, default=OpportunityStatus.DRAFT)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    requirements: Mapped[list[Requirement]] = relationship(
        back_populates="opportunity",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Requirement.order_index",
    )
    sources: Mapped[list[Source]] = relationship(
        back_populates="opportunity",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Source.retrieved_at.desc()",
    )

    __table_args__ = (
        enum_check_constraint("opportunities", "opportunity_type", OpportunityType),
        enum_check_constraint("opportunities", "deadline_type", DeadlineType),
        enum_check_constraint("opportunities", "location_mode", LocationMode),
        enum_check_constraint("opportunities", "status", OpportunityStatus),
        Index("ix_opportunities_status_deadline", "status", "deadline_at"),
        Index("ix_opportunities_type_status", "opportunity_type", "status"),
    )

    def __repr__(self) -> str:
        return f"<Opportunity {self.slug!r} ({self.opportunity_type})>"
