"""Sign in with Google: OpenID Connect, Authorization Code flow with PKCE, verified on the server.

The flow
1. ``begin``: the API creates a single-use state (with a nonce and a PKCE verifier) bound to this
   browser by a random value in an httpOnly cookie, and returns Google's authorization URL.
2. Google sends the browser back to the API's callback with ``code`` and ``state``.
   ``consume_state`` claims the state atomically (a replayed callback finds it already consumed) and
   checks the browser's binding cookie against it (no login CSRF: an attacker's state is useless in a
   victim's browser).
3. ``exchange_code`` redeems the code at Google's token endpoint, server to server, with the client
   secret and the PKCE verifier. ``verify_id_token`` checks the ID token's RS256 signature against
   Google's published keys, its issuer, audience (and authorized party), expiry and issue time, the
   nonce, and that Google has verified the email.
4. ``complete`` maps Google's stable subject (``sub``) to an account — never the email alone:
   * a known subject signs in to its account;
   * an unknown subject whose verified email belongs to no account creates a new account;
   * an unknown subject whose email already belongs to an account is refused (``link_required``):
     the owner must sign in the usual way and connect Google from their profile;
   * ``link`` (started by a signed-in user) attaches the subject to that user, unless it already
     belongs to someone else (``identity_in_use``) or the user already has another Google account
     connected (``already_linked``).
5. ``create_handoff`` returns a single-use code (60 s, bound to the same browser) that the web app
   exchanges for an ordinary session (``redeem_handoff``). No token ever appears in a URL.

Nothing the browser submits about the identity (email, name, subject) is trusted; only the verified
ID token is.
"""
from __future__ import annotations

import base64
import functools
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ExternalIdentity, OAuthHandoff, OAuthState, User
from app.services import audit

AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")
PROVIDER = "google"
STATE_TTL = timedelta(minutes=10)
HANDOFF_TTL = timedelta(seconds=60)
CLOCK_SKEW_SECONDS = 60
MAX_NEXT_LENGTH = 512


class GoogleSignInError(Exception):
    """A refused sign-in. ``code`` is safe to show the browser; details are only logged."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def safe_next(value: str | None) -> str | None:
    """A same-site path to return to, or None. Never an absolute or protocol-relative URL."""
    if not value or len(value) > MAX_NEXT_LENGTH:
        return None
    if not value.startswith("/") or value.startswith("//") or "\\" in value or any(ord(c) < 0x20 for c in value):
        return None
    return value


# --- 1. begin --------------------------------------------------------------------------------------

@dataclass
class Begun:
    authorization_url: str
    binding: str  # the raw value for the browser's httpOnly binding cookie


def begin(db: Session, *, intent: str, next_path: str | None, user_id: uuid.UUID | None = None,
          now: datetime | None = None) -> Begun:
    if intent not in ("login", "link"):
        raise ValueError("intent must be login or link")
    if intent == "link" and user_id is None:
        raise ValueError("linking needs the signed-in user")
    now = now or _now()
    state = secrets.token_urlsafe(32)
    binding = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)  # 86 characters: within RFC 7636's 43-128
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    # Old attempts are useless after they expire; keep the table small.
    db.execute(delete(OAuthState).where(OAuthState.expires_at < now - timedelta(days=1)))
    db.execute(delete(OAuthHandoff).where(OAuthHandoff.expires_at < now - timedelta(days=1)))
    db.add(OAuthState(
        provider=PROVIDER, state_hash=_hash(state), binding_hash=_hash(binding), nonce=nonce,
        code_verifier=verifier, intent=intent, user_id=user_id, next_path=safe_next(next_path),
        created_at=now, expires_at=now + STATE_TTL,
    ))
    db.flush()
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    return Begun(f"{AUTHORIZATION_ENDPOINT}?{urlencode(params)}", binding)


# --- 2. the callback's state -------------------------------------------------------------------------

def consume_state(db: Session, raw_state: str | None, binding: str | None, *, now: datetime | None = None) -> OAuthState:
    """Claim the state exactly once; it must be unexpired and belong to this browser."""
    now = now or _now()
    if not raw_state or not binding or len(raw_state) > 256:
        raise GoogleSignInError("state_invalid", "missing state or binding cookie")
    row_id = db.scalar(
        update(OAuthState)
        .where(OAuthState.state_hash == _hash(raw_state), OAuthState.consumed_at.is_(None), OAuthState.expires_at > now)
        .values(consumed_at=now)
        .returning(OAuthState.id)
    )
    if row_id is None:
        raise GoogleSignInError("state_invalid", "unknown, expired or already used state")
    row = db.get(OAuthState, row_id)
    if not hmac.compare_digest(row.binding_hash, _hash(binding)):
        raise GoogleSignInError("state_invalid", "state belongs to another browser")
    return row


# --- 3. Google ---------------------------------------------------------------------------------------

def exchange_code(code: str, verifier: str) -> str:
    """Redeem the authorization code at Google's token endpoint; return the ID token."""
    try:
        response = httpx.post(
            TOKEN_ENDPOINT,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET.get_secret_value() if settings.GOOGLE_CLIENT_SECRET else "",
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
                "code_verifier": verifier,
            },
            timeout=10.0,
            follow_redirects=False,
        )
    except httpx.HTTPError as error:
        raise GoogleSignInError("provider_error", f"token endpoint unreachable: {type(error).__name__}") from None
    if response.status_code != 200:
        raise GoogleSignInError("provider_error", f"token endpoint answered {response.status_code}")
    id_token = response.json().get("id_token")
    if not isinstance(id_token, str):
        raise GoogleSignInError("provider_error", "no ID token in the token response")
    return id_token


