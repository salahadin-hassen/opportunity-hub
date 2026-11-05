"""ORM models for Opportunity Hub (database slice 1)."""
from app.models.enums import (
    DeadlineType,
    LocationMode,
    MatchOutcome,
    MatchStatus,
    OpportunityStatus,
    OpportunityType,
    RequirementCategory,
    RequirementKind,
    SourceType,
    DegreeLevel,
)
from app.models.acquisition_source import AcquisitionSource, AcquisitionSourceHost
from app.models.application import Application, ApplicationItem
from app.models.audit_log import AuditLog
from app.models.deletion_tombstone import DeletionTombstone
from app.models.education import Education
from app.models.email_outbox import EmailOutbox
from app.models.email_token import EmailToken
from app.models.match import Match
from app.models.match_requirement import MatchRequirement
from app.models.opportunity import Opportunity
from app.models.profile import Profile
from app.models.profile_skill import ProfileSkill
from app.models.rate_limit_bucket import RateLimitBucket
from app.models.requirement import Requirement
from app.models.saved_opportunity import SavedOpportunity
from app.models.session import Session
from app.models.skill import Skill
from app.models.source import Source
from app.models.test_score import TestScore
from app.models.user import User

__all__ = [
    "Opportunity",
    "Requirement",
    "Source",
    "Profile",
    "ProfileSkill",
    "Skill",
    "Education",
    "TestScore",
    "Match",
    "MatchRequirement",
    "User",
    "Session",
    "EmailToken",
    "EmailOutbox",
    "DeletionTombstone",
    "SavedOpportunity",
    "Application",
    "ApplicationItem",
    "AcquisitionSource",
    "AcquisitionSourceHost",
    "AuditLog",
    "RateLimitBucket",
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
]
