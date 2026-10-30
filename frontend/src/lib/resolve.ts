/**
 * The missing-information loop: which absent profile facts keep which
 * opportunities undecided, and whether adding a fact alone can settle one.
 */
import type { Match } from "../api/types";
import { type Fact, factsForRow } from "./rules";

export type FactImpact = {
  fact: Fact;
  /** Opportunities whose verdict currently waits only on this fact. */
  decisive: string[];
  /** Opportunities where the fact is missing but other rules decide the verdict. */
  informational: string[];
};

function missingFacts(match: Match): Set<Fact> {
  const facts = new Set<Fact>();
  for (const row of match.requirements) {
    if (row.outcome === "unknown" && row.reason_code !== "invalid_any_of") {
      for (const fact of factsForRow(row)) facts.add(fact);
    }
  }
  return facts;
}

/**
 * Group matches by missing fact, most impactful first.
 *
 * A fact is *decisive* for a match when the match is a potential match and
 * every unknown row in it depends on that fact alone: supplying it is then
 * enough to produce a final verdict (in either direction).
 */
export function missingFactImpacts(matches: Match[]): FactImpact[] {
  const byFact = new Map<Fact, FactImpact>();
  for (const match of matches) {
    const facts = missingFacts(match);
    for (const fact of facts) {
      const impact = byFact.get(fact) ?? { fact, decisive: [], informational: [] };
      const decisive = match.status === "potential_match" && facts.size === 1;
      (decisive ? impact.decisive : impact.informational).push(match.opportunity_id);
      byFact.set(fact, impact);
    }
  }
  return [...byFact.values()].sort(
    (a, b) =>
      b.decisive.length - a.decisive.length ||
      b.informational.length - a.informational.length ||
      a.fact.localeCompare(b.fact),
  );
}

export function affectedOpportunities(impact: FactImpact): string[] {
  return [...impact.decisive, ...impact.informational];
}
