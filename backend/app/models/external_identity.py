"""Sign-in with an external identity provider (Google), and the short-lived records of the OAuth flow.

* ``ExternalIdentity`` links one provider account to one user. The provider's stable subject
  identifier (Google's ``sub``) is the key: an email address is never used to decide whose account a
  sign-in belongs to. One subject belongs to at most one user; a user has at most one identity per
  provider.
* ``OAuthState`` is one authorization attempt: its state, nonce and PKCE verifier, the browser it is
  bound to and what it is for (signing in, or linking to an already signed-in account). It is consumed
  exactly once and expires after a few minutes.
* ``OAuthHandoff`` is the single-use code that carries a finished sign-in from the API's callback back
  to the web app, which exchanges it for an ordinary session. It holds no token.

Secrets (state, binding, handoff code) are stored only as SHA-256 hashes.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

PROVIDERS = ("google",)
INTENTS = ("login", "link")


class ExternalIdentity(Base):
    __tablename__ = "external_identities"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    #: The provider's stable, unique account identifier (Google: the ID token's ``sub``).
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    #: The provider's verified email at the last sign-in; informational only, never used for matching.
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("provider", "subject", name="uq_external_identities_provider_subject"),
        UniqueConstraint("user_id", "provider", name="uq_external_identities_user_provider"),
        CheckConstraint("provider IN ('google')", name="ck_external_identities_provider"),
    )


class OAuthState(Base):
    __tablename__ = "oauth_states"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    state_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    #: Hash of the random value in the browser's binding cookie: the callback must come from this browser.
    binding_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    nonce: Mapped[str] = mapped_column(String(128), nullable=False)
    code_verifier: Mapped[str] = mapped_column(String(128), nullable=False)
    intent: Mapped[str] = mapped_column(String(8), nullable=False)
    #: For ``link``: the signed-in account that started the flow.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    next_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("intent IN ('login', 'link')", name="ck_oauth_states_intent"),
        CheckConstraint("intent <> 'link' OR user_id IS NOT NULL", name="ck_oauth_states_link_has_user"),
        Index("ix_oauth_states_expires_at", "expires_at"),
    )


class OAuthHandoff(Base):
    __tablename__ = "oauth_handoffs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    binding_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    is_new_user: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    next_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("outcome IN ('signed_in', 'linked')", name="ck_oauth_handoffs_outcome"),
        Index("ix_oauth_handoffs_expires_at", "expires_at"),
    )


__all__ = ["ExternalIdentity", "INTENTS", "OAuthHandoff", "OAuthState", "PROVIDERS"]
