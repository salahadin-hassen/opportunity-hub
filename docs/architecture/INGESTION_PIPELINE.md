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

- **Nothing is published automatically.** Approval creates a *draft*. Publishing is the existing curator action (`POST /curate/opportunities/{id}/publish`, "Check & publish" in the UI), with its own checks. Pipeline code never modifies an existing opportunity.
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

### A. Source Management
1. **Propose and load new sources:**
   ```bash
   python -m app.cli ingest-source-load sources.json
   ```
2. **Dry-run test discovery on a source:**
   ```bash
   python -m app.cli ingest-source-test "Max Planck Institute Official Portal"
   ```
3. **Record terms-of-use review:**
   ```bash
   python -m app.cli ingest-source-terms "Max Planck Institute Official Portal" acceptable --actor curator@example.org --notes "Public university open access"
   ```
4. **Approve source for operational discovery:**
   ```bash
   python -m app.cli ingest-source-status "Max Planck Institute Official Portal" approved --actor curator@example.org
   ```

### B. Discovery and Processing
1. **Run lead discovery across approved sources:**
   ```bash
   python -m app.cli ingest-discover
   ```
2. **Process discovered candidates (fetch, extract, validate, deduplicate):**
   ```bash
   python -m app.cli ingest-process --limit 50
   ```
3. **Inspect queue statistics:**
   ```bash
   python -m app.cli ingest-stats
   ```
4. **View recent discovery and processing runs:**
   ```bash
   python -m app.cli ingest-runs --limit 10
   ```

### C. Curator Review and Opportunity Lifecycle
1. **Inspect candidate extraction, quality score, and verbatim evidence:**
   ```bash
   python -m app.cli ingest-show <CANDIDATE_UUID>
   ```
2. **Approve candidate into a draft opportunity (specifying structured countries):**
   ```bash
   python -m app.cli ingest-review <CANDIDATE_UUID> approve --actor curator@example.org --countries "GB,DE" --notes "Curator verified against source"
   ```
3. **Request changes on a candidate:**
   ```bash
   python -m app.cli ingest-review <CANDIDATE_UUID> request_changes --actor curator@example.org --notes "Verify whether 2027 or 2028 call"
   ```
4. **Re-queue failed or retry candidates:**
   ```bash
   python -m app.cli ingest-requeue --state retry
   ```
5. **Expire candidates past deadline:**
   ```bash
   python -m app.cli ingest-expire
   ```

## 7. Scheduling and Monitoring Recommendations

*Note: All production cron jobs remain suspended until platform release authorization.*

### Recommended Execution Cadence

| Workflow | Recommended Cadence | Concurrency Guard | Rate Limit & Budget |
|---|---|---|---|
| **Discovery** | Daily at 02:00 UTC | Single worker | 50 URLs max per run; min 5s delay per domain |
| **Processing** | Hourly | Concurrent workers safe (`SKIP LOCKED`) | 50 candidates per batch; 10s socket timeout |
| **Expiry** | Daily at 00:05 UTC | Single worker | Processes all candidates whose deadline < `today` |
| **Health Audit** | Weekly | Read-only | Generates source error rates and HTTP 304 hit ratios |

### Monitoring & Alerting Thresholds

1. **Connector Error Spike:** Alert if `IngestionRun.errors > 5` in a single run.
2. **Source Degradation:** Alert if `consecutive_failures >= 3` on any official acquisition source.
3. **Queue Congestion:** Alert if candidates in `needs_review` state exceed 100 for more than 48 hours.
4. **Robots Refusal:** Alert if an official source changes `robots.txt` to disallow opportunity discovery paths.
5. **Worker Lease Timeout:** Leased candidates become claimable again after `pipeline.LEASE_DURATION` (10 minutes); alert if expired leases exceed 10% of active workers.

## 8. Reliability, Caching, and Engine Invariants

- **Conditional Requests (HTTP 304 Not Modified) — partially implemented:** `fetcher.fetch_url` and `SafePageReader.read` accept `etag` / `last_modified` and send `If-None-Match` / `If-Modified-Since`, and `pipeline._store_page` handles a 304 by updating `last_seen_at` and releasing the lease without re-extracting. **The pipeline does not yet store a page's validators or pass them to the reader**, so no conditional request is sent in a real run; every re-fetch is a full GET. Storing `ETag` / `Last-Modified` on the candidate needs a follow-up migration.
- **Worker Concurrency Isolation:** Candidate leasing uses PostgreSQL `FOR UPDATE SKIP LOCKED`. Multiple ingestion workers can operate in parallel without double-processing or deadlock contention.
- **Structured Geographic Integrity:** `Opportunity.countries` is preserved through `ApprovalInput`, `ReviewRequest`, `pipeline.approve_candidate`, and `OpportunityCreate`. Country codes conform strictly to ISO-3166-1 alpha-2 standards.
- **Eligibility Engine Safety:** Unparsed requirements and ambiguous rules are strictly assigned outcome `needs_review` / `unknown`. Under no circumstance can an unparsed rule evaluate to `eligible`, completely eliminating false-positive matches for students.
