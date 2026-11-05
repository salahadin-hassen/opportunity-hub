"""Scheduled user account deletion and data sanitization service (plan §H.2).

Guarantees:
- Only accounts with active deletion requests past their 30-day grace period are eligible.
- Account cancellation (`deletion_requested_at IS NULL`) is strictly respected.
- Cascades relational deletion across profiles, sessions, tokens, tracking, and evidence.
- Anonymized deletion tombstone is recorded for audit retention compliance.
- Audit log records the purge event without leaking personal email or name.
- Safe and idempotent: can be triggered via CLI or daily cron job.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.deletion_tombstone import DeletionTombstone
from app.models.email_outbox import EmailOutbox
from app.models.user import User
from app.services import audit

logger = logging.getLogger(__name__)


def purge_due_accounts(
    db: Session,
    *,
    batch_size: int = 50,
    dry_run: bool = False,
) -> int:
    """Identify and permanently purge accounts whose deletion grace period has expired.
    
    Returns the number of accounts purged.
    """
    now = datetime.now(timezone.utc)

    # Only accounts where deletion was requested AND the deadline has passed
    stmt = (
        select(User)
        .where(
            User.deletion_requested_at.is_not(None),
            User.deletion_due_at.is_not(None),
            User.deletion_due_at <= now,
        )
        .limit(batch_size)
    )

    eligible_users = list(db.scalars(stmt).all())
    if not eligible_users:
        logger.info("Account deletion job: No accounts due for permanent purge.")
        return 0

    purged_count = 0
    for user in eligible_users:
        user_id = user.id
        logger.info("Purging user account %s (requested at %s, due at %s)", user_id, user.deletion_requested_at, user.deletion_due_at)

        if dry_run:
            purged_count += 1
            continue

        # 1. Record anonymized tombstone
        tombstone = DeletionTombstone(
            user_id=user_id,
            purged_at=now,
        )
        db.add(tombstone)

        # 2. Audit log entry (actor is None for system background process, target_id is user_id)
        audit.record(
            db,
            action="user.account_purged",
            target_type="user",
            target_id=user_id,
            actor_id=None,
        )

        # 3. Clean up any pending email outbox messages for this user
        db.execute(delete(EmailOutbox).where(EmailOutbox.user_id == user_id))

        # 4. Delete the user row. Relational cascades remove:
        # - profiles (and cascaded education, test_scores, profile_skills, saved_opportunities, applications, matches)
        # - sessions
        # - email_tokens
        db.delete(user)
        purged_count += 1

    if not dry_run:
        db.flush()
        logger.info("Account deletion job completed: Successfully purged %d accounts.", purged_count)
    else:
        logger.info("Account deletion job (dry run): Identified %d accounts for purge.", purged_count)

    return purged_count

