# Ingestion pipeline: operator guide

| | |
|---|---|
| Code | `backend/app/intelligence/` (pipeline, connectors, reader, extract, validate, normalize, text), `backend/app/ingest_cli.py`, `backend/app/api/routers/ingestion.py` |
| Tables | `ingestion_runs`, `ingestion_candidates` (migration `4bc3f2f0619d`), plus the existing `acquisition_sources` registry |
| Tests | `backend/tests/test_ingestion_units.py`, `backend/tests/test_ingestion_pipeline.py` (no network) |
| Status | Works end to end locally against real official pages. **Not deployed; no scheduled job is configured.** |

## 1. What it does and what it never does

```
approved source ─► discovery (connector) ─► candidates ─► fetch (safe reader) ─► extract ─► validate ─► de-duplicate
      ▲                                                                                                    │
  curator: propose, test,                                         needs_review / expired / duplicate / rejected
  terms review, approve                                                                                    │
                                                         curator review (API or CLI): approve / reject / request changes
                                                                                                           │
                                                                       approve ─► DRAFT opportunity (source snapshot + quoted rules)
                                                                                                           │
                                                                curator "Check & publish" ─► publication checks ─► published
```

- **Nothing is published automatically unless an admin opts a source in** (see *Automatic review* below). By default approval creates a *draft*, and publishing is the curator action (`POST /curate/opportunities/{id}/publish`, "Check & publish" in the UI), with its own checks. Pipeline code never modifies an existing opportunity.
- **Nothing is invented.** Every extracted field has a status:
  - `explicit`: stated on the page;
  - `inferred`: derived from wording, e.g. the category from the title;
  - `ambiguous`: e.g. `03/04/2027`, or a date with no year;
  - `conflicting`: the page states several values;
  - `not_found`.

  Missing stays missing; ambiguous dates are never resolved by guessing.
- **Evidence is mandatory.** Every claim taken from the page text quotes it verbatim. Validation re-checks each quote against the stored page text and drops any field whose quote isn't there. A future model-based extractor would be held to the same check.
- **Page text is data.** Instructions on a page are just text; at most they make a field `conflicting`, which then needs a curator.

## 2. Candidate states

| State | Meaning | Next |
|---|---|---|
| `discovered` | Found by discovery or re-queued | processed by `ingest-process` |
| `retry` | Fetch or processing failed; waits `15 min × 2^(attempts−1)` | processed again when due |
| `failed` | 5 failed attempts | `ingest-requeue` after fixing the cause |
| `needs_review` | Extracted and validated | curator decision |
| `expired` | Explicit deadline passed, or the page says applications are closed | approve only with `force` and a new deadline |
| `duplicate` | Same content as another candidate, or same page/title and cycle as an existing opportunity | approve only with `force` |
| `rejected` | Not an opportunity page, page gone (404/410), off the allow-list, robots disallowed, or rejected by a curator | `ingest-requeue` if wrong |
| `changes_requested` | Curator asked for a correction | `ingest-requeue` |
| `approved` | A draft opportunity exists | publish via the curator workspace |

A page from the same source matching an existing record but with a deadline in a **different year** is a *possible new cycle*: it goes to review with a warning and a link to the earlier record, not to `duplicate`.

## 3. Safety controls (where they live)

| Control | Implementation |
|---|---|
| Only approved hosts | `discovery.check_in_scope` on every lead; `fetcher.fetch_url(allowed_hosts=…)` on the first URL **and every redirect hop**, ports 80/443 only |
| SSRF | `fetcher.py`: private, loopback, link-local, metadata, CGNAT and ULA addresses refused at the socket; connection pinned to the vetted IP |
| robots.txt (RFC 9309) | `reader.SafePageReader`, once per host per run:<br>• a missing file (4xx) allows everything;<br>• an unreachable or 5xx file disallows everything;<br>• every discovered lead is checked too, not only pages the connector reads |
| Politeness | At least `crawl_policy.min_delay_seconds` (minimum 1 s, default 5 s) between requests to one host; `Crawl-delay` can only raise it; per-run page budget `max_pages_per_run` |
| Time | 10 s per network operation and 45 s in total per fetch, including redirects |
| Size and type | 5 MiB streamed cap; HTML, XML/feeds, JSON and plain text only; only HTML pages become candidates |
| XML | Documents with a DOCTYPE or ENTITY declaration are refused (blocks entity-expansion attacks) |
| Concurrency | `FOR UPDATE SKIP LOCKED` leasing with a 10-minute lease; each candidate runs in a savepoint and is committed on its own; a crashed worker's lease expires |
| Idempotency | `candidate_key` = sha256(source id, canonical URL); re-discovery only refreshes `last_seen_at` |
| Source health | Discovery failures go through `registry.record_run_failure` (auto-pause after repeated failures); a robots disallow pauses an approved source |
| Who can do what | CLI review, terms and status commands require the `--actor` account to hold the same permission as the API. Review API: list and read need `source.read`; approve, reject and request changes need `opportunity.create`; re-queue needs `source.test`. Students get 403. Discovery and processing are CLI-only, so no web request can trigger outbound fetching |
| Audit | Approve, reject, request changes and re-queue are written to the append-only audit log with the actor |

