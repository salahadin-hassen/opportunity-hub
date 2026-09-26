"""Domain enumerations shared by models and schemas.

Values are stored in the database as plain VARCHAR columns guarded by
CHECK constraints (see ``enum_check_constraint``); PostgreSQL native ENUM
types are deliberately avoided so new values never require a migration
of the type itself.
"""
from enum import StrEnum

from sqlalchemy import CheckConstraint


class OpportunityType(StrEnum):
    """The kind of opportunity an item represents."""

    SCHOLARSHIP = "scholarship"
    INTERNSHIP = "internship"
    FELLOWSHIP = "fellowship"
    RESEARCH_PROGRAM = "research_program"
    SUMMER_SCHOOL = "summer_school"
    HACKATHON = "hackathon"
    COMPETITION = "competition"
    OPEN_SOURCE_PROGRAM = "open_source_program"
    GRANT = "grant"
    CONFERENCE = "conference"
    COURSE = "course"
    JOB = "job"
    OTHER = "other"


class OpportunityStatus(StrEnum):
    """Publication lifecycle state of an opportunity."""

    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"
    ARCHIVED = "archived"


class DeadlineType(StrEnum):
    """How the deadline of an opportunity behaves."""

    FIXED = "fixed"
    ROLLING = "rolling"
    NONE = "none"


class LocationMode(StrEnum):
    """Where/how an opportunity takes place."""

    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNKNOWN = "unknown"


class RequirementKind(StrEnum):
    """Discriminator for the shape of a requirement's ``params`` payload."""

    NUMERIC_THRESHOLD = "numeric_threshold"
    SET_MEMBERSHIP = "set_membership"
    EQUALITY = "equality"
    BOOLEAN_FLAG = "boolean_flag"
    DATE_GATE = "date_gate"
    SKILL_SET = "skill_set"
    ANY_OF = "any_of"
    UNPARSED = "unparsed"


class RequirementCategory(StrEnum):
    """High-level grouping used to organize requirement explanations."""

    ACADEMIC = "academic"
    LANGUAGE = "language"
    DEMOGRAPHIC = "demographic"
    DOCUMENT = "document"
    LOGISTICS = "logistics"
    TIMING = "timing"
    OTHER = "other"


class SourceType(StrEnum):
    """Where an opportunity record or requirement evidence came from."""

    OFFICIAL_PAGE = "official_page"
    PARTNER_API = "partner_api"
    MANUAL_ENTRY = "manual_entry"
    SCRAPED = "scraped"
    MIRROR = "mirror"


class DegreeLevel(StrEnum):
    """Common degree levels used by profiles and education records."""

    HIGH_SCHOOL = "high_school"
    ASSOCIATE = "associate"
    BACHELOR = "bachelor"
    MASTER = "master"
    DOCTORATE = "doctorate"
    OTHER = "other"


class MatchStatus(StrEnum):
    """Overall verdict of one persisted Profile x Opportunity evaluation.

    Values mirror ``app.services.matching.evaluate.OpportunityMatchStatus``
    (kept in sync by a test); the model layer owns its own StrEnum so the
    database vocabulary follows the VARCHAR + CHECK convention used here.
    """

    ELIGIBLE = "eligible"
    POTENTIAL_MATCH = "potential_match"
    NOT_ELIGIBLE = "not_eligible"
    NEEDS_REVIEW = "needs_review"


class MatchOutcome(StrEnum):
    """Outcome of one persisted requirement evaluation inside a Match.

    Values mirror ``app.services.matching.result.RequirementOutcome``
    (kept in sync by a test).
    """

    MET = "met"
    NOT_MET = "not_met"
    UNKNOWN = "unknown"
    NEEDS_REVIEW = "needs_review"


def enum_check_constraint(table: str, column: str, enum_cls: type[StrEnum]) -> CheckConstraint:
    """Build a CHECK constraint limiting ``column`` to the enum's values.

    The constraint text is derived from the Python enum so the enum
    remains the single source of truth for allowed values.
    """
    values = ", ".join(f"'{item.value}'" for item in enum_cls)
    return CheckConstraint(f"{column} IN ({values})", name=f"ck_{table}_{column}")


__all__ = [
    "OpportunityType",
    "OpportunityStatus",
    "DeadlineType",
    "LocationMode",
    "RequirementKind",
    "RequirementCategory",
    "SourceType",
    "DegreeLevel",
    "MatchStatus",
    "MatchOutcome",
    "enum_check_constraint",
]
