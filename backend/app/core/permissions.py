"""What each role may do (plan §F.6). Code-defined on purpose: no permission tables.

Students have no permissions beyond their own data, which is protected by
ownership checks elsewhere. Curators do the day-to-day work on sources and
opportunities, including every action that *reduces* automation (pausing,
lowering publication). Actions that *extend trust* (approving a source,
raising its publication mode, retiring it) and administration are admin-only.
"""
from __future__ import annotations

from enum import StrEnum

from app.models.enums import UserRole


class Permission(StrEnum):
    OPPORTUNITY_CREATE = "opportunity.create"
    OPPORTUNITY_EDIT = "opportunity.edit"
    OPPORTUNITY_PUBLISH = "opportunity.publish"
    SOURCE_READ = "source.read"
    SOURCE_PROPOSE = "source.propose"
    SOURCE_EDIT = "source.edit"
    SOURCE_REVIEW = "source.review"
    SOURCE_TEST = "source.test"
    SOURCE_PAUSE = "source.pause"
    SOURCE_PUBLISH_LOWER = "source.publish.lower"
    SOURCE_APPROVE = "source.approve"
    SOURCE_PUBLISH_RAISE = "source.publish.raise"
    SOURCE_RETIRE = "source.retire"
    AUDIT_READ = "audit.read"
    USER_MANAGE = "user.manage"


_CURATOR = frozenset(
    {
        Permission.OPPORTUNITY_CREATE,
        Permission.OPPORTUNITY_EDIT,
        Permission.OPPORTUNITY_PUBLISH,
        Permission.SOURCE_READ,
        Permission.SOURCE_PROPOSE,
        Permission.SOURCE_EDIT,
        Permission.SOURCE_REVIEW,
        Permission.SOURCE_TEST,
        Permission.SOURCE_PAUSE,
        Permission.SOURCE_PUBLISH_LOWER,
    }
)

ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.STUDENT: frozenset(),
    UserRole.CURATOR: _CURATOR,
    UserRole.ADMIN: frozenset(Permission),
}


def has_permission(role: str, permission: Permission) -> bool:
    """Whether ``role`` grants ``permission``; unknown roles grant nothing."""
    try:
        return permission in ROLE_PERMISSIONS[UserRole(role)]
    except ValueError:
        return False


__all__ = ["Permission", "ROLE_PERMISSIONS", "has_permission"]