## 4. Onboarding a source

Definitions live in `backend/data/ingestion/sources.json`; the format is `SourceDefinition` (`app/intelligence/definitions.py`). Prefer official university, government, foundation and research-institute pages.

| Connector | Use for | Required config |
|---|---|---|
| `url_list` | A handful of known programme pages | `urls` |
| `sitemap` | Sites with an XML sitemap | `sitemap_urls`, `include_patterns` (keep it narrow) |
| `feed` | RSS/Atom calls for applications | `feed_urls`, optional `include_patterns` |
| `html_index` | A listing page linking to programme pages | `index_urls`, `link_patterns` (required) |

```bash
cd backend
python -m app.cli ingest-source-load data/ingestion/sources.json          # proposed
python -m app.cli ingest-source-test "<name>"                             # testing; real dry-run; records robots + test run
python -m app.cli ingest-source-terms "<name>" acceptable --actor <curator email> --notes "<what was checked>"
python -m app.cli ingest-source-status "<name>" approved --actor <admin email> --reason "<why>"
```

A source can be approved only with all of the following; the database enforces it:
- an accepted terms review;
- robots `allowed`;
- a passed test run.

Read the site's terms before marking them acceptable.

## 5. Running the pipeline

```bash
python -m app.cli ingest-discover [--source "<name>"] [--dry-run]   # all approved sources, or one testing source
python -m app.cli ingest-process --limit 20 [--source "<name>"]     # fetch → extract → validate → de-duplicate
python -m app.cli ingest-preview --source "<name>" <url>            # one page, printed, nothing stored
python -m app.cli ingest-candidates --state needs_review
python -m app.cli ingest-show <candidate id>
python -m app.cli ingest-review <id> approve --actor <email> [--type scholarship] [--deadline 2027-01-15 | --deadline-type rolling] [--statements 0,2,3] [--notes ...]
python -m app.cli ingest-review <id> reject|request_changes --actor <email> --notes "..."
python -m app.cli ingest-requeue <id> | --state failed
python -m app.cli ingest-runs
python -m app.cli ingest-stats
python -m app.cli ingest-expire                                     # dry run for published records
python -m app.cli ingest-expire --close-published --yes             # closes published opportunities past their deadline
```

**Review checklist** (approve only when every item holds). Open the official page itself and check:
- the deadline and cycle;
- that each kept statement is a real eligibility requirement (use `--statements` to drop the rest);
- the category.

Then also check that the page describes **one** opportunity; split hub pages into separate sources or URLs. A fixed deadline is stored as 23:59 UTC on the stated date, because pages rarely give a time zone; correct it in the curator workspace if the page states a time.

**API equivalents** (curator workspace or scripts):
- `GET /curate/candidates?state=needs_review`
- `GET /curate/candidates/{id}`
- `POST /curate/candidates/{id}/review` with `{"decision": "approve" | "reject" | "request_changes", ...}`
- `POST /curate/candidates/{id}/requeue`
- `GET /curate/candidates/runs`

**Curator Review UI**:
The curator workspace in `frontend/src/routes/Curate.tsx` includes an interactive **Candidate Queue** tab (`CuratorCandidateQueue`):
- Tabbed state filters: `needs_review` (default), `all`, `approved`, `expired`, `duplicate`, `rejected`, `changes_requested`.
- Quality score indicator (0-100% badge with color coding).
- Extracted deadline badge, canonical URL link, and warning/signal indicators.
- Review modal / drawer providing:
  - Editable title, opportunity type selector, deadline date picker, and deadline type (`fixed`, `rolling`, `none`).
  - Verbatim quoted eligibility statement checklist (allows keeping or excluding specific extracted statements while enforcing that at least one is kept).
  - Duplicate match banner with links to existing candidates or opportunities.
  - One-click actions: "Approve as Draft Opportunity", "Request Changes", "Reject Candidate", and "Re-queue".
