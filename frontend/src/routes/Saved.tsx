import { Bookmark, BookmarkX, Calendar, ChevronRight, FileCheck, MapPin } from "lucide-react";
import { Link, useNavigate } from "react-router";
import { useCreateApplication, useSavedOpportunities, useUnsaveOpportunity } from "../api/queries";
import { Content, Page } from "../components/layout/Page";
import { TYPE_LABELS, deadlineInfo } from "../lib/format";
import { locationText } from "../components/opportunities/OpportunityRow";
import { EmptyState, ErrorState, Spinner } from "../components/ui/States";
import { TypeTile } from "../components/opportunities/TypeTile";

export function Saved() {
  const navigate = useNavigate();
  const saved = useSavedOpportunities();
  const unsave = useUnsaveOpportunity();
  const createApplication = useCreateApplication();

  if (saved.isPending) {
    return (
      <Content>
        <div className="flex min-h-[50vh] items-center justify-center text-muted">
          <Spinner />
        </div>
      </Content>
    );
  }

  if (saved.isError) {
    return (
      <Content>
        <ErrorState message="Could not load your saved opportunities." onRetry={() => saved.refetch()} />
      </Content>
    );
  }

  const items = saved.data ?? [];
  const active = items.filter((s) => s.opportunity.status !== "closed");
  const closed = items.filter((s) => s.opportunity.status === "closed");

  async function handleTrack(opportunityId: string) {
    try {
      await createApplication.mutateAsync({ opportunity_id: opportunityId });
      navigate("/applications");
    } catch {
      navigate("/applications");
    }
  }

  return (
    <Page title="Saved opportunities">
      <Content width="wide">
        <header className="border-b border-rule pb-6">
          <div className="flex items-center gap-3 text-persimmon">
            <Bookmark size={24} />
            <h1 className="display text-[32px] text-ink sm:text-[44px]">Saved opportunities</h1>
          </div>
          <p className="mt-2 text-[15px] text-ink-soft">
            Opportunities you’ve bookmarked for this cycle. Set reminders and track your application checklists.
          </p>
        </header>

        {items.length === 0 ? (
          <div className="mt-12">
            <EmptyState
              icon={Bookmark}
              title="No saved opportunities yet"
              action={
                <Link to="/discover" className="btn btn-ink">
                  Discover opportunities
                </Link>
              }
            >
              When you find scholarships or fellowships you like, bookmark them to track deadlines and application steps.
            </EmptyState>
          </div>
        ) : (
          <div className="mt-8 space-y-12">
            {active.length > 0 && (
              <section aria-labelledby="active-saved-title">
                <h2 id="active-saved-title" className="text-[14px] font-semibold uppercase tracking-wider text-muted">
                  Open ({active.length})
                </h2>
                <ul className="mt-4 divide-y divide-rule rounded-panel border border-rule bg-paper">
                  {active.map(({ opportunity }) => {
                    const deadline = deadlineInfo(opportunity);
                    return (
                      <li key={opportunity.id} className="flex flex-col justify-between gap-4 p-5 sm:flex-row sm:items-center">
                        <div className="flex items-start gap-4">
                          <TypeTile type={opportunity.opportunity_type} host={opportunity.host_name} size={42} />
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="text-[12px] font-semibold uppercase tracking-wider text-muted">
                                {TYPE_LABELS[opportunity.opportunity_type]}
                              </span>
                              {opportunity.host_name && <span className="text-[13px] text-muted">• {opportunity.host_name}</span>}
                            </div>
                            <Link
                              to={`/opportunities/${opportunity.id}`}
                              className="mt-1 block text-[17px] font-semibold text-ink hover:text-persimmon"
                            >
                              {opportunity.title}
                            </Link>
                            <div className="mt-2 flex flex-wrap items-center gap-4 text-[13px] text-ink-soft">
                              <span className="flex items-center gap-1.5">
                                <Calendar size={14} className="text-muted" />
                                {deadline.label}
                                {deadline.relative && <span className="text-persimmon-deep">({deadline.relative})</span>}
                              </span>
                              <span className="flex items-center gap-1.5">
                                <MapPin size={14} className="text-muted" />
                                {locationText(opportunity)}
                              </span>
                            </div>
                          </div>
                        </div>

                        <div className="flex items-center gap-2.5 sm:shrink-0">
                          <button
                            type="button"
                            onClick={() => handleTrack(opportunity.id)}
                            className="btn btn-quiet inline-flex items-center gap-1.5 text-[13.5px]"
                          >
                            <FileCheck size={15} />
                            Track
                          </button>
                          <button
                            type="button"
                            onClick={() => unsave.mutate(opportunity.id)}
                            disabled={unsave.isPending}
                            className="btn btn-quiet text-muted hover:text-persimmon"
                            title="Remove from saved"
                          >
                            <BookmarkX size={16} />
                          </button>
                          <Link to={`/opportunities/${opportunity.id}`} className="btn btn-quiet">
                            <ChevronRight size={16} />
                          </Link>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </section>
            )}

            {closed.length > 0 && (
              <section aria-labelledby="closed-saved-title">
                <h2 id="closed-saved-title" className="text-[14px] font-semibold uppercase tracking-wider text-muted">
                  Closed cycles ({closed.length})
                </h2>
                <ul className="mt-4 divide-y divide-rule rounded-panel border border-rule bg-paper opacity-75">
                  {closed.map(({ opportunity }) => (
                    <li key={opportunity.id} className="flex flex-col justify-between gap-4 p-5 sm:flex-row sm:items-center">
                      <div className="flex items-start gap-4">
                        <TypeTile type={opportunity.opportunity_type} host={opportunity.host_name} size={42} />
                        <div>
                          <Link to={`/opportunities/${opportunity.id}`} className="text-[17px] font-semibold text-ink hover:underline">
                            {opportunity.title}
                          </Link>
                          <p className="mt-1 text-[13px] text-muted">Applications for this cycle have closed.</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => unsave.mutate(opportunity.id)}
                          className="btn btn-quiet text-muted hover:text-persimmon"
                        >
                          <BookmarkX size={16} />
                          Remove
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        )}
      </Content>
    </Page>
  );
}
