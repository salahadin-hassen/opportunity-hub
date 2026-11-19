import { motion } from "motion/react";
import { ArrowUpRight } from "lucide-react";
import { Link } from "react-router";
import type { Match, Opportunity } from "../../api/types";
import { LOCATION_LABELS, countryName, deadlineInfo } from "../../lib/format";
import { DateBlock } from "../ui/DateBlock";
import { UncheckedBadge, VerdictBadge } from "../ui/Verdict";
import { SaveToggle } from "./SaveToggle";
import { TypeLabel } from "./TypeTile";

export function locationText(opportunity: Pick<Opportunity, "countries" | "location_mode">): string {
  const places = (opportunity.countries ?? []).map((code) => countryName(String(code)));
  if (opportunity.location_mode === "remote") return "Remote";
  if (places.length === 0) return LOCATION_LABELS[opportunity.location_mode];
  return opportunity.location_mode === "hybrid" ? `${places.join(", ")} (hybrid)` : places.join(", ");
}

/** "2 of 3 rules met", plus what is still open, from the engine's own counts. */
export function factsLine(match: Match): string {
  const { total, met, unknown, needs_review, not_met } = match.facts;
  const parts = [`${met} of ${total} rules met`];
  if (not_met) parts.push(`${not_met} not met`);
  if (unknown) parts.push(`${unknown} missing`);
  if (needs_review) parts.push(`${needs_review} to review`);
  return parts.join(", ");
}

const STRIP: Record<string, string> = {
  met: "bg-eligible",
  not_met: "bg-ineligible",
  unknown: "bg-potential",
  needs_review: "bg-review",
};

/** One mark per rule, in published order: the verdict's composition at a glance. */
export function RuleStrip({ match }: { match: Match }) {
  return (
    <span className="inline-flex items-center gap-2" title={factsLine(match)}>
      <span className="inline-flex gap-[3px]" aria-hidden="true">
        {match.requirements.map((row) => (
          <span key={row.id} className={`h-3 w-[5px] rounded-[2px] ${STRIP[row.outcome]}`} />
        ))}
      </span>
      <span className="text-[12.5px] text-muted">
        <span className="sr-only">{factsLine(match)}</span>
        <span aria-hidden="true">
          {match.facts.met}/{match.facts.total} met
        </span>
      </span>
    </span>
  );
}

/** "Closes in 7 days", "Rolling admissions", "Deadline not published": the deadline in words. */
export function deadlineWords(opportunity: Pick<Opportunity, "deadline_at" | "deadline_type">): { text: string; urgent: boolean } {
  const info = deadlineInfo(opportunity);
  if (info.state === "rolling") return { text: "Rolling admissions", urgent: false };
  if (info.state === "none") return { text: "No deadline", urgent: false };
  if (info.state === "unknown") return { text: "Deadline not published here", urgent: false };
  if (info.state === "closed") return { text: `Closed ${info.label}`, urgent: false };
  return { text: `Closes ${info.relative}`, urgent: info.state === "soon" };
}

/**
 * One listing in the index: the deadline leads (it's what people compare
 * first), then the title, then who runs it and where. The whole row is one
 * link (stretched from the title), and Save sits above it as its own control.
 */
export function OpportunityRow({
  opportunity,
  match,
  showVerdict,
  changedAt,
  canSave = false,
}: {
  opportunity: Opportunity;
  match?: Match;
  showVerdict: boolean;
  changedAt?: number;
  canSave?: boolean;
}) {
  const deadline = deadlineWords(opportunity);
  const info = deadlineInfo(opportunity);
  return (
    <motion.li
      layout="position"
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
      className="row-press group relative grid grid-cols-[auto_minmax(0,1fr)_auto] gap-x-4 py-4 transition-transform duration-150 sm:gap-x-5 md:grid-cols-[auto_minmax(0,1fr)_190px_auto] md:items-center"
    >
      <div className="row-span-2 self-start md:row-span-1 md:self-center">
        <DateBlock opportunity={opportunity} />
      </div>
      <div className="min-w-0">
        <p className="flex min-w-0 items-center gap-2 text-[12.5px] text-muted">
          <TypeLabel type={opportunity.opportunity_type} quiet />
        </p>
        <h3 className="heading mt-1 text-[17.5px] leading-[1.2] text-ink sm:text-[19px]">
          <Link
            to={`/opportunities/${opportunity.id}`}
            className="decoration-1 underline-offset-4 outline-none after:absolute after:inset-0 after:rounded-[10px] group-hover:underline focus-visible:after:outline-2 focus-visible:after:outline-offset-2 focus-visible:after:outline-cobalt"
          >
            {opportunity.title}
          </Link>
        </h3>
        <p className="mt-1 truncate text-[13.5px] text-ink-soft">
          {opportunity.host_name ?? "Host not named"}
          <span className="mx-1.5 text-faint" aria-hidden="true">
            ·
          </span>
          <span className="text-muted">{locationText(opportunity)}</span>
        </p>
        <p className={`mt-1.5 text-[12.5px] ${deadline.urgent ? "font-semibold text-persimmon-deep" : "text-muted"}`}>
          {deadline.text}
          {info.state !== "unknown" && info.state !== "rolling" && info.state !== "none" && <span className="sr-only">, {info.label}</span>}
        </p>
      </div>
      {/* One verdict element: under the text on phones, its own column from md up. */}
      <div
        className={`col-start-2 row-start-2 mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 md:col-start-3 md:row-start-1 md:mt-0 md:flex-col md:items-end md:gap-1.5 ${showVerdict ? "" : "hidden md:flex"}`}
      >
        {showVerdict ? (
          match ? (
            <>
              <VerdictBadge status={match.status} size="sm" animateKey={changedAt} />
              <RuleStrip match={match} />
            </>
          ) : (
            <UncheckedBadge />
          )
        ) : (
          <span className="inline-flex items-center gap-1 text-[13px] text-muted transition-colors group-hover:text-ink">
            Read the rules
            <ArrowUpRight size={14} className="transition-transform duration-300 group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
          </span>
        )}
      </div>
      <div className="col-start-3 row-start-1 -mr-1 self-start md:col-start-4 md:self-center">
        {canSave ? <SaveToggle opportunityId={opportunity.id} title={opportunity.title} /> : <span className="block w-1" />}
      </div>
    </motion.li>
  );
}

export function RowSkeleton() {
  return (
    <li className="grid grid-cols-[auto_minmax(0,1fr)] gap-4 py-4 md:grid-cols-[auto_minmax(0,1fr)_190px]" aria-hidden="true">
      <div className="skeleton h-[68px] w-[60px] rounded-[10px]" />
      <div className="flex flex-col gap-2 pt-1">
        <div className="skeleton h-3 w-24" />
        <div className="skeleton h-5 w-3/4" />
        <div className="skeleton h-3 w-1/3" />
      </div>
      <div className="skeleton hidden h-4 w-28 self-center justify-self-end md:block" />
    </li>
  );
}