- Automatically refreshes queues and stats via React Query (`useCuratorCandidates`, `useCandidateDetail`, `useReviewCandidate`, `useRequeueCandidate`).

## 6. Operator Workflow & CLI Runbook

### A. Register and Test a Source
1. **Load source definitions into proposed state:**
   ```bash
   python -m app.cli ingest-source-load backend/data/ingestion/sources.json
   ```
2. **Perform real live test on source (dry-run):**
   ```bash
   python -m app.cli ingest-source-test "Max Planck Institute Official Portal"
   ```
   *Fetches robots.txt, connector URLs, enforces SSRF/redirect guards, and records the test run in `acquisition_sources`.*
3. **Record terms-of-use review:**
   ```bash
   python -m app.cli ingest-source-terms "Max Planck Institute Official Portal" acceptable --actor curator@example.org --notes "Public university open access"
   ```
4. **Approve source for operational discovery:**
   ```bash
   python -m app.cli ingest-source-status "Max Planck Institute Official Portal" approved --actor curator@example.org
   ```
   *Enforced by database: approval requires acceptable terms review, robots `allowed`, and a passed test run.*

### B. Run Discovery
1. **Discover leads across all approved sources (or a single source):**
   ```bash
   python -m app.cli ingest-discover [--source "<name>"] [--dry-run]
   ```
   *Connector crawls feeds, sitemaps, or HTML indices. Checks allowed hostnames, respects robots.txt, deduplicates via `candidate_key = sha256(source_id, canonical_url)`, and creates candidate records in `discovered` state.*

### C. Process Candidates
1. **Process due candidates with conditional-request handling:**
   ```bash
   python -m app.cli ingest-process --limit 50 [--source "<name>"]
   ```
   *Leases candidates (`FOR UPDATE SKIP LOCKED`). Issues conditional HTTP GET with persisted ETag and Last-Modified validators.*
   - **On HTTP 304 Not Modified:** Updates `last_seen_at`, avoids redundant LLM/HTML extraction, and releases lease.
   - **On HTTP 200 OK:** Parses HTML, extracts metadata, verifies verbatim rule quotes against stored page text, checks duplicate and cycle status, and advances state (`needs_review`, `duplicate`, `expired`, `retry`, or `failed`).
   - **On Fetch Failure:** Preserves existing stored page text and validators, applying exponential backoff retry.

### D. Review Candidates
1. **Via Curator Web UI:**
   Navigate to the **Candidate Queue** tab in the Curator Workspace (`/curate`).
   - Filter by queue state (`needs_review`, `all`, `approved`, `expired`, `duplicate`, `rejected`, `changes_requested`).
   - Inspect quality scores, canonical URLs, warnings, and duplicate matches.
   - Review and toggle verbatim eligibility statements (at least one must be retained).
   - Override title, category, deadline date, and deadline type (`fixed`, `rolling`, `none`).
   - Actions: "Approve as Draft Opportunity", "Request Changes", "Reject Candidate", "Re-queue".
2. **Via Curator CLI:**
   ```bash
   python -m app.cli ingest-candidates --state needs_review
   python -m app.cli ingest-show <CANDIDATE_UUID>
   python -m app.cli ingest-review <CANDIDATE_UUID> approve --actor curator@example.org --countries "GB,DE" --notes "Curator verified against source"
   python -m app.cli ingest-review <CANDIDATE_UUID> request_changes --actor curator@example.org --notes "Verify whether 2027 or 2028 call"
   python -m app.cli ingest-review <CANDIDATE_UUID> reject --actor curator@example.org --notes "Not student relevant"
   python -m app.cli ingest-requeue <CANDIDATE_UUID>
   ```

### E. Approve and Publish
1. **Curator Approval:**
   Approving a candidate creates a **DRAFT** record in `opportunities` containing the source snapshot, verbatim quotes, and ISO-3166-1 alpha-2 country codes. The pipeline publishes on its own only for sources an admin has raised to `full` automation (below).
