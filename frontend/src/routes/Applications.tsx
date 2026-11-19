import { FileCheck, Plus, Trash2, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import {
  useApplications,
  useCreateApplicationItem,
  useDeleteApplication,
  useDeleteApplicationItem,
  useUpdateApplication,
  useUpdateApplicationItem,
} from "../api/queries";
import type { Application } from "../api/types";
import { PageHeader } from "../components/layout/AppShell";
import { Content, Page } from "../components/layout/Page";
import { deadlineWords } from "../components/opportunities/OpportunityRow";
import { TypeLabel } from "../components/opportunities/TypeTile";
import { DateBlock } from "../components/ui/DateBlock";
import { Sheet } from "../components/ui/Sheet";
import { EmptyState, ErrorState, Spinner } from "../components/ui/States";
import { useToast } from "../components/ui/Toast";
import { formatPlainDate } from "../lib/format";

const STATUS_LABELS: Record<string, string> = {
  draft: "Draft",
  in_progress: "In progress",
  submitted: "Submitted",
  accepted: "Accepted",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

/** Status as a dot plus words, in system colours: never colour alone. */
const STATUS_DOT: Record<string, string> = {
  draft: "bg-faint",
  in_progress: "bg-cobalt",
  submitted: "bg-persimmon",
  accepted: "bg-eligible",
  rejected: "bg-ineligible",
  withdrawn: "bg-rule-strong",
};

export function Applications() {
  const applications = useApplications();
  const updateApp = useUpdateApplication();
  const deleteApp = useDeleteApplication();
  const createItem = useCreateApplicationItem();
  const updateItem = useUpdateApplicationItem();
  const deleteItem = useDeleteApplicationItem();

  const [filter, setFilter] = useState<string>("all");
  const [newItemLabel, setNewItemLabel] = useState<Record<string, string>>({});
  const [editingNotes, setEditingNotes] = useState<Record<string, string>>({});
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  // Ticks show at once; the server's answer replaces them, and a failure puts them back.
  const [optimistic, setOptimistic] = useState<Record<string, string>>({});
  const toast = useToast();

  if (applications.isPending) {
    return (
      <Content>
        <div className="flex min-h-[50vh] items-center justify-center text-muted">
          <Spinner />
        </div>
      </Content>
    );
  }

  if (applications.isError) {
    return (
      <Content>
        <ErrorState message="Could not load your applications." onRetry={() => applications.refetch()} />
      </Content>
    );
  }

  const list = applications.data ?? [];
  const filtered = filter === "all" ? list : list.filter((a) => a.status === filter);

  const counts: Record<string, number> = {
    all: list.length,
    draft: list.filter((a) => a.status === "draft").length,
    in_progress: list.filter((a) => a.status === "in_progress").length,
    submitted: list.filter((a) => a.status === "submitted").length,
    accepted: list.filter((a) => a.status === "accepted").length,
  };

  async function handleAddItem(appId: string) {
    const label = (newItemLabel[appId] ?? "").trim();
    if (!label) return;
    await createItem.mutateAsync({
      applicationId: appId,
      body: { label, order_index: 0 },
    });
    setNewItemLabel((prev) => ({ ...prev, [appId]: "" }));
  }

  async function handleSaveNotes(app: Application) {
    const notes = editingNotes[app.id] ?? app.notes ?? "";
    if (notes === (app.notes ?? "")) return;
    try {
      await updateApp.mutateAsync({
        id: app.id,
        body: { notes },
      });
      toast.show("Notes saved");
    } catch {
      toast.show("Your notes didn’t save. Try again.", "error");
    }
  }

  const pendingDelete = list.find((app) => app.id === confirmDelete);

  return (
    <Page title="Applications">
      <Content width="wide">
        <PageHeader
          kicker="Your tracker"
          title="Applications"
          description="Steps, documents, a target date and private notes for each application you’re preparing. Only you can see them."
          actions={
            list.length > 0 && (
              <Link to="/saved" className="btn btn-quiet">
                From your saved list
              </Link>
            )
          }
        />

        {list.length > 0 && (
          <div role="group" aria-label="Filter by status" className="-mx-4 mt-8 flex gap-6 overflow-x-auto border-b border-rule px-4 [scrollbar-width:none] sm:mx-0 sm:px-0">
            {[
              { id: "all", label: "All" },
              { id: "draft", label: "Draft" },
              { id: "in_progress", label: "In progress" },
              { id: "submitted", label: "Submitted" },
              { id: "accepted", label: "Accepted" },
            ].map((tab) => (
              <button key={tab.id} type="button" aria-pressed={filter === tab.id} onClick={() => setFilter(tab.id)} className="index-tab">
                {tab.label}
                <span className="count">{counts[tab.id] ?? 0}</span>
                {filter === tab.id && <span className="absolute inset-x-0 -bottom-px h-[2px] bg-ink" aria-hidden="true" />}
              </button>
            ))}
          </div>
        )}

        {list.length === 0 ? (
          <EmptyState
            icon={FileCheck}
            title="No applications yet"
            action={
              <>
                <Link to="/saved" className="btn btn-ink">
                  Open your saved list
                </Link>
                <Link to="/discover" className="btn btn-quiet">
                  Browse opportunities
                </Link>
              </>
            }
          >
            Choose <span className="font-semibold text-ink">Track my application</span> on any opportunity to start a checklist, set a target date and keep notes here.
          </EmptyState>
        ) : filtered.length === 0 ? (
          <p className="mt-10 text-[15px] text-muted">No applications with this status.</p>
        ) : (
          <div className="mt-8 space-y-6">
            {filtered.map((app) => {
              const deadline = deadlineWords(app.opportunity);
              const items = app.items ?? [];
              const completedCount = items.filter((i) => (optimistic[i.id] ?? i.status) === "completed").length;
              const percent = items.length ? Math.round((completedCount / items.length) * 100) : 0;

              return (
                <article key={app.id} aria-labelledby={`app-${app.id}`} className="rounded-panel border border-rule bg-paper">
                  <div className="flex flex-col gap-5 border-b border-rule p-5 sm:p-6 lg:flex-row lg:items-start lg:justify-between">
                    <div className="flex min-w-0 gap-4">
                      <DateBlock opportunity={app.opportunity} />
                      <div className="min-w-0">
                        <p className="text-[12.5px] text-muted">
                          <TypeLabel type={app.opportunity.opportunity_type} quiet />
                          {app.opportunity.host_name && <span> · {app.opportunity.host_name}</span>}
                        </p>
                        <h2 id={`app-${app.id}`} className="heading mt-1 text-[20px] leading-[1.2] text-ink">
                          <Link to={`/opportunities/${app.opportunity.id}`} className="decoration-1 underline-offset-4 hover:underline">
                            {app.opportunity.title}
                          </Link>
                        </h2>
                        <p className={`mt-1.5 text-[13px] ${deadline.urgent ? "font-semibold text-persimmon-deep" : "text-muted"}`}>
                          {deadline.text}
                          {app.target_date && <span className="font-normal text-ink-soft"> · your target {formatPlainDate(app.target_date)}</span>}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-end gap-2">
                      <div>
                        <label htmlFor={`status-${app.id}`} className="field-label">
                          Status
                        </label>
                        <div className="relative">
                          <span className={`pointer-events-none absolute left-3 top-1/2 size-2 -translate-y-1/2 rounded-full ${STATUS_DOT[app.status] ?? "bg-faint"}`} aria-hidden="true" />
                          <select
                            id={`status-${app.id}`}
                            value={app.status}
                            onChange={(e) => updateApp.mutate({ id: app.id, body: { status: e.target.value } })}
                            className="input h-10 w-44 pl-7 text-[14px]"
                          >
                            {Object.entries(STATUS_LABELS).map(([val, label]) => (
                              <option key={val} value={val}>
                                {label}
                              </option>
                            ))}
                          </select>
                        </div>
                      </div>
                      <button type="button" onClick={() => setConfirmDelete(app.id)} className="icon-btn" aria-label={`Stop tracking ${app.opportunity.title}`} title="Stop tracking">
                        <Trash2 size={17} />
                      </button>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-8 p-5 sm:p-6 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
                    <section aria-labelledby={`steps-${app.id}`}>
                      <div className="flex items-baseline justify-between">
                        <h3 id={`steps-${app.id}`} className="eyebrow">
                          Steps and documents
                        </h3>
                        <span className="num text-[13px] text-muted">
                          {completedCount} of {items.length} done
                        </span>
                      </div>
                      <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-cream" role="progressbar" aria-label="Steps done" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
                        <div className="h-full rounded-full bg-eligible transition-[width] duration-500" style={{ width: `${percent}%` }} />
                      </div>

                      {items.length > 0 && (
                        <ul className="mt-3 divide-y divide-rule">
                          {items.map((item) => {
                            const isDone = (optimistic[item.id] ?? item.status) === "completed";
                            return (
                              <li key={item.id} className="flex items-center gap-3 py-1.5">
                                <label className="flex min-h-10 flex-1 cursor-pointer items-center gap-3 text-[14.5px]">
                                  <input
                                    type="checkbox"
                                    checked={isDone}
                                    onChange={() => {
                                      const status = isDone ? "pending" : "completed";
                                      setOptimistic((prev) => ({ ...prev, [item.id]: status }));
                                      updateItem.mutate(
                                        { applicationId: app.id, itemId: item.id, body: { status } },
                                        {
                                          onError: () => toast.show("That step didn’t update. Try again.", "error"),
                                          onSettled: () =>
                                            setOptimistic((prev) => {
                                              const next = { ...prev };
                                              delete next[item.id];
                                              return next;
                                            }),
                                        },
                                      );
                                    }}
                                    className="size-[18px] shrink-0 accent-[var(--color-eligible)]"
                                  />
                                  <span className={isDone ? "text-muted line-through decoration-1" : "text-ink"}>{item.label}</span>
                                </label>
                                <button
                                  type="button"
                                  onClick={() => deleteItem.mutate({ applicationId: app.id, itemId: item.id })}
                                  className="icon-btn size-9 text-muted"
                                  aria-label={`Remove step: ${item.label}`}
                                >
                                  <X size={15} />
                                </button>
                              </li>
                            );
                          })}
                        </ul>
                      )}

                      <form
                        className="mt-3 flex gap-2"
                        onSubmit={(event) => {
                          event.preventDefault();
                          handleAddItem(app.id);
                        }}
                      >
                        <label htmlFor={`new-step-${app.id}`} className="sr-only">
                          Add a step or document
                        </label>
                        <input
                          id={`new-step-${app.id}`}
                          type="text"
                          placeholder="Add a step, e.g. Transcript"
                          value={newItemLabel[app.id] ?? ""}
                          onChange={(e) => setNewItemLabel((prev) => ({ ...prev, [app.id]: e.target.value }))}
                          className="input h-10 flex-1 text-[14px]"
                        />
                        <button type="submit" className="btn btn-quiet h-10" disabled={!(newItemLabel[app.id] ?? "").trim() || createItem.isPending}>
                          <Plus size={15} />
                          Add
                        </button>
                      </form>
                    </section>

                    <section aria-labelledby={`notes-${app.id}`} className="flex flex-col gap-4">
                      <h3 id={`notes-${app.id}`} className="eyebrow">
                        Your plan
                      </h3>
                      <div>
                        <label htmlFor={`target-${app.id}`} className="field-label">
                          Target submission date
                        </label>
                        <input
                          id={`target-${app.id}`}
                          type="date"
                          defaultValue={app.target_date ?? ""}
                          onChange={(e) =>
                            updateApp.mutate({
                              id: app.id,
                              body: { target_date: e.target.value || null },
                            })
                          }
                          className="input h-10 text-[14px] sm:w-56"
                        />
                      </div>
                      <div>
                        <label htmlFor={`notes-field-${app.id}`} className="field-label">
                          Private notes
                        </label>
                        <textarea
                          id={`notes-field-${app.id}`}
                          placeholder="Advisor comments, portal links, reminders"
                          value={editingNotes[app.id] ?? app.notes ?? ""}
                          onChange={(e) => setEditingNotes((prev) => ({ ...prev, [app.id]: e.target.value }))}
                          onBlur={() => handleSaveNotes(app)}
                          rows={4}
                          className="input resize-y text-[14px]"
                          aria-describedby={`notes-hint-${app.id}`}
                        />
                        <p id={`notes-hint-${app.id}`} className="mt-1.5 text-[12.5px] text-muted">
                          Saved when you leave the field.
                        </p>
                      </div>
                    </section>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </Content>

      <Sheet
        open={Boolean(pendingDelete)}
        onClose={() => setConfirmDelete(null)}
        title="Stop tracking this application?"
        placement="center"
        footer={
          <div className="flex justify-end gap-2">
            <button type="button" className="btn btn-ghost" onClick={() => setConfirmDelete(null)}>
              Keep it
            </button>
            <button
              type="button"
              className="btn bg-ineligible text-white hover:bg-ineligible-ink"
              onClick={() => {
                if (pendingDelete) deleteApp.mutate(pendingDelete.id);
                setConfirmDelete(null);
              }}
            >
              Stop tracking
            </button>
          </div>
        }
      >
        <p className="text-[15px] text-ink-soft">
          Its steps, target date and notes for <span className="font-semibold text-ink">{pendingDelete?.opportunity.title}</span> will be deleted. The opportunity itself stays in the index.
        </p>
      </Sheet>
    </Page>
  );
}
