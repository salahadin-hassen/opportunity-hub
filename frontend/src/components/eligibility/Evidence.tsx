import { AnimatePresence, motion } from "motion/react";
import { ChevronDown, ExternalLink, Quote } from "lucide-react";
import { useId, useState } from "react";
import { Link } from "react-router";
import type { Match, MatchOutcome, MatchRow, PublicRequirement, PublicSource } from "../../api/types";
import { formatDate } from "../../lib/format";
import { FACT_NOUNS, describeActual, describeRule, factsForRow, factsForRule, reviewReason, type Fact } from "../../lib/rules";
import { OUTCOME_TEXT, OutcomeMark } from "../ui/Verdict";

/** Where in the profile each engine fact is edited. */
export const FACT_ANCHOR: Record<Fact, string> = {
  gpa: "/profile#education",
  date_of_birth: "/profile#identity",
  citizenship: "/profile#identity",
  enrollment: "/profile#academic",
  degree_level: "/profile#academic",
  skills: "/profile#skills",
};

type RuleView = {
  id: string;
  label: string;
  /** The rule in words, from the published kind/params when available. */
  rule: string | null;
  quote: string | null;
  sourceId: string | null;
  /** Curator's note on why an unparsed rule can't be checked. */
  unparsedReason: string | null;
  isMandatory: boolean;
  row: MatchRow | null;
  previousOutcome: MatchOutcome | null;
};

function curatorReason(requirement: PublicRequirement | undefined): string | null {
  if (!requirement || requirement.kind !== "unparsed") return null;
  const reason = (requirement.params as { reason?: unknown }).reason;
  return typeof reason === "string" ? reason : null;
}

/** Merge the published rules with a match's evidence rows, in published order. */
export function buildRuleViews(
  requirements: PublicRequirement[] | undefined,
  match: Match | undefined,
  previous: Match | undefined,
): RuleView[] {
  const rows = new Map((match?.requirements ?? []).map((row) => [row.requirement_id, row]));
  const before = new Map((previous?.requirements ?? []).map((row) => [row.requirement_id, row.outcome]));
  if (requirements) {
    return [...requirements]
      .sort((a, b) => a.order_index - b.order_index)
      .map((requirement) => ({
        id: requirement.id,
        label: requirement.label,
        rule: describeRule(requirement.kind, requirement.params),
        quote: requirement.source_quote,
        sourceId: requirement.source_id,
        unparsedReason: curatorReason(requirement),
        isMandatory: requirement.is_mandatory,
        row: rows.get(requirement.id) ?? null,
        previousOutcome: before.get(requirement.id) ?? null,
      }));
  }
  return (match?.requirements ?? []).map((row) => ({
    id: row.requirement_id,
    label: row.requirement.label,
    rule: row.requirement.kind === "unparsed" ? null : describeRule(row.requirement.kind, row.expected),
    quote: row.requirement.source_quote,
    sourceId: row.requirement.source_id,
    unparsedReason: null,
    isMandatory: row.requirement.is_mandatory,
    row,
    previousOutcome: before.get(row.requirement_id) ?? null,
  }));
}

function missingFacts(view: RuleView): Fact[] {
  if (view.row) return factsForRow(view.row);
  return [];
}

/** The plain-language "why" for one evaluated rule. */
function explanation(view: RuleView): string | null {
  const row = view.row;
  if (!row) return view.unparsedReason ? `Not machine-checkable: ${view.unparsedReason}` : null;
  switch (row.outcome) {
    case "met":
      return "Your profile meets this rule.";
    case "not_met":
      return view.isMandatory
        ? "Your profile doesn’t meet this rule, and it’s mandatory, so it rules this opportunity out."
        : "Your profile doesn’t meet this rule. It isn’t mandatory, so it doesn’t decide the verdict on its own.";
    case "unknown": {
      const facts = missingFacts(view);
      const names = facts.map((fact) => FACT_NOUNS[fact]).join(" and ");
      return names
        ? `Your profile has no ${names}, so this rule can’t be checked yet. Add it and re-run the check.`
        : "A fact this rule needs is missing from your profile.";
    }
    case "needs_review":
      if (row.reason_code === "unsupported_requirement_kind" && view.unparsedReason) {
        return `This condition isn’t machine-checkable: ${view.unparsedReason.replace(/\.$/, "")}. Read the official wording and decide.`;
      }
      return reviewReason(row) ?? "This rule needs a human to confirm it.";
  }
}

const ROW_ACCENT: Record<MatchOutcome, string> = {
  met: "",
  not_met: "bg-ineligible-wash/50",
  unknown: "bg-potential-wash/50",
  needs_review: "",
};

