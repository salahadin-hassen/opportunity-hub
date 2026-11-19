import { AnimatePresence, motion, useInView, useReducedMotion, useScroll, useTransform } from "motion/react";
import { ArrowRight, ArrowUpRight } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import { useOpportunity } from "../api/queries";
import type { Opportunity, OpportunityType } from "../api/types";
import { InkEdge } from "../components/landing/Atlas";
import AtlasVoyage from "../components/landing/AtlasVoyage";
import { CROSSROADS, ChartTable, Crossroads } from "../components/landing/AtlasScenes";
import { CHART_POINTS } from "../components/landing/geo-chart";
import { EASE, Sharpen, Stamp, isCountry, useAtlas, useEntrance, useSceneActive } from "../components/landing/shared";
import { deadlineWords } from "../components/opportunities/OpportunityRow";
import { ErrorState } from "../components/ui/States";
import { VerdictMark } from "../components/ui/Verdict";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { STATUS_LONG, STATUS_ORDER, TYPE_LABELS, TYPE_PLURALS, countryName, formatDate } from "../lib/format";

/**
 * The landing page below the fold: the unfolding atlas, then three scenes,
 * loaded after the hero so the first view carries only the globe.
 */
/* ------------------------------------------------------------------------ */
/* 2. Find your direction                                                    */
/* ------------------------------------------------------------------------ */

