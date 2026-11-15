"""Deterministic requirement evaluation services."""

from app.services.matching.capabilities import (
    Capability,
    CAPABILITIES_CATALOG,
    get_capabilities,
    find_capability,
    is_supported_rule,
)
from app.services.matching.evaluate import (
	MatchEvaluationResult,
	OpportunityMatchStatus,
	evaluate_requirements,
)
from app.services.matching.registry import evaluate_requirement
from app.services.matching.result import RequirementOutcome, RequirementResult

#: Deterministic version of these matching rules. Increment deliberately
#: whenever evaluator semantics change so persisted matches stay traceable.
ENGINE_VERSION = "1"

__all__ = [
	"ENGINE_VERSION",
	"Capability",
	"CAPABILITIES_CATALOG",
	"get_capabilities",
	"find_capability",
	"is_supported_rule",
	"MatchEvaluationResult",
	"OpportunityMatchStatus",
	"RequirementOutcome",
	"RequirementResult",
	"evaluate_requirement",
	"evaluate_requirements",
]