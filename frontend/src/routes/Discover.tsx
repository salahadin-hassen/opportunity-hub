import { AnimatePresence, motion } from "motion/react";
import { LayoutGrid, RefreshCw, ScanSearch, Search, SearchX, X } from "lucide-react";
import { useEffect, useMemo, useRef } from "react";
import { Link, useSearchParams } from "react-router";
import { ApiError } from "../api/client";
import { useMatchMap, useMatches, useOpportunities, useProfile } from "../api/queries";
import type { MatchStatus, Opportunity, OpportunityType } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Content, Page } from "../components/layout/Page";
import { OpportunityRow, RowSkeleton } from "../components/opportunities/OpportunityRow";
import { Postcard } from "../components/opportunities/Postcard";
import { TYPE_STYLE } from "../components/opportunities/TypeTile";
import { EmptyState, ErrorState, Spinner } from "../components/ui/States";
import { VERDICT_TONE, VerdictMark } from "../components/ui/Verdict";
import { useEligibility } from "../features/eligibility";
import { STATUS_LONG, STATUS_ORDER, TYPE_PLURALS, deadlineInfo, plural } from "../lib/format";

type Sort = "deadline" | "verdict" | "title";

function matchesQuery(opportunity: Opportunity, query: string): boolean {
  if (!query) return true;
  const haystack = [opportunity.title, opportunity.host_name ?? "", opportunity.description ?? "", ...(opportunity.tags ?? []).map(String)]
    .join(" ")
    .toLowerCase();
  return query
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((word) => haystack.includes(word));
}

