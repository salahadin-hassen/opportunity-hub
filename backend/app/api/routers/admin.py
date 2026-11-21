"""The admin console: platform analytics, the user directory, and account actions.

Admin-only (``Permission.USER_MANAGE``, which only the admin role holds). Every
figure is computed from the database at request time; nothing is estimated or
sampled. Responses never include password hashes, session tokens or full client
IP addresses.

Account actions (role, suspension, signing a user out everywhere) each require a
reason, are written to the append-only audit log with the acting admin, and are
guarded: an admin can't act on their own account (another admin must), and the
last active admin can't be demoted or suspended, so the platform can never be
left without one.
"""
from __future__ import annotations

import ipaddress
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, exists, func, or_, select, text
from sqlalchemy.orm import Session as DbSession

from app.api.deps import require_permission
from app.core.config import settings
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import (
    AcquisitionSource,
    Application,
    AuditLog,
    EmailOutbox,
    ExternalIdentity,
    IngestionCandidate,
    Match,
    Opportunity,
    Profile,
    SavedOpportunity,
    User,
)
from app.models import Session as UserSession
from app.models.enums import UserRole
from app.schemas.admin import (
    ActivityOverview,
    AdminOverview,
    AdminSessionRead,
    AdminUserDetail,
    AdminUserPage,
    AdminUserRow,
    CatalogueOverview,
    DayCount,
    EmailOverview,
    EngagementOverview,
    NamedCount,
    AccountActionReason,
    AccountRoleChange,
    AccountStatusChange,
    SystemOverview,
    TopOpportunity,
    UsersOverview,
)
from app.schemas.acquisition_source import AuditEntryRead
from app.services import audit
from app.services.sessions import revoke_all_user_sessions

router = APIRouter(prefix="/admin", tags=["admin"])
require_admin = require_permission(Permission.USER_MANAGE)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _grouped(db: DbSession, column, *where) -> list[NamedCount]:
    rows = db.execute(select(column, func.count()).where(*where).group_by(column).order_by(func.count().desc())).all()
    return [NamedCount(key=str(key), count=count) for key, count in rows]


def _count(db: DbSession, model, *where) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*where)) or 0


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


@router.get("/overview", response_model=AdminOverview)
def overview(db: DbSession = Depends(get_db, scope="function"), _: User = Depends(require_admin)) -> AdminOverview:
    now = _now()
    seen = func.coalesce(UserSession.last_seen_at, UserSession.created_at)

    users = UsersOverview(
        total=_count(db, User),
        active=_count(db, User, User.is_active.is_(True), User.deletion_requested_at.is_(None)),
        suspended=_count(db, User, User.is_active.is_(False)),
        pending_deletion=_count(db, User, User.deletion_requested_at.is_not(None)),
        verified_email=_count(db, User, User.email_verified_at.is_not(None)),
        with_google=db.scalar(select(func.count(func.distinct(ExternalIdentity.user_id)))) or 0,
        with_profile=_count(db, Profile),
        new_7d=_count(db, User, User.created_at >= now - timedelta(days=7)),
        new_30d=_count(db, User, User.created_at >= now - timedelta(days=30)),
        by_role=_grouped(db, User.role),
    )

    def active_since(days: int) -> int:
        return db.scalar(select(func.count(func.distinct(UserSession.user_id))).where(seen >= now - timedelta(days=days))) or 0

    start = (now - timedelta(days=29)).date()
    day = func.date(func.timezone("UTC", User.created_at))
    per_day = dict(db.execute(select(day, func.count()).where(User.created_at >= datetime.combine(start, datetime.min.time(), timezone.utc)).group_by(day)).all())
    signups = [DayCount(day=start + timedelta(days=i), count=int(per_day.get(start + timedelta(days=i), 0))) for i in range(30)]
    activity = ActivityOverview(
        active_1d=active_since(1),
        active_7d=active_since(7),
        active_30d=active_since(30),
        open_sessions=_count(db, UserSession, UserSession.revoked_at.is_(None), UserSession.expires_at > now),
        signups_30d=signups,
    )

    def top(model) -> list[TopOpportunity]:
        rows = db.execute(
            select(Opportunity.id, Opportunity.title, func.count())
            .join(model, model.opportunity_id == Opportunity.id)
            .group_by(Opportunity.id, Opportunity.title)
            .order_by(func.count().desc(), Opportunity.title)
            .limit(5)
        ).all()
        return [TopOpportunity(id=row[0], title=row[1], count=row[2]) for row in rows]

    engagement = EngagementOverview(
        eligibility_checks=_count(db, Match),
        profiles_checked=db.scalar(select(func.count(func.distinct(Match.profile_id)))) or 0,
        verdicts=_grouped(db, Match.status),
        saved=_count(db, SavedOpportunity),
        profiles_saving=db.scalar(select(func.count(func.distinct(SavedOpportunity.profile_id)))) or 0,
        applications=_count(db, Application),
        applications_by_status=_grouped(db, Application.status),
        most_saved=top(SavedOpportunity),
        most_tracked=top(Application),
    )
    catalogue = CatalogueOverview(
        opportunities_by_status=_grouped(db, Opportunity.status),
        candidates_by_state=_grouped(db, IngestionCandidate.state),
        sources_by_status=_grouped(db, AcquisitionSource.status),
    )
    email = EmailOverview(
        by_status=_grouped(db, EmailOutbox.status),
        oldest_pending=db.scalar(select(func.min(EmailOutbox.send_after)).where(EmailOutbox.status == "pending")),
    )
    try:
        revision = db.scalar(text("SELECT version_num FROM alembic_version"))
    except Exception:  # pragma: no cover - only when migrations were never run
        revision = None
    system = SystemOverview(
        environment=settings.APP_ENV, schema_revision=revision, database_time=db.scalar(select(func.now())),
        ai_review=bool(settings.GROQ_API_KEY), ai_model=settings.GROQ_MODEL if settings.GROQ_API_KEY else None,
    )
    return AdminOverview(generated_at=now, users=users, activity=activity, engagement=engagement, catalogue=catalogue, email=email, system=system)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


