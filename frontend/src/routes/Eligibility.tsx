import { AnimatePresence, motion } from "motion/react";
import { ChevronDown, RefreshCw, ScanSearch } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { useMatches, useOpportunities } from "../api/queries";
import type { Match, MatchOutcome, MatchStatus, Opportunity } from "../api/types";
import { EvidenceList } from "../components/eligibility/Evidence";
import { ChangeSummary, ResolvePanel, type Change } from "../components/eligibility/ResolvePanel";
import { PageHeader } from "../components/layout/AppShell";
import { Content, Page } from "../components/layout/Page";
import { RuleStrip } from "../components/opportunities/OpportunityRow";
import { TypeLabel, TypeTile } from "../components/opportunities/TypeTile";
import { EmptyState, ErrorState, Spinner } from "../components/ui/States";
import { OutcomeMark, VERDICT_MEANING, VERDICT_SCOPE, VERDICT_TONE, VerdictBadge, VerdictMark } from "../components/ui/Verdict";
import { useEligibility } from "../features/eligibility";
import { useDeviceChecklist } from "../hooks/useDeviceChecklist";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { STATUS_LONG, STATUS_ORDER, deadlineInfo, deadlineIsDate, formatDateTime, plural } from "../lib/format";

const GROUP_TITLE: Record<MatchStatus, string> = {
  eligible: "You meet every published rule",
  potential_match: "Missing information",
  needs_review: "Needs your review",
  not_eligible: "Ruled out by a mandatory rule",
};

function Composition({ counts, total }: { counts: Map<MatchStatus, number>; total: number }) {
  return (
    <div className="border-y border-ink py-6">
      <div className="flex h-3 overflow-hidden rounded-full bg-cream" aria-hidden="true">
        {STATUS_ORDER.map((status) => {
          const count = counts.get(status) ?? 0;
          return count ? (
            <motion.div
              key={status}
              className={`${VERDICT_TONE[status].dot} h-full border-r-2 border-paper last:border-r-0`}
              initial={false}
              animate={{ width: `${(count / total) * 100}%` }}
              transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
            />
          ) : null;
        })}
      </div>
      <dl className="mt-6 grid grid-cols-2 gap-x-4 gap-y-5 sm:grid-cols-4">
        {STATUS_ORDER.map((status) => (
          <a key={status} href={`#group-${status}`} className="group rounded-md">
            <dt className="flex items-center gap-1.5 text-[13px] text-ink-soft group-hover:text-ink">
              <VerdictMark status={status} size={13} />
              {STATUS_LONG[status]}
            </dt>
            <dd className="display mt-1 text-[44px] text-ink">{counts.get(status) ?? 0}</dd>
          </a>
        ))}
      </dl>
    </div>
  );
}

/** The rows that produced each verdict under the engine's rollup order. */
const DECIDING: Record<MatchStatus, MatchOutcome[]> = {
  not_eligible: ["not_met"],
  potential_match: ["unknown"],
  needs_review: ["unknown", "needs_review"],
  eligible: [],
};