export function EvidenceRow({
  view,
  source,
  defaultQuoteOpen = false,
  number,
  flush = false,
}: {
  view: RuleView;
  source?: PublicSource;
  defaultQuoteOpen?: boolean;
  /** Footnote number shared by the rule and its official wording. */
  number: number;
  /** No side padding, for rows set directly on the page rather than in a card. */
  flush?: boolean;
}) {
  const [quoteOpen, setQuoteOpen] = useState(defaultQuoteOpen);
  const quoteId = useId();
  const row = view.row;
  const actual = row ? describeActual(row) : null;
  const changed = row && view.previousOutcome && view.previousOutcome !== row.outcome;
  const facts = row?.outcome === "unknown" ? missingFacts(view) : [];
  const why = explanation(view);

  return (
    <motion.li
      layout="position"
      className={`relative py-5 ${flush ? "sm:px-3" : "px-4 sm:px-5"} ${row ? ROW_ACCENT[row.outcome] : ""}`}
      initial={changed ? { backgroundColor: "rgba(101,120,255,0.12)" } : false}
      animate={changed ? { backgroundColor: "rgba(101,120,255,0)" } : undefined}
      transition={{ duration: 1.6, ease: "easeOut" }}
    >
      <div className="flex gap-3.5">
        <div className="pt-0.5">
          <AnimatePresence mode="wait" initial={false}>
            <motion.span
              key={row?.outcome ?? "pending"}
              initial={{ scale: 0.6, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.6, opacity: 0 }}
              transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
              className="inline-flex"
            >
              <OutcomeMark outcome={row?.outcome ?? "pending"} />
            </motion.span>
          </AnimatePresence>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <p className="heading text-[17.5px] text-ink">
              {view.label}
              {view.quote && <sup className="num ml-0.5 text-[10.5px] font-normal text-cobalt-deep">[{number}]</sup>}
            </p>
            {!view.isMandatory && <span className="text-[12px] text-muted">Optional</span>}
            {changed && (
              <span className="rounded-full bg-cobalt-wash px-2 py-0.5 text-[11.5px] font-medium text-cobalt-deep">
                Was {OUTCOME_TEXT[view.previousOutcome!].toLowerCase()}, now {OUTCOME_TEXT[row.outcome].toLowerCase()}
              </span>
            )}
          </div>

          {view.rule && (
            <dl className="mt-2.5 grid grid-cols-1 gap-x-6 gap-y-2 text-[13px] sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
              <div className="min-w-0">
                <dt className="text-muted">Required</dt>
                <dd className="num mt-0.5 break-words text-[12.5px] text-ink">{view.rule ?? "Stated only in the official wording"}</dd>
              </div>
              {row && (
                <div className="min-w-0">
                  <dt className="text-muted">Your profile</dt>
                  <dd
                    className={`num mt-0.5 break-words text-[12.5px] ${
                      row.outcome === "unknown" ? "text-potential-ink" : row.outcome === "not_met" ? "text-ineligible-ink" : "text-ink"
                    }`}
                  >
                    {actual ?? (row.outcome === "needs_review" ? "Not evaluated" : "—")}
                  </dd>
                </div>
              )}
            </dl>
          )}

          {why && <p className="mt-2.5 max-w-[68ch] text-[13.5px] leading-relaxed text-muted">{why}</p>}

          <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-2">
            {facts.length > 0 && (
              <Link to={FACT_ANCHOR[facts[0]!]} className="text-[13px] font-medium text-cobalt-deep hover:underline">
                Add your {FACT_NOUNS[facts[0]!]}
              </Link>
            )}
            {view.quote && (
              <button
                type="button"
                className="inline-flex items-center gap-1.5 text-[13px] text-muted hover:text-ink"
                aria-expanded={quoteOpen}
                aria-controls={quoteId}
                onClick={() => setQuoteOpen((open) => !open)}
              >
                <Quote size={13} />
                Official wording [{number}]
                <ChevronDown size={14} className={`transition-transform duration-200 ${quoteOpen ? "rotate-180" : ""}`} />
              </button>
            )}
          </div>

          <AnimatePresence initial={false}>
            {quoteOpen && view.quote && (
              <motion.div
                id={quoteId}
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
                className="overflow-hidden"
              >
                <figure className="mt-3 grid grid-cols-[40px_minmax(0,1fr)] rounded-[10px] bg-paper/70 py-3 pr-4 ring-1 ring-inset ring-rule">
                  <span className="num pl-3 text-[11px] text-cobalt-deep">[{number}]</span>
                  <blockquote className="text-[14px] italic leading-relaxed text-ink">“{view.quote}”</blockquote>
                  {source && (
                    <figcaption className="col-start-2 mt-1.5 flex flex-wrap items-center gap-x-3 text-[12px] text-muted">
                      <a href={source.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-ink">
                        {source.publisher ?? new URL(source.url).hostname}
                        <ExternalLink size={11} />
                      </a>
                      <span>Retrieved {formatDate(source.retrieved_at)}</span>
                    </figcaption>
                  )}
                </figure>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </motion.li>
  );
}

export function EvidenceList({
  requirements,
  match,
  previous,
  sources,
  quotesOpen = false,
  flush = false,
}: {
  requirements?: PublicRequirement[];
  match?: Match;
  previous?: Match;
  sources?: PublicSource[];
  quotesOpen?: boolean;
  flush?: boolean;
}) {
  const views = buildRuleViews(requirements, match, previous);
  const sourceById = new Map((sources ?? []).map((source) => [source.id, source]));
  if (views.length === 0) {
    return <p className="px-5 py-6 text-[14px] text-muted">No eligibility rules have been published for this opportunity yet.</p>;
  }
  return (
    <ol className="divide-y divide-rule">
      {views.map((view, index) => (
        <EvidenceRow
          number={index + 1}
          flush={flush}
          key={view.id}
          view={view}
          source={view.sourceId ? sourceById.get(view.sourceId) : undefined}
          defaultQuoteOpen={quotesOpen}
        />
      ))}
    </ol>
  );
}

/** Facts a published rule reads, for showing which profile fields matter before any check. */
export function ruleFacts(requirements: PublicRequirement[]): Fact[] {
  return [...new Set(requirements.flatMap((requirement) => factsForRule(requirement.kind, requirement.params)))];
}
