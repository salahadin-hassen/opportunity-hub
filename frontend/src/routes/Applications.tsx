import {
  Calendar,
  CheckCircle2,
  Circle,
  Clock,
  FileCheck,
  Plus,
  Trash2,
} from "lucide-react";
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
import { Content, Page } from "../components/layout/Page";
import { EmptyState, ErrorState, Spinner } from "../components/ui/States";
import { TYPE_LABELS, deadlineInfo } from "../lib/format";

const STATUS_LABELS: Record<string, string> = {
  draft: "Draft",
  in_progress: "In progress",
  submitted: "Submitted",
  accepted: "Accepted",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-sand text-ink",
  in_progress: "bg-cobalt text-white",
  submitted: "bg-persimmon text-white",
  accepted: "bg-emerald-600 text-white",
  rejected: "bg-faint text-ink-soft",
  withdrawn: "bg-cream text-muted",
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
    await updateApp.mutateAsync({
      id: app.id,
      body: { notes },
    });
  }

  return (
    <Page title="Application tracking">
      <Content width="wide">
        <header className="border-b border-rule pb-6">
          <div className="flex items-center gap-3 text-cobalt">
            <FileCheck size={26} />
            <h1 className="display text-[32px] text-ink sm:text-[44px]">Application tracking</h1>
          </div>
          <p className="mt-2 text-[15px] text-ink-soft">
            Manage your materials, requirements, and target submission dates for every scholarship cycle.
          </p>

          <div className="mt-6 flex flex-wrap gap-2">
            {[
              { id: "all", label: `All (${counts.all ?? 0})` },
              { id: "draft", label: `Draft (${counts.draft ?? 0})` },
              { id: "in_progress", label: `In progress (${counts.in_progress ?? 0})` },
              { id: "submitted", label: `Submitted (${counts.submitted ?? 0})` },
              { id: "accepted", label: `Accepted (${counts.accepted ?? 0})` },
            ].map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setFilter(tab.id)}
                className={`rounded-full px-3.5 py-1 text-[13.5px] font-medium transition-colors ${
                  filter === tab.id ? "bg-ink text-paper" : "bg-cream text-ink-soft hover:bg-sand"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </header>

        {list.length === 0 ? (
          <div className="mt-12">
            <EmptyState
              icon={FileCheck}
              title="No applications tracked yet"
              action={
                <Link to="/discover" className="btn btn-ink">
                  Browse opportunities
                </Link>
              }
            >
              When you find an opportunity you want to apply for, click &ldquo;Track&rdquo; from the listing or details page to manage deadlines, notes, and checklist items.
            </EmptyState>
          </div>
        ) : filtered.length === 0 ? (
          <div className="mt-12 py-12 text-center text-muted">No applications in this category.</div>
        ) : (
          <div className="mt-8 space-y-8">
            {filtered.map((app) => {
              const deadline = deadlineInfo(app.opportunity);
              const items = app.items ?? [];
              const completedCount = items.filter((i) => i.status === "completed").length;

              return (
                <article key={app.id} className="rounded-panel border border-rule bg-paper p-6 shadow-card">
                  <div className="flex flex-col justify-between gap-4 border-b border-rule pb-5 lg:flex-row lg:items-center">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-[12px] font-semibold uppercase tracking-wider text-muted">
                          {TYPE_LABELS[app.opportunity.opportunity_type]}
                        </span>
                        {app.opportunity.host_name && <span className="text-[13px] text-muted">• {app.opportunity.host_name}</span>}
                      </div>
                      <Link
                        to={`/opportunities/${app.opportunity.id}`}
                        className="mt-1 block text-[20px] font-semibold text-ink hover:text-persimmon"
                      >
                        {app.opportunity.title}
                      </Link>
                      <div className="mt-2 flex items-center gap-4 text-[13px] text-ink-soft">
                        <span className="flex items-center gap-1.5">
                          <Calendar size={14} className="text-muted" />
                          Deadline: {deadline.label}
                        </span>
                        {app.target_date && (
                          <span className="flex items-center gap-1.5 text-persimmon-deep">
                            <Clock size={14} />
                            Target: {app.target_date}
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-3">
                      <select
                        value={app.status}
                        onChange={(e) => updateApp.mutate({ id: app.id, body: { status: e.target.value } })}
                        className={`rounded-full px-3 py-1.5 text-[13px] font-medium border border-transparent ${
                          STATUS_COLORS[app.status] ?? "bg-sand text-ink"
                        }`}
                      >
                        {Object.entries(STATUS_LABELS).map(([val, label]) => (
                          <option key={val} value={val} className="bg-paper text-ink">
                            {label}
                          </option>
                        ))}
                      </select>

                      <button
                        type="button"
                        onClick={() => {
                          if (confirm("Are you sure you want to stop tracking this application?")) {
                            deleteApp.mutate(app.id);
                          }
                        }}
                        className="btn btn-quiet text-muted hover:text-persimmon p-2"
                        title="Delete application"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>

                  {/* Checklist and Notes */}
                  <div className="mt-6 grid grid-cols-1 gap-8 md:grid-cols-2">
                    {/* Checklist section */}
                    <div>
                      <div className="flex items-center justify-between">
                        <h2 className="text-[14px] font-semibold uppercase tracking-wider text-muted">
                          Requirements & Checklist ({completedCount}/{items.length})
                        </h2>
                      </div>

                      <ul className="mt-3 space-y-2">
                        {items.map((item) => {
                          const isDone = item.status === "completed";
                          return (
                            <li
                              key={item.id}
                              className="group flex items-center justify-between gap-3 rounded-[8px] bg-cream/50 px-3 py-2 text-[14px]"
                            >
                              <button
                                type="button"
                                onClick={() =>
                                  updateItem.mutate({
                                    applicationId: app.id,
                                    itemId: item.id,
                                    body: { status: isDone ? "pending" : "completed" },
                                  })
                                }
                                className="flex items-center gap-2.5 text-left text-ink hover:text-persimmon"
                              >
                                {isDone ? (
                                  <CheckCircle2 size={18} className="text-emerald-600 shrink-0" />
                                ) : (
                                  <Circle size={18} className="text-muted shrink-0" />
                                )}
                                <span className={isDone ? "line-through text-muted" : "font-medium"}>{item.label}</span>
                              </button>

                              <button
                                type="button"
                                onClick={() => deleteItem.mutate({ applicationId: app.id, itemId: item.id })}
                                className="opacity-0 group-hover:opacity-100 text-muted hover:text-persimmon transition-opacity"
                                title="Remove item"
                              >
                                <Trash2 size={14} />
                              </button>
                            </li>
                          );
                        })}
                      </ul>

                      <div className="mt-3 flex gap-2">
                        <input
                          type="text"
                          placeholder="Add step or document (e.g. Transcript, Essay)..."
                          value={newItemLabel[app.id] ?? ""}
                          onChange={(e) => setNewItemLabel((prev) => ({ ...prev, [app.id]: e.target.value }))}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") handleAddItem(app.id);
                          }}
                          className="input text-[13.5px] py-1.5 flex-1"
                        />
                        <button
                          type="button"
                          onClick={() => handleAddItem(app.id)}
                          className="btn btn-quiet inline-flex items-center gap-1 text-[13px]"
                        >
                          <Plus size={15} />
                          Add
                        </button>
                      </div>
                    </div>

                    {/* Notes & Target Date section */}
                    <div className="flex flex-col">
                      <div className="flex items-center justify-between">
                        <h2 className="text-[14px] font-semibold uppercase tracking-wider text-muted">
                          Private notes & Target date
                        </h2>
                      </div>

                      <div className="mt-3 flex flex-col gap-3">
                        <div className="flex items-center gap-2 text-[13px] text-muted">
                          <label htmlFor={`target-${app.id}`}>Target submission date:</label>
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
                            className="input py-1 text-[13px]"
                          />
                        </div>

                        <textarea
                          placeholder="Add private application notes, advisor comments, portal links..."
                          value={editingNotes[app.id] ?? app.notes ?? ""}
                          onChange={(e) => setEditingNotes((prev) => ({ ...prev, [app.id]: e.target.value }))}
                          onBlur={() => handleSaveNotes(app)}
                          rows={3}
                          className="input text-[13.5px] p-2 resize-none"
                        />
                      </div>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </Content>
    </Page>
  );
}
