import { AnimatePresence, motion, useReducedMotion, useScroll, useTransform } from "motion/react";
import { ArrowLeft, ArrowRight, ArrowUpRight } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { useOpportunities, useOpportunity } from "../api/queries";
import type { MatchOutcome, MatchStatus, OpportunityDetail, OpportunityType } from "../api/types";
import { Page } from "../components/layout/Page";
import { EngineStory } from "../components/marketing/EngineStory";
import { MarketingFooter, MarketingNav } from "../components/marketing/MarketingChrome";
import { Postcard, PostcardSkeleton } from "../components/opportunities/Postcard";
import { TYPE_STYLE } from "../components/opportunities/TypeTile";
import { Credit, Plate } from "../components/ui/Plate";
import { ErrorState } from "../components/ui/States";
import { OutcomeMark, VERDICT_MEANING, VERDICT_SCOPE, VerdictMark } from "../components/ui/Verdict";
import { STATUS_LONG, TYPE_PLURALS, deadlineInfo, formatDate } from "../lib/format";
import { PHOTOS } from "../lib/photos";
import { describeRule } from "../lib/rules";

const EASE = [0.22, 1, 0.36, 1] as const;

/** A headline line that rises out of its own mask. */
function Line({ children, delay }: { children: React.ReactNode; delay: number }) {
  const reduced = useReducedMotion();
  return (
    <span className="block overflow-hidden pb-[0.06em]">
      <motion.span
        className="block"
        initial={reduced ? false : { y: "105%" }}
        animate={{ y: "0%" }}
        transition={{ duration: 0.9, delay, ease: [0.65, 0, 0.35, 1] }}
      >
        {children}
      </motion.span>
    </span>
  );
}

