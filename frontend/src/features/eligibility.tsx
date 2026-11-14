import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../api/client";
import { batchEvaluateOpportunities, keys, mergeMatch, opportunitiesQuery } from "../api/queries";
import type { Match, Opportunity } from "../api/types";

type Progress = { total: number; done: number; failed: number };

type EligibilityState = {
  running: boolean;
  progress: Progress;
  /** Opportunity id -> time its verdict last changed, for one-shot animations. */
  changedAt: Map<string, number>;
  /** Opportunity id -> the match a re-check replaced, kept when any outcome changed. */
  before: Map<string, Match>;
  /** True after a profile edit until the next completed check. */
  stale: boolean;
  markStale: () => void;
  /** Evaluate the given opportunities (default: every published one). */
  run: (ids?: string[]) => Promise<Match[]>;
};

function outcomesDiffer(a: Match, b: Match): boolean {
  if (a.status !== b.status) return true;
  const outcomes = new Map(a.requirements.map((row) => [row.requirement_id, row.outcome]));
  return b.requirements.some((row) => outcomes.get(row.requirement_id) !== row.outcome);
}

const EligibilityContext = createContext<EligibilityState | null>(null);

export function EligibilityProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<Progress>({ total: 0, done: 0, failed: 0 });
  const [changedAt, setChangedAt] = useState<Map<string, number>>(new Map());
  const [before, setBefore] = useState<Map<string, Match>>(new Map());
  const [stale, setStale] = useState(false);
  const inFlight = useRef<Promise<Match[]> | null>(null);

  const run = useCallback(
    (ids?: string[]) => {
      if (inFlight.current) return inFlight.current;
      const job = (async () => {
        const opportunities: Opportunity[] = await client.fetchQuery(opportunitiesQuery);
        const queue = ids ?? opportunities.map((item) => item.id);
        const previous = new Map(
          (client.getQueryData<Match[]>(keys.matches) ?? []).map((match) => [match.opportunity_id, match]),
        );
        setRunning(true);
        setProgress({ total: queue.length, done: 0, failed: 0 });

        try {
          // Robust server-side batch evaluation in 1 HTTP transaction
          const results = await batchEvaluateOpportunities(ids);
          for (const match of results) {
            client.setQueryData<Match[]>(keys.matches, (old) => mergeMatch(old, match));
            const prior = previous.get(match.opportunity_id);
            if (prior && prior.status !== match.status) {
              setChangedAt((old) => new Map(old).set(match.opportunity_id, Date.now()));
            }
            if (prior && outcomesDiffer(prior, match)) {
              setBefore((old) => new Map(old).set(match.opportunity_id, prior));
            }
          }
          setProgress({ total: queue.length, done: queue.length, failed: 0 });
          setStale(false);
          return results;
        } catch (error) {
          setProgress({ total: queue.length, done: 0, failed: queue.length });
          if (error instanceof ApiError && error.status === 401) throw error;
          return [];
        } finally {
          setRunning(false);
          inFlight.current = null;
        }
      })();
      inFlight.current = job;
      return job;
    },
    [client],
  );

  const markStale = useCallback(() => setStale(true), []);

  const value = useMemo(
    () => ({ running, progress, changedAt, before, stale, markStale, run }),
    [running, progress, changedAt, before, stale, markStale, run],
  );
  return <EligibilityContext.Provider value={value}>{children}</EligibilityContext.Provider>;
}

export function useEligibility(): EligibilityState {
  const value = useContext(EligibilityContext);
  if (!value) throw new Error("useEligibility must be used inside <EligibilityProvider>");
  return value;
}
