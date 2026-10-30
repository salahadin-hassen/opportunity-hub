/**
 * The copy layer: turns engine rules and evidence into plain sentences.
 *
 * The engine's own ``message`` strings are generic ("Profile satisfies the
 * numeric threshold requirement."), so everything a person reads is derived
 * here from ``kind``/``params`` (the published rule) or ``expected``/``actual``
 * (the evidence). Unknown shapes degrade to the curator-written label rather
 * than guessing.
 */
import type { DegreeLevel, MatchRow, RequirementKind } from "../api/types";
import { DEGREE_LABELS, countryName, formatPlainDate } from "./format";

type Params = Record<string, unknown>;

/** Profile facts the engine reads; anything else is never used for verdicts. */
export type Fact =
  | "gpa"
  | "date_of_birth"
  | "citizenship"
  | "enrollment"
  | "degree_level"
  | "skills";

export const FACT_LABELS: Record<Fact, string> = {
  gpa: "Primary education GPA",
  date_of_birth: "Date of birth",
  citizenship: "Citizenship",
  enrollment: "Enrolment status",
  degree_level: "Degree level",
  skills: "Skills",
};

/** Lower-case noun for running text ("Add your GPA", "no date of birth"). */
export const FACT_NOUNS: Record<Fact, string> = {
  gpa: "GPA",
  date_of_birth: "date of birth",
  citizenship: "citizenship",
  enrollment: "enrolment status",
  degree_level: "degree level",
  skills: "skills",
};

const METRIC_FACTS: Record<string, Fact> = {
  gpa: "gpa",
  date_of_birth: "date_of_birth",
  citizenship: "citizenship",
  is_currently_enrolled: "enrollment",
  degree_level: "degree_level",
  skills: "skills",
};

const OPERATOR_WORDS: Record<string, string> = {
  ">=": "≥",
  "<=": "≤",
  ">": ">",
  "<": "<",
  "==": "=",
  "!=": "≠",
};

