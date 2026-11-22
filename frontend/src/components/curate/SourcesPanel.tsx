/**
 * Sources and the ingestion pipeline, run from the site.
 *
 * A source goes: proposed → test (its robots.txt and pages are fetched) → terms review (a person reads
 * the site's terms) → approved → runs (discovery and processing). Runs only produce candidates for the
 * Candidate Queue; nothing is published without a curator.
 *
 * Starting a test or a run is admin-only (the API enforces it too); curators can review terms, pause a
 * source and watch progress. One job runs at a time.
 */
import { AlertCircle, CheckCircle2, Download, ExternalLink, Play, RefreshCw, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import { useIngestionActions, useIngestionJobs, useCuratorSources } from "../../api/queries";
import type { components } from "../../api/schema";
import { formatDateTime, plural } from "../../lib/format";
import { EmptyState, Spinner } from "../ui/States";

type Source = components["schemas"]["SourceRead"];
type Job = components["schemas"]["JobRead"];

const errorText = (error: unknown) => (error instanceof ApiError ? error.message : error ? "That didn’t go through. Try again." : null);

function Pill({ tone, children }: { tone: "good" | "warn" | "bad" | "neutral"; children: React.ReactNode }) {
  const style = { good: "bg-eligible-wash text-eligible-ink", warn: "bg-potential-wash text-potential-ink", bad: "bg-ineligible-wash text-ineligible-ink", neutral: "bg-cream text-ink-soft" }[tone];
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11.5px] font-medium ${style}`}>{children}</span>;
}

function elapsed(from: string): string {
  const seconds = Math.max(0, Math.round((Date.now() - new Date(from).getTime()) / 1000));
  return seconds < 60 ? `${seconds} s` : `${Math.floor(seconds / 60)} min ${seconds % 60} s`;
}

function JobSummary({ job, onOpenQueue }: { job: Job; onOpenQueue: () => void }) {
  const s = job.summary as Record<string, unknown>;
  if (job.status === "failed") {
    return (
      <p className="flex items-start gap-2 text-[14px] text-ineligible-ink">
        <XCircle size={16} className="mt-0.5 shrink-0" aria-hidden="true" /> {job.label} failed: {job.error}
      </p>
    );
  }
  if (job.kind === "source_test") {
    const passed = Boolean(s.passed);
    return (
      <div className="text-[14px]">
        <p className={`flex items-start gap-2 ${passed ? "text-eligible-ink" : "text-ineligible-ink"}`}>
          {passed ? <CheckCircle2 size={16} className="mt-0.5 shrink-0" aria-hidden="true" /> : <XCircle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />}
          {job.label}: {passed ? "passed" : "failed"}. robots.txt {String(s.robots)}; {String(s.fetched_ok)} page(s) read, {String(s.fetched_failed)} failed.
        </p>
        {Array.isArray(s.problems) && s.problems.length > 0 && (
          <ul className="mt-1 list-disc pl-6 text-[13px] text-ink-soft">
            {(s.problems as string[]).map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        )}
      </div>
    );
  }
  const byState = (s.by_state ?? {}) as Record<string, number>;
  const ready = byState.needs_review ?? 0;
  return (
    <div className="text-[14px]">
      <p className="flex items-start gap-2 text-eligible-ink">
        <CheckCircle2 size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
        {job.label}: {plural(Number(s.sources ?? 0), "source")} checked, {plural(Number(s.new_leads ?? 0), "new page")} found, {plural(Number(s.processed ?? 0), "candidate")} processed.
      </p>
      {s.automatic ? (
        <p className="mt-1 pl-6 text-[13px] text-ink-soft">
          Automatic review{s.ai_review ? " (with AI)" : " (rule-based only: no AI key set)"}:{" "}
          {(["published", "drafted", "shadow", "held"] as const)
            .map((key) => `${(s.automatic as Record<string, number>)[key] ?? 0} ${key === "shadow" ? "recorded in shadow" : key}`)
            .join(" · ")}
        </p>
      ) : null}
      {Object.keys(byState).length > 0 && (
        <p className="mt-1 pl-6 text-[13px] text-ink-soft">
          {Object.entries(byState)
            .map(([state, count]) => `${count} ${state.replace(/_/g, " ")}`)
            .join(" · ")}
        </p>
      )}
      {ready > 0 && (
        <button type="button" onClick={onOpenQueue} className="mt-2 ml-6 text-[13.5px] font-semibold text-ink underline underline-offset-4">
          Review {plural(ready, "candidate")} in the Candidate Queue
        </button>
      )}
    </div>
  );
}

export function SourcesPanel({ role, onOpenQueue }: { role?: string; onOpenQueue: () => void }) {
  const isAdmin = role === "admin";
  const sources = useCuratorSources();
  const jobs = useIngestionJobs();
  const actions = useIngestionActions();
  const running = jobs.data?.current ?? null;
  const latest = jobs.data?.recent?.[0] ?? null;
  const [reviewing, setReviewing] = useState<string | null>(null);
  const approvedCount = (sources.data ?? []).filter((s) => s.status === "approved").length;

  // When a job finishes, refresh the sources and the queue it changed.
  const lastRunning = useRef<string | null>(null);
  useEffect(() => {
    if (lastRunning.current && !running) actions.refresh();
    lastRunning.current = running?.id ?? null;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running?.id]);

  // Re-render the elapsed time while a job runs.
  const [, tick] = useState(0);
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => tick((n) => n + 1), 1000);
    return () => window.clearInterval(timer);
  }, [running]);

  const startError = errorText(actions.startPipeline.error) ?? errorText(actions.testSource.error) ?? errorText(actions.importStarter.error) ?? errorText(actions.changeStatus.error);

  return (
    <section className="mt-8 space-y-6" aria-labelledby="sources-heading">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 id="sources-heading" className="text-[18px] font-semibold text-ink">
            Sources and the pipeline
          </h2>
          <p className="mt-1 max-w-[70ch] text-[14px] text-ink-soft">
            Each source is an official programme page. Test it, read the site’s terms, approve it, then run the pipeline: it reads approved sources and puts what it finds in the Candidate
            Queue. Nothing is published until a curator approves and publishes it.
          </p>
        </div>
        {isAdmin && (
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn btn-quiet" onClick={() => actions.importStarter.mutate()} disabled={actions.importStarter.isPending}>
              {actions.importStarter.isPending ? <Spinner size={14} /> : <Download size={15} />} Import starter sources
            </button>
            <button type="button" className="btn btn-ink" onClick={() => actions.startPipeline.mutate(undefined)} disabled={Boolean(running) || approvedCount === 0 || actions.startPipeline.isPending}>
              <Play size={15} /> Run pipeline now
            </button>
          </div>
        )}
      </div>

      {actions.importStarter.data && (
        <p role="status" className="text-[13.5px] text-ink-soft">
          Starter list: {plural(actions.importStarter.data.created.length, "source")} added as proposed
          {(actions.importStarter.data.updated?.length ?? 0) > 0 ? `, ${plural(actions.importStarter.data.updated!.length, "source")} updated (test and approve again)` : ""}
          {actions.importStarter.data.skipped.length > 0 ? `, ${actions.importStarter.data.skipped.length} already up to date` : ""}.
        </p>
      )}
      {startError && (
        <p role="alert" className="flex items-start gap-2 text-[13.5px] text-ineligible-ink">
          <AlertCircle size={15} className="mt-0.5 shrink-0" aria-hidden="true" /> {startError}
        </p>
      )}

      <div className="rounded-[12px] border border-rule bg-paper px-4 py-3" aria-live="polite">
        {running ? (
          <p className="flex items-center gap-2.5 text-[14px] text-ink">
            <Spinner size={15} /> <span className="font-semibold">{running.label}</span>
            <span className="text-muted">
              · started by {running.started_by} · {elapsed(running.started_at)}
            </span>
          </p>
        ) : latest ? (
          <div>
            <JobSummary job={latest} onOpenQueue={onOpenQueue} />
            <p className="mt-1 pl-6 text-[12px] text-muted">
              Finished {latest.finished_at ? formatDateTime(latest.finished_at) : ""} · started by {latest.started_by}
            </p>
          </div>
        ) : (
          <p className="text-[14px] text-muted">
            No job has run since the server started. {approvedCount ? `${plural(approvedCount, "approved source")} ready to run.` : "Approve a source to run the pipeline."}
          </p>
        )}
      </div>

      {sources.isPending ? (
        <Spinner />
      ) : (sources.data ?? []).length === 0 ? (
        <EmptyState icon={RefreshCw} title="No sources yet">
          {isAdmin ? "Import the starter sources: a reviewed list of official programme pages." : "An admin can import the starter sources."}
        </EmptyState>
      ) : (
        <ul className="divide-y divide-rule rounded-[12px] border border-rule bg-paper">
          {(sources.data ?? []).map((source) => (
            <SourceRow
              key={source.id}
              source={source}
              isAdmin={isAdmin}
              busy={Boolean(running)}
              reviewing={reviewing === source.id}
              onReview={() => setReviewing(reviewing === source.id ? null : source.id)}
              actions={actions}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function SourceRow({
  source,
  isAdmin,
  busy,
  reviewing,
  onReview,
  actions,
}: {
  source: Source;
  isAdmin: boolean;
  busy: boolean;
  reviewing: boolean;
  onReview: () => void;
  actions: ReturnType<typeof useIngestionActions>;
}) {
  const page = (source.connector_config as { urls?: string[] }).urls?.[0];
  const testable = source.status === "proposed" || source.status === "testing";
  const approvable = source.status === "testing" && source.last_test_passed === true && source.robots_status === "allowed" && source.terms_status === "acceptable";
  const missing = [
    source.last_test_passed !== true && "a passing test",
    source.robots_status !== "allowed" && "robots.txt allowed",
    source.terms_status !== "acceptable" && "an acceptable terms review",
  ].filter(Boolean) as string[];
  const report = source.last_test_report as { problems?: string[] } | null | undefined;

  return (
    <li className="px-4 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[15px] font-semibold text-ink">{source.name}</p>
          {page && (
            <a href={page} target="_blank" rel="noreferrer" className="mt-0.5 inline-flex max-w-full items-center gap-1 truncate text-[12.5px] text-muted hover:text-ink hover:underline">
              {page.replace(/^https?:\/\//, "")} <ExternalLink size={11} className="shrink-0" aria-hidden="true" />
            </a>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <Pill tone={source.status === "approved" ? "good" : source.status === "paused" || source.status === "retired" ? "bad" : "neutral"}>{source.status}</Pill>
            <Pill tone={source.robots_status === "allowed" ? "good" : source.robots_status === "unknown" ? "neutral" : "bad"}>robots {source.robots_status}</Pill>
            <Pill tone={source.terms_status === "acceptable" ? "good" : source.terms_status === "restricted" ? "bad" : "warn"}>terms {source.terms_status.replace("_", " ")}</Pill>
            {source.last_test_at && (
              <Pill tone={source.last_test_passed ? "good" : "bad"}>
                test {source.last_test_passed ? "passed" : "failed"} {formatDateTime(source.last_test_at)}
              </Pill>
            )}
          </div>
          {source.last_test_passed === false && report?.problems?.length ? <p className="mt-1.5 text-[12.5px] text-ineligible-ink">{report.problems[0]}</p> : null}
          {source.terms_notes && <p className="mt-1.5 text-[12.5px] text-ink-soft">Terms note: {source.terms_notes}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          {isAdmin && testable && (
            <button type="button" className="btn btn-sm btn-quiet" disabled={busy || actions.testSource.isPending} onClick={() => actions.testSource.mutate(source.id)}>
              Test
            </button>
          )}
          {source.status !== "retired" && (
            <button type="button" className="btn btn-sm btn-quiet" aria-expanded={reviewing} onClick={onReview}>
              Review terms
            </button>
          )}
          {isAdmin && source.status === "testing" && (
            <button
              type="button"
              className="btn btn-sm btn-ink"
              disabled={!approvable || actions.changeStatus.isPending}
              title={approvable ? undefined : `Needs ${missing.join(", ")}`}
              onClick={() => actions.changeStatus.mutate({ sourceId: source.id, status: "approved", reason: "Approved in the curator workspace" })}
            >
              Approve
            </button>
          )}
          {isAdmin && source.status === "approved" && (
            <button type="button" className="btn btn-sm btn-quiet" disabled={busy || actions.startPipeline.isPending} onClick={() => actions.startPipeline.mutate(source.id)}>
              <Play size={13} /> Run
            </button>
          )}
          {source.status === "approved" && (
            <button type="button" className="btn btn-sm btn-ghost" disabled={actions.changeStatus.isPending} onClick={() => actions.changeStatus.mutate({ sourceId: source.id, status: "paused", reason: "Paused in the curator workspace" })}>
              Pause
            </button>
          )}
        </div>
      </div>
      {isAdmin && source.status === "testing" && !approvable && <p className="mt-2 text-[12.5px] text-muted">To approve, this source needs {missing.join(", ")}.</p>}
      {source.status === "approved" && <AutomationControl source={source} isAdmin={isAdmin} actions={actions} />}
      {reviewing && <TermsForm source={source} actions={actions} onDone={onReview} />}
    </li>
  );
}

const MODES = ["off", "shadow", "listing_only", "full"] as const;
const MODE_TEXT: Record<(typeof MODES)[number], [string, string]> = {
  off: ["Off", "Every candidate waits for a person."],
  shadow: ["Shadow", "Checks run and the verdict is recorded on each candidate; nothing is drafted or published."],
  listing_only: ["Drafts automatically", "Candidates that pass every check become drafts; a person publishes."],
  full: ["Publishes automatically", "Candidates that pass every check are drafted and published; the rest wait for a person."],
};

/** The source's automation level: raised one step at a time by an admin, turned off at once. */
function AutomationControl({ source, isAdmin, actions }: { source: Source; isAdmin: boolean; actions: ReturnType<typeof useIngestionActions> }) {
  const mode = (MODES as readonly string[]).includes(source.publish_mode) ? (source.publish_mode as (typeof MODES)[number]) : "off";
  const index = MODES.indexOf(mode);
  const next = MODES[index + 1];
  const official = source.authority_level === "official";
  const error = errorText(actions.setPublishMode.error);
  return (
    <div className="mt-3 rounded-[10px] border border-rule bg-cream/30 px-3 py-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[13px] text-ink">
          <span className="font-semibold">Automation: {MODE_TEXT[mode][0]}.</span> <span className="text-ink-soft">{MODE_TEXT[mode][1]}</span>
        </p>
        {isAdmin && (
          <div className="flex gap-2">
            {next && official && (
              <button
                type="button"
                className="btn btn-sm btn-quiet"
                disabled={actions.setPublishMode.isPending}
                onClick={() => actions.setPublishMode.mutate({ sourceId: source.id, mode: next, reason: `Raised to ${next} in the curator workspace` })}
              >
                Raise to “{MODE_TEXT[next][0]}”
              </button>
            )}
            {mode !== "off" && (
              <button type="button" className="btn btn-sm btn-ghost" disabled={actions.setPublishMode.isPending} onClick={() => actions.setPublishMode.mutate({ sourceId: source.id, mode: "off", reason: "Turned off in the curator workspace" })}>
                Turn off
              </button>
            )}
          </div>
        )}
      </div>
      {!official && <p className="mt-1 text-[12px] text-muted">Only official sources can be automated.</p>}
      {error && (
        <p role="alert" className="mt-1 text-[12.5px] text-ineligible-ink">
          {error}
        </p>
      )}
    </div>
  );
}

function TermsForm({ source, actions, onDone }: { source: Source; actions: ReturnType<typeof useIngestionActions>; onDone: () => void }) {
  const [status, setStatus] = useState<"acceptable" | "restricted">(source.terms_status === "restricted" ? "restricted" : "acceptable");
  const [notes, setNotes] = useState(source.terms_notes ?? "");
  const ok = notes.trim().length >= 10;
  const error = errorText(actions.reviewTerms.error);
  return (
    <form
      className="mt-3 rounded-[10px] border border-rule bg-cream/40 p-4"
      onSubmit={async (event) => {
        event.preventDefault();
        try {
          await actions.reviewTerms.mutateAsync({ sourceId: source.id, status, notes: notes.trim() });
          onDone();
        } catch {
          /* shown below */
        }
      }}
    >
      <p className="text-[13.5px] text-ink-soft">
        Read the site’s own terms (usually “Terms”, “Legal” or “Copyright” in its footer) before deciding. The pipeline stores the page and shows short quotes of its rules, with a
        link back.
      </p>
      <fieldset className="mt-3 flex flex-wrap gap-4">
        <legend className="sr-only">Terms decision</legend>
        <label className="flex items-center gap-2 text-[14px] text-ink">
          <input type="radio" name={`terms-${source.id}`} checked={status === "acceptable"} onChange={() => setStatus("acceptable")} /> Acceptable
        </label>
        <label className="flex items-center gap-2 text-[14px] text-ink">
          <input type="radio" name={`terms-${source.id}`} checked={status === "restricted"} onChange={() => setStatus("restricted")} /> Restricted (don’t use)
        </label>
      </fieldset>
      <label htmlFor={`terms-notes-${source.id}`} className="field-label mt-3">
        What you checked <span className="font-normal text-muted">(saved with the review)</span>
      </label>
      <textarea
        id={`terms-notes-${source.id}`}
        className="input"
        rows={2}
        maxLength={5000}
        value={notes}
        onChange={(event) => setNotes(event.target.value)}
        placeholder="e.g. Read example.org/terms on 20 Nov 2026: content licensed CC-BY"
      />
      <div className="mt-3 flex items-center gap-2">
        <button type="submit" className="btn btn-sm btn-ink" disabled={!ok || actions.reviewTerms.isPending}>
          Save terms review
        </button>
        <button type="button" className="btn btn-sm btn-ghost" onClick={onDone}>
          Cancel
        </button>
        {!ok && <span className="text-[12.5px] text-muted">Write at least a sentence about what you checked.</span>}
      </div>
      {error && (
        <p role="alert" className="mt-2 text-[13px] text-ineligible-ink">
          {error}
        </p>
      )}
    </form>
  );
}