2. **Curator Publication:**
   Publishing is performed via the curator opportunity editor ("Check & publish" button) or `POST /curate/opportunities/{id}/publish`.
   - Strict publication checks verify complete title, valid future deadline or rolling status, and syntax-valid requirement rules.
   - Pipeline code never modifies an already published opportunity.

### F. Refresh Published Opportunities
1. **Re-check official source pages of published opportunities:**
   ```bash
   python -m app.cli ingest-refresh --limit 20 [--opportunity <UUID>] [--min-interval-hours 24]
   ```
   *Re-reads canonical source URLs using conditional HTTP requests (ETag / Last-Modified). Detects content drift, deadline changes, cycle rollovers, or removed pages (HTTP 404/410). Records an immutable check in `opportunity_refresh_checks`. Never directly mutates approved/published records.*

### G. Inspect Refresh Findings
1. **Via CLI:**
   ```bash
   python -m app.cli ingest-refresh-checks --state pending --limit 50
   python -m app.cli ingest-refresh-show <CHECK_UUID>
   ```
2. **Via API:**
   - `GET /curate/candidates/refresh-checks?review_state=pending`
   - `GET /curate/candidates/refresh-checks/{check_id}`
3. **Frontend Limitation Notice:**
   > [!NOTE]
   > The refresh findings API exists and is fully functional, but there is currently **no dedicated curator frontend screen** for refresh findings in the UI. Operators inspect and resolve refresh findings via CLI (`ingest-refresh-checks`, `ingest-refresh-show`) or directly via API.

### H. Resolve Curator Findings
1. **Acknowledge or dismiss findings:**
   ```bash
   python -m app.cli ingest-refresh-resolve <CHECK_UUID> acknowledge --actor curator@example.org --notes "Noted deadline change, updating opportunity manually"
   python -m app.cli ingest-refresh-resolve <CHECK_UUID> dismiss --actor curator@example.org --notes "Styling change only, no requirement changes"
   ```
2. **Via API:**
   - `POST /curate/candidates/refresh-checks/{check_id}/resolve` with `{"decision": "acknowledge" | "dismiss", "notes": "..."}`.
   - If an opportunity has closed or rolled over to a new cycle, curator either marks the opportunity closed or updates the opportunity rules with new verbatim evidence.

### I. Monitor Source Health
1. **Inspect source operational health metrics:**
   ```bash
   python -m app.cli ingest-source-health
   python -m app.cli ingest-source-health --failed
   ```
2. **Via API:**
   - `GET /curate/candidates/source-health`
   - Returns real evidence-based counts: registered, tested, test_passed, never_tested, fetchable, parsed, producing, failed, needs_review, untraceable_candidates.
   - Registration alone confers no operational credit.

### J. Expire Opportunities
1. **Audit and expire past-deadline records:**
   ```bash
   # Dry-run inspection
   python -m app.cli ingest-expire
   # Close published opportunities past deadline
   python -m app.cli ingest-expire --close-published --yes
   ```
   *Marks past-deadline candidates as `expired` and sets published opportunities past their fixed deadline to `closed`.*

### K. Recover Workers
1. **Lease-based automatic recovery:**
   - Worker leasing uses PostgreSQL `FOR UPDATE SKIP LOCKED` with `lease_until = now() + 10 minutes`.
   - If an ingestion worker abruptly terminates or crashes, its lease automatically expires after 10 minutes.
   - Subsequent `ingest-process` workers immediately re-lease and resume due candidates whose `lease_until` has lapsed, without requiring manual DB unlock scripts.
2. **Re-queue failed or retry candidates:**
   ```bash
   python -m app.cli ingest-requeue --state retry
   python -m app.cli ingest-requeue --state failed
   ```

## 7. Scheduling and Monitoring Recommendations

*Note: All production cron jobs remain suspended until platform release authorization.*

### Recommended Execution Cadence

| Workflow | Recommended Cadence | Concurrency Guard | Rate Limit & Budget |
|---|---|---|---|
| **Discovery** | Daily at 02:00 UTC | Single worker | 50 URLs max per run; min 5s delay per domain |
| **Processing** | Hourly | Concurrent workers safe (`SKIP LOCKED`) | 50 candidates per batch; 10s socket timeout |
| **Refresh** | Daily at 04:00 UTC | Single worker | 50 opportunities per batch; conditional requests |
| **Expiry** | Daily at 00:05 UTC | Single worker | Processes all candidates whose deadline < `today` |
| **Health Audit** | Weekly | Read-only | Generates source error rates and HTTP 304 hit ratios |