function MatchCard({
  match,
  opportunity,
  previous,
  changedAt,
  checklist,
}: {
  match: Match;
  opportunity: Opportunity;
  previous?: Match;
  changedAt?: number;
  checklist: ReturnType<typeof useDeviceChecklist>;
}) {
  const [expanded, setExpanded] = useState(false);
  const deciding = match.requirements.filter((row) => DECIDING[match.status].includes(row.outcome));
  // Review items are short checklists; the full evidence is one click away.
  const compact = match.status === "needs_review" && !expanded;
  const shown = expanded ? match : { ...match, requirements: deciding };
  const deadline = deadlineInfo(opportunity);
  return (
    <motion.li layout="position" className="sheet overflow-hidden">
      <div className="flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-start sm:px-5">
        <TypeTile type={opportunity.opportunity_type} host={opportunity.host_name} size={44} />
        <div className="min-w-0 flex-1">
          <TypeLabel type={opportunity.opportunity_type} />
          <Link to={`/opportunities/${opportunity.id}`} className="heading mt-1 block text-[18px] text-ink decoration-1 underline-offset-4 hover:underline">
            {opportunity.title}
          </Link>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12.5px] text-muted">
            <RuleStrip match={match} />
            <span>
              Deadline <span className={deadlineIsDate(opportunity) ? "num" : ""}>{deadline.label}</span>
            </span>
          </div>
        </div>
        <VerdictBadge status={match.status} size="sm" animateKey={changedAt} />
      </div>
      {compact ? (
        <div className="border-t border-rule px-4 py-3 sm:px-5">
          <p className="text-[12.5px] font-semibold text-ink">For you to confirm</p>
          <ul className="mt-1">
            {deciding.map((row) =>
              row.outcome === "needs_review" ? (
                <li key={row.id}>
                  <label className="flex cursor-pointer items-start gap-3 py-2">
                    <input
                      type="checkbox"
                      checked={Boolean(checklist.checked[row.id])}
                      onChange={() => checklist.toggle(row.id)}
                      className="mt-0.5 size-[18px] shrink-0 accent-review"
                    />
                    <span className={`text-[14.5px] ${checklist.checked[row.id] ? "text-muted line-through decoration-1" : "text-ink"}`}>{row.requirement.label}</span>
                  </label>
                </li>
              ) : (
                <li key={row.id} className="flex items-start gap-3 py-2">
                  <OutcomeMark outcome={row.outcome} size={18} />
                  <span className="text-[14.5px] text-ink">{row.requirement.label}</span>
                  <span className="ml-auto shrink-0 text-[12.5px] text-potential-ink">Missing from your profile</span>
                </li>
              ),
            )}
          </ul>
        </div>
      ) : shown.requirements.length > 0 ? (
        <div className="border-t border-rule">
          <EvidenceList match={shown} previous={previous} />
        </div>
      ) : null}
      {match.requirements.length > (compact ? 0 : deciding.length) && (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          aria-expanded={expanded}
          className="flex w-full items-center justify-center gap-1.5 border-t border-rule py-2.5 text-[13px] text-muted hover:bg-tint hover:text-ink"
        >
          {expanded ? "Show only what decided this" : `Show evidence for all ${match.requirements.length} rules`}
          <ChevronDown size={14} className={`transition-transform ${expanded ? "rotate-180" : ""}`} />
        </button>
      )}
    </motion.li>
  );
}

