import { motion } from "motion/react";
import { ArrowUpRight } from "lucide-react";
import { Link } from "react-router";
import type { Match, Opportunity } from "../../api/types";
import { LOCATION_LABELS, countryName, deadlineInfo, deadlineIsDate } from "../../lib/format";
import { UncheckedBadge, VerdictBadge } from "../ui/Verdict";
import { TypeLabel, TypeTile } from "./TypeTile";

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

export function OpportunityRow({
  opportunity,
  match,
  showVerdict,
  changedAt,
}: {
  opportunity: Opportunity;
  match?: Match;
  showVerdict: boolean;
  changedAt?: number;
}) {
  const deadline = deadlineInfo(opportunity);
  return (
    <motion.li
      layout="position"
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
    >
      <Link
        to={`/opportunities/${opportunity.id}`}
        className="group grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-3 py-5 transition-colors duration-200 md:grid-cols-[auto_minmax(0,1fr)_150px_170px] md:items-center md:gap-x-6"
      >
        <TypeTile type={opportunity.opportunity_type} host={opportunity.host_name} size={52} />
        <div className="min-w-0">
          <TypeLabel type={opportunity.opportunity_type} />
          <p className="heading mt-1 text-[19px] text-ink decoration-1 underline-offset-4 group-hover:underline">{opportunity.title}</p>
          <p className="mt-1 truncate text-[13.5px] text-muted">
            {opportunity.host_name}
            <span className="mx-2 text-rule-strong">/</span>
            {locationText(opportunity)}
          </p>
        </div>
        <div className="col-start-2 flex items-baseline gap-2 md:col-start-auto md:block">
          <span className="text-[12px] text-muted md:block">Deadline</span>
          <span className={`text-[14px] text-ink ${deadlineIsDate(opportunity) ? "num" : ""}`}>{deadline.label}</span>
          {deadline.relative && (
            <span className={`text-[12.5px] md:block ${deadline.state === "soon" ? "font-medium text-persimmon-deep" : "text-muted"}`}>{deadline.relative}</span>
          )}
        </div>
        <div className="col-start-2 flex items-center justify-between gap-3 md:col-start-auto md:flex-col md:items-end md:justify-center md:gap-1.5">
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
            <span className="hidden items-center gap-1 text-[13px] text-muted group-hover:text-ink md:inline-flex">
              View rules
              <ArrowUpRight size={14} />
            </span>
          )}
        </div>
      </Link>
    </motion.li>
  );
}

export function RowSkeleton() {
  return (
    <li className="grid grid-cols-[auto_minmax(0,1fr)] gap-4 py-5 md:grid-cols-[auto_minmax(0,1fr)_150px_170px]">
      <div className="skeleton size-[52px] rounded-[10px]" />
      <div className="flex flex-col gap-2">
        <div className="skeleton h-3 w-24" />
        <div className="skeleton h-5 w-3/4" />
        <div className="skeleton h-3 w-1/3" />
      </div>
      <div className="skeleton hidden h-4 w-24 self-center md:block" />
      <div className="skeleton hidden h-4 w-24 self-center justify-self-end md:block" />
    </li>
  );
}
