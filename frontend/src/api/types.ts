import type { components } from "./schema";

type Schemas = components["schemas"];

export type Opportunity = Schemas["OpportunityRead"];
export type OpportunityDetail = Schemas["OpportunityDetailRead"];
export type PublicRequirement = Schemas["PublicRequirementRead"];
export type PublicSource = Schemas["PublicSourceRead"];
export type OpportunityType = Schemas["OpportunityType"];
export type LocationMode = Schemas["LocationMode"];
export type DeadlineType = Schemas["DeadlineType"];
/** ``requirements`` has a server-side default, so OpenAPI marks it optional; responses always carry it. */
export type Match = Omit<Schemas["MatchRead"], "requirements"> & { requirements: Schemas["MatchRequirementRead"][] };
export type MatchRow = Schemas["MatchRequirementRead"];
export type MatchStatus = Schemas["MatchStatus"];
export type MatchOutcome = Schemas["MatchOutcome"];
export type RequirementKind = Schemas["RequirementKind"];
export type Profile = Schemas["ProfileRead"];
export type ProfileCreate = Schemas["ProfileCreate"];
export type ProfileUpdate = Schemas["ProfileUpdate"];
export type DegreeLevel = Schemas["DegreeLevel"];
export type Education = Schemas["EducationRead"];
export type EducationCreate = Schemas["EducationCreate"];
export type EducationUpdate = Schemas["EducationUpdate"];
export type TestScore = Schemas["TestScoreRead"];
export type TestScoreCreate = Schemas["TestScoreCreate"];
export type Skill = Schemas["SkillRead"];
export type UserAccount = Schemas["UserAccountRead"];
export type SavedOpportunity = Schemas["SavedOpportunityRead"];
export type Application = Schemas["ApplicationRead"];
export type ApplicationItem = Schemas["ApplicationItemRead"];
export type ApplicationCreate = Schemas["ApplicationCreate"];
export type ApplicationUpdate = Schemas["ApplicationUpdate"];
export type ApplicationItemCreate = Schemas["ApplicationItemCreate"];
export type ApplicationItemUpdate = Schemas["ApplicationItemUpdate"];
export type Source = Schemas["SourceRead"];
export type AuditEntry = Schemas["AuditEntryRead"];
export type OpportunityUpdate = Schemas["OpportunityUpdate"];