export function Eligibility() {
  const opportunities = useOpportunities();
  const matches = useMatches();
  const { run, running, progress, before, changedAt, stale } = useEligibility();
  const [changes, setChanges] = useState<Change[]>([]);
  const [error, setError] = useState<string | null>(null);
  // One summary, placed beside the results on wide screens and above them otherwise.
  const wide = useMediaQuery("(min-width: 1280px)");
  const checklist = useDeviceChecklist();

  const byId = new Map((opportunities.data ?? []).map((item) => [item.id, item]));
  // Only currently listed opportunities count; closed ones keep their history but leave the summary.
  const listed = (matches.data ?? []).filter((match) => byId.has(match.opportunity_id));
  const counts = new Map<MatchStatus, number>();
  for (const match of listed) counts.set(match.status, (counts.get(match.status) ?? 0) + 1);
  const unchecked = (opportunities.data ?? []).filter((item) => !listed.some((match) => match.opportunity_id === item.id));
  const lastChecked = listed.reduce<string | null>((latest, match) => (!latest || match.evaluated_at > latest ? match.evaluated_at : latest), null);

  async function runAll() {
    setError(null);
    setChanges([]);
    const statuses = new Map(listed.map((match) => [match.opportunity_id, match.status]));
    try {
      const results = await run();
      setChanges(
        results
          .filter((match) => statuses.has(match.opportunity_id) && statuses.get(match.opportunity_id) !== match.status)
          .map((match) => ({
            id: match.opportunity_id,
            title: byId.get(match.opportunity_id)?.title ?? "Opportunity",
            from: statuses.get(match.opportunity_id)!,
            to: match.status,
          })),
      );
    } catch {
      setError("The check stopped before it finished. Try again.");
    }
  }

  const loading = opportunities.isPending || matches.isPending;

  return (
    <Page title="Eligibility">
      <Content width="wide">
        <PageHeader
          title="Your eligibility"
          description={
            lastChecked ? (
              <>
                {plural(listed.length, "opportunity", "opportunities")} checked against your profile. Last check <span className="num">{formatDateTime(lastChecked)}</span>.
              </>
            ) : (
              "Run a check to evaluate every published opportunity against your profile."
            )
          }
          actions={
            <button type="button" className="btn btn-primary" onClick={runAll} disabled={running || loading}>
              {running ? <Spinner size={14} /> : listed.length ? <RefreshCw size={15} /> : <ScanSearch size={15} />}
              {running ? `Checking ${progress.done} of ${progress.total}` : listed.length ? "Re-check all" : "Run my first check"}
            </button>
          }
        />

        {(matches.isError || opportunities.isError) && (
          <div className="mt-6">
            <ErrorState message="Your results couldn’t load. Check that the API is running." onRetry={() => { matches.refetch(); opportunities.refetch(); }} />
          </div>
        )}
        {error && <div className="mt-6"><ErrorState message={error} /></div>}

        {loading ? (
          <div className="mt-8 flex flex-col gap-3">
            <div className="skeleton h-28 w-full" />
            <div className="skeleton h-40 w-full" />
          </div>
        ) : listed.length === 0 && !running ? (
          <div className="sheet mt-8">
            <EmptyState
              icon={ScanSearch}
              title="No verdicts yet"
              action={
                <button type="button" className="btn btn-primary" onClick={runAll}>
                  Run my first check
                </button>
              }
            >
              The engine checks {plural(opportunities.data?.length ?? 0, "published opportunity", "published opportunities")} against your profile, one rule at a time, and keeps the evidence.
            </EmptyState>
          </div>
        ) : (
          <div className="mt-8 grid grid-cols-1 gap-8 xl:grid-cols-[minmax(0,1fr)_380px]">
            <div className="flex min-w-0 flex-col gap-8">
              <div>
                <Composition counts={counts} total={Math.max(listed.length, 1)} />
                <p className="mt-4 max-w-[70ch] text-[13.5px] text-ink-soft">{VERDICT_SCOPE}</p>
              </div>
              {stale && !running && (
                <div className="flex items-center gap-3 rounded-panel border border-potential/40 bg-potential-wash px-4 py-3 text-[14px] text-potential-ink">
                  <p className="flex-1">Your profile changed since these verdicts were calculated.</p>
                  <button type="button" className="btn btn-quiet btn-sm" onClick={runAll}>
                    Re-check all
                  </button>
                </div>
              )}
              {unchecked.length > 0 && !running && (
                <p className="text-[13.5px] text-muted">
                  {plural(unchecked.length, "opportunity", "opportunities")} haven’t been checked yet.{" "}
                  <button type="button" className="font-medium text-cobalt-deep hover:underline" onClick={runAll}>
                    Check them now
                  </button>
                </p>
              )}
              {!wide && <ChangeSummary changes={changes} onDismiss={() => setChanges([])} />}
              {!wide && <ResolvePanel matches={listed} onChanges={setChanges} />}

              {STATUS_ORDER.map((status) => {
                const group = listed.filter((match) => match.status === status);
                if (group.length === 0) return null;
                return (
                  <section key={status} id={`group-${status}`} aria-labelledby={`group-${status}-title`} className="scroll-mt-20">
                    <div className="mb-3 flex items-center gap-3">
                      <VerdictMark status={status} size={20} />
                      <h2 id={`group-${status}-title`} className="heading text-[26px] text-ink">
                        {GROUP_TITLE[status]}
                      </h2>
                      <span className="num text-[13px] text-muted">{group.length}</span>
                    </div>
                    <p className="mb-5 text-[14.5px] text-ink-soft">
                      {VERDICT_MEANING[status]}
                      {status === "needs_review" && " Tick a condition once you’ve confirmed it yourself. Ticks are notes saved on this device only and don’t change the verdict."}
                    </p>
                    <ul className="flex flex-col gap-4">
                      <AnimatePresence initial={false}>
                        {group.map((match) => (
                          <MatchCard
                            key={match.opportunity_id}
                            match={match}
                            opportunity={byId.get(match.opportunity_id)!}
                            previous={before.get(match.opportunity_id)}
                            changedAt={changedAt.get(match.opportunity_id)}
                            checklist={checklist}
                          />
                        ))}
                      </AnimatePresence>
                    </ul>
                  </section>
                );
              })}
            </div>
            <aside className="flex flex-col gap-4 xl:sticky xl:top-8 xl:max-h-[calc(100dvh-4rem)] xl:self-start xl:overflow-y-auto xl:pb-4">
              {wide && <ChangeSummary changes={changes} onDismiss={() => setChanges([])} />}
              {wide && <ResolvePanel matches={listed} onChanges={setChanges} />}
              <div className="rounded-panel border border-dashed border-rule-strong px-4 py-3.5 text-[13px] text-muted">
                The engine reads only GPA, citizenship, degree level, enrolment, date of birth and skills. Languages, residence, interests and test scores are stored but never affect a verdict.
              </div>
            </aside>
          </div>
        )}
      </Content>
    </Page>
  );
}
