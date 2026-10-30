# Opportunity Hub — Frontend

React 19 + TypeScript + Vite client for the Opportunity Hub API. Tailwind CSS v4 (CSS-first tokens in
`src/styles/app.css`), React Router 7, TanStack Query 5, Motion for React, Lucide icons. API types are
generated from the backend's OpenAPI schema; no response shape is written by hand.

Visual direction, "Opportunity Atlas": warm ivory and deep ink, Bricolage Grotesque display type, DM Sans
for the interface, IBM Plex Mono for dates and evidence values. Photographs are treated as numbered plates with
their credits, verdicts are shape-coded legend marks (disc, half disc, crossed circle, diamond), and every
rule carries a footnote to its official wording.

## Run

Prerequisites: Node 20+, the backend on `http://localhost:8000` with the demo seed applied
(see `docs/DEMO_RUNBOOK.md`).

```bash
cd frontend
npm install
cp .env.development.example .env.development.local   # optional: enables "Use the local demo account"
npm run dev                                           # http://localhost:5173
```

The dev server proxies `/api/*` to the backend, so the API needs no CORS configuration. A production build that calls the API on another origin sets `VITE_API_BASE` at build time (see
`.env.production.example` and `docs/DEPLOYMENT.md`). Point it
elsewhere with `OH_API_TARGET=http://host:port npm run dev`. For deployment, serve `dist/` and the API
from one origin (a reverse proxy routing `/api` to FastAPI) for the same reason.

## Scripts

| Command | What it does |
| --- | --- |
| `npm run dev` | Dev server with the `/api` proxy |
| `npm run build` | Type-check and build to `dist/` |
| `npm run typecheck` | TypeScript only |
| `npm test` | Unit tests for the copy layer and missing-fact analysis |
| `npx playwright test` | End-to-end journey tests against the running stack (seed first) |
| `node e2e/capture.mjs <name>` | Visual QA screenshots (1440×900 and 390×844) into `docs/screenshots/<name>` |
| `npm run gen:api` | Regenerate `src/api/schema.d.ts` from the running API |
| `npx playwright test e2e/smoke.spec.ts` | Production smoke test (no new accounts; demo account only). See `docs/DEPLOYMENT.md` |

`capture.mjs` and the journey tests change the demo profile; re-run the seed afterwards.

## Structure

```
src/
  app/            providers, routing, auth/profile guards
  routes/         Landing, Auth, Onboarding, Discover, OpportunityDetail, Eligibility, Profile
  components/
    marketing/    nav/footer, the scroll-told engine story
    eligibility/  evidence rows, the fill-the-gaps resolve panel
    opportunities/ index rows, postcards, type tiles and monograms, rule strip
    layout/       masthead app shell (bottom tabs on phones), guest shell, page frame
    ui/           logo, verdict legend marks, photo plates and credits, form parts, states, toasts
  features/       the eligibility run: 4 concurrent evaluations, real progress, before/after diffs
  api/            generated types, typed client (openapi-fetch), query hooks
  auth/           session handling; expiry and 401s return to sign-in, then back
  lib/            rule and evidence copy, missing-fact analysis, formatting, photo credits
  hooks/          media query, device-only confirmation checklist
  assets/photos/  self-hosted WebP plates (800w and 1600w)
```

## Photography

Six photographs from Wikimedia Commons (CC0, CC BY, CC BY-SA), resized to 800w/1600w WebP. Each is credited
where it appears and on `/credits`. None shows a partner institution or an Opportunity Hub user. Unsplash was
not used: it blocks automated access.

## Honesty rules the UI follows

- Every verdict says it isn't an admission, award or approval: the organization decides.
- "For you to confirm" ticks are stored in this browser only and never change a verdict.
- Verdicts and evidence come only from the engine's persisted matches. Nothing is simulated in the app;
  the landing page's engine story and GPA example are labelled as examples.
- Every profile field says whether the engine reads it. Test scores, languages, interests and residence
  are "Stored only".
- GPA is entered with its scale. A threshold is compared only on its own scale; any other scale is sent
  to review rather than converted.
- Deadlines appear only where the official page publishes one; date-only deadlines show no time.
