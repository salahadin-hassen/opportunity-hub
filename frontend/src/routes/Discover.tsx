import { AnimatePresence, motion } from "motion/react";
import { RefreshCw, ScanSearch, Search, SearchX, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";
import { ApiError } from "../api/client";
import { useMatchMap, useMatches, useOpportunities, useProfile } from "../api/queries";
import type { MatchStatus, Opportunity, OpportunityType } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { PageHeader } from "../components/layout/AppShell";
import { Content, Page } from "../components/layout/Page";
import { OpportunityRow, RowSkeleton } from "../components/opportunities/OpportunityRow";
import { Postcard, PostcardSkeleton } from "../components/opportunities/Postcard";
import { Pagination } from "../components/ui/Pagination";
import { Sheet } from "../components/ui/Sheet";
import { EmptyState, ErrorState, Spinner } from "../components/ui/States";
import { VERDICT_TONE, VerdictMark } from "../components/ui/Verdict";
import { useEligibility } from "../features/eligibility";
import { STATUS_LONG, STATUS_ORDER, TYPE_PLURALS, countryName, deadlineInfo, plural } from "../lib/format";

type Sort = "deadline" | "verdict" | "title" | "recent";
type Window = "30" | "90" | "dated" | "open";

const PAGE_SIZE = 20;

const WINDOWS: Record<Window, string> = {
  "30": "Closes within 30 days",
  "90": "Closes within 90 days",
  dated: "Has a published deadline",
  open: "Rolling or no deadline",
};

const SORTS: Record<Sort, string> = {
  verdict: "Best verdict",
  deadline: "Soonest deadline",
  recent: "Newest",
  title: "Name, A–Z",
};

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

function inWindow(opportunity: Opportunity, span: Window | null, info = deadlineInfo(opportunity)): boolean {
  if (!span) return true;
  if (span === "open") return info.state === "rolling" || info.state === "none";
  if (span === "dated") return info.state === "open" || info.state === "soon";
  const days = Number(span);
  return (info.state === "open" || info.state === "soon") && info.sortKey <= days * 86_400_000;
}

function inRegion(opportunity: Opportunity, region: string | null): boolean {
  if (!region) return true;
  if (region === "remote") return opportunity.location_mode === "remote";
  return (opportunity.countries ?? []).map(String).includes(region);
}

function Labelled({ id, label, children }: { id: string; label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <label htmlFor={id} className="field-label">
        {label}
      </label>
      {children}
    </div>
  );
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
  const indexRef = useRef<HTMLElement>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);

  const query = params.get("q") ?? "";
  const type = (params.get("type") as OpportunityType | null) ?? null;
  const verdict = (params.get("verdict") as MatchStatus | null) ?? null;
  const when = (params.get("when") as Window | null) ?? null;
  const region = params.get("where");
  const requestedSort = params.get("sort") as Sort | null;
  const sort: Sort = requestedSort && (requestedSort !== "verdict" || hasProfile) ? requestedSort : hasProfile ? "verdict" : "deadline";
  const page = Math.max(1, Number(params.get("page")) || 1);

  // Built from this render's params, not the router's functional updater, which can replay
  // stale values after a full clear.
  function update(changes: Record<string, string | null>, keepPage = false) {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    if (!keepPage) next.delete("page");
    setParams(next, { replace: true });
  }

  // "/" focuses search from anywhere on the page, as in most keyboard-first tools.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (event.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) && !document.querySelector("dialog[open]")) {
        event.preventDefault();
        searchRef.current?.focus();
      }
    };
    globalThis.addEventListener("keydown", onKey);
    return () => globalThis.removeEventListener("keydown", onKey);
  }, []);

  const all = useMemo(() => opportunities.data ?? [], [opportunities.data]);
  // deadlineInfo formats dates, which is costly inside a sort comparator: compute it once per item.
  const deadlines = useMemo(() => new Map(all.map((item) => [item.id, deadlineInfo(item)])), [all]);
  const infoOf = (item: Opportunity) => deadlines.get(item.id) ?? deadlineInfo(item);
  const types = useMemo(() => {
    const counts = new Map<OpportunityType, number>();
    for (const item of all) counts.set(item.opportunity_type, (counts.get(item.opportunity_type) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [all]);

  const regions = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of all) for (const code of item.countries ?? []) counts.set(String(code), (counts.get(String(code)) ?? 0) + 1);
    const remote = all.filter((item) => item.location_mode === "remote").length;
    const list = [...counts.entries()].map(([code, count]) => ({ code, name: countryName(code), count })).sort((a, b) => a.name.localeCompare(b.name));
    return remote ? [{ code: "remote", name: "Remote", count: remote }, ...list] : list;
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
      .filter((item) => inWindow(item, when, infoOf(item)))
      .filter((item) => inRegion(item, region))
      .sort((a, b) => {
        if (sort === "title") return a.title.localeCompare(b.title);
        if (sort === "recent") return (b.published_at ?? "").localeCompare(a.published_at ?? "") || a.title.localeCompare(b.title);
        if (sort === "verdict") return rank(a) - rank(b) || infoOf(a).sortKey - infoOf(b).sortKey;
        return infoOf(a).sortKey - infoOf(b).sortKey || a.title.localeCompare(b.title);
      });
  }, [all, deadlines, query, type, verdict, when, region, sort, matchMap]);

  const pageCount = Math.max(1, Math.ceil(visible.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount);
  const pageItems = visible.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  const closingSoon = useMemo(
    () =>
      [...all]
        .filter((item) => ["soon", "open"].includes(infoOf(item).state))
        .sort((a, b) => infoOf(a).sortKey - infoOf(b).sortKey)
        .slice(0, 3),
    [all, deadlines],
  );

  const checked = all.filter((item) => matchMap.has(item.id)).length;
  const sheetFilterCount = [when, region, verdict, requestedSort].filter(Boolean).length;
  const filtersActive = Boolean(query || type || verdict || when || region);
  const runError = matches.error instanceof ApiError ? matches.error.message : null;
  const regionName = regions.find((entry) => entry.code === region)?.name ?? (region ? countryName(region) : "");

  function goToPage(next: number) {
    update({ page: next > 1 ? String(next) : null }, true);
    indexRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  const applied: { key: string; label: string }[] = [
    query ? { key: "q", label: `“${query}”` } : null,
    type ? { key: "type", label: TYPE_PLURALS[type] } : null,
    when ? { key: "when", label: WINDOWS[when] } : null,
    region ? { key: "where", label: regionName } : null,
    verdict ? { key: "verdict", label: STATUS_LONG[verdict] } : null,
  ].filter((entry): entry is { key: string; label: string } => entry !== null);

  const filterFields = (prefix: string) => (
    <>
      <Labelled id={`${prefix}-when`} label="Deadline">
        <select id={`${prefix}-when`} className="input" value={when ?? ""} onChange={(event) => update({ when: event.target.value || null })}>
          <option value="">Any deadline</option>
          {(Object.keys(WINDOWS) as Window[]).map((key) => (
            <option key={key} value={key}>
              {WINDOWS[key]}
            </option>
          ))}
        </select>
      </Labelled>
      <Labelled id={`${prefix}-where`} label="Where">
        <select id={`${prefix}-where`} className="input" value={region ?? ""} onChange={(event) => update({ where: event.target.value || null })}>
          <option value="">Anywhere</option>
          {regions.map((entry) => (
            <option key={entry.code} value={entry.code}>
              {entry.name} ({entry.count})
            </option>
          ))}
        </select>
      </Labelled>
      <Labelled id={`${prefix}-sort`} label="Order">
        <select id={`${prefix}-sort`} className="input" value={sort} onChange={(event) => update({ sort: event.target.value })}>
          {(Object.keys(SORTS) as Sort[])
            .filter((key) => key !== "verdict" || hasProfile)
            .map((key) => (
              <option key={key} value={key}>
                {SORTS[key]}
              </option>
            ))}
        </select>
      </Labelled>
    </>
  );

  return (
    <Page title={hasProfile ? "Discover" : "Opportunities"}>
      <Content width="wide">
        <PageHeader
          kicker={hasProfile ? "Checked against your profile" : "The index"}
          title={hasProfile ? "Discover" : "Opportunities"}
          description={
            hasProfile
              ? "Every published opportunity, with a verdict once you run a check. Open one to read the official wording behind it."
              : "Scholarships, internships, fellowships and research programs. Every listing quotes its eligibility rules from the official page."
          }
          actions={
            hasProfile && (
              <button type="button" className="btn btn-primary btn-lg" onClick={() => run()} disabled={running || all.length === 0}>
                {running ? <Spinner size={15} /> : checked ? <RefreshCw size={16} /> : <ScanSearch size={16} />}
                {running ? `Checking ${progress.done} of ${progress.total}` : checked ? "Re-check all" : "Check my eligibility"}
              </button>
            )
          }
        />

        {!isAuthenticated && (
          <div className="mt-8 flex flex-col gap-4 rounded-panel bg-night px-5 py-4 text-snow ring-1 ring-night-edge sm:flex-row sm:items-center sm:px-6">
            <p className="flex-1 text-[14.5px] text-snow/80">
              <span className="font-semibold text-snow">See which of these you qualify for.</span> Add a profile and each listing gets a verdict, with the rule-by-rule evidence.
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
          <div className="mt-8 flex flex-col gap-3 rounded-panel border border-cobalt/30 bg-cobalt-wash px-5 py-4 text-[14.5px] sm:flex-row sm:items-center">
            <p className="flex-1 text-ink">Finish your profile to get verdicts on these opportunities.</p>
            <Link to="/onboarding" className="btn btn-primary btn-sm self-start sm:self-auto">
              Continue setup
            </Link>
          </div>
        )}
        {hasProfile && stale && checked > 0 && !running && (
          <div className="mt-8 flex flex-col gap-3 rounded-panel bg-potential-wash px-5 py-4 text-[14.5px] text-potential-ink sm:flex-row sm:items-center">
            <p className="flex-1">Your profile changed since these verdicts were calculated.</p>
            <button type="button" className="btn btn-quiet btn-sm self-start sm:self-auto" onClick={() => run()}>
              Re-check all
            </button>
          </div>
        )}

        {/* Search and refine. Phones get search plus a Filters sheet; wider screens see every control. */}
        <div className="mt-10 flex flex-col gap-4 lg:flex-row lg:items-end">
          <div className="min-w-0 flex-1">
            <label htmlFor="discover-search" className="field-label">
              Search
            </label>
            <div className="search-shell relative">
              <Search size={17} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" aria-hidden="true" />
              <input
                id="discover-search"
                ref={searchRef}
                type="search"
                className="input h-12 pl-10 pr-12 text-[15.5px]"
                placeholder="Title, host or topic"
                value={query}
                onChange={(event) => update({ q: event.target.value || null })}
              />
              <span className="kbd pointer-events-none absolute right-3.5 top-1/2 hidden -translate-y-1/2 md:inline-flex" aria-hidden="true">
                /
              </span>
            </div>
          </div>
          <div className="hidden grid-cols-3 gap-3 md:grid lg:w-[600px] lg:shrink-0 [&_.input]:h-12">{filterFields("desktop")}</div>
          <button type="button" className="btn btn-quiet h-12 justify-between md:hidden" onClick={() => setFiltersOpen(true)}>
            <span className="inline-flex items-center gap-2">
              <SlidersHorizontal size={16} />
              Filters and order
            </span>
            {sheetFilterCount > 0 && <span className="num inline-flex size-6 items-center justify-center rounded-full bg-ink text-[12px] font-semibold text-paper">{sheetFilterCount}</span>}
          </button>
        </div>

        {/* The type index. */}
        <div className="relative mt-6">
          <div role="group" aria-label="Filter by type" className="-mx-4 flex gap-6 overflow-x-auto border-b border-rule px-4 [scrollbar-width:none] sm:mx-0 sm:px-0">
            {[null, ...types.map(([key]) => key)].map((key) => {
              const active = type === key;
              const count = key ? types.find(([value]) => value === key)?.[1] : all.length;
              return (
                <button key={key ?? "all"} type="button" aria-pressed={active} onClick={() => update({ type: active || !key ? null : key })} className="index-tab">
                  {key ? TYPE_PLURALS[key] : "All types"}
                  <span className="count">{opportunities.isPending ? "" : count}</span>
                  {active && <motion.span layoutId="discover-type" className="absolute inset-x-0 -bottom-px h-[2px] bg-ink" transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }} />}
                </button>
              );
            })}
          </div>
          <span className="pointer-events-none absolute inset-y-0 right-0 w-10 bg-gradient-to-l from-ivory sm:hidden" aria-hidden="true" />
        </div>

        {hasProfile && checked > 0 && (
          <div className="-mx-4 mt-4 flex items-center gap-2 overflow-x-auto px-4 [scrollbar-width:none] sm:mx-0 sm:flex-wrap sm:px-0" role="group" aria-label="Filter by verdict">
            {STATUS_ORDER.map((status) => {
              const count = verdictCounts.get(status) ?? 0;
              const active = verdict === status;
              if (count === 0 && !active) return null;
              return (
                <button
                  key={status}
                  type="button"
                  aria-pressed={active}
                  onClick={() => update({ verdict: active ? null : status })}
                  className={`chip ${active ? `!border-transparent ${VERDICT_TONE[status].wash} ${VERDICT_TONE[status].ink} !font-semibold` : ""}`}
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
              <div className="mt-6 h-1 overflow-hidden rounded-full bg-cream" role="progressbar" aria-label="Eligibility check progress" aria-valuemin={0} aria-valuemax={progress.total} aria-valuenow={progress.done}>
                <motion.div className="h-full rounded-full bg-cobalt" animate={{ width: `${progress.total ? (progress.done / progress.total) * 100 : 0}%` }} transition={{ duration: 0.25 }} />
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {!filtersActive && currentPage === 1 && (opportunities.isPending || closingSoon.length > 0) && (
          <section aria-labelledby="closing-soon" className="mt-12">
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <h2 id="closing-soon" className="heading text-[24px] text-ink">
                Closing soonest
              </h2>
              <span className="text-[13px] text-muted">Only listings with a published date</span>
            </div>
            <div className="-mx-4 mt-5 flex snap-x snap-mandatory gap-5 overflow-x-auto px-4 pb-2 [scrollbar-width:none] sm:mx-0 sm:grid sm:grid-cols-2 sm:overflow-visible sm:px-0 lg:grid-cols-3">
              {opportunities.isPending
                ? Array.from({ length: 3 }, (_, index) => <PostcardSkeleton key={index} />)
                : closingSoon.map((item) => (
                    <Postcard key={item.id} className="w-[78vw] shrink-0 snap-start sm:w-auto" opportunity={item} match={hasProfile ? matchMap.get(item.id) : undefined} cover="short" />
                  ))}
            </div>
          </section>
        )}

        <section ref={indexRef} aria-labelledby="index-title" className="mt-14 scroll-mt-24">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-ink pb-3">
            <h2 id="index-title" className="heading text-[24px] text-ink">
              {filtersActive ? "Results" : "All opportunities"}
            </h2>
            <p className="num text-[13.5px] text-muted" aria-live="polite">
              {opportunities.isPending
                ? "Loading the index"
                : visible.length > PAGE_SIZE
                  ? `${(currentPage - 1) * PAGE_SIZE + 1}–${Math.min(currentPage * PAGE_SIZE, visible.length)} of ${plural(visible.length, "opportunity", "opportunities")}${filtersActive ? `, from ${all.length}` : ""}`
                  : `${plural(visible.length, "opportunity", "opportunities")}${filtersActive ? ` of ${all.length}` : ""}`}
            </p>
          </div>

          {applied.length > 0 && (
            <div className="mt-4 flex flex-wrap items-center gap-2" aria-label="Applied filters">
              <AnimatePresence initial={false} mode="popLayout">
                {applied.map((entry) => (
                  <motion.button
                    layout
                    key={entry.key}
                    type="button"
                    className="chip"
                    onClick={() => update({ [entry.key]: null })}
                    aria-label={`Remove filter: ${entry.label}`}
                    initial={{ opacity: 0, scale: 0.85 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.85 }}
                    transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
                  >
                    {entry.label}
                    <X size={13} className="text-muted" />
                  </motion.button>
                ))}
              </AnimatePresence>
              <button type="button" className="ml-1 text-[13px] font-medium text-cobalt-deep underline-offset-4 hover:underline" onClick={() => setParams({}, { replace: true })}>
                Clear filters
              </button>
            </div>
          )}

          {opportunities.isError ? (
            <div className="mt-6">
              <ErrorState message={opportunities.error instanceof ApiError ? opportunities.error.message : "Opportunities couldn’t load."} onRetry={() => opportunities.refetch()} />
            </div>
          ) : opportunities.isPending ? (
            <ul className="mt-2 divide-y divide-rule" aria-busy="true" aria-label="Loading opportunities">
              {Array.from({ length: 6 }, (_, index) => (
                <RowSkeleton key={index} />
              ))}
            </ul>
          ) : visible.length === 0 ? (
            all.length === 0 ? (
              <EmptyState icon={SearchX} title="No opportunities are published yet">
                Opportunities appear here once a curator has checked them against their official pages.
              </EmptyState>
            ) : (
              <EmptyState
                icon={SearchX}
                title="Nothing matches all of these"
                action={
                  <button type="button" className="btn btn-quiet btn-sm" onClick={() => setParams({}, { replace: true })}>
                    <X size={14} />
                    Clear filters
                  </button>
                }
              >
                The index holds {plural(all.length, "opportunity", "opportunities")}. Remove a filter above, or search for a broader word.
              </EmptyState>
            )
          ) : (
            <>
              <ul className="mt-2 divide-y divide-rule">
                <AnimatePresence initial={false} mode="popLayout">
                  {pageItems.map((item) => (
                    <OpportunityRow key={item.id} opportunity={item} match={matchMap.get(item.id)} showVerdict={hasProfile} changedAt={changedAt.get(item.id)} canSave={hasProfile} />
                  ))}
                </AnimatePresence>
              </ul>
              <div className="mt-8 border-t border-rule pt-6">
                <Pagination page={currentPage} pageCount={pageCount} onChange={goToPage} label="Opportunity pages" />
              </div>
            </>
          )}
          {runError && (
            <div className="mt-3">
              <ErrorState message={runError} />
            </div>
          )}
        </section>
      </Content>

      <Sheet
        open={filtersOpen}
        onClose={() => setFiltersOpen(false)}
        title="Filters and order"
        footer={
          <div className="flex items-center gap-3">
            <button type="button" className="btn btn-ghost" onClick={() => update({ when: null, where: null, verdict: null, sort: null })}>
              Reset
            </button>
            <button type="button" className="btn btn-ink flex-1" onClick={() => setFiltersOpen(false)}>
              Show {plural(visible.length, "result")}
            </button>
          </div>
        }
      >
        <div className="flex flex-col gap-5">{filterFields("sheet")}</div>
      </Sheet>
    </Page>
  );
}
