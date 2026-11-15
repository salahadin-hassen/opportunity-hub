import {
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  ExternalLink,
  Plus,
  RefreshCw,
  Shield,
  ShieldAlert,
  X,
  XCircle,
} from "lucide-react";
import { useEffect, useState } from "react";
import {
  useAuditLog,
  useCandidateDetail,
  useCloseOpportunity,
  useCreateOpportunity,
  useCuratorCandidates,
  useCuratorOpportunities,
  useCuratorSources,
  usePublishOpportunity,
  useRequeueCandidate,
  useReviewCandidate,
  useUserAccount,
} from "../api/queries";
import { Content, Page } from "../components/layout/Page";
import { EmptyState, Spinner } from "../components/ui/States";
import { formatDate } from "../lib/format";

export function Curate() {
  const account = useUserAccount();
  const [tab, setTab] = useState<"opportunities" | "candidates" | "sources" | "audit">("opportunities");
  const [oppFilter, setOppFilter] = useState<string>("all");
  const [candFilter, setCandFilter] = useState<string>("needs_review");
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [publishError, setPublishError] = useState<string | null>(null);

  // Review modal state
  const [reviewTitle, setReviewTitle] = useState("");
  const [reviewType, setReviewType] = useState<string>("scholarship");
  const [reviewDeadline, setReviewDeadline] = useState("");
  const [reviewDeadlineType, setReviewDeadlineType] = useState<"fixed" | "rolling" | "none">("fixed");
  const [reviewDescription, setReviewDescription] = useState("");
  const [reviewNotes, setReviewNotes] = useState("");
  const [reviewForce, setReviewForce] = useState(false);
  const [selectedStatements, setSelectedStatements] = useState<number[]>([]);
  const [reviewError, setReviewError] = useState<string | null>(null);

  // Form states for new opportunity
  const [slug, setSlug] = useState("");
  const [title, setTitle] = useState("");
  const [oppType, setOppType] = useState<any>("fellowship");
  const [hostName, setHostName] = useState("");
  const [officialUrl, setOfficialUrl] = useState("");
  const [deadlineAt, setDeadlineAt] = useState("");

  const sources = useCuratorSources();
  const opportunities = useCuratorOpportunities(oppFilter);
  const candidates = useCuratorCandidates(candFilter);
  const candidateDetail = useCandidateDetail(selectedCandidateId);
  const auditLogs = useAuditLog();

  const createOpp = useCreateOpportunity();
  const publishOpp = usePublishOpportunity();
  const closeOpp = useCloseOpportunity();
  const reviewMutation = useReviewCandidate();
  const requeueMutation = useRequeueCandidate();

  useEffect(() => {
    if (candidateDetail.data) {
      const ext = (candidateDetail.data.extraction as any) || {};
      setReviewTitle(ext.title?.value || candidateDetail.data.title || "");
      setReviewType(ext.opportunity_type?.value || "scholarship");
      setReviewDeadline(ext.deadline?.value || "");
      const dt = ext.deadline_type?.value;
      setReviewDeadlineType(dt === "rolling" ? "rolling" : dt === "none" ? "none" : "fixed");
      setReviewDescription(ext.description?.value || "");
      setReviewNotes("");
      setReviewForce(false);
      setReviewError(null);
      const stmts: string[] = ext.eligibility?.value || [];
      setSelectedStatements(stmts.map((_, i) => i));
    }
  }, [candidateDetail.data]);

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

  async function handleApprove(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedCandidateId) return;
    setReviewError(null);
    try {
      await reviewMutation.mutateAsync({
        id: selectedCandidateId,
        body: {
          decision: "approve",
          title: reviewTitle.trim() || undefined,
          opportunity_type: reviewType || undefined,
          deadline: reviewDeadlineType === "fixed" && reviewDeadline ? reviewDeadline : undefined,
          deadline_type: reviewDeadlineType,
          description: reviewDescription.trim() || undefined,
          statements: selectedStatements.length > 0 ? selectedStatements : undefined,
          notes: reviewNotes.trim() || undefined,
          force: reviewForce,
        },
      });
      setSelectedCandidateId(null);
    } catch (err: any) {
      setReviewError(err?.message ?? "Approval failed.");
    }
  }

  async function handleReject(decision: "reject" | "request_changes") {
    if (!selectedCandidateId) return;
    setReviewError(null);
    try {
      await reviewMutation.mutateAsync({
        id: selectedCandidateId,
        body: {
          decision,
          notes: reviewNotes.trim() || undefined,
          force: false,
        },
      });
      setSelectedCandidateId(null);
    } catch (err: any) {
      setReviewError(err?.message ?? `${decision} failed.`);
    }
  }

  async function handleRequeue(id: string) {
    setReviewError(null);
    try {
      await requeueMutation.mutateAsync(id);
    } catch (err: any) {
      setReviewError(err?.message ?? "Re-queue failed.");
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
            Manage acquisition sources, review opportunity drafts, and audit administrative actions.
          </p>

          <div className="mt-6 flex flex-wrap gap-2">
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
              onClick={() => setTab("candidates")}
              className={`inline-flex items-center gap-1.5 rounded-full px-4 py-1.5 text-[14px] font-medium transition-colors ${
                tab === "candidates" ? "bg-ink text-paper" : "bg-cream text-ink-soft hover:bg-sand"
              }`}
            >
              Candidate Queue
              {candidates.data && candidates.data.filter((c) => c.state === "needs_review").length > 0 && (
                <span className="rounded-full bg-persimmon px-2 py-0.5 text-[11px] font-bold text-paper">
                  {candidates.data.filter((c) => c.state === "needs_review").length}
                </span>
              )}
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
                          title="Publishes only if the completeness checks pass: an official URL, a source record, and quoted mandatory rules citing it. Sources are not independently verified."
                        >
                          Check & publish
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

        {/* Tab 2: Candidate Review Queue */}
        {tab === "candidates" && (
          <section className="mt-8 space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex flex-wrap gap-2">
                {["needs_review", "all", "approved", "expired", "duplicate", "rejected", "changes_requested"].map((st) => (
                  <button
                    key={st}
                    type="button"
                    onClick={() => setCandFilter(st)}
                    className={`rounded-full px-3 py-1 text-[13px] font-medium capitalize transition-colors ${
                      candFilter === st ? "bg-sand text-ink font-semibold" : "bg-cream/60 text-muted hover:bg-cream"
                    }`}
                  >
                    {st.replace("_", " ")}
                  </button>
                ))}
              </div>
              <span className="text-[13px] text-muted">
                {candidates.data?.length ?? 0} candidate(s)
              </span>
            </div>

            {candidates.isPending ? (
              <Spinner />
            ) : (candidates.data ?? []).length === 0 ? (
              <div className="rounded-panel border border-rule bg-paper p-8 text-center text-muted">
                <p className="text-[15px] font-medium text-ink">No candidates in &ldquo;{candFilter.replace("_", " ")}&rdquo; state</p>
                <p className="mt-1 text-[13px]">Run discovery or ingestion to find opportunities on registered sources.</p>
              </div>
            ) : (
              <div className="overflow-x-auto rounded-panel border border-rule bg-paper shadow-card">
                <table className="w-full text-left text-[13.5px]">
                  <thead className="border-b border-rule bg-cream/40 text-[12px] uppercase text-muted">
                    <tr>
                      <th className="px-4 py-3">Candidate / Title</th>
                      <th className="px-4 py-3">Source</th>
                      <th className="px-4 py-3">State</th>
                      <th className="px-4 py-3">Quality</th>
                      <th className="px-4 py-3">Deadline</th>
                      <th className="px-4 py-3">Signals</th>
                      <th className="px-4 py-3 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-rule">
                    {(candidates.data ?? []).map((cand) => (
                      <tr key={cand.id} className="hover:bg-cream/20">
                        <td className="px-4 py-3 max-w-[280px]">
                          <p className="font-semibold text-ink truncate" title={cand.title || cand.url}>
                            {cand.title || "(Untitled candidate)"}
                          </p>
                          <a
                            href={cand.url}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1 font-mono text-[11.5px] text-persimmon hover:underline truncate max-w-full"
                          >
                            <span className="truncate">{cand.url}</span>
                            <ExternalLink size={11} className="shrink-0" />
                          </a>
                        </td>
                        <td className="px-4 py-3 text-ink-soft text-[13px]">
                          {cand.source_name || "—"}
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wider ${
                              cand.state === "approved"
                                ? "bg-emerald-100 text-emerald-800"
                                : cand.state === "needs_review"
                                ? "bg-amber-100 text-amber-900 border border-amber-300"
                                : cand.state === "duplicate"
                                ? "bg-purple-100 text-purple-800"
                                : cand.state === "expired"
                                ? "bg-rose-100 text-rose-800"
                                : "bg-gray-100 text-gray-700"
                            }`}
                          >
                            {cand.state.replace("_", " ")}
                          </span>
                        </td>
                        <td className="px-4 py-3 font-mono text-[12.5px]">
                          {cand.quality_score !== null && cand.quality_score !== undefined ? (
                            <span
                              className={`font-semibold ${
                                cand.quality_score >= 70
                                  ? "text-emerald-700"
                                  : cand.quality_score >= 40
                                  ? "text-amber-700"
                                  : "text-rose-700"
                              }`}
                            >
                              {cand.quality_score}%
                            </span>
                          ) : (
                            <span className="text-muted">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-[12.5px] text-ink-soft">
                          {cand.deadline ? String(cand.deadline) : "—"}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex flex-col gap-0.5 text-[11.5px]">
                            {cand.duplicate_of_opportunity_id && (
                              <span className="text-purple-700 font-medium">Opp duplicate</span>
                            )}
                            {cand.duplicate_of_candidate_id && (
                              <span className="text-purple-700 font-medium">Cand duplicate</span>
                            )}
                            {cand.problems && cand.problems.length > 0 && (
                              <span className="text-amber-700">{cand.problems.length} issue(s)</span>
                            )}
                            {!cand.duplicate_of_opportunity_id && !cand.duplicate_of_candidate_id && (!cand.problems || cand.problems.length === 0) && (
                              <span className="text-emerald-700 font-medium">Clean</span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <button
                            type="button"
                            onClick={() => setSelectedCandidateId(cand.id)}
                            className="btn btn-sm btn-ink inline-flex items-center gap-1 text-[12px] py-1 px-3"
                          >
                            Review
                            <ChevronRight size={13} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Review Candidate Modal / Panel */}
            {selectedCandidateId && (
              <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/50 p-4 backdrop-blur-xs">
                <div
                  role="dialog"
                  aria-modal="true"
                  aria-labelledby="candidate-review-heading"
                  className="relative max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-panel border border-rule bg-paper p-6 shadow-2xl space-y-6"
                >
                  <div className="flex items-start justify-between gap-4 border-b border-rule pb-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="rounded-full bg-cream px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wider text-ink">
                          {candidateDetail.data?.state.replace("_", " ")}
                        </span>
                        <span className="text-[13px] text-muted">
                          Source: {candidateDetail.data?.source_name ?? "—"}
                        </span>
                      </div>
                      <h2 id="candidate-review-heading" className="mt-1 text-[20px] font-bold text-ink">
                        Review Ingestion Candidate
                      </h2>
                      <a
                        href={candidateDetail.data?.final_url || candidateDetail.data?.url}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-1 inline-flex items-center gap-1 text-[13px] text-persimmon hover:underline font-mono"
                      >
                        {candidateDetail.data?.final_url || candidateDetail.data?.url}
                        <ExternalLink size={13} />
                      </a>
                    </div>
                    <button
                      type="button"
                      onClick={() => setSelectedCandidateId(null)}
                      aria-label="Close review"
                      className="rounded-full p-1.5 text-muted hover:bg-cream hover:text-ink transition-colors"
                    >
                      <X size={20} />
                    </button>
                  </div>

                  {candidateDetail.isPending ? (
                    <div className="flex justify-center py-12">
                      <Spinner />
                    </div>
                  ) : (
                    <form onSubmit={handleApprove} className="space-y-6">
                      {reviewError && (
                        <div role="alert" className="flex items-start gap-3 rounded-panel border border-persimmon/30 bg-persimmon/10 p-4 text-[13.5px] text-persimmon-deep">
                          <AlertCircle size={18} className="mt-0.5 shrink-0" />
                          <div>
                            <p className="font-semibold">Review Error</p>
                            <p className="mt-0.5">{reviewError}</p>
                          </div>
                        </div>
                      )}

                      {/* Warnings / Duplicate Banner */}
                      {(candidateDetail.data?.duplicate_of_opportunity_id || candidateDetail.data?.duplicate_of_candidate_id) && (
                        <div className="rounded-panel border border-purple-300 bg-purple-50 p-4 text-[13px] text-purple-900">
                          <p className="font-bold">Duplicate Warning</p>
                          <p className="mt-0.5">
                            This candidate matches an existing opportunity or candidate cycle. Check whether this is a recurring new cycle or a duplicate. If approving, check &ldquo;Force approve override&rdquo;.
                          </p>
                        </div>
                      )}

                      {/* What was fetched, and what the pipeline could and could not support with a quote */}
                      <CandidateEvidence candidate={candidateDetail.data} />

                      {/* Extracted Fields */}
                      <div className="space-y-4 rounded-panel border border-rule bg-cream/20 p-5">
                        <h3 className="text-[15px] font-bold text-ink">1. Extracted Details</h3>
                        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                          <div className="sm:col-span-2">
                            <label htmlFor="cand-title" className="block text-[12.5px] font-medium text-ink">Title</label>
                            <input
                              id="cand-title"
                              required
                              type="text"
                              value={reviewTitle}
                              onChange={(e) => setReviewTitle(e.target.value)}
                              className="input mt-1 w-full text-[13.5px]"
                              placeholder="Programme title"
                            />
                          </div>

                          <div>
                            <label htmlFor="cand-type" className="block text-[12.5px] font-medium text-ink">Opportunity Type</label>
                            <select
                              id="cand-type"
                              value={reviewType}
                              onChange={(e) => setReviewType(e.target.value)}
                              className="input mt-1 w-full text-[13.5px]"
                            >
                              <option value="scholarship">Scholarship</option>
                              <option value="fellowship">Fellowship</option>
                              <option value="internship">Internship</option>
                              <option value="research_program">Research Program</option>
                              <option value="summer_school">Summer School</option>
                              <option value="competition">Competition</option>
                              <option value="grant">Grant</option>
                              <option value="other">Other</option>
                            </select>
                          </div>

                          <div>
                            <label htmlFor="cand-deadline-type" className="block text-[12.5px] font-medium text-ink">Deadline Type</label>
                            <select
                              id="cand-deadline-type"
                              value={reviewDeadlineType}
                              onChange={(e) => setReviewDeadlineType(e.target.value as any)}
                              className="input mt-1 w-full text-[13.5px]"
                            >
                              <option value="fixed">Fixed date</option>
                              <option value="rolling">Rolling (open)</option>
                              <option value="none">None / Open-ended</option>
                            </select>
                          </div>

                          {reviewDeadlineType === "fixed" && (
                            <div>
                              <label htmlFor="cand-deadline" className="block text-[12.5px] font-medium text-ink">Deadline Date (YYYY-MM-DD)</label>
                              <input
                                id="cand-deadline"
                                required
                                type="date"
                                value={reviewDeadline}
                                onChange={(e) => setReviewDeadline(e.target.value)}
                                className="input mt-1 w-full text-[13.5px]"
                              />
                            </div>
                          )}

                          <div className="sm:col-span-2">
                            <label htmlFor="cand-description" className="block text-[12.5px] font-medium text-ink">Description</label>
                            <textarea
                              id="cand-description"
                              rows={3}
                              value={reviewDescription}
                              onChange={(e) => setReviewDescription(e.target.value)}
                              className="input mt-1 w-full text-[13.5px]"
                              placeholder="Official description quoted from the source page"
                            />
                          </div>
                        </div>
                      </div>

                      {/* Quoted Verbatim Eligibility Statements */}
                      <div className="space-y-3 rounded-panel border border-rule bg-cream/20 p-5">
                        <div className="flex items-center justify-between">
                          <div>
                            <h3 className="text-[15px] font-bold text-ink">2. Verbatim Quoted Eligibility Statements</h3>
                            <p className="text-[12px] text-muted">
                              Every kept statement is verified against the page text and becomes a quoted rule. Publication requires at least one quote.
                            </p>
                          </div>
                          <span className="text-[12px] font-semibold text-persimmon">
                            {selectedStatements.length} selected
                          </span>
                        </div>

                        {((candidateDetail.data?.extraction as any)?.eligibility?.value ?? []).length === 0 ? (
                          <p className="text-[13px] text-muted italic">No explicit eligibility statements extracted from this page.</p>
                        ) : (
                          <div className="space-y-2 max-h-[220px] overflow-y-auto">
                            {((candidateDetail.data?.extraction as any)?.eligibility?.value as string[]).map((stmt, idx) => (
                              <label
                                key={idx}
                                className={`flex items-start gap-3 rounded-lg border p-3 text-[13px] cursor-pointer transition-colors ${
                                  selectedStatements.includes(idx)
                                    ? "border-ink bg-paper shadow-xs"
                                    : "border-rule bg-cream/40 opacity-70"
                                }`}
                              >
                                <input
                                  type="checkbox"
                                  checked={selectedStatements.includes(idx)}
                                  onChange={(e) => {
                                    if (e.target.checked) {
                                      setSelectedStatements([...selectedStatements, idx]);
                                    } else {
                                      setSelectedStatements(selectedStatements.filter((i) => i !== idx));
                                    }
                                  }}
                                  className="mt-0.5"
                                />
                                <span className="font-serif italic text-ink leading-relaxed">&ldquo;{stmt}&rdquo;</span>
                              </label>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Curator Notes & Overrides */}
                      <div className="space-y-3 rounded-panel border border-rule bg-cream/20 p-5">
                        <h3 className="text-[15px] font-bold text-ink">3. Review Audit & Decisions</h3>
                        <div>
                          <label htmlFor="cand-notes" className="block text-[12.5px] font-medium text-ink">Curator Review Notes</label>
                          <input
                            id="cand-notes"
                            type="text"
                            value={reviewNotes}
                            onChange={(e) => setReviewNotes(e.target.value)}
                            placeholder="Reason for decision / audit comments"
                            className="input mt-1 w-full text-[13.5px]"
                          />
                        </div>

                        {(candidateDetail.data?.state === "expired" || candidateDetail.data?.state === "duplicate") && (
                          <label className="flex items-center gap-2 text-[13px] font-medium text-persimmon-deep cursor-pointer">
                            <input
                              type="checkbox"
                              checked={reviewForce}
                              onChange={(e) => setReviewForce(e.target.checked)}
                            />
                            Force approve override (approves an expired or duplicate candidate into a draft)
                          </label>
                        )}
                      </div>

                      {/* Action buttons */}
                      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-rule pt-4">
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => handleReject("reject")}
                            disabled={reviewMutation.isPending}
                            className="btn btn-sm btn-quiet text-persimmon hover:bg-persimmon/10"
                          >
                            <XCircle size={15} />
                            Reject
                          </button>
                          <button
                            type="button"
                            onClick={() => handleReject("request_changes")}
                            disabled={reviewMutation.isPending}
                            className="btn btn-sm btn-quiet text-ink-soft hover:bg-cream"
                          >
                            Request Changes
                          </button>
                          <button
                            type="button"
                            onClick={() => handleRequeue(selectedCandidateId)}
                            disabled={requeueMutation.isPending}
                            className="btn btn-sm btn-quiet text-ink-soft hover:bg-cream"
                            title="Re-queue candidate for fresh fetch"
                          >
                            <RefreshCw size={14} />
                            Re-queue
                          </button>
                        </div>

                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => setSelectedCandidateId(null)}
                            className="btn btn-sm btn-quiet"
                          >
                            Cancel
                          </button>
                          <button
                            type="submit"
                            disabled={reviewMutation.isPending}
                            className="btn btn-ink inline-flex items-center gap-1.5 text-[13.5px]"
                          >
                            <CheckCircle2 size={16} />
                            Approve as Draft Opportunity
                          </button>
                        </div>
                      </div>
                    </form>
                  )}
                </div>
              </div>
            )}
          </section>
        )}

        {/* Tab 3: Sources */}
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

type CandidateEvidenceProps = { candidate: ReturnType<typeof useCandidateDetail>["data"] };

/** The fetch record and the quotes behind the extracted deadline and title, with every validation finding. */
function CandidateEvidence({ candidate }: CandidateEvidenceProps) {
  if (!candidate) return null;
  const extraction = (candidate.extraction ?? {}) as Record<string, { status?: string; value?: unknown; evidence?: { quote: string }[]; note?: string | null }>;
  const validation = (candidate.validation ?? {}) as { problems?: string[]; warnings?: string[] };
  const quote = (field: string) => extraction[field]?.evidence?.[0]?.quote;
  const when = (value?: string | null) => (value ? new Date(value).toLocaleString() : "—");
  const problems = validation.problems ?? [];
  const warnings = validation.warnings ?? [];
  return (
    <section aria-label="Source evidence" className="space-y-3 rounded-panel border border-rule bg-cream/20 p-5">
      <h3 className="text-[15px] font-bold text-ink">Source evidence</h3>
      <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-[12.5px] sm:grid-cols-2">
        <div>
          <dt className="text-muted">Fetched</dt>
          <dd className="text-ink">
            {when(candidate.fetched_at)}
            {candidate.http_status ? ` · HTTP ${candidate.http_status}` : ""}
          </dd>
        </div>
        <div>
          <dt className="text-muted">Last confirmed unchanged or re-read</dt>
          <dd className="text-ink">{when(candidate.last_seen_at)}</dd>
        </div>
        <div>
          <dt className="text-muted">Page content hash (SHA-256)</dt>
          <dd className="font-mono text-ink" title={candidate.content_hash ?? undefined}>
            {candidate.content_hash ? `${candidate.content_hash.slice(0, 16)}…` : "—"}
          </dd>
        </div>
        <div>
          <dt className="text-muted">Extractor</dt>
          <dd className="font-mono text-ink">{candidate.extractor_version ?? "—"}</dd>
        </div>
      </dl>
      <div className="space-y-2 text-[13px]">
        <p>
          <span className="font-medium text-ink">Deadline quote: </span>
          {quote("deadline") ? (
            <q className="font-serif italic text-ink">{quote("deadline")}</q>
          ) : (
            <span className="text-muted">
              none found on the page{extraction.deadline?.note ? ` (${extraction.deadline.note})` : ""}
            </span>
          )}
        </p>
        <p>
          <span className="font-medium text-ink">Title quote: </span>
          {quote("title") ? <q className="font-serif italic text-ink">{quote("title")}</q> : <span className="text-muted">none found on the page</span>}
        </p>
      </div>
      {problems.length === 0 && warnings.length === 0 ? (
        <p className="text-[12.5px] font-medium text-emerald-700">No validation problems or warnings.</p>
      ) : (
        <ul className="space-y-1 text-[12.5px]">
          {problems.map((problem) => (
            <li key={`p-${problem}`} className="text-persimmon-deep">
              <span className="font-semibold">Problem:</span> {problem}
            </li>
          ))}
          {warnings.map((warning) => (
            <li key={`w-${warning}`} className="text-amber-800">
              <span className="font-semibold">Warning:</span> {warning}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