function Hero() {
  const opportunities = useOpportunities();
  const reduced = useReducedMotion();
  const plateRef = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: plateRef, offset: ["start end", "end start"] });
  const drift = useTransform(scrollYProgress, [0, 1], reduced ? ["0%", "0%"] : ["-6%", "6%"]);
  const count = opportunities.data?.length;
  const telescope = PHOTOS.telescope;

  return (
    <section className="relative pt-[104px] sm:pt-[120px]">
      <div className="mx-auto max-w-[1320px] px-5 sm:px-8">
        <h1 className="display text-[clamp(56px,11.2vw,172px)] text-ink">
          <Line delay={0.05}>There’s more</Line>{" "}
          <Line delay={0.15}>
            out there{" "}
            <motion.span
              className="relative mx-[0.12em] inline-block h-[0.74em] translate-y-[0.06em] overflow-hidden rounded-full align-baseline"
              initial={reduced ? false : { width: 0 }}
              animate={{ width: "1.9em" }}
              transition={{ duration: 1, delay: 0.75, ease: [0.65, 0, 0.35, 1] }}
              style={reduced ? { width: "1.9em" } : undefined}
            >
              <img
                src={telescope.small}
                srcSet={`${telescope.small} 800w, ${telescope.large} 1600w`}
                sizes="30vw"
                alt=""
                fetchPriority="high"
                className="absolute inset-0 h-full w-full object-cover object-[30%_40%]"
              />
            </motion.span>
          </Line>{" "}
          <Line delay={0.25}>for you.</Line>
        </h1>

        <div className="mt-10 grid grid-cols-1 gap-10 pb-20 lg:mt-14 lg:grid-cols-12 lg:gap-8 lg:pb-28">
          <motion.div
            className="lg:col-span-5 lg:pt-2 lg:pr-10"
            initial={reduced ? false : { opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.55, ease: EASE }}
          >
            <p className="max-w-[36ch] text-[19px] leading-[1.5] text-ink-soft">
              Discover scholarships, internships and research programs worth your ambition, and know where you stand before you write a
              single application.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/opportunities" className="btn btn-primary btn-lg">
                Explore opportunities
              </Link>
              <Link to="/register" className="btn btn-quiet btn-lg">
                Check my eligibility
              </Link>
            </div>
            <p className="mt-8 flex items-center gap-2.5 text-[14px] text-ink-soft">
              <span className="inline-flex size-2.5 rounded-full bg-persimmon" aria-hidden="true" />
              {count === undefined ? "Loading open programs" : `${count} programs open now, each with its official rules quoted`}
            </p>
          </motion.div>

          <div ref={plateRef} className="relative lg:col-span-7">
            <figure>
              <div className="relative overflow-hidden rounded-plate bg-sand" style={{ aspectRatio: "16 / 10" }}>
                <motion.img
                  src={PHOTOS.campusPath.small}
                  srcSet={`${PHOTOS.campusPath.small} 800w, ${PHOTOS.campusPath.large} 1600w`}
                  sizes="(min-width: 1024px) 60vw, 100vw"
                  alt={PHOTOS.campusPath.alt}
                  fetchPriority="high"
                  className="absolute inset-x-0 -top-[8%] h-[116%] w-full object-cover"
                  style={{ y: drift }}
                  initial={reduced ? false : { clipPath: "inset(100% 0 0 0)" }}
                  animate={{ clipPath: "inset(0% 0 0 0)" }}
                  transition={{ duration: 1.2, delay: 0.35, ease: [0.65, 0, 0.35, 1] }}
                />
              </div>
              <figcaption className="mt-2.5 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-[12.5px] text-muted">
                <span>
                  <span className="num mr-2 text-ink">Pl. 1</span>
                  {PHOTOS.campusPath.caption}
                </span>
                <Credit photo="campusPath" />
              </figcaption>
            </figure>
            <motion.div
              initial={reduced ? false : { scale: 0.6, rotate: -30, opacity: 0 }}
              animate={{ scale: 1, rotate: -9, opacity: 1 }}
              transition={{ duration: 0.8, delay: 1.2, ease: EASE }}
              className="absolute -top-14 right-6 z-10 hidden size-[132px] items-center justify-center rounded-full bg-persimmon p-5 text-center font-display text-[15px] font-bold leading-[1.1] tracking-[-0.02em] text-night sm:flex"
            >
              Every rule from its official page
            </motion.div>
            <p className="mt-1 text-right text-[12px] text-faint">
              Headline photo: {telescope.caption}. <Credit photo="telescope" />
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

const STRIP_TYPES: (OpportunityType | null)[] = [null, "scholarship", "internship", "research_program", "fellowship", "open_source_program", "other"];

function OpenNow() {
  const opportunities = useOpportunities();
  const [type, setType] = useState<OpportunityType | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const all = opportunities.data ?? [];
  const present = new Set(all.map((item) => item.opportunity_type));
  const items = useMemo(
    () => [...all].filter((item) => !type || item.opportunity_type === type).sort((a, b) => deadlineInfo(a).sortKey - deadlineInfo(b).sortKey),
    [all, type],
  );
  const scrollBy = (direction: 1 | -1) => scroller.current?.scrollBy({ left: direction * 340, behavior: "smooth" });

  return (
    <section aria-labelledby="open-now" className="border-t border-rule bg-paper py-20 sm:py-28">
      <div className="mx-auto max-w-[1320px] px-5 sm:px-8">
        <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
          <h2 id="open-now" className="display max-w-[12ch] text-[48px] text-ink sm:text-[72px]">
            Open right now.
          </h2>
          <div className="flex items-center gap-3">
            <button type="button" onClick={() => scrollBy(-1)} className="btn btn-quiet size-11 px-0" aria-label="Scroll back">
              <ArrowLeft size={18} />
            </button>
            <button type="button" onClick={() => scrollBy(1)} className="btn btn-quiet size-11 px-0" aria-label="Scroll forward">
              <ArrowRight size={18} />
            </button>
            <Link to="/opportunities" className="btn btn-ink ml-2">
              Browse all
            </Link>
          </div>
        </div>

        <div role="group" aria-label="Filter by type" className="-mx-5 mt-10 flex gap-6 overflow-x-auto border-b border-rule px-5 sm:mx-0 sm:px-0">
          {STRIP_TYPES.filter((key) => key === null || present.has(key)).map((key) => {
            const active = type === key;
            const Icon = key ? TYPE_STYLE[key].icon : null;
            return (
              <button
                key={key ?? "all"}
                type="button"
                aria-pressed={active}
                onClick={() => setType(key)}
                className={`relative flex shrink-0 items-center gap-2 pb-3.5 pt-1 text-[14.5px] transition-colors ${active ? "font-semibold text-ink" : "text-muted hover:text-ink"}`}
              >
                {Icon && <Icon size={17} strokeWidth={active ? 2.2 : 1.7} />}
                {key ? TYPE_PLURALS[key] : "Everything"}
                {active && <motion.span layoutId="open-now-tab" className="absolute inset-x-0 -bottom-px h-[2px] bg-ink" transition={{ duration: 0.3, ease: EASE }} />}
              </button>
            );
          })}
        </div>

        {opportunities.isError ? (
          <div className="mt-10">
            <ErrorState message="Opportunities couldn’t load from the API." onRetry={() => opportunities.refetch()} />
          </div>
        ) : (
          <div ref={scroller} className="-mx-5 mt-10 flex snap-x snap-mandatory gap-6 overflow-x-auto scroll-smooth px-5 pb-4 [scrollbar-width:none] sm:mx-0 sm:px-0">
            {opportunities.isPending
              ? Array.from({ length: 4 }, (_, index) => (
                  <div key={index} className="w-[280px] shrink-0 sm:w-[300px]">
                    <PostcardSkeleton />
                  </div>
                ))
              : items.map((item) => (
                  <motion.div key={item.id} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="w-[280px] shrink-0 snap-start sm:w-[300px]">
                    <Postcard opportunity={item} />
                  </motion.div>
                ))}
          </div>
        )}
      </div>
    </section>
  );
}

function Difference() {
  return (
    <section aria-labelledby="different" className="bg-ivory py-20 sm:py-32">
      <div className="mx-auto grid max-w-[1320px] grid-cols-1 gap-12 px-5 sm:px-8 lg:grid-cols-12 lg:gap-8">
        <div className="lg:col-span-7">
          <Plate photo="readingRoom" number="Pl. 2" ratio={4 / 3.4} sizes="(min-width: 1024px) 55vw, 100vw" />
        </div>
        <div className="flex flex-col justify-center lg:col-span-5 lg:pl-8">
          <h2 id="different" className="display text-[44px] text-ink sm:text-[60px]">
            A list says what exists. We say where you stand.
          </h2>
          <dl className="mt-10 flex flex-col gap-7">
            {[
              ["Rules from the source", "Eligibility is copied from each official page, word for word, and kept beside the rule it became."],
              ["Checked against you", "Your profile is compared with every rule, one at a time, so a verdict is never a vibe."],
              ["Honest about gaps", "If a fact is missing or a condition needs a human, we say so plainly instead of guessing."],
            ].map(([title, text]) => (
              <div key={title} className="grid grid-cols-[18px_minmax(0,1fr)] gap-x-4">
                <span className="mt-[9px] size-2.5 rounded-full bg-persimmon" aria-hidden="true" />
                <div>
                  <dt className="heading text-[21px] text-ink">{title}</dt>
                  <dd className="mt-1.5 text-[15.5px] text-ink-soft">{text}</dd>
                </div>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </section>
  );
}

function Engine() {
  return (
    <section id="engine" aria-labelledby="engine-title" className="scroll-mt-16 bg-cream py-20 sm:py-32">
      <div className="mx-auto max-w-[1320px] px-5 sm:px-8">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          <h2 id="engine-title" className="display text-[48px] text-ink sm:text-[76px] lg:col-span-8">
            How one rule becomes a clear answer.
          </h2>
          <p className="max-w-[40ch] self-end text-[16px] text-ink-soft lg:col-span-4">
            The eligibility engine is deterministic: no guessing and no scoring. Here it is on a real opportunity’s published rules.
          </p>
        </div>
        <div className="mt-14">
          <EngineStory />
        </div>
      </div>
    </section>
  );
}

const ROUTE = [
  { title: "Make a profile", text: "Three short steps. Each field says whether rules actually read it." },
  { title: "Run one check", text: "Every open program is evaluated against you, with live progress." },
  { title: "Read the evidence", text: "Each verdict lists the rules, your facts and the official wording." },
  { title: "Fill a gap", text: "Add a missing fact and the affected programs are checked again." },
];

function HowItWorks() {
  return (
    <section id="how-it-works" aria-labelledby="how-title" className="scroll-mt-16 bg-ivory py-20 sm:py-32">
      <div className="mx-auto grid max-w-[1320px] grid-cols-1 gap-12 px-5 sm:px-8 lg:grid-cols-12 lg:gap-8">
        <div className="lg:col-span-4">
          <h2 id="how-title" className="display text-[48px] text-ink sm:text-[64px]">
            Four steps, about two minutes.
          </h2>
          <div className="mt-10 hidden lg:block">
            <Plate photo="spiral" number="Pl. 3" ratio={1} sizes="30vw" />
          </div>
        </div>
        <ol className="lg:col-span-7 lg:col-start-6">
          {ROUTE.map((step, index) => (
            <li key={step.title} className="grid grid-cols-[auto_minmax(0,1fr)] items-baseline gap-x-6 border-t border-ink py-8 last:border-b sm:gap-x-10">
              <span className="display text-[64px] text-persimmon sm:text-[96px]" aria-hidden="true">
                {index + 1}
              </span>
              <div>
                <h3 className="heading text-[26px] text-ink sm:text-[32px]">
                  <span className="sr-only">Step {index + 1}: </span>
                  {step.title}
                </h3>
                <p className="mt-2 max-w-[42ch] text-[16px] text-ink-soft">{step.text}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

const LEGEND: { status: MatchStatus; order: string }[] = [
  { status: "eligible", order: "When every rule is met" },
  { status: "potential_match", order: "When a fact is missing" },
  { status: "needs_review", order: "When a person must confirm" },
  { status: "not_eligible", order: "When a mandatory rule fails" },
];

function Legend() {
  return (
    <section aria-labelledby="legend-title" className="bg-night py-20 text-snow sm:py-28">
      <div className="mx-auto max-w-[1320px] px-5 sm:px-8">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <h2 id="legend-title" className="display text-[48px] sm:text-[72px]">
            The legend.
          </h2>
          <p className="max-w-[44ch] text-[15.5px] text-snow/75">
            Four possible answers, each with its own symbol. A hard “no” is checked first, then anything needing review, then missing facts.
          </p>
        </div>
        <ul className="mt-14 grid grid-cols-1 border-t border-snow/20 sm:grid-cols-2 lg:grid-cols-4">
          {LEGEND.map(({ status, order }) => (
            <li key={status} className="border-b border-snow/20 py-8 sm:pr-8 lg:border-b-0 lg:border-r lg:px-8 lg:first:pl-0 lg:last:border-r-0">
              <span className="inline-flex size-14 items-center justify-center rounded-full bg-snow">
                <VerdictMark status={status} size={28} />
              </span>
              <p className="heading mt-6 text-[26px] text-snow">{STATUS_LONG[status]}</p>
              <p className="mt-1 text-[13px] text-lime">{order}</p>
              <p className="mt-4 text-[15px] leading-relaxed text-snow/75">{VERDICT_MEANING[status]}</p>
            </li>
          ))}
        </ul>
        <p className="mt-10 max-w-[70ch] border-l-2 border-lime pl-4 text-[15px] text-snow/85">{VERDICT_SCOPE}</p>
      </div>
    </section>
  );
}

function FootnotedOpportunity({ detail }: { detail: OpportunityDetail }) {
  const rules = [...detail.requirements].sort((a, b) => a.order_index - b.order_index);
  const source = detail.sources.find((item) => item.is_primary) ?? detail.sources[0];
  return (
    <article className="flex flex-col">
      <p className="kicker">{detail.host_name}</p>
      <h3 className="heading mt-2 text-[28px] text-ink sm:text-[34px]">
        <Link to={`/opportunities/${detail.id}`} className="decoration-1 underline-offset-4 hover:underline">
          {detail.title}
        </Link>
      </h3>
      <ol className="mt-6 flex flex-col gap-3">
        {rules.map((rule, index) => (
          <li key={rule.id} className="flex gap-3 text-[16px] text-ink">
            <span className="mt-2 size-1.5 shrink-0 rounded-full bg-ink" aria-hidden="true" />
            <span>
              {rule.label}
              <sup className="num ml-0.5 text-[10.5px] text-cobalt-deep">[{index + 1}]</sup>
              {rule.kind === "unparsed" ? (
                <span className="ml-2 text-[13px] text-review-ink">for you to confirm</span>
              ) : (
                <span className="num ml-2 text-[12px] text-muted">{describeRule(rule.kind, rule.params)}</span>
              )}
            </span>
          </li>
        ))}
      </ol>
      <ol className="mt-6 flex flex-col gap-2 border-t border-rule pt-4">
        {rules.map((rule, index) => (
          <li key={rule.id} className="grid grid-cols-[28px_minmax(0,1fr)] text-[13.5px] text-ink-soft">
            <span className="num text-[11px] text-cobalt-deep">[{index + 1}]</span>
            <span className="italic">“{rule.source_quote}”</span>
          </li>
        ))}
      </ol>
      {source && (
        <p className="mt-4 text-[12.5px] text-muted">
          Source:{" "}
          <a href={source.url} target="_blank" rel="noreferrer" className="link">
            {source.publisher ?? new URL(source.url).hostname}
          </a>
          , retrieved {formatDate(source.retrieved_at)}
        </p>
      )}
    </article>
  );
}

function FromTheAtlas() {
  const opportunities = useOpportunities();
  const pick = (slug: string) => opportunities.data?.find((item) => item.slug === slug)?.id;
  const kaust = useOpportunity(pick("kaust-visiting-student-research-program"));
  const gates = useOpportunity(pick("gates-cambridge-scholarship"));
  const details = [kaust.data, gates.data].filter((item): item is OpportunityDetail => Boolean(item));
  return (
    <section aria-labelledby="atlas-title" className="bg-paper py-20 sm:py-32">
      <div className="mx-auto max-w-[1320px] px-5 sm:px-8">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          <h2 id="atlas-title" className="display text-[48px] text-ink sm:text-[72px] lg:col-span-7">
            Every rule comes with its footnote.
          </h2>
          <p className="max-w-[42ch] self-end text-[16px] text-ink-soft lg:col-span-4 lg:col-start-9">
            Two real listings, straight from the API: their rules, and the official sentences those rules were copied from.
          </p>
        </div>
        <div className="mt-14 grid grid-cols-1 gap-16 lg:grid-cols-2 lg:gap-20">
          {details.length === 0
            ? Array.from({ length: 2 }, (_, index) => (
                <div key={index} className="flex flex-col gap-3">
                  <div className="skeleton h-3 w-40" />
                  <div className="skeleton h-8 w-3/4" />
                  <div className="skeleton mt-4 h-24 w-full" />
                </div>
              ))
            : details.map((detail) => <FootnotedOpportunity key={detail.id} detail={detail} />)}
        </div>
      </div>
    </section>
  );
}

type ResolveState = "missing" | "added" | "other-scale";

const RESOLVE: Record<ResolveState, { outcome: MatchOutcome; actual: string; note: string; label: string }> = {
  missing: { outcome: "unknown", actual: "not in your profile", label: "Before", note: "The rule can’t be checked yet, so it’s marked missing rather than failed." },
  added: { outcome: "met", actual: "3.72 on a 4.0 scale", label: "GPA added", note: "Same scale as the threshold, so it’s compared directly: met." },
  "other-scale": {
    outcome: "needs_review",
    actual: "8.40 on a 10.0 scale",
    label: "Another scale",
    note: "Grading scales don’t convert reliably, so this one goes to you for review instead of being guessed.",
  },
};

function Resolve() {
  const [state, setState] = useState<ResolveState>("missing");
  const current = RESOLVE[state];
  return (
    <section aria-labelledby="resolve-title" className="relative overflow-hidden bg-night">
      <img
        src={PHOTOS.observatory.small}
        srcSet={`${PHOTOS.observatory.small} 800w, ${PHOTOS.observatory.large} 1600w`}
        sizes="100vw"
        alt={PHOTOS.observatory.alt}
        loading="lazy"
        decoding="async"
        className="absolute inset-0 h-full w-full object-cover"
      />
      <div className="absolute inset-0 bg-gradient-to-r from-night/90 via-night/60 to-night/25" aria-hidden="true" />
      <div className="relative mx-auto grid max-w-[1320px] grid-cols-1 items-center gap-12 px-5 py-24 sm:px-8 sm:py-36 lg:grid-cols-12">
        <div className="lg:col-span-6">
          <h2 id="resolve-title" className="display text-[48px] text-snow sm:text-[72px]">
            One missing fact shouldn’t close a door.
          </h2>
          <p className="mt-6 max-w-[44ch] text-[17px] text-snow/80">
            When a rule needs something your profile lacks, the verdict stays open. Add it and the affected programs are checked again, with the
            change shown rule by rule.
          </p>
        </div>
        <div className="lg:col-span-5 lg:col-start-8">
          <div role="tablist" aria-label="GPA example" className="inline-flex rounded-full bg-snow/15 p-1 backdrop-blur-sm">
            {(Object.keys(RESOLVE) as ResolveState[]).map((key) => (
              <button
                key={key}
                role="tab"
                type="button"
                aria-selected={state === key}
                onClick={() => setState(key)}
                className={`relative rounded-full px-3.5 py-1.5 text-[13.5px] transition-colors ${state === key ? "text-night" : "text-snow/85 hover:text-snow"}`}
              >
                {state === key && <motion.span layoutId="resolve-tab" className="absolute inset-0 rounded-full bg-lime" transition={{ duration: 0.3, ease: EASE }} />}
                <span className="relative">{RESOLVE[key].label}</span>
              </button>
            ))}
          </div>
          <div role="tabpanel" className="mt-4 rounded-panel bg-paper p-6 shadow-float">
            <p className="kicker">KAUST Visiting Student Research Program</p>
            <p className="heading mt-1.5 text-[21px] text-ink">GPA of at least 3.5 on a 4.0 scale</p>
            <div className="mt-5 flex gap-4">
              <AnimatePresence mode="wait" initial={false}>
                <motion.span key={current.outcome} initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.6, opacity: 0 }} transition={{ duration: 0.22 }} className="inline-flex h-fit">
                  <OutcomeMark outcome={current.outcome} size={24} />
                </motion.span>
              </AnimatePresence>
              <div className="min-w-0 flex-1">
                <dl className="grid grid-cols-2 gap-4 text-[13px]">
                  <div>
                    <dt className="text-muted">Required</dt>
                    <dd className="num mt-0.5 text-ink">≥ 3.5 on a 4.0 scale</dd>
                  </div>
                  <div>
                    <dt className="text-muted">Your profile</dt>
                    <AnimatePresence mode="wait" initial={false}>
                      <motion.dd key={current.actual} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} className={`num mt-0.5 ${state === "missing" ? "text-potential-ink" : "text-ink"}`}>
                        {current.actual}
                      </motion.dd>
                    </AnimatePresence>
                  </div>
                </dl>
                <p className="mt-4 text-[14px] text-ink-soft">{current.note}</p>
                <p className="mt-4 border-t border-rule pt-3 text-[13px] italic text-muted">“Minimum GPA: 3.5 on a 4-point scale (or equivalent).”</p>
              </div>
            </div>
          </div>
          <p className="mt-3 text-[12.5px] text-snow/70">Example rule row. In the app, outcomes come from the engine evaluating your own profile.</p>
        </div>
      </div>
      <p className="relative mx-auto max-w-[1320px] px-5 pb-5 text-right text-[12px] sm:px-8">
        <Credit photo="observatory" tone="paper" />
      </p>
    </section>
  );
}

function Closing() {
  return (
    <section className="bg-persimmon">
      <div className="mx-auto grid max-w-[1320px] grid-cols-1 gap-10 px-5 py-20 sm:px-8 sm:py-28 lg:grid-cols-12">
        <h2 className="display text-[56px] text-night sm:text-[110px] lg:col-span-9">Go see what’s out there.</h2>
        <div className="flex flex-col justify-end gap-3 lg:col-span-3">
          <Link to="/register" className="btn btn-lg justify-between bg-night text-snow hover:bg-[#24324c]">
            Create a profile
            <ArrowUpRight size={18} />
          </Link>
          <Link to="/opportunities" className="btn btn-lg justify-between border border-night text-night hover:bg-night/5">
            Explore opportunities
            <ArrowUpRight size={18} />
          </Link>
        </div>
      </div>
    </section>
  );
}

export function Landing() {
  return (
    <Page title="Opportunity Hub">
      <div className="bg-ivory">
        <MarketingNav />
        <main id="main">
          <Hero />
          <OpenNow />
          <Difference />
          <Engine />
          <HowItWorks />
          <Legend />
          <FromTheAtlas />
          <Resolve />
          <Closing />
        </main>
        <MarketingFooter />
      </div>
    </Page>
  );
}
