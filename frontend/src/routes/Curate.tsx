import {
  AlertCircle,
  Plus,
  Shield,
  ShieldAlert,
} from "lucide-react";
import { useState } from "react";
import {
  useAuditLog,
  useCloseOpportunity,
  useCreateOpportunity,
  useCuratorOpportunities,
  useCuratorSources,
  usePublishOpportunity,
  useUserAccount,
} from "../api/queries";
import { Content, Page } from "../components/layout/Page";
import { EmptyState, Spinner } from "../components/ui/States";
import { formatDate } from "../lib/format";

export function Curate() {
  const account = useUserAccount();
  const [tab, setTab] = useState<"opportunities" | "sources" | "audit">("opportunities");
  const [oppFilter, setOppFilter] = useState<string>("all");
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [publishError, setPublishError] = useState<string | null>(null);

  // Form states for new opportunity
  const [slug, setSlug] = useState("");
  const [title, setTitle] = useState("");
  const [oppType, setOppType] = useState<any>("fellowship");
  const [hostName, setHostName] = useState("");
  const [officialUrl, setOfficialUrl] = useState("");
  const [deadlineAt, setDeadlineAt] = useState("");

  const sources = useCuratorSources();
  const opportunities = useCuratorOpportunities(oppFilter);
  const auditLogs = useAuditLog();

  const createOpp = useCreateOpportunity();
  const publishOpp = usePublishOpportunity();
  const closeOpp = useCloseOpportunity();

  if (account.isPending) {
    return (
      <Content>
        <div className="flex min-h-[50vh] items-center justify-center text-muted">
          <Spinner />
        </div>
      </Content>
    );
  }

  const role = account.data?.role;
  const isAuthorized = role === "curator" || role === "admin";

  if (!isAuthorized) {
    return (
      <Page title="Restricted access">
        <Content>
          <div className="mt-12">
            <EmptyState
              icon={ShieldAlert}
              title="Curator access required"
              action={
                <a href="/discover" className="btn btn-ink">
                  Return to student discover
                </a>
              }
            >
              This workspace is restricted to authorized platform curators and administrators. Your current role is &ldquo;{role ?? "student"}&rdquo;.
            </EmptyState>
          </div>
        </Content>
      </Page>
    );
  }

  async function handleCreateOpp(e: React.FormEvent) {
    e.preventDefault();
    setPublishError(null);
    try {
      await createOpp.mutateAsync({
        slug: slug.trim(),
        title: title.trim(),
        opportunity_type: oppType,
        host_name: hostName.trim() || undefined,
        official_url: officialUrl.trim() ? (officialUrl.trim() as any) : undefined,
        deadline_type: "fixed",
        location_mode: "unknown",
        deadline_at: deadlineAt ? new Date(deadlineAt).toISOString() : undefined,
        status: "draft" as any,
      });
      setShowCreateForm(false);
      setSlug("");
      setTitle("");
      setHostName("");
      setOfficialUrl("");
      setDeadlineAt("");
    } catch (err: any) {
      setPublishError(err?.message ?? "Failed to create opportunity.");
    }
  }

  async function handlePublish(id: string) {
    setPublishError(null);
    try {
      await publishOpp.mutateAsync(id);
    } catch (err: any) {
      setPublishError(err?.message ?? "Publishing failed.");
    }
  }

  return (
    <Page title="Curator workspace">
      <Content width="wide">
        <header className="border-b border-rule pb-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 text-persimmon">
              <Shield size={26} />
              <h1 className="display text-[32px] text-ink sm:text-[44px]">Curator workspace</h1>
            </div>
            <span className="rounded-full bg-cream px-3 py-1 text-[13px] font-semibold text-ink-soft">
              Role: {role}
            </span>
          </div>
          <p className="mt-2 text-[15px] text-ink-soft">
            Manage acquisition sources, review verified opportunity drafts, and audit administrative actions.
          </p>

          <div className="mt-6 flex gap-2">
            <button
              type="button"
              onClick={() => setTab("opportunities")}
              className={`rounded-full px-4 py-1.5 text-[14px] font-medium transition-colors ${
                tab === "opportunities" ? "bg-ink text-paper" : "bg-cream text-ink-soft hover:bg-sand"
              }`}
            >
              Opportunities
            </button>
            <button
              type="button"
              onClick={() => setTab("sources")}
              className={`rounded-full px-4 py-1.5 text-[14px] font-medium transition-colors ${
                tab === "sources" ? "bg-ink text-paper" : "bg-cream text-ink-soft hover:bg-sand"
              }`}
            >
              Acquisition Sources
            </button>
            {role === "admin" && (
              <button
                type="button"
                onClick={() => setTab("audit")}
                className={`rounded-full px-4 py-1.5 text-[14px] font-medium transition-colors ${
                  tab === "audit" ? "bg-ink text-paper" : "bg-cream text-ink-soft hover:bg-sand"
                }`}
              >
                Audit Log
              </button>
            )}
          </div>
        </header>

        {publishError && (
          <div role="alert" className="mt-6 flex items-start gap-3 rounded-panel border border-persimmon/30 bg-persimmon/10 p-4 text-[14px] text-persimmon-deep">
            <AlertCircle size={18} className="mt-0.5 shrink-0" />
            <div>
              <p className="font-semibold">Action refused</p>
              <p className="mt-0.5">{publishError}</p>
            </div>
          </div>
        )}

        {/* Tab 1: Opportunities */}
        {tab === "opportunities" && (
          <section className="mt-8 space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex gap-2">
                {["all", "draft", "published", "closed"].map((st) => (
                  <button
                    key={st}
                    type="button"
                    onClick={() => setOppFilter(st)}
                    className={`rounded-full px-3 py-1 text-[13px] font-medium capitalize ${
                      oppFilter === st ? "bg-sand text-ink" : "bg-cream/60 text-muted"
                    }`}
                  >
                    {st}
                  </button>
                ))}
              </div>

              <button
                type="button"
                onClick={() => setShowCreateForm(!showCreateForm)}
                className="btn btn-ink inline-flex items-center gap-1.5 text-[13.5px]"
              >
                <Plus size={15} />
                {showCreateForm ? "Cancel" : "New Opportunity Draft"}
              </button>
            </div>

            {showCreateForm && (
              <form onSubmit={handleCreateOpp} className="rounded-panel border border-rule bg-paper p-6 shadow-card space-y-4">
                <h3 className="text-[16px] font-semibold text-ink">Create new opportunity draft</h3>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div>
                    <label htmlFor="opp-slug" className="block text-[13px] font-medium text-ink">Slug (lowercase with hyphens)</label>
                    <input
                      id="opp-slug"
                      required
                      type="text"
                      pattern="^[a-z0-9]+(?:-[a-z0-9]+)*$"
                      placeholder="e.g. kaust-vsrp-2027"
                      value={slug}
                      onChange={(e) => setSlug(e.target.value)}
                      className="input mt-1 w-full text-[13.5px]"
                    />
                  </div>
                  <div>
                    <label htmlFor="opp-title" className="block text-[13px] font-medium text-ink">Title</label>
                    <input
                      id="opp-title"
                      required
                      type="text"
                      placeholder="Official Opportunity Name"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      className="input mt-1 w-full text-[13.5px]"
                    />
                  </div>
                  <div>
                    <label htmlFor="opp-type" className="block text-[13px] font-medium text-ink">Type</label>
                    <select
                      id="opp-type"
                      value={oppType}
                      onChange={(e) => setOppType(e.target.value as any)}
                      className="input mt-1 w-full text-[13.5px]"
                    >
                      <option value="scholarship">Scholarship</option>
                      <option value="fellowship">Fellowship</option>
                      <option value="internship">Internship</option>
                      <option value="grant">Grant</option>
                      <option value="exchange">Exchange</option>
                      <option value="competition">Competition</option>
                      <option value="other">Other</option>
                    </select>
                  </div>
                  <div>
                    <label htmlFor="opp-host" className="block text-[13px] font-medium text-ink">Host Organization</label>
                    <input
                      id="opp-host"
                      type="text"
                      placeholder="e.g. Oxford University"
                      value={hostName}
                      onChange={(e) => setHostName(e.target.value)}
                      className="input mt-1 w-full text-[13.5px]"
                    />
                  </div>
                  <div>
                    <label htmlFor="opp-url" className="block text-[13px] font-medium text-ink">Official Page URL</label>
                    <input
                      id="opp-url"
                      type="url"
                      placeholder="https://..."
                      value={officialUrl}
                      onChange={(e) => setOfficialUrl(e.target.value)}
                      className="input mt-1 w-full text-[13.5px]"
                    />
                  </div>
                  <div>
                    <label htmlFor="opp-deadline" className="block text-[13px] font-medium text-ink">Application Deadline</label>
                    <input
                      id="opp-deadline"
                      type="datetime-local"
                      value={deadlineAt}
                      onChange={(e) => setDeadlineAt(e.target.value)}
                      className="input mt-1 w-full text-[13.5px]"
                    />
                  </div>
                </div>

                <div className="flex justify-end gap-2 pt-2">
                  <button type="submit" disabled={createOpp.isPending} className="btn btn-ink">
                    Save Draft
                  </button>
                </div>
              </form>
            )}

            {opportunities.isPending ? (
              <Spinner />
            ) : (
              <ul className="divide-y divide-rule rounded-panel border border-rule bg-paper">
                {(opportunities.data ?? []).map((opp) => (
                  <li key={opp.id} className="flex flex-col justify-between gap-4 p-5 sm:flex-row sm:items-center">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-[12px] font-semibold uppercase tracking-wider text-muted">
                          {opp.opportunity_type}
                        </span>
                        <span className="rounded-full bg-cream px-2.5 py-0.5 text-[11px] font-bold uppercase text-ink">
                          {opp.status}
                        </span>
                      </div>
                      <a href={`/opportunities/${opp.id}`} className="mt-1 block text-[17px] font-semibold text-ink hover:underline">
                        {opp.title}
                      </a>
                      <p className="text-[12.5px] text-muted">Slug: {opp.slug} {opp.host_name ? `• ${opp.host_name}` : ""}</p>
                    </div>

                    <div className="flex items-center gap-2">
                      {opp.status !== "published" && (
                        <button
                          type="button"
                          onClick={() => handlePublish(opp.id)}
                          disabled={publishOpp.isPending}
                          className="btn btn-ink text-[13px] py-1.5"
                          title="Requires at least 1 verified source & quoted rule"
                        >
                          Verify & Publish
                        </button>
                      )}
                      {opp.status === "published" && (
                        <button
                          type="button"
                          onClick={() => closeOpp.mutate(opp.id)}
                          disabled={closeOpp.isPending}
                          className="btn btn-quiet text-[13px] py-1.5 text-muted hover:text-persimmon"
                        >
                          Close Cycle
                        </button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {/* Tab 2: Sources */}
        {tab === "sources" && (
          <section className="mt-8 space-y-4">
            <h2 className="text-[16px] font-semibold text-ink">Acquisition Source Registry</h2>
            {sources.isPending ? (
              <Spinner />
            ) : (
              <div className="overflow-x-auto rounded-panel border border-rule bg-paper">
                <table className="w-full text-left text-[13.5px]">
                  <thead className="border-b border-rule bg-cream/40 text-[12px] uppercase text-muted">
                    <tr>
                      <th className="px-4 py-3">Source Name</th>
                      <th className="px-4 py-3">Base Domain</th>
                      <th className="px-4 py-3">Authority</th>
                      <th className="px-4 py-3">Discovery</th>
                      <th className="px-4 py-3">Robots.txt</th>
                      <th className="px-4 py-3">Terms</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3">Publish Mode</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-rule">
                    {(sources.data ?? []).map((src) => (
                      <tr key={src.id} className="hover:bg-cream/20">
                        <td className="px-4 py-3 font-semibold text-ink">{src.name}</td>
                        <td className="px-4 py-3 font-mono text-[12.5px] text-muted">{src.base_domain}</td>
                        <td className="px-4 py-3 capitalize">{src.authority_level}</td>
                        <td className="px-4 py-3 capitalize">{src.discovery_method}</td>
                        <td className="px-4 py-3">
                          <span
                            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${
                              src.robots_status === "allowed"
                                ? "bg-emerald-100 text-emerald-800"
                                : src.robots_status === "disallowed"
                                ? "bg-red-100 text-red-800"
                                : "bg-gray-100 text-gray-800"
                            }`}
                          >
                            {src.robots_status}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${
                              src.terms_status === "acceptable"
                                ? "bg-emerald-100 text-emerald-800"
                                : "bg-amber-100 text-amber-800"
                            }`}
                          >
                            {src.terms_status}
                          </span>
                        </td>
                        <td className="px-4 py-3 capitalize font-medium">{src.status}</td>
                        <td className="px-4 py-3 font-mono text-[12px]">{src.publish_mode}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}

        {/* Tab 3: Audit Log (Admins) */}
        {tab === "audit" && role === "admin" && (
          <section className="mt-8 space-y-4">
            <h2 className="text-[16px] font-semibold text-ink">Administrative & Privileged Audit Log</h2>
            {auditLogs.isPending ? (
              <Spinner />
            ) : (
              <div className="overflow-x-auto rounded-panel border border-rule bg-paper">
                <table className="w-full text-left text-[13.5px]">
                  <thead className="border-b border-rule bg-cream/40 text-[12px] uppercase text-muted">
                    <tr>
                      <th className="px-4 py-3">Timestamp</th>
                      <th className="px-4 py-3">Action</th>
                      <th className="px-4 py-3">Target Type</th>
                      <th className="px-4 py-3">Target ID</th>
                      <th className="px-4 py-3">Actor Kind</th>
                      <th className="px-4 py-3">Summary</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-rule font-mono text-[12.5px]">
                    {(auditLogs.data ?? []).map((entry) => (
                      <tr key={entry.id} className="hover:bg-cream/20">
                        <td className="px-4 py-3 text-muted">{formatDate(entry.occurred_at)}</td>
                        <td className="px-4 py-3 font-semibold text-ink">{entry.action}</td>
                        <td className="px-4 py-3 text-ink-soft">{entry.target_type}</td>
                        <td className="px-4 py-3 truncate max-w-[120px] text-muted">{entry.target_id}</td>
                        <td className="px-4 py-3 uppercase text-[11px] font-bold text-muted">{entry.actor_kind}</td>
                        <td className="px-4 py-3 truncate max-w-[200px] text-muted">
                          {JSON.stringify(entry.changes)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}
      </Content>
    </Page>
  );
}
