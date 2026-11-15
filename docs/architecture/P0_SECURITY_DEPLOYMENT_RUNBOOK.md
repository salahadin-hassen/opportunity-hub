# Runbook: deploying the P0 security hardening

| | |
|---|---|
| Applies to | Branch `fix/p0-security-hardening` (base `06eb905`) once merged into the release |
| Related | `P0_SECURITY_HARDENING_2026-11-14.md` (what changed and why), `FRESH_SECURITY_REVIEW_2026-11-14.md` (independent review), `RENDER_CLIENT_IP_VERIFICATION.md` |
| Why a separate file | `docs/architecture/RELEASE_RUNBOOK_2026-11.md` and `docs/DEPLOYMENT.md` carry substantial uncommitted edits in the founder's main checkout. Editing them on this branch would conflict. When those edits land, link this runbook from the release runbook's pre-deploy section |

Nothing here was executed against production. Every production step needs the founder's explicit go-ahead.

## 1. Settings the release refuses to start without

Set these on the live **API** service before deploying. A Blueprint sync from `render.yaml` sets them; a dashboard-managed service must have them added by hand.

| Variable | Value | What happens if wrong |
|---|---|---|
| `APP_ENV` | `production` (whitespace and case are tolerated; `prod` is an alias) | Missing on Render, or any unknown value such as `staging`: **refuses to start** |
| `CLIENT_IP_STRATEGY` | `none` | `peer`, or the variable missing, on Render in production: **refuses to start** |
| `AUTH_RATE_LIMIT_PER_MINUTE` | `10` (1–1000) | Invalid, zero, negative or `disabled`: **refuses to start**. Unset means 10 |
| `JWT_SECRET` | existing generated value | Missing or under 32 characters: refuses to start |
| `EMAIL_DELIVERY` | `disabled` | Leave disabled until section 4 is complete |

If the new release refuses to start, Render keeps the previous deploy running. Fix the variable and redeploy.

## 2. Deploy order
1. Back up, or confirm the PITR window on, the production Neon branch.
2. Run the migration to head (`3a14e912b77c`) with explicit authorisation.
3. Deploy the API, then the frontend.
4. **Do not create, and keep suspended, both scheduled jobs** (section 5).
5. Smoke test:
   - `/health` returns 200;
   - login works;
   - 11 wrong-password logins for one test account within a minute give 401 ×10, then 429;
   - `POST /auth/forgot-password` returns 503 (email disabled, by design).

## 3. Legacy email queue (F-1): before email delivery is ever enabled

Code before this release (`06eb905`) queued reset emails as `email_outbox.params = {"token": "<raw token>"}`. The new code queues only `{"token_id", "key_id"}`.

- **How they are told apart:** a row is *legacy* if its `params` has a `token` key and no `token_id`.
- **What the new worker does:** it never sends a legacy row. It marks the row `cancelled` (`last_error = "legacy raw-token message cancelled; never sent"`) and strips the token.

The procedure below removes the raw tokens from the database proactively, before any worker runs. No command prints token material: the report selects metadata only.

**Where to run it.** The API is on Render's free plan, which offers no dashboard shell, SSH or one-off jobs. An authorised operator therefore runs the CLI from a **trusted local machine** against the production database:

- **Code:** a clean checkout of the *released* commit (the one deployed to the API). Not a working copy with local edits.
- **Environment:** that checkout's backend virtual environment, set up with `pip install -e . -c constraints.txt` from `backend/`.
- **Credentials:** none are written to a file, `.env`, notebook or shell history. The production connection string is pasted at a hidden prompt and exists only in that one shell's environment. `JWT_SECRET` is a random throwaway value: Settings requires one, and this command never uses it, so the real secret is not needed.
- **Settings file:** `APP_ENV_FILE=""` makes the app ignore any `backend/.env` on that machine.

Run in a **new** terminal, from `backend/` of that checkout:

```bash
set +o history                          # this shell records nothing from here on
read -rs -p "Production DATABASE_URL: " DATABASE_URL; echo
export DATABASE_URL                     # e.g. postgresql://<role>:<password>@<production host>/<db>?sslmode=require
export APP_ENV=production APP_ENV_FILE="" CLIENT_IP_STRATEGY=none EMAIL_DELIVERY=disabled
export JWT_SECRET="$(openssl rand -base64 48)"   # throwaway; not the API's secret
```

Use the connection string of the database the API actually uses, copied from the Neon console for the production branch. Check the host and database name against the API's `DATABASE_URL` in the Render dashboard **without** copying that value anywhere else.

