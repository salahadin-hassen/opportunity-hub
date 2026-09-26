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
from app.models.education import Education
from app.models.match import Match
from app.models.match_requirement import MatchRequirement
from app.models.opportunity import Opportunity
from app.models.profile import Profile
from app.models.profile_skill import ProfileSkill
from app.models.requirement import Requirement
from app.models.skill import Skill
from app.models.source import Source
from app.models.test_score import TestScore

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