function Direction() {
  const { all, byCountry, specimenId } = useAtlas();
  const specimen = useOpportunity(specimenId).data;
  const rule = specimen?.requirements.find((item) => /gpa/i.test(item.label)) ?? specimen?.requirements[0];
  const source = specimen?.sources.find((item) => item.id === rule?.source_id) ?? specimen?.sources[0];
  const reduced = Boolean(useReducedMotion());
  const wide = useMediaQuery("(min-width: 1024px)");
  const navigate = useNavigate();
  const ref = useRef<HTMLElement>(null);
  const figure = useRef<HTMLElement>(null);
  const inView = useInView(ref, { margin: "-20% 0px" });
  const active = useSceneActive(ref);
  const entrance = useEntrance(figure, reduced);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "start 25%"] });
  // The table slides in from the left as the section arrives, ahead of the text, as the reference's foreground
  // does, and is settled before the section is read.
  const tableX = useTransform(scrollYProgress, (v) => `${(1 - Math.min(1, v)) * -7}vw`);
  const tableRotate = useTransform(scrollYProgress, (v) => (1 - Math.min(1, v)) * -2.5);
  const dots = useMemo(() => [...byCountry.entries()].filter(([code]) => CHART_POINTS[code]).map(([code, count]) => ({ code, count, label: countryName(code), point: CHART_POINTS[code]! })), [byCountry]);

  return (
    <section id="how-it-works" ref={ref} data-active={active} aria-labelledby="direction-title" className="paper-grain relative scroll-mt-16 overflow-hidden py-20 sm:py-28">
      <div className="mx-auto grid max-w-[1440px] grid-cols-1 items-center gap-12 px-5 sm:px-8 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)] lg:gap-14">
        <motion.figure ref={figure} style={reduced || !wide ? undefined : { x: tableX, rotate: tableRotate }} className={`chart-scene relative order-2 lg:order-1 ${entrance}`}>
          <ChartTable dots={dots} needleClass={inView && !reduced ? "needle-hunt" : ""} onDot={(code) => navigate(`/opportunities?where=${code}`)} className="block h-auto w-full" />
          <figcaption className="mt-3 max-w-[56ch] text-[13px] text-muted">
            Each red mark is a country with listings in the index; larger marks hold more. Choose one to see them. {byCountry.size} countries, from {all.length} listings.
          </figcaption>
        </motion.figure>

        <div className="order-1 lg:order-2">
          <p className="small-caps text-ink-soft">How it works</p>
          <Sharpen>
            <h2 id="direction-title" className="serif-display mt-5 text-[clamp(46px,5.4vw,92px)] text-ink">
              Find your direction.
            </h2>
          </Sharpen>
          <ol className="mt-9 flex flex-col">
            {[
              {
                n: "I",
                title: "Search the whole index",
                body: `${all.length} listings you can filter by kind, place and deadline, each linked to its official page.`,
              },
              {
                n: "II",
                title: "Check where you stand",
                body: "Your profile is compared with each published rule, one at a time. A missing fact is marked missing, never failed.",
              },
              {
                n: "III",
                title: "Read the source",
                body: "Every rule sits beside the sentence it was copied from, so you can always read the original.",
              },
            ].map((step, index) => (
              <motion.li
                key={step.n}
                className="grid grid-cols-[44px_minmax(0,1fr)] gap-3 border-t-[1.5px] border-ink py-5 last:border-b-[1.5px] sm:grid-cols-[52px_minmax(0,1fr)] sm:gap-4"
                initial={reduced ? false : { opacity: 0, x: 22 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true, margin: "-60px" }}
                transition={{ duration: 0.7, delay: index * 0.12, ease: EASE }}
              >
                <span className="font-[family-name:var(--font-serif)] text-[28px] leading-none text-ink">{step.n}</span>
                <span>
                  <span className="block text-[17px] font-semibold text-ink">{step.title}</span>
                  <span className="mt-1 block max-w-[48ch] text-[15px] leading-relaxed text-ink-soft">{step.body}</span>
                </span>
              </motion.li>
            ))}
          </ol>
          <ul className="mt-6 flex flex-wrap gap-x-5 gap-y-2" aria-label="The four verdicts">
            {STATUS_ORDER.map((status) => (
              <li key={status} className="flex items-center gap-1.5 text-[13.5px] font-semibold text-ink">
                <VerdictMark status={status} size={14} />
                {STATUS_LONG[status]}
              </li>
            ))}
          </ul>
          {rule?.source_quote && specimen && (
            <figure className="mt-8 border-l-[3px] border-[var(--atlas-terra)] pl-5">
              <blockquote className="font-[family-name:var(--font-serif)] text-[22px] leading-[1.25] text-ink">“{rule.source_quote}”</blockquote>
              <figcaption className="mt-2 text-[13px] text-muted">
                From{" "}
                <Link to={`/opportunities/${specimen.id}`} className="link">
                  {specimen.title}
                </Link>
                {source && <>, retrieved {formatDate(source.retrieved_at)}</>}.
              </figcaption>
            </figure>
          )}
          <div className="mt-10">
            <Stamp to="/register" solid>
              Check my eligibility
              <ArrowRight size={16} />
            </Stamp>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------------ */
/* 3. Understand your possibilities: the expedition ledger                    */
/* ------------------------------------------------------------------------ */

function Ledger() {
  const { all, upcoming, types, byCountry, isPending, isError, refetch } = useAtlas();
  const reduced = Boolean(useReducedMotion());
  const book = useRef<HTMLDivElement>(null);
  const entrance = useEntrance(book, reduced);
  const [kind, setKind] = useState<OpportunityType | null>(null);
  const next = (kind ? upcoming.filter((item) => item.opportunity_type === kind) : upcoming).slice(0, 6);
  const kindCount = kind ? (types.find(([type]) => type === kind)?.[1] ?? 0) : all.length;
  return (
    <section id="open-now" aria-labelledby="ledger-title" className="paper-grain relative scroll-mt-16 overflow-hidden py-20 sm:py-28">
      <InkEdge className="absolute inset-x-0 top-0" flip />
      <div className="mx-auto max-w-[1320px] px-5 sm:px-8">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12 lg:items-end">
          <div className="lg:col-span-7">
            <p className="small-caps text-ink-soft">Understand your possibilities</p>
            <Sharpen>
              <h2 id="ledger-title" className="serif-display mt-5 text-[clamp(42px,5.4vw,92px)] text-ink">
                The expedition ledger.
              </h2>
            </Sharpen>
          </div>
          <p className="max-w-[44ch] text-[16px] leading-relaxed text-ink-soft sm:text-[16.5px] lg:col-span-5">
            Choose a kind of opportunity to turn the page to its next deadlines. Every count and date comes straight from the catalogue.
          </p>
        </div>

        {isError ? (
          <div className="mt-12">
            <ErrorState message="The catalogue couldn’t load." onRetry={refetch} />
          </div>
        ) : (
          <div ref={book} className={`ledger relative mt-10 rounded-[18px] bg-[var(--atlas-wood-deep)] p-2 shadow-[0_30px_60px_-30px_rgb(31_40_51/0.6)] sm:mt-14 sm:p-3.5 ${entrance}`}>
            {/* The ribbon marking today's page. */}
            <svg className="absolute -bottom-10 right-[22%] z-10 hidden h-24 w-7 lg:block" viewBox="0 0 28 96" aria-hidden="true">
              <path d="M 0 0 H 28 V 96 L 14 82 L 0 96 Z" fill="var(--atlas-terra)" stroke="var(--atlas-ink)" strokeWidth="1.5" />
            </svg>
            <div className="grid grid-cols-1 rounded-[10px] text-[var(--atlas-ink)] [perspective:1600px] lg:grid-cols-2">
              <LedgerPage side="left">
                <h3 className="small-caps text-[11px] text-[#5c5a52]">Destinations, by kind</h3>
                <ul className="mt-3 grid grid-cols-2 gap-x-4 sm:mt-4 lg:grid-cols-1" role="group" aria-label="Choose a kind of opportunity">
                  {isPending
                    ? Array.from({ length: 6 }, (_, index) => <li key={index} className="skeleton my-2 h-5 w-full" />)
                    : [[null, all.length] as const, ...types.slice(0, 8)].map(([type, count]) => {
                        const selected = kind === type;
                        return (
                          <li key={type ?? "all"}>
                            <button
                              type="button"
                              aria-pressed={selected}
                              onClick={() => setKind(type)}
                              className={`group relative flex w-full items-baseline gap-2 rounded-[6px] px-2 py-[9px] text-left text-[13.5px] leading-tight transition-colors duration-200 sm:text-[16px] lg:-mx-2 lg:w-[calc(100%+16px)] ${selected ? "bg-[var(--atlas-ink)] text-[var(--atlas-paper)]" : "hover:bg-[var(--atlas-ink)]/[0.06]"}`}
                            >
                              <span className="min-w-0 font-semibold">{type ? TYPE_PLURALS[type] : "Everything"}</span>
                              <span className={`mb-[5px] hidden flex-1 border-b border-dotted lg:block ${selected ? "border-[var(--atlas-paper)]/50" : "border-[var(--atlas-ink)]/50"}`} aria-hidden="true" />
                              <span className="num ml-auto font-[family-name:var(--font-serif)] text-[17px] sm:text-[20px] lg:ml-0">{count}</span>
                            </button>
                          </li>
                        );
                      })}
                </ul>
                <p className="mt-5 border-t border-[var(--atlas-ink)]/25 pt-4 text-[13px] text-[#5c5a52] sm:mt-6 sm:text-[13.5px]">
                  {all.length} listings in total, across {byCountry.size} countries, plus programs open worldwide.
                </p>
              </LedgerPage>
              <LedgerPage side="right">
                <div className="flex items-baseline justify-between gap-3">
                  <h3 className="small-caps text-[11px] text-[#5c5a52]">
                    Open right now.<span className="sr-only"> {kind ? TYPE_PLURALS[kind] : "Everything"}</span>
                  </h3>
                  <Link to={kind ? `/opportunities?type=${kind}` : "/opportunities"} className="inline-flex shrink-0 items-center gap-1 text-[12.5px] font-semibold decoration-1 underline-offset-4 hover:underline">
                    All {kindCount} {kind ? TYPE_PLURALS[kind].toLowerCase() : "listings"}
                    <ArrowRight size={13} />
                  </Link>
                </div>
                <AnimatePresence mode="wait" initial={false}>
                  <motion.ol
                    key={kind ?? "all"}
                    className="mt-3"
                    aria-live="polite"
                    initial={reduced ? false : { opacity: 0, x: 18 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={reduced ? undefined : { opacity: 0, x: -18 }}
                    transition={{ duration: 0.28, ease: EASE }}
                  >
                    {isPending
                      ? Array.from({ length: 5 }, (_, index) => <li key={index} className="skeleton my-3 h-12 w-full" />)
                      : next.length === 0
                        ? <li className="py-6 text-[14px] text-[#5c5a52]">No dated deadlines for this kind right now. Its listings are rolling or open; see them all in the index.</li>
                        : next.map((item, index) => (
                            <motion.li
                              key={item.id}
                              className="border-b border-[var(--atlas-ink)]/20 last:border-0"
                              initial={reduced ? false : { opacity: 0, y: 8 }}
                              animate={{ opacity: 1, y: 0 }}
                              transition={{ duration: 0.3, delay: index * 0.04, ease: EASE }}
                            >
                              <LedgerEntry opportunity={item} />
                            </motion.li>
                          ))}
                  </motion.ol>
                </AnimatePresence>
              </LedgerPage>
            </div>
          </div>
        )}

        <div className="mt-16 flex justify-center sm:mt-20">
          <Stamp to="/opportunities" solid>
            Browse the full index
            <ArrowRight size={16} />
          </Stamp>
        </div>
      </div>
    </section>
  );
}

function LedgerPage({ side, children }: { side: "left" | "right"; children: React.ReactNode }) {
  return (
    <div
      className={`ledger-${side} relative bg-[var(--atlas-paper)] px-4 py-6 sm:px-10 sm:py-9 ${side === "left" ? "rounded-t-[10px] lg:rounded-l-[10px] lg:rounded-tr-none" : "rounded-b-[10px] lg:rounded-r-[10px] lg:rounded-bl-none"} ${side === "left" ? "lg:shadow-[inset_-26px_0_30px_-26px_rgb(31_40_51/0.45)]" : "lg:shadow-[inset_26px_0_30px_-26px_rgb(31_40_51/0.45)]"}`}
      style={{ backgroundImage: "repeating-linear-gradient(to bottom, transparent 0 33px, rgb(31 40 51 / 0.07) 33px 34px)" }}
    >
      {children}
    </div>
  );
}

function LedgerEntry({ opportunity }: { opportunity: Opportunity }) {
  const date = new Date(opportunity.deadline_at!);
  const deadline = deadlineWords(opportunity);
  const place = (opportunity.countries ?? []).map(String).filter(isCountry).map(countryName).slice(0, 2).join(", ") || "Open worldwide";
  return (
    <Link to={`/opportunities/${opportunity.id}`} className="group grid grid-cols-[54px_minmax(0,1fr)] gap-3 py-3 transition-transform duration-300 ease-[var(--ease-out-soft)] hover:translate-x-1 sm:grid-cols-[62px_minmax(0,1fr)]">
      <span className="flex flex-col leading-none">
        <span className="font-[family-name:var(--font-serif)] text-[30px]">{date.getDate()}</span>
        <span className="small-caps mt-1 text-[10px] text-[#5c5a52]">{date.toLocaleDateString("en-GB", { month: "short" })}</span>
      </span>
      <span className="min-w-0">
        <span className="block truncate text-[15.5px] font-semibold decoration-1 underline-offset-4 group-hover:underline">{opportunity.title}</span>
        <span className="mt-0.5 block truncate text-[13px] text-[#5c5a52]">
          {TYPE_LABELS[opportunity.opportunity_type]} · {opportunity.host_name} · {place}
        </span>
        <span className={`mt-0.5 block text-[12.5px] ${deadline.urgent ? "font-semibold text-[var(--atlas-terra)]" : "text-[#5c5a52]"}`}>{deadline.text}</span>
      </span>
    </Link>
  );
}

/* ------------------------------------------------------------------------ */
/* 4. Begin your journey                                                     */
/* ------------------------------------------------------------------------ */

const ARMS: { y: number; dir: 1 | -1; tilt: number }[] = [
  { y: 200, dir: 1, tilt: -5 },
  { y: 262, dir: -1, tilt: 4 },
  { y: 326, dir: 1, tilt: 3 },
  { y: 392, dir: -1, tilt: -3 },
];

function Journey() {
  const { types } = useAtlas();
  const arms = types.slice(0, 4);
  const { width, height, post } = CROSSROADS;
  const reduced = Boolean(useReducedMotion());
  const ref = useRef<HTMLElement>(null);
  const scene = useRef<HTMLDivElement>(null);
  const active = useSceneActive(ref);
  const entrance = useEntrance(scene, reduced);
  const [wiggle, setWiggle] = useState<number | null>(null);
  // The road draws itself as the scene scrolls into view.
  const { scrollYProgress } = useScroll({ target: scene, offset: ["start end", "end end"] });
  const roadDraw = useTransform(scrollYProgress, (v) => (reduced ? 0 : 1 - Math.min(1, Math.max(0, (v - 0.15) / 0.6))));
  return (
    <section ref={ref} data-active={active} aria-labelledby="journey-title" className="paper-grain relative overflow-hidden pt-20 sm:pt-28">
      <InkEdge className="absolute inset-x-0 top-0" />
      <div className="mx-auto max-w-[1320px] px-5 text-center sm:px-8">
        <p className="small-caps text-ink-soft">Your move</p>
        <Sharpen>
          <h2 id="journey-title" className="serif-display mx-auto mt-5 max-w-[14ch] text-[clamp(50px,7vw,120px)] text-ink">
            Begin your journey.
          </h2>
        </Sharpen>
        <div className="mt-10 flex flex-wrap items-center justify-center gap-x-5 gap-y-6">
          <Stamp to="/opportunities" solid>
            Explore opportunities
            <ArrowUpRight size={16} />
          </Stamp>
          <Stamp to="/register">Create a profile</Stamp>
        </div>
      </div>
      <div ref={scene} className={`crossroads relative mx-auto mt-6 max-w-[1440px] ${entrance}`}>
        <Crossroads arms={ARMS.slice(0, Math.max(arms.length, 1))} roadDraw={roadDraw} wiggle={wiggle} className="block h-auto w-full" />
        {/* The arms are real links into the index, with real counts. */}
        {arms.map(([type, count], index) => {
          const arm = ARMS[index]!;
          const centre = post + arm.dir * 128;
          return (
            <Link
              key={type}
              to={`/opportunities?type=${type}`}
              className="arm-label absolute hidden items-baseline gap-2 whitespace-nowrap rounded-sm text-[var(--atlas-ink)] decoration-1 underline-offset-4 hover:underline md:flex"
              style={{ left: `${(centre / width) * 100}%`, top: `${(arm.y / height) * 100}%`, transform: `translate(-50%, -50%) rotate(${arm.tilt}deg)`, ["--i" as string]: index }}
              onPointerEnter={() => setWiggle(index)}
              onPointerLeave={() => setWiggle(null)}
              onFocus={() => setWiggle(index)}
              onBlur={() => setWiggle(null)}
            >
              <span className="font-[family-name:var(--font-serif)] text-[clamp(14px,1.6vw,22px)] uppercase">{TYPE_PLURALS[type]}</span>
              <span className="num text-[clamp(11px,1vw,14px)] text-[#5c5a52]">{count}</span>
            </Link>
          );
        })}
      </div>
      {/* Phones: the signpost's destinations as plain links. */}
      <ul className="mx-auto grid max-w-[520px] grid-cols-2 gap-3 px-5 pb-12 md:hidden">
        {arms.map(([type, count]) => (
          <li key={type}>
            <Link to={`/opportunities?type=${type}`} className="flex items-baseline justify-between gap-2 border-[1.5px] border-ink px-3 py-2.5 text-[14px] font-semibold text-ink">
              {TYPE_PLURALS[type]}
              <span className="num font-normal text-muted">{count}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}


export default function LandingStory() {
  // Arriving at /#how-it-works or /#open-now: the target only exists once this chunk has loaded.
  useEffect(() => {
    const id = window.location.hash.slice(1);
    if (id) document.getElementById(id)?.scrollIntoView({ block: "start" });
  }, []);
  return (
    <>
      <AtlasVoyage />
      <Direction />
      <Ledger />
      <Journey />
    </>
  );
}