def _user_columns():
    last_active = (
        select(func.max(func.coalesce(UserSession.last_seen_at, UserSession.created_at))).where(UserSession.user_id == User.id).correlate(User).scalar_subquery()
    )
    google = exists().where(ExternalIdentity.user_id == User.id).correlate(User)
    saved = select(func.count()).select_from(SavedOpportunity).where(SavedOpportunity.profile_id == Profile.id).correlate(Profile).scalar_subquery()
    applications = select(func.count()).select_from(Application).where(Application.profile_id == Profile.id).correlate(Profile).scalar_subquery()
    return last_active, google, saved, applications


def _row(user: User, profile: Profile | None, last_active, google, saved, applications) -> AdminUserRow:
    return AdminUserRow(
        id=user.id,
        email=user.email,
        full_name=profile.full_name if profile else None,
        role=user.role,
        is_active=user.is_active,
        email_verified=user.email_verified_at is not None,
        has_password=bool(user.password_hash),
        google_linked=bool(google),
        has_profile=profile is not None,
        created_at=user.created_at,
        last_active_at=last_active,
        deletion_due_at=user.deletion_due_at,
        saved_count=saved or 0,
        applications_count=applications or 0,
    )


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/users", response_model=AdminUserPage)
def list_users(
    q: str | None = Query(default=None, max_length=200),
    role: UserRole | None = Query(default=None),
    state: str | None = Query(default=None, pattern="^(active|suspended|pending_deletion)$"),
    sort: str = Query(default="newest", pattern="^(newest|oldest|last_active|email)$"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: DbSession = Depends(get_db, scope="function"),
    _: User = Depends(require_admin),
) -> AdminUserPage:
    last_active, google, saved, applications = _user_columns()
    conditions = []
    if q and q.strip():
        pattern = f"%{_escape_like(q.strip())}%"
        conditions.append(or_(User.email.ilike(pattern, escape="\\"), Profile.full_name.ilike(pattern, escape="\\")))
    if role:
        conditions.append(User.role == role.value)
    if state == "active":
        conditions.extend([User.is_active.is_(True), User.deletion_requested_at.is_(None)])
    elif state == "suspended":
        conditions.append(User.is_active.is_(False))
    elif state == "pending_deletion":
        conditions.append(User.deletion_requested_at.is_not(None))

    base = select(User.id).outerjoin(Profile, Profile.user_id == User.id).where(*conditions)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    order = {
        "newest": [User.created_at.desc()],
        "oldest": [User.created_at.asc()],
        "last_active": [last_active.desc().nulls_last(), User.created_at.desc()],
        "email": [func.lower(User.email).asc()],
    }[sort]
    rows = db.execute(
        select(User, Profile, last_active, google, saved, applications)
        .outerjoin(Profile, Profile.user_id == User.id)
        .where(*conditions)
        .order_by(*order, User.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return AdminUserPage(items=[_row(*row) for row in rows], total=total, limit=limit, offset=offset)


_BROWSERS = (("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"), ("Chrome/", "Chrome"), ("Safari/", "Safari"))
_SYSTEMS = (("Windows", "Windows"), ("Android", "Android"), ("iPhone", "iOS"), ("iPad", "iPadOS"), ("Mac OS X", "macOS"), ("Linux", "Linux"))


def _device(user_agent: str | None) -> str | None:
    """A coarse device description ("Chrome on macOS"), not the raw user-agent string."""
    if not user_agent:
        return None
    browser = next((name for marker, name in _BROWSERS if marker in user_agent), None)
    system = next((name for marker, name in _SYSTEMS if marker in user_agent), None)
    if browser and system:
        return f"{browser} on {system}"
    return browser or system or "Other client"


def _network(client_ip: str | None) -> str | None:
    """The network, not the address: IPv4 to /24, IPv6 to /48."""
    if not client_ip:
        return None
    try:
        address = ipaddress.ip_address(client_ip.strip())
    except ValueError:
        return None
    prefix = 24 if address.version == 4 else 48
    return str(ipaddress.ip_network(f"{address}/{prefix}", strict=False))


def _detail(db: DbSession, user: User) -> AdminUserDetail:
    last_active, google, saved, applications = _user_columns()
    row = db.execute(
        select(User, Profile, last_active, google, saved, applications).outerjoin(Profile, Profile.user_id == User.id).where(User.id == user.id)
    ).one()
    base = _row(*row)
    profile: Profile | None = row[1]
    now = _now()
    sessions = db.scalars(
        select(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None), UserSession.expires_at > now)
        .order_by(UserSession.last_seen_at.desc())
        .limit(20)
    ).all()
    history = db.scalars(
        select(AuditLog)
        .where(or_(and_(AuditLog.target_type == "user", AuditLog.target_id == str(user.id)), AuditLog.actor_user_id == user.id))
        .order_by(AuditLog.id.desc())
        .limit(25)
    ).all()
    google_email = db.scalar(select(ExternalIdentity.email).where(ExternalIdentity.user_id == user.id).limit(1))
    return AdminUserDetail(
        **base.model_dump(),
        email_verified_at=user.email_verified_at,
        deletion_requested_at=user.deletion_requested_at,
        google_email=google_email,
        matches_count=_count(db, Match, Match.profile_id == profile.id) if profile else 0,
        sessions=[
            AdminSessionRead(id=s.id, created_at=s.created_at, last_seen_at=s.last_seen_at, expires_at=s.expires_at, device=_device(s.user_agent), network=_network(s.client_ip))
            for s in sessions
        ],
        history=[AuditEntryRead.model_validate(entry) for entry in history],
    )


def _target(db: DbSession, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No account with that id.")
    return user


def _not_self(actor: User, target: User, what: str) -> None:
    if actor.id == target.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"You can't {what} your own account. Ask another admin.")


def _other_active_admins(db: DbSession, target: User) -> int:
    return _count(db, User, User.role == UserRole.ADMIN.value, User.is_active.is_(True), User.id != target.id)


@router.get("/users/{user_id}", response_model=AdminUserDetail)
def read_user(user_id: uuid.UUID, db: DbSession = Depends(get_db, scope="function"), _: User = Depends(require_admin)) -> AdminUserDetail:
    return _detail(db, _target(db, user_id))


@router.post("/users/{user_id}/role", response_model=AdminUserDetail)
def change_role(
    user_id: uuid.UUID, payload: AccountRoleChange, db: DbSession = Depends(get_db, scope="function"), actor: User = Depends(require_admin)
) -> AdminUserDetail:
    target = _target(db, user_id)
    _not_self(actor, target, "change the role of")
    previous = target.role
    if previous == payload.role:
        return _detail(db, target)
    if previous == UserRole.ADMIN.value and target.is_active and _other_active_admins(db, target) == 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This is the last active admin; make someone else an admin first.")
    target.role = payload.role
    db.flush()
    audit.record(
        db, action="user.role_changed", target_type="user", target_id=target.id, actor_id=actor.id,
        changes={"role": {"from": previous, "to": payload.role}}, reason=payload.reason,
    )
    return _detail(db, target)


@router.post("/users/{user_id}/status", response_model=AdminUserDetail)
def change_status(
    user_id: uuid.UUID, payload: AccountStatusChange, db: DbSession = Depends(get_db, scope="function"), actor: User = Depends(require_admin)
) -> AdminUserDetail:
    target = _target(db, user_id)
    _not_self(actor, target, "suspend or reactivate")
    if target.is_active == payload.active:
        return _detail(db, target)
    if not payload.active and target.role == UserRole.ADMIN.value and _other_active_admins(db, target) == 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This is the last active admin and can't be suspended.")
    target.is_active = payload.active
    revoked = 0 if payload.active else revoke_all_user_sessions(db, target.id)  # suspension signs them out at once
    db.flush()
    audit.record(
        db, action="user.reactivated" if payload.active else "user.suspended", target_type="user", target_id=target.id, actor_id=actor.id,
        changes={"is_active": {"from": not payload.active, "to": payload.active}, **({} if payload.active else {"sessions_revoked": revoked})},
        reason=payload.reason,
    )
    return _detail(db, target)


@router.post("/users/{user_id}/sessions/revoke", response_model=AdminUserDetail)
def revoke_sessions(
    user_id: uuid.UUID, payload: AccountActionReason, db: DbSession = Depends(get_db, scope="function"), actor: User = Depends(require_admin)
) -> AdminUserDetail:
    target = _target(db, user_id)
    _not_self(actor, target, "sign out everywhere from the console for")
    revoked = revoke_all_user_sessions(db, target.id)
    db.flush()
    audit.record(
        db, action="user.sessions_revoked", target_type="user", target_id=target.id, actor_id=actor.id,
        changes={"sessions_revoked": revoked}, reason=payload.reason,
    )
    return _detail(db, target)


__all__ = ["router"]
