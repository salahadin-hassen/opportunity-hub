# Opportunity Hub — Task List (dependency order), 2026-11-13

See `CURRENT_STATE_ASSESSMENT_2026-11-13.md` for evidence.

| # | Task | Pri | Effort | Depends on | Owner |
|---|---|---|---|---|---|
| 1 | Remove `status`/`published_at` from `OpportunityCreate`/`OpportunityUpdate`; test that publish only via `/publish` | P0 | 2 h | — | Eng |
| 2 | Wire SMTP adapter in production; fail closed if SMTP unset; redact console adapter; clear raw token from outbox after send | P0 | 4 h | — | Eng |
| 3 | Choose SMTP provider; set `SMTP_*` on Render worker | P0 | 30 min | — | Founder |
| 4 | Remove `--proxy-headers --forwarded-allow-ips="*"`; add per-account failed-login throttle | P0 | 4 h | — | Eng |
| 5 | On staging, prove which client-IP header is trustworthy (origin bypass test); then set `CLIENT_IP_STRATEGY` | P0 | 2 h | 4 | Eng + Founder (Render/Cloudflare) |
| 6 | Align cron `branch:` with production branch; decide paid `starter` crons | P0 | 1 h | — | Founder decision |
| 7 | Frontend `/reset-password` and `/verify-email` pages; enqueue verification email on register | P1 | 4 h | 2 | Eng |
| 8 | Playwright E2E job in CI with service Postgres | P1 | 4 h | — | Eng |
| 9 | Auto-close/hide opportunities past deadline | P1 | 2 h | — | Eng |
| 10 | Uptime + error alerting | P1 | 2 h | — | Eng + Founder |
| 11 | Confirm Neon PITR + restore drill to a branch | P1 | 1 h | — | Founder |
| 12 | Open PR release → production branch; review; green CI incl. E2E | P0 | 1 h | 1,2,4,6,(7,8) | Eng + Founder approval |
| 13 | Run production migration (explicit authorization) | P0 | 30 min | 11,12 | Founder-authorized |
| 14 | Deploy API → frontend → crons; smoke test | P0 | 1 h | 13 | Founder-authorized |
| 15 | Curator API + UI for sources, quoted evidence, eligibility rules | P1 | 2–3 d | 1 | Eng |
| 16 | Curate to ≥100 verified published opportunities | P1 | 15–20 h | 15 | Curators |
| 17 | Server-side search/pagination | P2 | 1 d | — | Eng |
| 18 | Candidate inbox from registry sources (discovery + safe fetcher) | P3 | 1–2 wk | 15 | Eng |

**Do not do without explicit authorization:** 13, 14, any merge to `feat/opportunity-hub-product`,
Render/Cloudflare/env changes.