function str(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function degree(value: unknown): string {
  const key = str(value);
  return key && key in DEGREE_LABELS ? DEGREE_LABELS[key as DegreeLevel] : String(value);
}

function gpaText(value: number): string {
  return value.toFixed(2).replace(/0$/, "");
}

function dateGateText(operator: string | null, value: string | null): string | null {
  if (!value) return null;
  const date = formatPlainDate(value);
  switch (operator) {
    case "<=":
      return `Born on or before ${date}`;
    case "<":
      return `Born before ${date}`;
    case ">=":
      return `Born on or after ${date}`;
    case ">":
      return `Born after ${date}`;
    default:
      return `Date of birth ${operator ?? "?"} ${date}`;
  }
}

/** State a published rule in words, from its ``kind`` and ``params``. */
export function describeRule(kind: RequirementKind | string, params: Params): string | null {
  const metric = str(params.metric);
  const operator = str(params.operator);
  switch (kind) {
    case "numeric_threshold": {
      const value = num(params.value);
      const scale = num(params.scale);
      if (metric !== "gpa" || value === null) return null;
      return `GPA ${OPERATOR_WORDS[operator ?? ""] ?? operator} ${gpaText(value)}${scale ? ` on a ${scale.toFixed(1)} scale` : ""}`;
    }
    case "equality":
      if (metric !== "degree_level") return null;
      return operator === "!=" ? `Degree level is not ${degree(params.value)}` : `Degree level: ${degree(params.value)}`;
    case "boolean_flag":
      if (metric !== "is_currently_enrolled") return null;
      return params.expected === false ? "Not currently enrolled" : "Currently enrolled";
    case "set_membership": {
      const allowed = Array.isArray(params.allowed) ? params.allowed.filter((item): item is string => typeof item === "string") : [];
      if (metric !== "citizenship" || allowed.length === 0) return null;
      const names = allowed.map(countryName).join(", ");
      return operator === "not_in" ? `Not a citizen of ${names}` : `Citizen of ${names}`;
    }
    case "date_gate":
      return metric === "date_of_birth" ? dateGateText(operator, str(params.value)) : null;
    case "skill_set": {
      const required = Array.isArray(params.required) ? params.required.map(String) : [];
      if (required.length === 0) return null;
      return `${operator === "contains_all" ? "All of" : "Any of"}: ${required.join(", ")}`;
    }
    case "any_of": {
      const children = Array.isArray(params.any_of) ? params.any_of : [];
      const parts = children.map((child) => {
        const item = child as { kind?: string; params?: Params };
        return item.kind && item.params ? describeRule(item.kind, item.params) : null;
      });
      if (parts.length === 0 || parts.some((part) => part === null)) return null;
      // "Degree level: Bachelor’s or Master’s" reads better than repeating the prefix.
      const prefix = "Degree level: ";
      if (parts.every((part) => part!.startsWith(prefix))) {
        return prefix + parts.map((part) => part!.slice(prefix.length)).join(" or ");
      }
      return parts.join(" — or — ");
    }
    case "unparsed":
      return null;
    default:
      return null;
  }
}

/** Which profile fact a rule (or an ``any_of`` child set) depends on. */
export function factsForRule(kind: string, params: Params): Fact[] {
  if (kind === "any_of") {
    const children = Array.isArray(params.any_of) ? params.any_of : [];
    const facts = children.flatMap((child) => {
      const item = child as { kind?: string; params?: Params };
      return item.kind && item.params ? factsForRule(item.kind, item.params) : [];
    });
    return [...new Set(facts)];
  }
  const metric = str(params.metric);
  const fact = metric ? METRIC_FACTS[metric] : undefined;
  return fact ? [fact] : [];
}

/** The fact an evidence row is about, read from what the engine recorded. */
export function factsForRow(row: Pick<MatchRow, "expected" | "requirement">): Fact[] {
  const expected = row.expected as Params;
  if (Array.isArray(expected.children)) {
    return factsForRule("any_of", { any_of: expected.children });
  }
  return factsForRule(row.requirement.kind, expected);
}

/** Human summary of what the profile held when the rule was evaluated. */
export function describeActual(row: MatchRow): string | null {
  const actual = row.actual as Params;
  if (row.outcome === "unknown" && row.reason_code === "profile_fact_unavailable") {
    return "Not in your profile";
  }
  if (Array.isArray(actual.children)) {
    const values = (actual.children as Array<{ actual?: Params }>)
      .map((child) => child.actual?.value)
      .filter((value) => value !== undefined && value !== null);
    if (values.length > 0) {
      const first = values[0];
      return typeof first === "string" && first in DEGREE_LABELS ? degree(first) : String(first);
    }
    return null;
  }
  switch (row.requirement.kind) {
    case "numeric_threshold": {
      const value = num(actual.value);
      const scale = num(actual.scale);
      if (value === null) return null;
      return scale === null ? `GPA ${gpaText(value)}` : `GPA ${gpaText(value)} on a ${scale.toFixed(1)} scale`;
    }
    case "equality":
      return actual.value == null ? null : degree(actual.value);
    case "boolean_flag":
      if (typeof actual.value === "boolean") return actual.value ? "Enrolled" : "Not enrolled";
      return null;
    case "set_membership": {
      const values = Array.isArray(actual.values) ? actual.values.map(String) : null;
      if (!values) return null;
      return values.length ? values.map(countryName).join(", ") : "No citizenship listed";
    }
    case "date_gate": {
      const value = str(actual.value);
      return value ? `Born ${formatPlainDate(value)}` : null;
    }
    case "skill_set": {
      const values = Array.isArray(actual.values) ? actual.values.map(String) : null;
      return values ? (values.length ? values.join(", ") : "No skills listed") : null;
    }
    default:
      return null;
  }
}

/** Why the engine could not decide, phrased for the person reading it. */
export function reviewReason(row: Pick<MatchRow, "reason_code" | "outcome">): string | null {
  if (row.outcome !== "needs_review") return null;
  const code = row.reason_code;
  if (code === "gpa_scale_mismatch") {
    return "Your GPA is on a different grading scale. Scales aren’t converted automatically, so compare it to the official threshold yourself.";
  }
  if (code === "gpa_threshold_scale_unspecified") {
    return "The threshold doesn’t say which grading scale it uses, so it can’t be compared.";
  }
  if (code === "unsupported_requirement_kind") {
    return "Not machine-checkable — read the official wording and decide.";
  }
  if (code === "ambiguous_requirement") {
    return "The official wording is ambiguous — confirm it on the official page.";
  }
  if (code.startsWith("unsupported_") && code.endsWith("_operator")) {
    return "This comparison isn’t supported by the engine yet — check it yourself.";
  }
  if (code === "any_of_needs_review") {
    return "One alternative couldn’t be checked automatically.";
  }
  return "The engine couldn’t check this rule — verify it on the official page.";
}

export const OUTCOME_LABELS: Record<MatchRow["outcome"], string> = {
  met: "Met",
  not_met: "Not met",
  unknown: "Missing fact",
  needs_review: "Your call",
};