export function Discover() {
  const { isAuthenticated } = useAuth();
  const profile = useProfile();
  const hasProfile = Boolean(profile.data);
  const opportunities = useOpportunities();
  const matches = useMatches();
  const matchMap = useMatchMap();
  const { run, running, progress, changedAt, stale } = useEligibility();
  const [params, setParams] = useSearchParams();
  const searchRef = useRef<HTMLInputElement>(null);

  const query = params.get("q") ?? "";
  const type = (params.get("type") as OpportunityType | null) ?? null;
  const verdict = (params.get("verdict") as MatchStatus | null) ?? null;
  const sort = (params.get("sort") as Sort | null) ?? (hasProfile ? "verdict" : "deadline");

  function update(key: string, value: string | null) {
    setParams(
      (old) => {
        const next = new URLSearchParams(old);
        if (value) next.set(key, value);
        else next.delete(key);
        return next;
      },
      { replace: true },
    );
  }

  // "/" focuses search from anywhere on the page, as in most keyboard-first tools.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (event.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) {
        event.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const all = opportunities.data ?? [];
  const types = useMemo(() => {
    const counts = new Map<OpportunityType, number>();
    for (const item of all) counts.set(item.opportunity_type, (counts.get(item.opportunity_type) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [all]);

  const verdictCounts = useMemo(() => {
    const counts = new Map<MatchStatus, number>();
    for (const item of all) {
      const status = matchMap.get(item.id)?.status;
      if (status) counts.set(status, (counts.get(status) ?? 0) + 1);
    }
    return counts;
  }, [all, matchMap]);

  const visible = useMemo(() => {
    const rank = (item: Opportunity) => {
      const status = matchMap.get(item.id)?.status;
      return status ? STATUS_ORDER.indexOf(status) : STATUS_ORDER.length;
    };
    return all
      .filter((item) => matchesQuery(item, query))
      .filter((item) => !type || item.opportunity_type === type)
      .filter((item) => !verdict || matchMap.get(item.id)?.status === verdict)
      .sort((a, b) => {
        if (sort === "title") return a.title.localeCompare(b.title);
        if (sort === "verdict") return rank(a) - rank(b) || deadlineInfo(a).sortKey - deadlineInfo(b).sortKey;
        return deadlineInfo(a).sortKey - deadlineInfo(b).sortKey || a.title.localeCompare(b.title);
      });
  }, [all, query, type, verdict, sort, matchMap]);

  const closingSoon = useMemo(
    () =>
      [...all]
        .filter((item) => ["soon", "open"].includes(deadlineInfo(item).state))
        .sort((a, b) => deadlineInfo(a).sortKey - deadlineInfo(b).sortKey)
        .slice(0, 3),
    [all],
  );

  const checked = all.filter((item) => matchMap.has(item.id)).length;
  const filtersActive = Boolean(query || type || verdict);
  const runError = matches.error instanceof ApiError ? matches.error.message : null;

  return (
    <Page title="Discover">
      <Content width="wide">
        <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="display text-[52px] text-ink sm:text-[76px]">{hasProfile ? "Discover" : "Opportunities"}</h1>
            <p className="mt-4 max-w-[58ch] text-[16px] text-ink-soft">
              {hasProfile
                ? "Every open program, checked against your profile. Open one to read the evidence behind its verdict."
                : "Scholarships, internships, fellowships and research programs, each with eligibility rules quoted from its official page."}
            </p>
          </div>
          {hasProfile && (
            <button type="button" className="btn btn-primary btn-lg shrink-0" onClick={() => run()} disabled={running || all.length === 0}>
              {running ? <Spinner size={15} /> : checked ? <RefreshCw size={16} /> : <ScanSearch size={16} />}
              {running ? `Checking ${progress.done} of ${progress.total}` : checked ? "Re-check all" : "Check my eligibility"}
            </button>
          )}
        </div>

        {!isAuthenticated && (
          <div className="mt-8 flex flex-col gap-4 rounded-panel bg-night px-6 py-5 text-snow sm:flex-row sm:items-center">
            <p className="flex-1 text-[15px] text-snow/80">
              <span className="font-semibold text-snow">See which of these you qualify for.</span> Create a profile and every listing gets a verdict, with the evidence behind it.
            </p>
            <div className="flex gap-2">
              <Link to="/login?next=/discover" className="btn btn-outline-light btn-sm">
                Sign in
              </Link>
              <Link to="/register" className="btn btn-sm bg-lime text-night hover:bg-snow">
                Create a profile
              </Link>
            </div>
          </div>
        )}
        {isAuthenticated && !hasProfile && profile.isSuccess && (
          <div className="mt-8 flex items-center gap-3 rounded-panel border border-cobalt/30 bg-cobalt-wash px-5 py-4 text-[14.5px]">
            <p className="flex-1 text-ink">Finish your profile to get verdicts on these opportunities.</p>
            <Link to="/onboarding" className="btn btn-primary btn-sm">
              Continue setup
            </Link>
          </div>
        )}
        {hasProfile && stale && checked > 0 && !running && (
          <div className="mt-8 flex items-center gap-3 rounded-panel bg-potential-wash px-5 py-4 text-[14.5px] text-potential-ink">
            <p className="flex-1">Your profile changed since these verdicts were calculated.</p>
            <button type="button" className="btn btn-quiet btn-sm" onClick={() => run()}>
              Re-check all
            </button>
          </div>
        )}

        {/* Segmented search: what, type, order. */}
        <div className="search-shell mt-10 flex flex-col overflow-hidden rounded-[22px] border border-rule-strong bg-paper shadow-panel md:h-[68px] md:flex-row md:items-stretch md:rounded-full">
          <label htmlFor="discover-search" className="group relative flex flex-1 cursor-text flex-col justify-center px-6 py-3 md:py-0">
            <span className="text-[12px] font-semibold text-ink">Search opportunities</span>
            <span className="flex items-center gap-2">
              <input
                id="discover-search"
                ref={searchRef}
                type="search"
                className="w-full bg-transparent text-[15px] text-ink outline-none placeholder:text-faint"
                placeholder="Name, host or topic"
                value={query}
                onChange={(event) => update("q", event.target.value || null)}
              />
              <span className="kbd hidden md:inline-flex">/</span>
            </span>
          </label>
          <span className="mx-6 h-px bg-rule md:mx-0 md:my-4 md:h-auto md:w-px" aria-hidden="true" />
          <label htmlFor="discover-type" className="flex flex-col justify-center px-6 py-3 md:w-56 md:py-0">
            <span className="text-[12px] font-semibold text-ink">Type</span>
            <select id="discover-type" className="bg-transparent text-[15px] text-ink-soft outline-none" value={type ?? ""} onChange={(event) => update("type", event.target.value || null)}>
              <option value="">Any type</option>
              {types.map(([key]) => (
                <option key={key} value={key}>
                  {TYPE_PLURALS[key]}
                </option>
              ))}
            </select>
          </label>
          <span className="mx-6 h-px bg-rule md:mx-0 md:my-4 md:h-auto md:w-px" aria-hidden="true" />
          <label htmlFor="discover-sort" className="flex flex-col justify-center px-6 py-3 md:w-60 md:py-0">
            <span className="text-[12px] font-semibold text-ink">Sort</span>
            <select id="discover-sort" className="bg-transparent text-[15px] text-ink-soft outline-none" value={sort} onChange={(event) => update("sort", event.target.value)}>
              {hasProfile && <option value="verdict">Best verdict first</option>}
              <option value="deadline">Deadline, soonest first</option>
              <option value="title">Name</option>
            </select>
          </label>
          <div className="hidden items-center px-3 md:flex">
            <button
              type="button"
              onClick={() => searchRef.current?.focus()}
              className="inline-flex size-11 items-center justify-center rounded-full bg-cobalt text-snow hover:bg-cobalt-deep"
              aria-label="Focus search"
            >
              <Search size={18} />
            </button>
          </div>
        </div>

        {/* Category strip. */}
        <div role="group" aria-label="Filter by type" className="-mx-4 mt-8 flex gap-7 overflow-x-auto border-b border-rule px-4 sm:mx-0 sm:px-0">
          {[null, ...types.map(([key]) => key)].map((key) => {
            const active = type === key;
            const Icon = key ? TYPE_STYLE[key].icon : LayoutGrid;
            const count = key ? types.find(([value]) => value === key)?.[1] : all.length;
            return (
              <button
                key={key ?? "all"}
                type="button"
                aria-pressed={active}
                onClick={() => update("type", active || !key ? null : key)}
                className={`relative flex shrink-0 flex-col items-center gap-1.5 pb-3 pt-1 text-[13px] transition-colors ${active ? "font-semibold text-ink" : "text-muted hover:text-ink"}`}
              >
                <Icon size={22} strokeWidth={active ? 2.1 : 1.6} />
                <span className="whitespace-nowrap">
                  {key ? TYPE_PLURALS[key] : "All types"} <span className="num text-[11px] text-faint">{count}</span>
                </span>
                {active && <motion.span layoutId="discover-category" className="absolute inset-x-0 -bottom-px h-[2px] bg-ink" transition={{ duration: 0.3 }} />}
              </button>
            );
          })}
        </div>

        {hasProfile && checked > 0 && (
          <div className="-mx-4 mt-5 flex items-center gap-x-5 overflow-x-auto whitespace-nowrap px-4 [scrollbar-width:none] sm:mx-0 sm:flex-wrap sm:px-0" role="group" aria-label="Filter by verdict">
            <span className="text-[13px] text-muted">Show</span>
            {STATUS_ORDER.map((status) => {
              const count = verdictCounts.get(status) ?? 0;
              const active = verdict === status;
              if (count === 0 && !active) return null;
              return (
                <button
                  key={status}
                  type="button"
                  aria-pressed={active}
                  disabled={count === 0 && !active}
                  onClick={() => update("verdict", active ? null : status)}
                  className={`inline-flex items-center gap-1.5 rounded-full py-1 text-[14px] transition-colors disabled:opacity-35 ${
                    active ? `${VERDICT_TONE[status].wash} px-3 font-semibold ${VERDICT_TONE[status].ink}` : "text-ink-soft hover:text-ink"
                  }`}
                >
                  <VerdictMark status={status} size={13} />
                  {STATUS_LONG[status]}
                  <span className="num text-[12px] opacity-70">{count}</span>
                </button>
              );
            })}
          </div>
        )}

        <AnimatePresence>
          {running && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
              <div className="mt-6 h-1 overflow-hidden rounded-full bg-cream" role="progressbar" aria-valuemin={0} aria-valuemax={progress.total} aria-valuenow={progress.done}>
                <motion.div className="h-full rounded-full bg-cobalt" animate={{ width: `${progress.total ? (progress.done / progress.total) * 100 : 0}%` }} transition={{ duration: 0.25 }} />
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {!filtersActive && closingSoon.length > 0 && (
          <section aria-labelledby="closing-soon" className="mt-12">
            <div className="flex items-baseline justify-between">
              <h2 id="closing-soon" className="heading text-[24px] text-ink">
                Closing soonest
              </h2>
              <span className="text-[13px] text-muted">Published deadlines only</span>
            </div>
            <div className="-mx-4 mt-5 flex snap-x snap-mandatory gap-5 overflow-x-auto px-4 pb-2 [scrollbar-width:none] sm:mx-0 sm:grid sm:grid-cols-2 sm:overflow-visible sm:px-0 lg:grid-cols-3">
              {closingSoon.map((item) => (
                <Postcard
                  key={item.id}
                  className="w-[78vw] shrink-0 snap-start sm:w-auto"
                  opportunity={item}
                  match={hasProfile ? matchMap.get(item.id) : undefined}
                  cover="short"
                />
              ))}
            </div>
          </section>
        )}

        <section aria-labelledby="index-title" className="mt-14">
          <div className="flex items-baseline justify-between border-b border-ink pb-3">
            <h2 id="index-title" className="heading text-[24px] text-ink">
              {filtersActive ? "Results" : "All opportunities"}
            </h2>
            <span className="text-[13.5px] text-muted">
              {opportunities.isPending ? "Loading" : `${plural(visible.length, "opportunity", "opportunities")}${filtersActive ? ` of ${all.length}` : ""}`}
            </span>
          </div>
          {opportunities.isError ? (
            <div className="mt-6">
              <ErrorState message={opportunities.error instanceof ApiError ? opportunities.error.message : "Opportunities couldn’t load."} onRetry={() => opportunities.refetch()} />
            </div>
          ) : opportunities.isPending ? (
            <ul className="divide-y divide-rule">
              {Array.from({ length: 6 }, (_, index) => (
                <RowSkeleton key={index} />
              ))}
            </ul>
          ) : visible.length === 0 ? (
            all.length === 0 ? (
              <EmptyState icon={SearchX} title="No opportunities are published yet">
                Published opportunities appear here as soon as they’re added.
              </EmptyState>
            ) : (
              <EmptyState
                icon={SearchX}
                title="Nothing matches these filters"
                action={
                  <button type="button" className="btn btn-quiet btn-sm" onClick={() => setParams({}, { replace: true })}>
                    <X size={14} />
                    Clear filters
                  </button>
                }
              >
                Try a broader search or another type.
              </EmptyState>
            )
          ) : (
            <ul className="divide-y divide-rule">
              <AnimatePresence initial={false}>
                {visible.map((item) => (
                  <OpportunityRow key={item.id} opportunity={item} match={matchMap.get(item.id)} showVerdict={hasProfile} changedAt={changedAt.get(item.id)} />
                ))}
              </AnimatePresence>
            </ul>
          )}
          {runError && (
            <div className="mt-3">
              <ErrorState message={runError} />
            </div>
          )}
        </section>
      </Content>
    </Page>
  );
}
