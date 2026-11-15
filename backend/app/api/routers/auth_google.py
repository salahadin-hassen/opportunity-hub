"""Sign in with Google (see ``app.services.google_oauth`` for the flow and its guarantees).

    POST   /auth/google/start         begin signing in (or creating an account) with Google
    POST   /auth/google/link/start    begin connecting Google to the signed-in account
    GET    /auth/google/callback      Google's redirect target; always answers with a redirect to the web app
    POST   /auth/google/exchange      the web app trades the single-use handoff code for a session
    GET    /auth/providers            which sign-in methods this deployment offers (public)
    GET    /auth/identities           the signed-in account's sign-in methods
    DELETE /auth/google/link          disconnect Google (refused while it is the only way to sign in)

Every endpoint except ``/auth/providers`` answers 404 unless Google Sign-In is configured.
Browser-initiated POSTs must carry a trusted Origin (or Referer), like cookie-authenticated
mutations elsewhere. The callback never answers with data, only a redirect to the web app.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import SESSION_COOKIE_NAME, _origin_of, get_current_user
from app.core.config import settings
from app.core.rate_limit import client_identity, limit_auth_attempts, record_auth_failure, record_auth_success
from app.db.session import get_db
from app.models import ExternalIdentity, User
from app.services import google_oauth
from app.services.sessions import create_session

logger = logging.getLogger("app.auth.google")
router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(limit_auth_attempts)])

BINDING_COOKIE = "oh_oauth_binding"
SESSION_TTL = timedelta(minutes=30)  # the same as password sign-in


def _require_enabled() -> None:
    if not settings.google_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")


def _require_trusted_origin(request: Request) -> None:
    origin = request.headers.get("origin") or request.headers.get("referer")
    allowed = {_origin_of(item) for item in settings.cors_origins} - {None}
    if not allowed or not origin or _origin_of(origin) not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Request origin is not allowed.")


def _set_binding(response: Response, value: str) -> None:
    response.set_cookie(BINDING_COOKIE, value, httponly=True, secure=settings.is_production, samesite="lax",
                        max_age=int(google_oauth.STATE_TTL.total_seconds()), path="/")


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    next: str | None = Field(default=None, max_length=google_oauth.MAX_NEXT_LENGTH)


class StartResponse(BaseModel):
    authorization_url: str


class ExchangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=10, max_length=256)


class ExchangeResponse(BaseModel):
    outcome: Literal["signed_in", "linked"]
    access_token: str | None = None
    token_type: str = "bearer"
    email: str | None = None
    is_new_user: bool = False
    next: str | None = None


class ProvidersResponse(BaseModel):
    password: bool = True
    google: bool


class IdentitiesResponse(BaseModel):
    has_password: bool
    google_available: bool
    google_linked: bool
    google_email: str | None = None


@router.get("/providers", response_model=ProvidersResponse)
def providers() -> ProvidersResponse:
    return ProvidersResponse(google=settings.google_enabled)


@router.post("/google/start", response_model=StartResponse)
def start(payload: StartRequest, request: Request, response: Response,
          db: Session = Depends(get_db, scope="function")) -> StartResponse:
    """Begin signing in with Google. Signing in creates an account only for a new, verified address."""
    _require_enabled()
    _require_trusted_origin(request)
    begun = google_oauth.begin(db, intent="login", next_path=payload.next)
    _set_binding(response, begun.binding)
    return StartResponse(authorization_url=begun.authorization_url)


@router.post("/google/link/start", response_model=StartResponse)
def link_start(payload: StartRequest, request: Request, response: Response,
               user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")) -> StartResponse:
    """Begin connecting Google to the signed-in account (the only way an existing account gains Google)."""
    _require_enabled()
    _require_trusted_origin(request)
    begun = google_oauth.begin(db, intent="link", next_path=payload.next or "/profile", user_id=user.id)
    _set_binding(response, begun.binding)
    return StartResponse(authorization_url=begun.authorization_url)


@router.get("/google/callback", include_in_schema=False)
def callback(request: Request, db: Session = Depends(get_db, scope="function")) -> RedirectResponse:
    _require_enabled()
    frontend = settings.frontend_url or ""
    params = request.query_params
    binding = request.cookies.get(BINDING_COOKIE)
    intent = "login"
    try:
        state = google_oauth.consume_state(db, params.get("state"), binding)
        intent = state.intent
        if params.get("error"):
            # The person cancelled, or Google refused; the state is spent either way.
            raise google_oauth.GoogleSignInError("cancelled" if params.get("error") == "access_denied" else "provider_error",
                                                 params.get("error", "")[:64])
        code = params.get("code")
        if not code or len(code) > 2048:
            raise google_oauth.GoogleSignInError("provider_error", "no authorization code")
        id_token = google_oauth.exchange_code(code, state.code_verifier)
        claims = google_oauth.verify_id_token(id_token, nonce=state.nonce)
        done = google_oauth.complete(db, state, claims)
        handoff = google_oauth.create_handoff(db, done, binding=binding, next_path=state.next_path)
    except google_oauth.GoogleSignInError as error:
        record_auth_failure("/auth/google/callback")
        logger.warning("google sign-in refused: %s", error)
        where = "/profile" if intent == "link" else "/login"
        # A plain redirect (not an exception): the consumed state still commits, so it can't be replayed.
        return RedirectResponse(f"{frontend}{where}?google_error={error.code}", status_code=status.HTTP_303_SEE_OTHER)
    # The code travels in the fragment: never sent to a server, never in a Referer.
    return RedirectResponse(f"{frontend}/auth/google/complete#code={handoff}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/google/exchange", response_model=ExchangeResponse)
def exchange(payload: ExchangeRequest, request: Request, response: Response,
             db: Session = Depends(get_db, scope="function")) -> ExchangeResponse:
    _require_enabled()
    _require_trusted_origin(request)
    try:
        handoff = google_oauth.redeem_handoff(db, payload.code, request.cookies.get(BINDING_COOKIE))
    except google_oauth.GoogleSignInError:
        record_auth_failure("/auth/google/exchange")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="This sign-in link is no longer valid.") from None
    user = db.get(User, handoff.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="This sign-in link is no longer valid.")
    response.delete_cookie(BINDING_COOKIE, path="/")
    if handoff.outcome == "linked":
        return ExchangeResponse(outcome="linked", next=handoff.next_path or "/profile")
    record_auth_success(request, "/auth/google/exchange", user.email)
    _, raw_token = create_session(db=db, user_id=user.id,
                                  user_agent=request.headers.get("user-agent", "")[:255] or None,
                                  client_ip=client_identity(request).identity, ttl=SESSION_TTL)
    response.set_cookie(key=SESSION_COOKIE_NAME, value=raw_token, httponly=True, secure=settings.is_production,
                        samesite="lax", max_age=int(SESSION_TTL.total_seconds()), path="/")
    return ExchangeResponse(outcome="signed_in", access_token=raw_token, email=user.email,
                            is_new_user=handoff.is_new_user, next=handoff.next_path)


@router.get("/identities", response_model=IdentitiesResponse)
def identities(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")) -> IdentitiesResponse:
    identity = db.scalar(select(ExternalIdentity).where(
        ExternalIdentity.user_id == user.id, ExternalIdentity.provider == google_oauth.PROVIDER))
    return IdentitiesResponse(has_password=bool(user.password_hash), google_available=settings.google_enabled,
                              google_linked=identity is not None, google_email=identity.email if identity else None)


@router.delete("/google/link", status_code=status.HTTP_204_NO_CONTENT)
def unlink(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")) -> Response:
    _require_enabled()
    try:
        google_oauth.unlink(db, user)
    except google_oauth.GoogleSignInError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Set a password before disconnecting Google; it's this account's only sign-in.") from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