### Monitoring & Alerting Thresholds

1. **Connector Error Spike:** Alert if `IngestionRun.errors > 5` in a single run.
2. **Source Degradation:** Alert if `consecutive_failures >= 3` on any official acquisition source.
3. **Queue Congestion:** Alert if candidates in `needs_review` state exceed 100 for more than 48 hours.
4. **Robots Refusal:** Alert if an official source changes `robots.txt` to disallow opportunity discovery paths.
5. **Worker Lease Timeout:** Leased candidates become claimable again after `pipeline.LEASE_DURATION` (10 minutes); alert if expired leases exceed 10% of active workers.

## 8. Reliability, Caching, and Engine Invariants

- **Conditional Requests (HTTP 304 Not Modified) — Fully Implemented:**
  - `http_etag` and `http_last_modified` columns added to `ingestion_candidates` and `opportunity_refresh_checks` via migration `15603fdb3a61`.
  - Stored headers are passed to `SafePageReader.read` and sent as `If-None-Match` and `If-Modified-Since`.
  - On HTTP 304, `last_seen_at` is updated, previous extracted data is retained, unnecessary re-extraction is avoided, and leases are released cleanly.
  - Failed network requests preserve existing cached page content and validators (preventing cached data loss during transient network glitches).
  - Conditional requests lacking prior validators or returning invalid 304s are safely handled without state corruption.
- **Worker Concurrency Isolation:** Candidate leasing uses PostgreSQL `FOR UPDATE SKIP LOCKED`. Multiple ingestion workers can operate in parallel without double-processing or deadlock contention.
- **Structured Geographic Integrity:** `Opportunity.countries` is preserved through `ApprovalInput`, `ReviewRequest`, `pipeline.approve_candidate`, and `OpportunityCreate`. Country codes conform strictly to ISO-3166-1 alpha-2 standards.
- **Eligibility Engine Safety:** Unparsed requirements and ambiguous rules are strictly assigned outcome `needs_review` / `unknown`. Under no circumstance can an unparsed rule evaluate to `eligible`, completely eliminating false-positive matches for students.


## Automatic review (`app/intelligence/autonomy.py`, `app/intelligence/ai_review.py`)

Each approved source has a `publish_mode`. An admin raises it one step at a time, and only for official sources. Anyone can drop it back to `off`, and it falls to `off` by itself when the source leaves `approved`.

| Mode | What happens to a `needs_review` candidate from this source |
|---|---|
| `off` | Waits for a person (default). |
| `shadow` | Every check runs and the verdict is stored in `validation.autonomy`. Nothing is drafted or published. |
| `listing_only` | A candidate that passes every check becomes a draft. A person publishes it. |
| `full` | A candidate that passes every check is drafted and published (`opportunity.auto_published` audit). |

A candidate fails and is **held for a person** if any of these is not true:
- the source is approved, official and its terms are acceptable;
- validation has no problems;
- the page isn't a possible new cycle;
- the page has a specific title;
- the page has an opportunity type;
- there is one future deadline that the rules (and the AI, when on) agree on, or an explicit rolling/no-deadline statement;
- at least 2 eligibility rules are quoted verbatim.

With AI review on, the AI must also say this is one open opportunity page, with confidence ≥ 0.7. Without AI, the candidate also needs a quality score ≥ 60 and a deadline found by the rules.

A candidate is decided once per content hash, mode and policy version. Each pipeline run also expires stale candidates and closes published listings whose deadline has passed (`opportunity.auto_closed`).

**AI review (optional).** Set `GROQ_API_KEY` (and optionally `GROQ_MODEL`, default `openai/gpt-oss-120b`) to turn it on.
- The model reads the stored page text with a strict JSON schema, and every field must come with a verbatim quote.
- Quotes are checked against the page; anything not on the page is dropped and recorded.
- The AI can only veto or confirm; it never publishes on its own say-so.
- Calls are throttled under Groq's free-tier token limit.
- A failed call means "no AI opinion", and the rule-only path then applies.
- Only public programme-page text is sent.
