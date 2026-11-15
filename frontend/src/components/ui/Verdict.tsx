import { Check, Minus, X } from "lucide-react";
import { motion } from "motion/react";
import type { MatchOutcome, MatchStatus } from "../../api/types";
import { STATUS_LONG } from "../../lib/format";

type Tone = { dot: string; ink: string; wash: string; ring: string; stroke: string };

export const VERDICT_TONE: Record<MatchStatus, Tone> = {
  eligible: { dot: "bg-eligible", ink: "text-eligible-ink", wash: "bg-eligible-wash", ring: "ring-eligible/30", stroke: "var(--color-eligible)" },
  potential_match: { dot: "bg-potential", ink: "text-potential-ink", wash: "bg-potential-wash", ring: "ring-potential/35", stroke: "var(--color-potential)" },
  not_eligible: { dot: "bg-ineligible", ink: "text-ineligible-ink", wash: "bg-ineligible-wash", ring: "ring-ineligible/30", stroke: "var(--color-ineligible)" },
  needs_review: { dot: "bg-review", ink: "text-review-ink", wash: "bg-review-wash", ring: "ring-review/30", stroke: "var(--color-review)" },
};

/** One sentence per verdict, mirroring the engine's rollup order. */
export const VERDICT_MEANING: Record<MatchStatus, string> = {
  eligible: "Every published rule was checked against your profile and met.",
  potential_match: "Nothing rules you out, but a fact the rules need is missing from your profile.",
  not_eligible: "At least one mandatory rule is not met by your profile.",
  needs_review: "Nothing checked rules you out, but at least one condition needs a human to confirm it.",
};

/** What a verdict is not: the engine never stands in for the organization's decision. */
export const VERDICT_SCOPE =
  "A verdict compares your profile with the published rules. It isn’t an admission, award or approval: the organization makes that decision.";

/**
 * Legend symbols, shape-coded so colour is never the only signal:
 * eligible ● disc, potential ◐ half disc, not eligible ⊗ crossed circle,
 * needs review ◇ diamond.
 */
export function VerdictMark({ status, size = 14 }: { status: MatchStatus; size?: number }) {
  const color = VERDICT_TONE[status].stroke;
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden="true" className="shrink-0">
      {status === "eligible" && <circle cx="8" cy="8" r="6.5" fill={color} />}
      {status === "potential_match" && (
        <>
          <circle cx="8" cy="8" r="6" fill="none" stroke={color} strokeWidth="1.8" />
          <path d="M8 2a6 6 0 0 1 0 12z" fill={color} />
        </>
      )}
      {status === "not_eligible" && (
        <>
          <circle cx="8" cy="8" r="6" fill="none" stroke={color} strokeWidth="1.8" />
          <path d="m5.4 5.4 5.2 5.2m0-5.2-5.2 5.2" stroke={color} strokeWidth="1.8" strokeLinecap="round" />
        </>
      )}
      {status === "needs_review" && <path d="M8 1.8 14.2 8 8 14.2 1.8 8z" fill="none" stroke={color} strokeWidth="1.8" strokeLinejoin="round" />}
    </svg>
  );
}

/** A verdict as a legend entry: symbol plus words, no pill. */
export function VerdictBadge({
  status,
  size = "md",
  animateKey,
}: {
  status: MatchStatus;
  size?: "sm" | "md" | "lg";
  /** Change this to replay the arrival animation (e.g. when the verdict changes). */
  animateKey?: string | number;
}) {
  const tone = VERDICT_TONE[status];
  const text = size === "lg" ? "text-[17px]" : size === "sm" ? "text-[13px]" : "text-[14px]";
  return (
    <motion.span
      key={animateKey ?? status}
      initial={animateKey ? { opacity: 0, y: 4 } : false}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      className={`inline-flex shrink-0 items-center gap-1.5 font-semibold ${tone.ink} ${text}`}
    >
      <VerdictMark status={status} size={size === "lg" ? 17 : 13} />
      {STATUS_LONG[status]}
    </motion.span>
  );
}

export function UncheckedBadge({ label = "Not checked" }: { label?: string }) {
  return (
    <span className="inline-flex shrink-0 items-center gap-1.5 text-[13px] text-faint">
      <svg width="13" height="13" viewBox="0 0 16 16" aria-hidden="true">
        <circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="2.4 2.2" />
      </svg>
      {label}
    </span>
  );
}

const OUTCOME_STYLE: Record<MatchOutcome, { className: string; label: string }> = {
  met: { className: "bg-eligible text-paper", label: "Met" },
  not_met: { className: "bg-ineligible text-paper", label: "Not met" },
  unknown: { className: "bg-potential-wash text-potential-ink ring-1 ring-inset ring-potential/50", label: "Missing from your profile" },
  needs_review: { className: "bg-review-wash text-review-ink ring-1 ring-inset ring-review/40", label: "Needs your review" },
};

/** Rule-level outcome, sized for a line of text. */
export function OutcomeMark({ outcome, size = 20 }: { outcome: MatchOutcome | "pending"; size?: number }) {
  if (outcome === "pending") {
    return (
      <span
        className="inline-flex shrink-0 items-center justify-center rounded-full text-faint ring-1 ring-inset ring-rule-strong"
        style={{ width: size, height: size }}
        aria-label="Not checked yet"
      >
        <Minus size={size * 0.55} strokeWidth={2.4} />
      </span>
    );
  }
  const { className, label } = OUTCOME_STYLE[outcome];
  return (
    <span className={`inline-flex shrink-0 items-center justify-center rounded-full ${className}`} style={{ width: size, height: size }} role="img" aria-label={label}>
      {outcome === "met" && <Check size={size * 0.6} strokeWidth={2.8} />}
      {outcome === "not_met" && <X size={size * 0.6} strokeWidth={2.8} />}
      {outcome === "unknown" && <span className="font-mono text-[0.62em] font-semibold leading-none">?</span>}
      {outcome === "needs_review" && (
        <svg width={size * 0.5} height={size * 0.5} viewBox="0 0 10 10" aria-hidden="true">
          <path d="M5 1 9 5 5 9 1 5z" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
        </svg>
      )}
    </span>
  );
}

export const OUTCOME_TEXT: Record<MatchOutcome, string> = {
  met: "Met",
  not_met: "Not met",
  unknown: "Missing",
  needs_review: "Your review",
};
