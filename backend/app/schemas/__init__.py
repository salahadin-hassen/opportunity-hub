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
from app.schemas.auth import TokenResponse, UserCreate, UserLogin
from app.schemas.source import SourceCreate, SourceRead
from app.schemas.education import EducationCreate, EducationRead, EducationUpdate
from app.schemas.profile import ProfileCreate, ProfileRead, ProfileUpdate
from app.schemas.skill import (
    SKILL_KEY_PATTERN,
    ProfileSkillCreate,
    SkillCreate,
    SkillRead,
)
from app.schemas.test_score import TestScoreCreate, TestScoreRead, TestScoreUpdate
from app.schemas.user import UserRead

__all__ = [
    "OpportunityCreate",
    "OpportunityRead",
    "MatchFacts",
    "MatchRead",
    "MatchRequirementRead",
    "RequirementSummary",
    "UserRead",
    "UserCreate",
    "UserLogin",
    "TokenResponse",
    "ProfileCreate",
    "ProfileRead",
    "ProfileUpdate",
    "EducationCreate",
    "EducationRead",
    "EducationUpdate",
    "TestScoreCreate",
    "TestScoreRead",
    "TestScoreUpdate",
    "SourceCreate",
    "SourceRead",
    "ProfileSkillCreate",
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
