"""Write audit entries in the caller's transaction (M2-T2).

``record`` adds one entry to the given session and flushes, so it commits
or rolls back together with the change it describes. ``diff`` turns two
snapshots of allow-listed fields into the ``changes`` payload. Payloads are
checked for keys that suggest secrets or personal data; such a payload is a
programming error and raises instead of being stored.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog

MAX_REASON_LENGTH = 1000
#: Substrings that must never appear in a changes key.
FORBIDDEN_KEY_PARTS = ("password", "token", "secret", "hash", "email", "api_key")


class AuditPayloadError(ValueError):
    """The audit payload would store something it must not."""


def diff(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Fields whose value changed, as ``{field: {"from": old, "to": new}}``."""
    return {
        key: {"from": before.get(key), "to": after.get(key)}
        for key in sorted(set(before) | set(after))
        if before.get(key) != after.get(key)
    }


def _check_payload(changes: Mapping[str, Any]) -> dict[str, Any]:
    for key in changes:
        lowered = str(key).lower()
        if any(part in lowered for part in FORBIDDEN_KEY_PARTS):
            raise AuditPayloadError(f"Audit changes must not include {key!r}.")
    try:
        return json.loads(json.dumps(dict(changes), default=str))
    except (TypeError, ValueError) as error:
        raise AuditPayloadError("Audit changes must be JSON-serialisable.") from error


def record(
    db: Session,
    *,
    action: str,
    target_type: str,
    target_id: uuid.UUID | str,
    actor_id: uuid.UUID | None = None,
    actor_kind: str | None = None,
    changes: Mapping[str, Any] | None = None,
    reason: str | None = None,
) -> AuditLog:
    """Append one entry in ``db``'s transaction. ``actor_kind`` defaults to user/system by ``actor_id``."""
    if reason is not None:
        reason = reason.strip()[:MAX_REASON_LENGTH] or None
    entry = AuditLog(
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        actor_user_id=actor_id,
        actor_kind=actor_kind or ("user" if actor_id is not None else "system"),
        changes=_check_payload(changes or {}),
        reason=reason,
    )
    db.add(entry)
    db.flush()
    return entry


__all__ = ["AuditPayloadError", "diff", "record"]
