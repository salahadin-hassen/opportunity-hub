"""Pydantic schemas for Opportunity Hub (database slice 1)."""
from app.schemas.match import MatchFacts, MatchRead, MatchRequirementRead, RequirementSummary
from app.schemas.opportunity import OpportunityCreate, OpportunityRead
from app.schemas.requirement import (
    AnyOfParams,
    BooleanFlagParams,
    DateGateParams,
    EqualityParams,
    NumericThresholdParams,
    PARAMS_MODELS,
    RequirementCondition,
    RequirementCreate,
    RequirementRead,
    SetMembershipParams,
    SkillSetParams,
    UnparsedParams,
    validate_params_for_kind,
)
from app.schemas.source import SourceCreate, SourceRead
from app.schemas.education import EducationCreate, EducationRead
from app.schemas.profile import ProfileCreate, ProfileRead
from app.schemas.skill import SKILL_KEY_PATTERN, SkillCreate, SkillRead
from app.schemas.test_score import TestScoreCreate, TestScoreRead
from app.schemas.user import UserRead

__all__ = [
    "OpportunityCreate",
    "OpportunityRead",
    "MatchFacts",
    "MatchRead",
    "MatchRequirementRead",
    "RequirementSummary",
    "UserRead",
    "ProfileCreate",
    "ProfileRead",
    "EducationCreate",
    "EducationRead",
    "TestScoreCreate",
    "TestScoreRead",
    "SourceCreate",
    "SourceRead",
    "SkillCreate",
    "SkillRead",
    "SKILL_KEY_PATTERN",
    "RequirementCreate",
    "RequirementRead",
    "RequirementCondition",
    "NumericThresholdParams",
    "SetMembershipParams",
    "EqualityParams",
    "BooleanFlagParams",
    "DateGateParams",
    "SkillSetParams",
    "AnyOfParams",
    "UnparsedParams",
    "PARAMS_MODELS",
    "validate_params_for_kind",
]
