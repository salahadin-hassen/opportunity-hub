"""Operator commands that must never be reachable over HTTP.

Run from ``backend/`` (locally, or as a one-off job against a deployment)::

    python -m app.cli grant-role <email> <student|curator|admin>
    python -m app.cli show-role <email>

Role changes exist only here, so no account can raise its own role
through the API. Every change is written to the audit log in the same
transaction as the change itself.
"""
from __future__ import annotations

import argparse
import sys

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import User
from app.models.enums import UserRole
from app.services import audit


_EMAIL = TypeAdapter(EmailStr)


class CliError(Exception):
    """A command could not be carried out; the message is safe to print."""


def find_user(db: Session, email: str) -> User:
    """The account ``email`` names: an exact match first, else the only case-insensitive one.

    Stored emails keep the case of their local part and the unique constraint
    compares exactly, so ``Alice@x.org`` and ``alice@x.org`` can be two
    different people. Picking either one on a case-insensitive match could
    hand a role to the wrong account, so ambiguity is refused instead.
    """
    try:
        normalised = _EMAIL.validate_python(email.strip())  # the same normalisation registration applies
    except ValidationError:
        normalised = email.strip()
    user = db.scalar(select(User).where(User.email == normalised))
    if user is not None:
        return user
    matches = list(db.scalars(select(User).where(func.lower(User.email) == normalised.lower()).limit(2)))
    if not matches:
        raise CliError("No account has that email address.")
    if len(matches) > 1:
        raise CliError("Several accounts differ from that address only in letter case; give the exact address.")
    return matches[0]


def grant_role(db: Session, email: str, role: str) -> tuple[User, str]:
    """Set ``email``'s role; return the user and the previous role. Flushes; the caller commits."""
    try:
        new_role = UserRole(role)
    except ValueError:
        raise CliError(f"Unknown role {role!r}; choose one of: {', '.join(r.value for r in UserRole)}.") from None
    user = find_user(db, email)
    previous = user.role
    if previous == new_role:
        return user, previous
    user.role = new_role
    db.flush()
    audit.record(
        db,
        action="user.role_changed",
        target_type="user",
        target_id=user.id,
        actor_kind="cli",
        changes={"role": {"from": previous, "to": new_role.value}},
    )
    return user, previous


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Opportunity Hub operator commands")
    commands = parser.add_subparsers(dest="command", required=True)
    grant = commands.add_parser("grant-role", help="set an account's role")
    grant.add_argument("email")
    grant.add_argument("role", choices=[role.value for role in UserRole])
    show = commands.add_parser("show-role", help="print an account's role")
    show.add_argument("email")

    email_cmd = commands.add_parser("process-outbox", help="deliver pending transactional emails from outbox")
    email_cmd.add_argument("--batch-size", type=int, default=50, help="maximum messages to deliver per run")

    purge_cmd = commands.add_parser("purge-deleted-accounts", help="purge accounts whose 30-day deletion grace period has expired")
    purge_cmd.add_argument("--batch-size", type=int, default=50, help="maximum accounts to purge per run")
    purge_cmd.add_argument("--dry-run", action="store_true", help="simulate without deleting records")

    commands.add_parser(
        "email-token-key-usage",
        help="list email-token key versions still needed by live pending emails (check before removing a key)",
    )
    legacy_cmd = commands.add_parser(
        "legacy-email-outbox",
        help="report (default) or cancel pre-hardening outbox rows that still hold a raw reset token",
    )
    legacy_cmd.add_argument("--cancel", action="store_true", help="cancel pending legacy rows and strip raw tokens")
    legacy_cmd.add_argument("--yes", action="store_true", help="required with --cancel")
    revoke_cmd = commands.add_parser(
        "revoke-reset-tokens", help="invalidate every unused password-reset link (e.g. after a compromise)"
    )
    revoke_cmd.add_argument("--yes", action="store_true", help="required: confirm revoking for all accounts")

    args = parser.parse_args(argv)

    from app.db.session import SessionLocal

    with SessionLocal() as db:
        try:
            if args.command == "grant-role":
                user, previous = grant_role(db, args.email, args.role)
                db.commit()
                print(f"Role changed from {previous} to {user.role}.")
            elif args.command == "show-role":
                print(find_user(db, args.email).role)
            elif args.command == "process-outbox":
                from app.services.email_worker import EmailDeliveryNotConfigured, process_outbox
                try:
                    sent = process_outbox(db, batch_size=args.batch_size)
                except EmailDeliveryNotConfigured as error:
                    # Exit non-zero so the cron run shows as failed; the queue is untouched.
                    db.rollback()
                    print(f"Email delivery is not configured: {error}", file=sys.stderr)
                    return 2
                db.commit()
                print(f"Processed email outbox: {sent} messages successfully sent.")
            elif args.command == "email-token-key-usage":
                from app.services.email_tokens import pending_key_usage

                usage = pending_key_usage(db)
                if not usage:
                    print("No live pending emails: any non-active key version can be removed.")
                for key_id, count in sorted(usage.items()):
                    print(f"{key_id}: {count} live pending email(s)")
            elif args.command == "legacy-email-outbox":
                from app.services.email_worker import cancel_legacy_outbox, legacy_outbox_report

                if args.cancel:
                    if not args.yes:
                        print("Refusing without --yes: this cancels queued legacy emails.", file=sys.stderr)
                        return 1
                    cancelled, scrubbed = cancel_legacy_outbox(db)
                    db.commit()
                    print(f"Cancelled {cancelled} pending legacy message(s); stripped raw tokens from {scrubbed} row(s).")
                report = legacy_outbox_report(db)
                if not report:
                    print("No outbox rows hold a raw token.")
                for status_, template, count, oldest, newest in report:
                    print(f"{status_}\t{template}\t{count}\toldest={oldest:%Y-%m-%d %H:%M}\tnewest={newest:%Y-%m-%d %H:%M}")
            elif args.command == "revoke-reset-tokens":
                if not args.yes:
                    print("Refusing without --yes: this invalidates every outstanding reset link.", file=sys.stderr)
                    return 1
                from app.services.email_tokens import PASSWORD_RESET, revoke_outstanding

                revoked = revoke_outstanding(db, None, PASSWORD_RESET)
                db.commit()
                print(f"Revoked {revoked} outstanding password-reset token(s).")
            elif args.command == "purge-deleted-accounts":
                from app.services.account_deletion import purge_due_accounts
                purged = purge_due_accounts(db, batch_size=args.batch_size, dry_run=args.dry_run)
                if not args.dry_run:
                    db.commit()
                print(f"Account purge job completed: {purged} accounts {'identified (dry run)' if args.dry_run else 'permanently purged'}.")
        except CliError as error:
            db.rollback()
            print(error, file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