@functools.lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(JWKS_URI, cache_keys=True, lifespan=3600, timeout=10)


def signing_key(id_token: str) -> Any:
    """Google's public key for this token (by ``kid``). Replaced in tests."""
    return _jwks_client().get_signing_key_from_jwt(id_token).key


def verify_id_token(id_token: str, *, nonce: str) -> dict[str, Any]:
    try:
        key = signing_key(id_token)
        claims = jwt.decode(
            id_token, key, algorithms=["RS256"], audience=settings.GOOGLE_CLIENT_ID, issuer=list(ISSUERS),
            leeway=CLOCK_SKEW_SECONDS, options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError as error:
        raise GoogleSignInError("token_invalid", type(error).__name__) from None
    except GoogleSignInError:
        raise
    except Exception as error:  # noqa: BLE001 - key fetch failures and the like
        raise GoogleSignInError("provider_error", type(error).__name__) from None
    if claims.get("azp") not in (None, settings.GOOGLE_CLIENT_ID):
        raise GoogleSignInError("token_invalid", "authorized party is another client")
    if not isinstance(claims.get("nonce"), str) or not hmac.compare_digest(claims["nonce"], nonce):
        raise GoogleSignInError("token_invalid", "nonce mismatch")
    if not isinstance(claims.get("sub"), str) or not claims["sub"] or len(claims["sub"]) > 255:
        raise GoogleSignInError("token_invalid", "bad subject")
    if claims.get("email_verified") not in (True, "true"):
        raise GoogleSignInError("email_unverified")
    if not isinstance(claims.get("email"), str) or "@" not in claims["email"]:
        raise GoogleSignInError("email_unverified", "no email in token")
    return claims


# --- 4. the account ---------------------------------------------------------------------------------

@dataclass
class Completed:
    user: User
    is_new_user: bool
    outcome: str  # signed_in | linked


def _user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == email.lower()))


