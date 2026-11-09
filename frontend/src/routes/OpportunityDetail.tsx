import { ArrowLeft, ArrowUpRight, Bookmark, BookmarkCheck, FileCheck, Lock, RefreshCw, ScanSearch, SearchX } from "lucide-react";
import { useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";
import { ApiError } from "../api/client";
import {
  useCreateApplication,
  useMatchMap,
  useOpportunity,
  useProfile,
  useSaveOpportunity,
  useSavedOpportunities,
  useUnsaveOpportunity,
} from "../api/queries";
import { useAuth } from "../auth/AuthContext";
import { EvidenceList, ruleFacts } from "../components/eligibility/Evidence";
import { Content, Page } from "../components/layout/Page";
import { locationText } from "../components/opportunities/OpportunityRow";
import { TYPE_STYLE, TypeTile } from "../components/opportunities/TypeTile";
import { EmptyState, ErrorState, Spinner } from "../components/ui/States";
import { VERDICT_MEANING, VERDICT_SCOPE, VERDICT_TONE, VerdictBadge } from "../components/ui/Verdict";
import { useEligibility } from "../features/eligibility";
import { STATUS_LONG, TYPE_LABELS, deadlineInfo, deadlineIsDate, deadlineTime, formatDate, formatDateTime, languageName } from "../lib/format";
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

  const savedQuery = useSavedOpportunities();
  const save = useSaveOpportunity();
  const unsave = useUnsaveOpportunity();
  const createApplication = useCreateApplication();

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
  const style = TYPE_STYLE[item.opportunity_type];
  const languages = (item.languages ?? []).map((code) => languageName(String(code)));

  async function recheck() {
    setError(null);
    try {
      await run([item.id]);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The check couldn’t run. Try again.");
    }
  }

  return (
    <Page title={item.title}>
      <div className={`h-2 ${style.tile}`} aria-hidden="true" />
      <Content width="wide">
        <Link to={hasProfile ? "/discover" : "/opportunities"} className="inline-flex items-center gap-1.5 text-[14px] text-ink-soft hover:text-ink">
          <ArrowLeft size={15} />
          {hasProfile ? "Discover" : "All opportunities"}
        </Link>

        <header className="mt-8 grid grid-cols-1 gap-8 border-b border-ink pb-10 lg:grid-cols-12">
          <div className="lg:col-span-8">
            <div className="flex items-center gap-3">
              <TypeTile type={item.opportunity_type} host={item.host_name} size={44} />
              <p className="text-[14px] text-ink-soft">
                <span className="font-semibold text-ink">{TYPE_LABELS[item.opportunity_type]}</span>
                {item.host_name && <span className="block">{item.host_name}</span>}
              </p>
            </div>
            <h1 className="display mt-6 text-[44px] text-ink sm:text-[68px]">{item.title}</h1>
            {item.status === "closed" && (
              <p className="mt-5 inline-flex rounded-full bg-cream px-3.5 py-1.5 text-[14px] text-ink-soft">Applications for this cycle are closed</p>
            )}
          </div>
          <dl className="grid grid-cols-2 content-end gap-x-6 gap-y-5 text-[14px] lg:col-span-4">
            <div>
              <dt className="text-muted">Deadline</dt>
              <dd className="mt-1 text-ink">
                <span className={deadlineIsDate(item) ? "num" : ""}>{deadline.label}</span>
                {time && <span className="num block text-[12.5px] text-muted">{time}</span>}
                {deadline.relative && <span className={`block text-[13px] ${deadline.state === "soon" ? "font-medium text-persimmon-deep" : "text-muted"}`}>{deadline.relative}</span>}
              </dd>
            </div>
            <div>
              <dt className="text-muted">Location</dt>
              <dd className="mt-1 text-ink">{locationText(item)}</dd>
            </div>
            {languages.length > 0 && (
              <div>
                <dt className="text-muted">Languages</dt>
                <dd className="mt-1 text-ink">{languages.join(", ")}</dd>
              </div>
            )}
            {item.official_url && (
              <div className="col-span-2">
                <a href={item.official_url} target="_blank" rel="noreferrer" className="btn btn-ink w-full justify-between sm:w-auto sm:gap-6">
                  Official page
                  <ArrowUpRight size={16} />
                </a>
              </div>
            )}
          </dl>
        </header>

        <div className="mt-12 grid grid-cols-1 gap-12 lg:grid-cols-12 lg:gap-10">
          <aside className="order-first lg:order-last lg:col-span-4">
            <div className="lg:sticky lg:top-24">
              <section aria-labelledby="standing-title" className={`rounded-panel p-6 ${match ? VERDICT_TONE[match.status].wash : "bg-cream"}`}>
                <h2 id="standing-title" className="text-[13px] font-semibold text-ink">
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
                {hasProfile && (
                  <div className="mt-3 flex flex-col gap-2">
                    <button
                      type="button"
                      onClick={() => (savedQuery.data ?? []).some((s) => s.opportunity_id === item.id) ? unsave.mutate(item.id) : save.mutate({ opportunityId: item.id })}
                      disabled={save.isPending || unsave.isPending}
                      className={`btn w-full justify-center gap-2 text-[13.5px] ${(savedQuery.data ?? []).some((s) => s.opportunity_id === item.id) ? "border border-persimmon text-persimmon font-semibold" : "btn-quiet"}`}
                    >
                      {(savedQuery.data ?? []).some((s) => s.opportunity_id === item.id) ? <BookmarkCheck size={16} /> : <Bookmark size={16} />}
                      {(savedQuery.data ?? []).some((s) => s.opportunity_id === item.id) ? "Saved to your list" : "Save opportunity"}
                    </button>
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          await createApplication.mutateAsync({ opportunity_id: item.id });
                        } catch {
                          /* already tracked */
                        }
                        navigate("/applications");
                      }}
                      className="btn btn-quiet w-full justify-center gap-2 text-[13.5px]"
                    >
                      <FileCheck size={16} />
                      Track application
                    </button>
                  </div>
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
                  <h3 className="text-[13px] font-semibold text-ink">Profile facts these rules read</h3>
                  <p className="mt-1.5 text-[14px] text-ink-soft">{facts.map((fact) => FACT_LABELS[fact]).join(", ")}</p>
                </div>
              )}
              {item.sources.length > 0 && (
                <div className="mt-8">
                  <h3 className="text-[13px] font-semibold text-ink">Sources</h3>
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