1. **Count and inspect** (read-only):
   ```bash
   python -m app.cli legacy-email-outbox
   ```
   This prints one tab-separated line per group: status, template, count, `oldest=YYYY-MM-DD HH:MM`, `newest=…`. If there are none, it prints "No outbox rows hold a raw token."
2. **Cancel and quarantine** (writes; needs explicit authorisation):
   ```bash
   python -m app.cli legacy-email-outbox --cancel --yes
   ```
   - Pending legacy rows become `cancelled`.
   - The raw token is stripped from *every* legacy row, including historical `sent` or `failed` rows.
   - The command prints the two counts, then reprints the report, which should say "No outbox rows hold a raw token."
   - Without `--yes` it refuses and exits 1.
3. Close the terminal (`exit`): this discards the variables. Affected users simply request a new reset link. Any legacy link had at most a 1-hour lifetime anyway.

Do **not** run this as part of the PR or deployment. It is a prerequisite only for enabling SMTP (section 4).

## 4. Enabling email delivery (all must be true first)
1. Section 3 has been run and reports no raw tokens.
2. A frontend page exists at `/reset-password` that reads the token from the URL fragment (`#token=…`). **It does not exist yet** (review I-1). Until it does, reset emails point at a 404.
3. An SMTP provider is chosen and the sending domain verified (SPF/DKIM). Then set:
   - **On the API and the worker:** `SMTP_HOST`, `SMTP_FROM`, `SMTP_PORT` and `SMTP_SECURITY`.
   - **On the worker only:** `SMTP_USERNAME` and `SMTP_PASSWORD`.
4. Generate the token keys, e.g. `k1:$(openssl rand -base64 48)`. Set `EMAIL_TOKEN_KEYS` and `EMAIL_TOKEN_ACTIVE_KEY=k1` on the API; the worker reads them through `fromService`.
5. Set `EMAIL_DELIVERY=smtp` on **both** the API and the worker in the same change. A mismatch either refuses resets on the API side, or queues emails that never send.
6. Only then create or resume the email worker (section 5).

**Accepted behaviour, F-2 (at-least-once delivery):**
- The worker commits after a batch. If it crashes after the provider accepted a message but before the commit, that message is sent again.
- The duplicate carries the same, still-valid link (tokens are rebuilt deterministically), so the user gets two identical emails, never a wrong link.
- This is accepted for launch. To make it at-most-once per attempt, commit per message, or mark the row `sending` before the SMTP call.

**Key rotation:** see "Key rotation procedure" in `P0_SECURITY_HARDENING_2026-11-14.md`.

## 5. Scheduled jobs (R-8): keep suspended or undeployed
- **Email worker:** `render.yaml` defines `opportunity-hub-email-worker` (every 2 minutes) and `opportunity-hub-account-purge` (daily). Both are on the paid `starter` plan, deploy from branch `ci/m1-m2-foundation` while the web services deploy `feat/opportunity-hub-product`, and have no `PYTHON_VERSION` pin. With email disabled, the worker exits non-zero every run, by design.
- **Account purge:** it deletes accounts whose deletion grace period has expired, so it should run only against a migrated database, from the production branch.
- **Action:** leave both uncreated, or suspended, until:
  - the release is merged to the production branch and migrated;
  - the branch is changed to the production branch and `PYTHON_VERSION: 3.12.7` is added;
  - for the email worker, section 4 is complete.

## 6. Risks that remain open after this release

| Risk | Status | Consequence |
|---|---|---|
| **R-3** No per-address credential limit | Unresolved; depends on proving a trustworthy client identity on Render/Cloudflare (`RENDER_CLIENT_IP_VERIFICATION.md` §5) | Password spraying, credential stuffing, registration floods and Argon2 saturation (503 to everyone) are limited only per account and by hashing capacity |
| **R-7** Targeted login lockout | Unresolved; founder decision (`ACCOUNT_LOCKOUT_THREAT_MODEL.md`) | Anyone can keep a known account unable to sign in with 11 requests a minute |
| **R-5** Sources and evidence are not verified | Unresolved | **Blocks the source/evidence editor, automated ingestion and automated publishing, and any "verified" wording.** Publication checks completeness only: an official URL, an own source record with an http(s) URL, and quoted mandatory rules citing it. It does not check authenticity, host matching against the official URL, or that the quote is on the page |
| **R-6 residual** | Accepted | An attacker can use up a victim's 5 daily reset emails; the victim's links from those emails stay valid for an hour each |
| **F-2** Duplicate email after a worker crash | Accepted (section 4) | Two identical, valid emails |
| **F-5** Publication invariant enforced in code only | Accepted until the evidence editor (R-5) | Direct database edits can leave a public record incomplete; there is no unpublish operation yet |
