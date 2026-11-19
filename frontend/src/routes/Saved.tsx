import { AnimatePresence, motion } from "motion/react";
import { Bookmark, BookmarkX, FileCheck, Search } from "lucide-react";
import { Link, useNavigate } from "react-router";
import { useCreateApplication, useSavedOpportunities, useUnsaveOpportunity } from "../api/queries";
import type { SavedOpportunity } from "../api/types";
import { PageHeader } from "../components/layout/AppShell";
import { Content, Page } from "../components/layout/Page";
import { deadlineWords, locationText } from "../components/opportunities/OpportunityRow";
import { TypeLabel } from "../components/opportunities/TypeTile";
import { DateBlock } from "../components/ui/DateBlock";
import { EmptyState, ErrorState } from "../components/ui/States";
import { useToast } from "../components/ui/Toast";
import { deadlineInfo, plural } from "../lib/format";

function SavedRow({ entry, onTrack, onRemove, removing }: { entry: SavedOpportunity; onTrack: () => void; onRemove: () => void; removing: boolean }) {
  const { opportunity } = entry;
  const deadline = deadlineWords(opportunity);
  const closed = opportunity.status === "closed";
  return (
    <motion.li
      layout
      initial={false}
      exit={{ opacity: 0, x: -24, transition: { duration: 0.25 } }}
      className="group relative grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-3 py-5 sm:gap-x-5 md:grid-cols-[auto_minmax(0,1fr)_auto] md:items-center"
    >
      <DateBlock opportunity={opportunity} />
      <div className="min-w-0">
        <TypeLabel type={opportunity.opportunity_type} quiet />
        <h3 className="heading mt-1 text-[18px] leading-[1.2] text-ink">
          <Link to={`/opportunities/${opportunity.id}`} className="decoration-1 underline-offset-4 hover:underline">
            {opportunity.title}
          </Link>
        </h3>
        <p className="mt-1 truncate text-[13.5px] text-ink-soft">
          {opportunity.host_name}
          <span className="mx-1.5 text-faint" aria-hidden="true">
            ·
          </span>
          <span className="text-muted">{locationText(opportunity)}</span>
        </p>
        <p className={`mt-1.5 text-[12.5px] ${closed ? "text-muted" : deadline.urgent ? "font-semibold text-persimmon-deep" : "text-muted"}`}>
          {closed ? "Applications for this cycle have closed" : deadline.text}
        </p>
      </div>
      <div className="col-start-2 flex items-center gap-2 md:col-start-auto">
        {!closed && (
          <button type="button" onClick={onTrack} className="btn btn-quiet btn-sm">
            <FileCheck size={15} />
            Track application
          </button>
        )}
        <button type="button" onClick={onRemove} disabled={removing} className="btn btn-ghost btn-sm">
          <BookmarkX size={15} />
          Remove
          <span className="sr-only">{opportunity.title}</span>
        </button>
      </div>
    </motion.li>
  );
}

export function Saved() {
  const navigate = useNavigate();
  const saved = useSavedOpportunities();
  const unsave = useUnsaveOpportunity();
  const createApplication = useCreateApplication();
  const toast = useToast();

  const items = [...(saved.data ?? [])].sort((a, b) => deadlineInfo(a.opportunity).sortKey - deadlineInfo(b.opportunity).sortKey);
  const open = items.filter((entry) => entry.opportunity.status !== "closed");
  const closed = items.filter((entry) => entry.opportunity.status === "closed");
  const soon = open.filter((entry) => deadlineInfo(entry.opportunity).state === "soon").length;

  async function track(opportunityId: string) {
    try {
      await createApplication.mutateAsync({ opportunity_id: opportunityId });
    } catch {
      /* already tracked: the list opens either way */
    }
    navigate("/applications");
  }

  async function remove(entry: SavedOpportunity) {
    try {
      await unsave.mutateAsync(entry.opportunity_id);
      toast.show("Removed from your saved list");
    } catch {
      toast.show("That didn’t remove. Try again.", "error");
    }
  }

  return (
    <Page title="Saved">
      <Content width="wide">
        <PageHeader
          kicker="Your shortlist"
          title="Saved"
          description={
            saved.isSuccess && items.length > 0
              ? `${plural(open.length, "open opportunity", "open opportunities")}, soonest deadline first${soon ? `. ${soon} close${soon === 1 ? "s" : ""} within 30 days.` : "."}`
              : "Opportunities you’ve kept to come back to, ordered by deadline."
          }
          actions={
            items.length > 0 && (
              <Link to="/discover" className="btn btn-quiet">
                <Search size={15} />
                Find more
              </Link>
            )
          }
        />

        {saved.isPending ? (
          <ul className="mt-10 divide-y divide-rule border-t border-ink" aria-busy="true" aria-label="Loading saved opportunities">
            {Array.from({ length: 3 }, (_, index) => (
              <li key={index} className="flex gap-5 py-5">
                <div className="skeleton h-[68px] w-[60px] rounded-[10px]" />
                <div className="flex flex-1 flex-col gap-2 pt-1">
                  <div className="skeleton h-3 w-24" />
                  <div className="skeleton h-5 w-2/3" />
                  <div className="skeleton h-3 w-1/3" />
                </div>
              </li>
            ))}
          </ul>
        ) : saved.isError ? (
          <div className="mt-10">
            <ErrorState message="Your saved list couldn’t load." onRetry={() => saved.refetch()} />
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            icon={Bookmark}
            title="Nothing saved yet"
            action={
              <Link to="/discover" className="btn btn-ink">
                Browse opportunities
              </Link>
            }
          >
            Use the bookmark on any listing to keep it here, ordered by deadline. From here you can start tracking an application.
          </EmptyState>
        ) : (
          <div className="mt-10 space-y-14">
            {open.length > 0 && (
              <section aria-labelledby="open-title">
                <div className="flex items-baseline justify-between border-b border-ink pb-3">
                  <h2 id="open-title" className="heading text-[22px] text-ink">
                    Open
                  </h2>
                  <span className="num text-[13.5px] text-muted">{open.length}</span>
                </div>
                <ul className="divide-y divide-rule">
                  <AnimatePresence initial={false}>
                    {open.map((entry) => (
                      <SavedRow key={entry.opportunity_id} entry={entry} onTrack={() => track(entry.opportunity_id)} onRemove={() => remove(entry)} removing={unsave.isPending} />
                    ))}
                  </AnimatePresence>
                </ul>
              </section>
            )}
            {closed.length > 0 && (
              <section aria-labelledby="closed-title">
                <div className="flex items-baseline justify-between border-b border-rule-strong pb-3">
                  <h2 id="closed-title" className="heading text-[22px] text-ink-soft">
                    Closed this cycle
                  </h2>
                  <span className="num text-[13.5px] text-muted">{closed.length}</span>
                </div>
                <ul className="divide-y divide-rule opacity-80">
                  <AnimatePresence initial={false}>
                    {closed.map((entry) => (
                      <SavedRow key={entry.opportunity_id} entry={entry} onTrack={() => track(entry.opportunity_id)} onRemove={() => remove(entry)} removing={unsave.isPending} />
                    ))}
                  </AnimatePresence>
                </ul>
              </section>
            )}
          </div>
        )}
      </Content>
    </Page>
  );
}
