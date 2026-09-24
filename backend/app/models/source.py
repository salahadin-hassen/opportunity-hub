"""OpportunitySource model: provenance and evidence for an opportunity."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import SourceType, enum_check_constraint

if TYPE_CHECKING:
    from app.models.opportunity import Opportunity
    from app.models.requirement import Requirement


class Source(Base):
    """One provenance record for an opportunity.

    Stores where the data came from and a snapshot of the official
    content so requirement evidence (``Requirement.source_quote``) stays
    verifiable even if the original page changes.
    """

    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default=SourceType.MANUAL_ENTRY)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_snapshot: Mapped[dict[str, Any] | list[Any] | str | None] = mapped_column(JSONB, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    opportunity: Mapped[Opportunity] = relationship(back_populates="sources")
    requirements: Mapped[list[Requirement]] = relationship(
        back_populates="source",
        passive_deletes=True,
    )

    __table_args__ = (
        enum_check_constraint("sources", "source_type", SourceType),
        Index("ix_sources_opportunity_id", "opportunity_id"),
        Index(
            "uq_sources_primary_per_opportunity",
            "opportunity_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
    )

    def __repr__(self) -> str:
        return f"<Source {self.source_type} {self.url!r}>"
