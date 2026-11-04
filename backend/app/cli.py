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
    args = parser.parse_args(argv)

    from app.db.session import SessionLocal

    with SessionLocal() as db:
        try:
            if args.command == "grant-role":
                user, previous = grant_role(db, args.email, args.role)
                db.commit()
                print(f"Role changed from {previous} to {user.role}.")
            else:
                print(find_user(db, args.email).role)
        except CliError as error:
            db.rollback()
            print(error, file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
