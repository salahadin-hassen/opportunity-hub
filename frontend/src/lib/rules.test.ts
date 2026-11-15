import { describe, expect, it } from "vitest";
import type { Match, OpportunityDetail } from "../api/types";
import fixture from "./__fixtures__/demo-api.json";
import { deadlineInfo } from "./format";
import { affectedOpportunities, missingFactImpacts } from "./resolve";
import { describeActual, describeRule, factsForRow, reviewReason } from "./rules";

// Real responses captured from the seeded backend for the demo profile.
const matches = fixture.matches as unknown as Match[];
const kaust = fixture.kaustDetail as unknown as OpportunityDetail;
const titleOf = (id: string) => fixture.opportunities.find((item) => item.id === id)?.title;

describe("describeRule", () => {
  it("states every published KAUST rule in words", () => {
    expect(kaust.requirements.map((rule) => describeRule(rule.kind, rule.params))).toEqual([
      "Degree level: Bachelor’s or Master’s",
      "GPA ≥ 3.5 on a 4.0 scale",
    ]);
  });

  it("covers citizenship, enrolment and date rules", () => {
    expect(describeRule("set_membership", { metric: "citizenship", operator: "in", allowed: ["US"] })).toBe(
      "Citizen of United States",
    );
    expect(describeRule("set_membership", { metric: "citizenship", operator: "not_in", allowed: ["GB"] })).toBe(
      "Not a citizen of United Kingdom",
    );
    expect(describeRule("boolean_flag", { metric: "is_currently_enrolled", expected: true })).toBe("Currently enrolled");
    expect(describeRule("date_gate", { metric: "date_of_birth", operator: "<=", value: "2010-08-01" })).toBe(
      "Born on or before 1 Aug 2010",
    );
  });

  it("returns null instead of guessing for unparsed or unknown shapes", () => {
    expect(describeRule("unparsed", { reason: "x" })).toBeNull();
    expect(describeRule("numeric_threshold", { metric: "ielts", operator: ">=", value: 7 })).toBeNull();
  });
});

describe("evidence copy", () => {
  it("explains a missing GPA as a missing profile fact", () => {
    const kaustMatch = matches.find((match) => titleOf(match.opportunity_id)?.startsWith("KAUST"))!;
    const gpaRow = kaustMatch.requirements.find((row) => row.requirement.kind === "numeric_threshold")!;
    expect(gpaRow.outcome).toBe("unknown");
    expect(describeActual(gpaRow)).toBe("Not in your profile");
    expect(factsForRow(gpaRow)).toEqual(["gpa"]);
  });

  it("reads the profile value out of any_of evidence", () => {
    const cern = matches.find((match) => titleOf(match.opportunity_id)?.startsWith("CERN"))!;
    const degreeRow = cern.requirements.find((row) => row.requirement.kind === "any_of")!;
    expect(degreeRow.outcome).toBe("met");
    expect(describeActual(degreeRow)).toBe("Bachelor’s");
    expect(factsForRow(degreeRow)).toEqual(["degree_level"]);
  });

  it("phrases review reasons for people, not engine codes", () => {
    const gates = matches.find((match) => titleOf(match.opportunity_id)?.startsWith("Gates"))!;
    expect(reviewReason(gates.requirements[0]!)).toMatch(/isn’t supported by the engine yet/);
    const gsoc = matches.find((match) => titleOf(match.opportunity_id)?.startsWith("Google"))!;
    expect(reviewReason(gsoc.requirements[0]!)).toMatch(/Not machine-checkable/);
  });
});

describe("missingFactImpacts", () => {
  it("finds the two facts that settle the demo's potential matches", () => {
    const impacts = missingFactImpacts(matches);
    const byFact = Object.fromEntries(impacts.map((impact) => [impact.fact, impact]));

    expect(byFact.gpa!.decisive.map(titleOf)).toEqual(["KAUST Visiting Student Research Program (VSRP)"]);
    expect(byFact.date_of_birth!.decisive.map(titleOf)).toEqual(["GitHub Student Developer Pack"]);
    // NASA is already not eligible on citizenship: the GPA is missing but not decisive.
    expect(byFact.gpa!.informational.map(titleOf)).toEqual(
      expect.arrayContaining(["NASA OSTEM Internships — Summer 2027", "NASA OSTEM Internships — Fall 2027"]),
    );
    expect(affectedOpportunities(byFact.gpa!)).toHaveLength(3);
  });

  it("reports nothing when no fact is missing", () => {
    expect(missingFactImpacts(matches.filter((match) => match.status === "eligible"))).toEqual([]);
  });
});

describe("deadlineInfo", () => {
  const now = Date.UTC(2026, 9, 30, 12);

  it("never invents a date for open-ended or unpublished deadlines", () => {
    expect(deadlineInfo({ deadline_type: "fixed", deadline_at: null }, now).label).toBe("See official page");
    expect(deadlineInfo({ deadline_type: "rolling", deadline_at: null }, now).label).toBe("Rolling");
    expect(deadlineInfo({ deadline_type: "none", deadline_at: null }, now).label).toBe("No deadline");
  });

  it("counts days to a fixed deadline and marks closed ones", () => {
    const soon = deadlineInfo({ deadline_type: "fixed", deadline_at: "2026-11-15T12:00:00Z" }, now);
    expect(soon).toMatchObject({ label: "15 Nov 2026", relative: "in 16 days", state: "soon" });
    expect(deadlineInfo({ deadline_type: "fixed", deadline_at: "2026-10-01T00:00:00Z" }, now).state).toBe("closed");
  });
});
