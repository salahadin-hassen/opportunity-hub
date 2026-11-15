# Pull Request Specification: Ingestion Pipeline Operationalization

**Status:** Ready to open (DO NOT MERGE)  
**Target Repository:** `salahadin-hassen/opportunity-hub`  
**Base Branch:** `feat/opportunity-hub-product`  
**Head Branch:** `feat/ingestion-pipeline`  
**Head Commit:** `7f3d534b41bcf03bdfbe64d2ff72ca9f5ab5d1b7`  
**Direct GitHub Compare URL:**  
[Open PR on GitHub](https://github.com/salahadin-hassen/opportunity-hub/compare/feat/opportunity-hub-product...feat/ingestion-pipeline)

---

## PR Title
```text
Ingestion: operationalize conditional requests, source testing, refresh and curator verification
```

## PR Description (Copy & Paste into GitHub)

```markdown
## Summary

Operationalizes the Opportunity Hub ingestion pipeline on top of the merged baseline (`feat/opportunity-hub-product`).

This release provides complete production-grade candidate extraction, conditional request persistence, live source testing, published opportunity refresh and drift detection, evidence-based source health reporting, and curator workflow verification.

This PR does **not** add synthetic or fabricated catalogue datasets. The earlier 317-record catalogue was rejected during quality audit and remains strictly quarantined on the local branch `wip/unverified-catalogue` (see "Not included").

## Key Operational Capabilities

1. **Persisted Conditional Requests (ETag & Last-Modified):**
   - Migration `15603fdb3a61` stores `http_etag` and `http_last_modified` on `ingestion_candidates` and `opportunity_refresh_checks`.
   - Reader sends `If-None-Match` and `If-Modified-Since` headers on re-fetches.
   - HTTP 304 handling updates `last_seen_at` without redundant HTML extraction or LLM cost, releasing worker leases cleanly.
   - Fetch failures preserve previously cached page content and validators.

2. **Live Source Testing Harness:**
   - Dry-run verification CLI `ingest-source-test` for `url_list`, feeds, sitemaps, and crawlers.
   - Strict socket-level SSRF defense and redirect validation across every hop.
   - RFC 9309 robots.txt compliance.
   - Enforces terms acceptance, robots allowance, and a passing test before a source can transition to `approved`.

3. **Published Opportunity Refresh & Change Detection:**
   - CLI command `ingest-refresh` and operator check tools (`ingest-refresh-checks`, `ingest-refresh-show`, `ingest-refresh-resolve`).
   - Detects content drift, deadline shifts, cycle rollovers, or removed pages (404/410).
   - Generates immutable audit records in `opportunity_refresh_checks`.
   - Never directly mutates approved/published opportunities without curator action.

4. **Source Health Auditing:**
   - Empirical source metrics (`ingest-source-health` and `GET /curate/candidates/source-health`).
   - Counts reflect strictly recorded database runs and candidate evidence; registration alone confers no credit.

5. **Curator Candidate Queue & Evidence Review:**
   - Interactive candidate drawer in `frontend/src/routes/Curate.tsx`.
   - Verbatim eligibility checklist (enforces retaining at least one verbatim requirement).
   - Category, title, and deadline overrides with duplicate match resolution.
   - Full Playwright E2E coverage (`curator_candidates.spec.ts`) verifying queue operations and ordinary student isolation (403 Forbidden).

## Migration

- **`15603fdb3a61`** revises `4bc3f2f0619d`.
- Adds `http_etag` and `http_last_modified` to `acquisition_sources` and `ingestion_candidates`.
- Adds `opportunity_refresh_checks` table with index on `opportunity_id` and `review_state`.
- Extends `ck_ingestion_runs_kind` constraint to include `'refresh'`.
- Verified single head, zero Alembic drift, and clean downgrade/upgrade round trip.

## Test Evidence (Local Disposable Databases)

| Suite | Tests | Result |
|---|---|---|
| Full Backend (`pytest -q`) | 1,531 | **1,531 passed in 167.8s (0 failures)** |
| Targeted Conditional Requests | 12 | **12 passed** |
| Targeted Source Testing | 37 | **37 passed** |
| Targeted Opportunity Refresh | 32 | **32 passed** |
| Targeted CSRF & Transaction Scope | 42 | **42 passed** |
| Frontend Typecheck (`tsc -b`) | — | **0 errors (Exit code 0)** |
| Frontend Unit Tests (`vitest`) | 10 | **10 passed in 1.02s** |
| Frontend Production Build (`vite build`) | — | **Success in 6.23s** |
| Playwright E2E (`scripts/e2e.sh`) | 28 | **28 passed in 2.6m (0 failed)** |
| Migration Round-Trip & `alembic check` | — | **Clean, 0 drift** |

## Not Included

`verified_catalog.json`, `sources.json`, synthetic catalogue datasets, `remediate_catalogue.py`, and `ingest-catalog-load` remain isolated on `wip/unverified-catalogue` and are **not** included.
```
