import { motion } from "motion/react";
import { Link } from "react-router";
import type { Match, Opportunity } from "../../api/types";
import { TYPE_LABELS, deadlineInfo, deadlineIsDate } from "../../lib/format";
import { VerdictBadge } from "../ui/Verdict";
import { locationText } from "./OpportunityRow";
import { TYPE_STYLE, monogram } from "./TypeTile";

/**
 * An opportunity as a postcard: a typographic cover in the type's colour
 * (host monogram, type, place) over the facts that matter: name, host, deadline.
 * Everything shown comes from the API.
 */
export function Postcard({ opportunity, match, className = "", cover = "tall" }: { opportunity: Opportunity; match?: Match; className?: string; cover?: "tall" | "short" }) {
  const style = TYPE_STYLE[opportunity.opportunity_type];
  const Icon = style.icon;
  const deadline = deadlineInfo(opportunity);
  return (
    <motion.article whileHover={{ y: -4 }} transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }} className={`group relative ${className}`}>
      <Link to={`/opportunities/${opportunity.id}`} className="block rounded-panel focus-visible:outline-offset-4">
        <div className={`relative flex ${cover === "tall" ? "aspect-[5/4]" : "aspect-[2/1]"} flex-col justify-between overflow-hidden rounded-panel p-5 ${style.tile} ${style.text}`}>
          <div className="flex items-start justify-between">
            <span className="font-display text-[44px] font-bold leading-none tracking-[-0.05em]">{monogram(opportunity.host_name)}</span>
            <Icon size={22} className={style.accent} strokeWidth={1.8} />
          </div>
          <div>
            <p className={`text-[12.5px] font-semibold ${style.accent}`}>{TYPE_LABELS[opportunity.opportunity_type]}</p>
            <p className="mt-0.5 text-[13px] opacity-80">{locationText(opportunity)}</p>
          </div>
          <span
            aria-hidden="true"
            className="pointer-events-none absolute -bottom-10 -right-6 font-display text-[150px] font-bold leading-none tracking-[-0.08em] opacity-[0.08] transition-transform duration-500 group-hover:-translate-x-2"
          >
            {monogram(opportunity.host_name)}
          </span>
        </div>
        <div className="px-1 pt-3.5">
          <h3 className="heading text-[18px] text-ink decoration-1 underline-offset-4 group-hover:underline">{opportunity.title}</h3>
          <p className="mt-1 line-clamp-1 text-[13.5px] text-muted">{opportunity.host_name}</p>
          <div className="mt-2.5 flex items-center justify-between gap-3 text-[13px]">
            <span className="text-ink-soft">
              <span className="text-muted">Deadline </span>
              <span className={deadlineIsDate(opportunity) ? "num text-ink" : "text-ink"}>{deadline.label}</span>
            </span>
            {match && <VerdictBadge status={match.status} size="sm" />}
          </div>
        </div>
      </Link>
    </motion.article>
  );
}

export function PostcardSkeleton() {
  return (
    <div>
      <div className="skeleton aspect-[5/4] w-full rounded-panel" />
      <div className="skeleton mt-3.5 h-5 w-3/4" />
      <div className="skeleton mt-2 h-3.5 w-1/2" />
    </div>
  );
}
