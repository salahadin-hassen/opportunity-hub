# Pull Request Preparation Specification

**Status:** Ready to open (DO NOT MERGE)
**Target Repository:** `salahadin-hassen/opportunity-hub`
**Base Branch:** `feat/opportunity-hub-product`
**Head Branch:** `ci/m1-m2-foundation`
**Head Commit:** `06eb905be36d1e8e382b2c84162d156f642a5a41`
**Direct GitHub Compare URL:**
[Open PR on GitHub](https://github.com/salahadin-hassen/opportunity-hub/compare/feat/opportunity-hub-product...ci/m1-m2-foundation?expand=1)

---

## PR Title
```text
Release Candidate: Production Hardening, Student Tracking, Curator Lifecycle & Safe Deployment Sequence (06eb905b)
```

## PR Description (Copy & Paste into GitHub)

```markdown
## Summary of Changes

This pull request promotes the release candidate commit `06eb905be36d1e8e382b2c84162d156f642a5a41` from `ci/m1-m2-foundation` into the production deployment branch `feat/opportunity-hub-product`.

It completes all M1-M2 milestone requirements, closes open security and reliability tasks, hardens the database migration pathway, and establishes a deterministic deployment sequence for Render and Neon.

### Key Features & Enhancements

1. **Student Core Journeys & Tracking:**
   - Saved opportunities state persistence and application tracking (`saved_opportunities`, `application_history`).
   - Missing-fact resolution loop with footnoted eligibility explanations.
   - User account lifecycle: session revocation, email verification, and 30-day soft deletion purge window.

2. **Administrator & Curator Lifecycle:**
   - Role-based authorization (`student`, `curator`, `admin`) enforced across API endpoints.
   - Acquisition sources registry (`acquisition_sources`, `acquisition_source_hosts`).
   - Append-only database audit log (`audit_log`) with PostgreSQL trigger enforcement against modifications or deletions.

3. **Security & Ingress Hardening:**
   - Strict socket-level IP connection pinning and SSRF defense on all external fetchers.
   - Transactional email outbox with async background processing CLI.
   - Client-IP resolution hardened for Cloudflare proxy ingress (`render_cf_connecting_ip` with peer fallback).
   - Strict CORS configuration targeting live production domains (`https://opportunities.sahelyon.com`).

4. **Production Architecture & Deployment Order:**
   - Removed `alembic upgrade head` from Render `startCommand` to prevent concurrency races and container restart loops.
   - Updated release runbook with strict Free-plan 9-step deployment order (disabling Auto-Deploy, Neon snapshot, singular migration run, fast-forward commit push, separate API & frontend manual deploys).
   - Documented paid Starter-plan `preDeployCommand` alternative.
   - Proven backward-compatibility: old production code (`b8da30f`) verified functioning 100% against upgraded schema `3a14e912b77c`. Application rollback does not touch database schema.

---

## Database Migration Path

Baseline production revision: `ba09eb02910b`
Target release revision: `3a14e912b77c`

1. `cf669b0daa53`: Add acquisition source registry
2. `7a929229fe00`: Add rate limit buckets
3. `e931cedef74a`: Add user roles
4. `2d0318b24522`: Add append-only audit log with triggers
5. `3a14e912b77c`: Add sessions, email outbox, tracking, and account lifecycle

*Neon Rehearsal Evidence:* Successfully rehearsed on isolated Neon branch `rehearsal-release-20261109` (`br-flat-feather-b5n2ty3c`), preserving 4 users, 4 profiles, 14 opportunities, and 48 matches.

---

## Verification & Test Evidence

- **Backend Pytest:** 1,156 passed, 0 failed.
- **Frontend Unit Tests:** 10 passed, 0 failed.
- **End-to-End Browser Tests (Playwright):** 26 passed, 0 failed.
- **Frontend Build & Typecheck:** Clean build, 0 TypeScript errors.
- **Alembic History & Schema Check:** Clean roundtrip, `alembic check` clean.
- **CI Run:** GitHub Actions run `42652492559` passed all jobs on commit `06eb905b`.

---

## Deployment Instructions

Do not merge or deploy automatically. Refer to `docs/architecture/RELEASE_RUNBOOK_2026-11.md` §6.1 for the strict execution sequence.
```
