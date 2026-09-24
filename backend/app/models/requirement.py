"""Requirement model: one atomic, checkable condition of an opportunity."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import RequirementCategory, RequirementKind, enum_check_constraint

if TYPE_CHECKING:
    from app.models.opportunity import Opportunity
    from app.models.source import Source


class Requirement(Base):
    """A single eligibility condition attached to an opportunity.

    The condition itself is the pair ``kind`` + ``params`` (stored as
    JSONB); the remaining columns form the relational shell shared by
    every requirement: ordering, mandatory flag, category, evidence
    (``source`` + ``source_quote``) and ambiguity.
    """

    __tablename__ = "requirements"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    label: Mapped[str] = mapped_column(String(500), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    is_mandatory: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    category: Mapped[str] = mapped_column(
        String(32), nullable=False, default=RequirementCategory.OTHER, server_default="other"
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sources.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_ambiguous: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    opportunity: Mapped[Opportunity] = relationship(back_populates="requirements")
    source: Mapped[Source | None] = relationship(back_populates="requirements")

    __table_args__ = (
        enum_check_constraint("requirements", "kind", RequirementKind),
        enum_check_constraint("requirements", "category", RequirementCategory),
        Index("ix_requirements_opportunity_order", "opportunity_id", "order_index"),
        Index("ix_requirements_source_id", "source_id"),
    )

    def __repr__(self) -> str:
        return f"<Requirement {self.kind} {self.label!r}>"
