import { AnimatePresence, motion } from "motion/react";
import { ArrowLeft, ArrowUpRight, Bookmark, FileCheck, Lock, RefreshCw, ScanSearch, SearchX } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";
import { ApiError } from "../api/client";
import {
  useCreateApplication,
  useMatchMap,
  useOpportunity,
  useProfile,

} from "../api/queries";
import { useAuth } from "../auth/AuthContext";
import { EvidenceList, ruleFacts } from "../components/eligibility/Evidence";
import { Content, Page } from "../components/layout/Page";
import { deadlineWords, locationText } from "../components/opportunities/OpportunityRow";
import { SaveToggle } from "../components/opportunities/SaveToggle";
import { TypeLabel } from "../components/opportunities/TypeTile";
import { DateBlock } from "../components/ui/DateBlock";
import { EmptyState, ErrorState, Spinner } from "../components/ui/States";
import { VERDICT_MEANING, VERDICT_SCOPE, VERDICT_TONE, VerdictBadge } from "../components/ui/Verdict";
import { useEligibility } from "../features/eligibility";
import { STATUS_LONG, deadlineInfo, deadlineIsDate, deadlineTime, formatDate, formatDateTime, languageName } from "../lib/format";
import { FACT_LABELS } from "../lib/rules";

export function OpportunityDetail() {
  const { id } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();
  const profile = useProfile();
  const opportunity = useOpportunity(id);
  const matchMap = useMatchMap();
  const { run, running, changedAt, before } = useEligibility();
  const [error, setError] = useState<string | null>(null);

  const createApplication = useCreateApplication();
  // Phones: once the header's actions scroll away, keep "Apply" and "Save" in reach at the bottom.
  const actions = useRef<HTMLDivElement>(null);
  const [actionsOut, setActionsOut] = useState(false);
  const ready = opportunity.isSuccess;
  useEffect(() => {
    const node = actions.current;
    if (!node || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(([entry]) => setActionsOut(Boolean(entry && !entry.isIntersecting && entry.boundingClientRect.top < 0)));
    observer.observe(node);
    return () => observer.disconnect();
  }, [ready]);

  if (opportunity.isPending) {
    return (
      <Content>
        <div className="skeleton h-4 w-32" />
        <div className="skeleton mt-8 h-14 w-2/3" />
        <div className="skeleton mt-4 h-4 w-1/3" />
        <div className="skeleton mt-12 h-72 w-full" />
      </Content>
    );
  }
  if (opportunity.isError) {
    const missing = opportunity.error instanceof ApiError && opportunity.error.status === 404;
    return (
      <Page title={missing ? "Not found" : "Unavailable"}>
        <Content>
          {missing ? (
            <EmptyState
              icon={SearchX}
              title="This opportunity isn’t available"
              action={
                <Link to="/opportunities" className="btn btn-quiet">
                  Browse opportunities
                </Link>
              }
            >
              It may have been unpublished, or the link is wrong.
            </EmptyState>
          ) : (
            <ErrorState message={opportunity.error.message} onRetry={() => opportunity.refetch()} />
          )}
        </Content>
      </Page>
    );
  }

  const item = opportunity.data;
  const match = matchMap.get(item.id);
  const previous = before.get(item.id);
  const hasProfile = Boolean(profile.data);
  const deadline = deadlineInfo(item);
  const time = deadlineTime(item.deadline_at);
  const facts = ruleFacts(item.requirements);
  const languages = (item.languages ?? []).map((code) => languageName(String(code)));

  async function recheck() {
    setError(null);
    try {
      await run([item.id]);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The check couldn’t run. Try again.");
    }
  }

  const lastRetrieved = item.sources.map((source) => source.retrieved_at).sort().at(-1);
  const deadlineText = deadlineWords(item);

  async function track() {
    try {
      await createApplication.mutateAsync({ opportunity_id: item.id });
    } catch {
      /* already tracked: the list opens either way */
    }
    navigate("/applications");
  }

  const mobileBar = item.official_url && (
    <AnimatePresence>
      {actionsOut && (
        <motion.div
          initial={{ y: "110%" }}
          animate={{ y: 0 }}
          exit={{ y: "110%" }}
          transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
          className={`fixed inset-x-0 z-30 flex items-center gap-2 border-t border-rule bg-paper/95 px-4 py-3 backdrop-blur-md sm:hidden ${hasProfile ? "bottom-[calc(4rem+env(safe-area-inset-bottom))]" : "bottom-0 pb-[max(0.75rem,env(safe-area-inset-bottom))]"}`}
        >
          <a href={item.official_url} target="_blank" rel="noreferrer" className="btn btn-primary h-11 flex-1 justify-between">
            Apply on the official site
            <ArrowUpRight size={16} />
            <span className="sr-only">(opens in a new tab)</span>
          </a>
          {hasProfile && <SaveToggle opportunityId={item.id} title={item.title} />}
        </motion.div>
      )}
    </AnimatePresence>
  );

  return (
    <Page title={item.title}>
      {mobileBar}
      <Content width="wide">
        <Link to={hasProfile ? "/discover" : "/opportunities"} className="inline-flex items-center gap-1.5 text-[14px] text-ink-soft hover:text-ink">
          <ArrowLeft size={15} />
          {hasProfile ? "Discover" : "All opportunities"}
        </Link>

        <header className="mt-8 grid grid-cols-1 gap-10 border-b border-ink pb-10 lg:grid-cols-12">
          <div className="lg:col-span-8">
            <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[14px] text-ink-soft">
              <TypeLabel type={item.opportunity_type} />
              {item.host_name && (
                <>
                  <span className="text-faint" aria-hidden="true">
                    ·
                  </span>
                  <span>{item.host_name}</span>
                </>
              )}
            </p>
            <h1 className="display mt-5 max-w-[18ch] text-[40px] text-ink sm:text-[60px]">{item.title}</h1>
            {item.status === "closed" && (
              <p className="mt-5 inline-flex rounded-full bg-cream px-3.5 py-1.5 text-[14px] text-ink-soft">Applications for this cycle are closed</p>
            )}
            <div ref={actions} className="mt-8 flex flex-col gap-2.5 sm:flex-row sm:flex-wrap sm:items-center">
              {item.official_url && (
                <a href={item.official_url} target="_blank" rel="noreferrer" className="btn btn-primary btn-lg justify-between sm:justify-center">
                  Apply on the official site
                  <ArrowUpRight size={17} />
                  <span className="sr-only">(opens in a new tab)</span>
                </a>
              )}
              {hasProfile ? (
                <>
                  <div className="sm:w-auto [&_.btn]:h-[3.25rem] [&_.btn]:px-5">
                    <SaveToggle opportunityId={item.id} title={item.title} variant="button" />
                  </div>
                  <button type="button" onClick={track} disabled={createApplication.isPending} className="btn btn-ghost btn-lg">
                    <FileCheck size={17} />
                    Track my application
                  </button>
                </>
              ) : (
                <Link to={`/login?next=${encodeURIComponent(location.pathname)}`} className="btn btn-ghost btn-lg">
                  <Bookmark size={17} />
                  Sign in to save
                </Link>
              )}
            </div>
          </div>

          <dl className="grid grid-cols-2 content-start gap-x-6 gap-y-6 self-end text-[14px] lg:col-span-4 lg:grid-cols-1 lg:border-l lg:border-rule lg:pl-8">
            <div className="col-span-2 flex items-center gap-4 lg:col-span-1">
              <DateBlock opportunity={item} />
              <div>
                <dt className="eyebrow">Deadline</dt>
                <dd className="mt-1 text-ink">
                  <span className={deadlineIsDate(item) ? "num font-semibold" : "font-semibold"}>{deadline.label}</span>
                  {time && <span className="num text-muted"> · {time}</span>}
                  <span className={`block text-[13px] ${deadlineText.urgent ? "font-semibold text-persimmon-deep" : "text-muted"}`}>{deadlineText.text}</span>
                </dd>
              </div>
            </div>
            <div>
              <dt className="eyebrow">Where</dt>
              <dd className="mt-1 text-ink">{locationText(item)}</dd>
            </div>
            {languages.length > 0 && (
              <div>
                <dt className="eyebrow">Languages</dt>
                <dd className="mt-1 text-ink">{languages.join(", ")}</dd>
              </div>
            )}
            <div>
              <dt className="eyebrow">Funding</dt>
              <dd className="mt-1 text-ink-soft">Amounts and terms are on the official page; we don’t summarise them.</dd>
            </div>
            {lastRetrieved && (
              <div>
                <dt className="eyebrow">Source checked</dt>
                <dd className="num mt-1 text-ink">{formatDate(lastRetrieved)}</dd>
              </div>
            )}
          </dl>
        </header>

        <div className="mt-12 grid grid-cols-1 gap-12 lg:grid-cols-12 lg:gap-10">
          <aside className="order-last lg:col-span-4">
            <div className="lg:sticky lg:top-24">
              <section aria-labelledby="standing-title" className={`rounded-panel p-6 ${match ? VERDICT_TONE[match.status].wash : "bg-cream"}`}>
                <h2 id="standing-title" className="eyebrow !text-ink">
                  Your standing
                </h2>
                {match ? (
                  <>
                    <div className="mt-3">
                      <VerdictBadge status={match.status} size="lg" animateKey={changedAt.get(item.id)} />
                    </div>
                    {previous && previous.status !== match.status && <p className="mt-1 text-[13px] text-ink-soft">Previously {STATUS_LONG[previous.status].toLowerCase()}</p>}
                    <p className="mt-3 text-[14.5px] text-ink-soft">{VERDICT_MEANING[match.status]}</p>
                    <p className="mt-3 text-[12.5px] text-muted">
                      Checked <span className="num">{formatDateTime(match.evaluated_at)}</span>
                    </p>
                  </>
                ) : (
                  <p className="mt-3 text-[14.5px] text-ink-soft">
                    {hasProfile
                      ? "Not checked yet. Run a check to compare your profile with these rules."
                      : `${item.requirements.length} published ${item.requirements.length === 1 ? "rule" : "rules"}, each with the official wording it comes from.`}
                  </p>
                )}
                {hasProfile && (
                  <button type="button" className="btn btn-ink mt-5 w-full" onClick={recheck} disabled={running}>
                    {running ? <Spinner size={14} /> : match ? <RefreshCw size={15} /> : <ScanSearch size={15} />}
                    {match ? "Re-check" : "Check my eligibility"}
                  </button>
                )}
                {!isAuthenticated && (
                  <Link to={`/login?next=${encodeURIComponent(location.pathname)}`} className="btn btn-ink mt-5 w-full">
                    <Lock size={14} />
                    Sign in to check
                  </Link>
                )}
                {isAuthenticated && !hasProfile && profile.isSuccess && (
                  <Link to="/onboarding" className="btn btn-ink mt-5 w-full">
                    Create profile to check
                  </Link>
                )}
                <p className="mt-5 border-t border-ink/10 pt-4 text-[12.5px] leading-relaxed text-ink-soft">{VERDICT_SCOPE}</p>
              </section>

              {facts.length > 0 && (
                <div className="mt-8">
                  <h3 className="eyebrow">Profile facts these rules read</h3>
                  <p className="mt-1.5 text-[14px] text-ink-soft">{facts.map((fact) => FACT_LABELS[fact]).join(", ")}</p>
                </div>
              )}
              {item.sources.length > 0 && (
                <div className="mt-8">
                  <h3 className="eyebrow">Official sources</h3>
                  <ul className="mt-2 flex flex-col divide-y divide-rule border-y border-rule">
                    {item.sources.map((source) => (
                      <li key={source.id}>
                        <a href={source.url} target="_blank" rel="noreferrer" className="group flex items-start justify-between gap-3 py-3">
                          <span className="min-w-0">
                            <span className="block text-[14px] font-medium text-ink group-hover:underline">{source.publisher ?? "Official page"}</span>
                            <span className="block truncate text-[12.5px] text-muted">{new URL(source.url).hostname + new URL(source.url).pathname}</span>
                            <span className="block text-[12.5px] text-faint">Retrieved {formatDate(source.retrieved_at)}</span>
                          </span>
                          <ArrowUpRight size={15} className="mt-0.5 shrink-0 text-muted" />
                        </a>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </aside>

          <div className="min-w-0 lg:col-span-8">
            <section aria-labelledby="rules-title">
              <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
                <h2 id="rules-title" className="heading text-[30px] text-ink">
                  The rules
                </h2>
                <span className="text-[13.5px] text-muted">
                  {item.requirements.length} published, quoted from the source
                </span>
              </div>
              {error && (
                <div className="mt-4">
                  <ErrorState message={error} />
                </div>
              )}
              <div className="mt-4 border-t border-ink">
                <EvidenceList requirements={item.requirements} match={match} previous={previous} sources={item.sources} quotesOpen flush />
              </div>
            </section>

            {item.description && (
              <section aria-labelledby="about-title" className="mt-16">
                <h2 id="about-title" className="heading text-[30px] text-ink">
                  About
                </h2>
                <p className="mt-1 text-[13px] text-muted">Quoted from the official page.</p>
                <blockquote className="mt-5 max-w-[66ch] whitespace-pre-line border-l-2 border-persimmon pl-5 text-[18px] leading-relaxed text-ink">{item.description}</blockquote>
              </section>
            )}
          </div>
        </div>
      </Content>
    </Page>
  );
}