def complete(db: Session, state: OAuthState, claims: dict[str, Any], *, now: datetime | None = None) -> Completed:
    now = now or _now()
    subject, email = claims["sub"], claims["email"].strip()
    identity = db.scalar(select(ExternalIdentity).where(
        ExternalIdentity.provider == PROVIDER, ExternalIdentity.subject == subject))

    if state.intent == "link":
        user = db.get(User, state.user_id)
        if user is None or not user.is_active:
            raise GoogleSignInError("account_inactive")
        if identity is not None:
            if identity.user_id != user.id:
                raise GoogleSignInError("identity_in_use")
            identity.email, identity.last_login_at = email, now
            return Completed(user, False, "linked")
        if db.scalar(select(ExternalIdentity.id).where(
                ExternalIdentity.user_id == user.id, ExternalIdentity.provider == PROVIDER)) is not None:
            raise GoogleSignInError("already_linked")
        try:
            with db.begin_nested():
                db.add(ExternalIdentity(user_id=user.id, provider=PROVIDER, subject=subject, email=email,
                                        created_at=now, last_login_at=now))
                db.flush()
        except IntegrityError:
            raise GoogleSignInError("identity_in_use") from None
        audit.record(db, action="auth.identity_linked", target_type="user", target_id=user.id, actor_id=user.id,
                     changes={"provider": PROVIDER})
        return Completed(user, False, "linked")

    # intent == "login"
    if identity is not None:
        user = db.get(User, identity.user_id)
        if user is None or not user.is_active or user.deletion_requested_at is not None:
            raise GoogleSignInError("account_inactive")
        identity.email, identity.last_login_at = email, now
        return Completed(user, False, "signed_in")
    if _user_by_email(db, email) is not None:
        # The address belongs to an account Google isn't connected to. Linking on a matching email
        # alone would let anyone controlling that address at Google take the account over.
        raise GoogleSignInError("link_required")
    user = User(email=email, password_hash=None, is_active=True, email_verified_at=now)
    try:
        with db.begin_nested():
            db.add(user)
            db.flush()
            db.add(ExternalIdentity(user_id=user.id, provider=PROVIDER, subject=subject, email=email,
                                    created_at=now, last_login_at=now))
            db.flush()
    except IntegrityError:
        # A concurrent callback created the account or the identity first.
        raise GoogleSignInError("state_invalid", "concurrent sign-in") from None
    audit.record(db, action="auth.account_created_with_google", target_type="user", target_id=user.id,
                 actor_id=user.id, changes={"provider": PROVIDER})
    return Completed(user, True, "signed_in")


def unlink(db: Session, user: User) -> bool:
    """Disconnect Google from ``user``. Refused while it is the account's only way to sign in."""
    identity = db.scalar(select(ExternalIdentity).where(
        ExternalIdentity.user_id == user.id, ExternalIdentity.provider == PROVIDER))
    if identity is None:
        return False
    if not user.password_hash:
        raise GoogleSignInError("password_required")
    db.delete(identity)
    db.flush()
    audit.record(db, action="auth.identity_unlinked", target_type="user", target_id=user.id, actor_id=user.id,
                 changes={"provider": PROVIDER})
    return True


# --- 5. handoff to the web app ------------------------------------------------------------------------

def create_handoff(db: Session, done: Completed, *, binding: str, next_path: str | None, now: datetime | None = None) -> str:
    now = now or _now()
    code = secrets.token_urlsafe(32)
    db.add(OAuthHandoff(code_hash=_hash(code), binding_hash=_hash(binding), user_id=done.user.id,
                        is_new_user=done.is_new_user, outcome=done.outcome, next_path=safe_next(next_path),
                        created_at=now, expires_at=now + HANDOFF_TTL))
    db.flush()
    return code


def redeem_handoff(db: Session, code: str | None, binding: str | None, *, now: datetime | None = None) -> OAuthHandoff:
    now = now or _now()
    if not code or not binding or len(code) > 256:
        raise GoogleSignInError("handoff_invalid")
    row_id = db.scalar(
        update(OAuthHandoff)
        .where(OAuthHandoff.code_hash == _hash(code), OAuthHandoff.consumed_at.is_(None), OAuthHandoff.expires_at > now)
        .values(consumed_at=now)
        .returning(OAuthHandoff.id)
    )
    if row_id is None:
        raise GoogleSignInError("handoff_invalid")
    row = db.get(OAuthHandoff, row_id)
    if not hmac.compare_digest(row.binding_hash, _hash(binding)):
        raise GoogleSignInError("handoff_invalid", "another browser")
    return row


__all__ = [
    "AUTHORIZATION_ENDPOINT", "Begun", "Completed", "GoogleSignInError", "ISSUERS", "begin", "complete",
    "consume_state", "create_handoff", "exchange_code", "redeem_handoff", "safe_next", "signing_key", "unlink",
    "verify_id_token",
]
