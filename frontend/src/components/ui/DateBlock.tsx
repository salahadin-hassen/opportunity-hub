import type { Opportunity } from "../../api/types";
import { deadlineInfo } from "../../lib/format";

/**
 * A deadline set like a calendar leaf: month, day, year. Deadlines are what
 * people compare first, so listings lead with them. Open-ended deadlines say
 * what they are ("Rolling", "No date") instead of inventing a date.
 */
export function DateBlock({ opportunity, size = "md" }: { opportunity: Pick<Opportunity, "deadline_at" | "deadline_type">; size?: "sm" | "md" }) {
  const info = deadlineInfo(opportunity);
  const box = size === "sm" ? "w-[52px] h-[58px]" : "w-[60px] h-[68px]";
  const urgent = info.state === "soon";
  const edge = urgent ? "border-persimmon bg-paper shadow-[inset_0_0_0_1px_var(--color-persimmon)]" : info.state === "closed" ? "border-rule bg-cream" : "border-rule-strong bg-paper";
  if (opportunity.deadline_at && (info.state === "open" || info.state === "soon" || info.state === "closed")) {
    const date = new Date(opportunity.deadline_at);
    const month = date.toLocaleDateString("en-GB", { month: "short" });
    const day = date.toLocaleDateString("en-GB", { day: "numeric" });
    const year = date.getFullYear();
    return (
      <span className={`date-leaf flex shrink-0 flex-col items-center justify-center rounded-[10px] border ${edge} ${box}`} aria-hidden="true">
        <span className={`text-[10.5px] font-semibold uppercase leading-none tracking-[0.08em] ${urgent ? "text-persimmon-deep" : "text-muted"}`}>{month}</span>
        <span className={`num font-display font-semibold leading-none tracking-[-0.03em] ${size === "sm" ? "mt-1 text-[22px]" : "mt-1.5 text-[26px]"} ${info.state === "closed" ? "text-muted line-through decoration-1" : "text-ink"}`}>
          {day}
        </span>
        <span className="num mt-1 text-[10.5px] leading-none text-muted">{year}</span>
      </span>
    );
  }
  const word = info.state === "rolling" ? "Rolling" : info.state === "none" ? "Open" : "No date";
  return (
    <span className={`date-leaf flex shrink-0 flex-col items-center justify-center rounded-[10px] border border-dashed border-rule-strong bg-transparent px-1 text-center ${box}`} aria-hidden="true">
      <span className="text-[11px] font-semibold leading-tight text-ink-soft">{word}</span>
    </span>
  );
}
