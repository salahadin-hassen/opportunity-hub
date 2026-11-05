"""Services for applicant saved opportunities and tracking (plan §C.2, M3)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.application import Application, ApplicationItem
from app.models.opportunity import Opportunity
from app.models.saved_opportunity import SavedOpportunity
from app.schemas.tracking import (
    ApplicationCreate,
    ApplicationItemCreate,
    ApplicationItemUpdate,
    ApplicationUpdate,
)
from app.services.opportunities import is_public


def save_opportunity(
    db: Session,
    profile_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    reminders_enabled: bool = True,
) -> SavedOpportunity | None:
    """Save/bookmark an opportunity for the applicant."""
    opp = db.get(Opportunity, opportunity_id)
    if opp is None or not is_public(opp):
        return None

    saved = db.scalar(
        select(SavedOpportunity).where(
            SavedOpportunity.profile_id == profile_id,
            SavedOpportunity.opportunity_id == opportunity_id,
        )
    )
    if saved is None:
        saved = SavedOpportunity(
            profile_id=profile_id,
            opportunity_id=opportunity_id,
            reminders_enabled=reminders_enabled,
        )
        db.add(saved)
    else:
        saved.reminders_enabled = reminders_enabled

    db.flush()
    return db.scalar(
        select(SavedOpportunity)
        .where(
            SavedOpportunity.profile_id == profile_id,
            SavedOpportunity.opportunity_id == opportunity_id,
        )
        .options(selectinload(SavedOpportunity.opportunity))
    )


def unsave_opportunity(
    db: Session, profile_id: uuid.UUID, opportunity_id: uuid.UUID
) -> bool:
    """Remove a saved opportunity."""
    saved = db.scalar(
        select(SavedOpportunity).where(
            SavedOpportunity.profile_id == profile_id,
            SavedOpportunity.opportunity_id == opportunity_id,
        )
    )
    if saved is None:
        return False
    db.delete(saved)
    db.flush()
    return True


def list_saved_opportunities(
    db: Session, profile_id: uuid.UUID
) -> list[SavedOpportunity]:
    """List all saved opportunities for a profile."""
    stmt = (
        select(SavedOpportunity)
        .where(SavedOpportunity.profile_id == profile_id)
        .options(selectinload(SavedOpportunity.opportunity))
        .order_by(SavedOpportunity.created_at.desc())
    )
    return list(db.scalars(stmt).all())


def create_application(
    db: Session, profile_id: uuid.UUID, payload: ApplicationCreate
) -> Application | None:
    """Track a new formal application toward an opportunity."""
    opp = db.get(Opportunity, payload.opportunity_id)
    if opp is None or not is_public(opp):
        return None

    existing = db.scalar(
        select(Application).where(
            Application.profile_id == profile_id,
            Application.opportunity_id == payload.opportunity_id,
        )
    )
    if existing is not None:
        return existing

    app = Application(
        profile_id=profile_id,
        opportunity_id=payload.opportunity_id,
        status="draft",
        notes=payload.notes,
        target_date=payload.target_date,
    )
    db.add(app)
    db.flush()

    for item_data in payload.initial_items:
        item = ApplicationItem(
            application_id=app.id,
            requirement_id=item_data.requirement_id,
            label=item_data.label,
            due_date=item_data.due_date,
            note=item_data.note,
            order_index=item_data.order_index,
        )
        db.add(item)

    db.flush()
    return get_application(db, profile_id, app.id)


def get_application(
    db: Session, profile_id: uuid.UUID, application_id: uuid.UUID
) -> Application | None:
    """Retrieve an application owned by profile_id."""
    stmt = (
        select(Application)
        .where(
            Application.id == application_id,
            Application.profile_id == profile_id,
        )
        .options(
            selectinload(Application.opportunity),
            selectinload(Application.items),
        )
    )
    return db.scalar(stmt)


def list_applications(db: Session, profile_id: uuid.UUID) -> list[Application]:
    """List all tracked applications for a profile."""
    stmt = (
        select(Application)
        .where(Application.profile_id == profile_id)
        .options(
            selectinload(Application.opportunity),
            selectinload(Application.items),
        )
        .order_by(Application.created_at.desc())
    )
    return list(db.scalars(stmt).all())


def update_application(
    db: Session,
    profile_id: uuid.UUID,
    application_id: uuid.UUID,
    payload: ApplicationUpdate,
) -> Application | None:
    """Update application status, notes, or outcome."""
    app = get_application(db, profile_id, application_id)
    if app is None:
        return None

    now = datetime.now(timezone.utc)
    if payload.status is not None:
        app.status = payload.status
        if payload.status == "submitted" and app.submitted_at is None:
            app.submitted_at = now
    if payload.outcome is not None:
        app.outcome = payload.outcome
        app.outcome_at = now
    if payload.notes is not None:
        app.notes = payload.notes
    if payload.target_date is not None:
        app.target_date = payload.target_date

    db.flush()
    return app


def add_application_item(
    db: Session,
    profile_id: uuid.UUID,
    application_id: uuid.UUID,
    payload: ApplicationItemCreate,
) -> ApplicationItem | None:
    """Add a checklist item to an owned application."""
    app = get_application(db, profile_id, application_id)
    if app is None:
        return None

    item = ApplicationItem(
        application_id=app.id,
        requirement_id=payload.requirement_id,
        label=payload.label,
        due_date=payload.due_date,
        note=payload.note,
        order_index=payload.order_index,
    )
    db.add(item)
    db.flush()
    return item


def update_application_item(
    db: Session,
    profile_id: uuid.UUID,
    application_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ApplicationItemUpdate,
) -> ApplicationItem | None:
    """Update status or notes for an application item."""
    app = get_application(db, profile_id, application_id)
    if app is None:
        return None

    stmt = select(ApplicationItem).where(
        ApplicationItem.id == item_id,
        ApplicationItem.application_id == application_id,
    )
    item = db.scalar(stmt)
    if item is None:
        return None

    if payload.status is not None:
        item.status = payload.status
    if payload.note is not None:
        item.note = payload.note
    if payload.due_date is not None:
        item.due_date = payload.due_date

    db.flush()
    return item
