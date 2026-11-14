# Credential limiter: account-lockout threat model and design options

| | |
| --- | --- |
| Status | Analysis for founder decision. **The lockout policy is unchanged.** Since 2026-11-03 the code (not deployed) also bounds Argon2 concurrency and rejects known emails before hashing (§5); implemented and tested locally only |
| Date | 2026-11-02 |
| Code | `ci/m1-m2-foundation`, not deployed; production runs `b8da30f` |
| Requirement | AUTH-008 (PRD); plan tasks M1-T2, M1-T3, M1b |
| Evidence | `backend/tests/test_rate_limit_store.py`, `backend/tests/test_release.py` (tests named `test_lockout_*` and the account-budget tests) |

Production runs `b8da30f`: an in-memory, per-process, per-IP limiter with no account budget. Everything
below describes the **not yet deployed** PostgreSQL limiter. Production's client-IP budget is forgeable
(`--proxy-headers --forwarded-allow-ips="*"`), so no design here may rely on a trustworthy client IP until
the Render proxy chain is verified (see `RENDER_CLIENT_IP_VERIFICATION.md`).

**Deploying this introduces targeted lockout to production, which has no account budget today.** The founder
accepted that risk for the first release on 2026-11-04 (`PRODUCTION_READINESS.md` §3.1). It is accepted, not fixed.

## 1. Current behaviour (characterised, not endorsed)

Each `/auth/login` and `/auth/register` request passes two fixed-window budgets of
`AUTH_RATE_LIMIT_PER_MINUTE` (10 in `render.yaml`) per 60-second window:

1. **Address budget**: a router dependency, keyed by HMAC of the client bucket. It runs before body
   validation, so malformed (422) requests also count. It is skipped when no trustworthy identity exists.
2. **Account budget**: first statement of the handler, keyed by HMAC of `email.strip().lower()`, scoped
   per endpoint. It runs after body validation and **before** any database lookup or Argon2.

| # | Question | Answer | Evidence |
| --- | --- | --- | --- |
| 1 | When is the account budget checked? | First line of the handler, after body validation, before the user lookup and Argon2 | `auth.py`; `test_lockout_budget_is_checked_before_the_password_and_no_hash_runs_when_over` |
| 2 | Successful attempts counted? | Yes | `test_lockout_successful_logins_also_spend_the_account_budget` ([200, 200, 429]) |
| 3 | Failed attempts counted? | Yes | `test_one_account_from_many_addresses_hits_the_account_budget` |
| 4 | 409 conflicts counted? | Yes. Since 2026-11-03 a known email is found before hashing, so a 409 costs no Argon2 (it did before) | `test_registration_is_budgeted_per_account`, `test_lockout_a_registration_conflict_counts_but_runs_no_argon2` |
| 5 | Updated before or after Argon2? | Before (an atomic upsert on its own committed connection); an over-budget request does no hashing | test in row 1 |
| 6 | Distributed attacker can exhaust it? | Yes, address rotation does not help the owner | `test_rotating_client_addresses_cannot_reset_one_accounts_budget`, `test_lockout_a_stranger_without_the_password_locks_the_owner_out_for_the_window` |
| 7 | Blocks a legitimate correct-password login? | Yes, until the window rolls over (≤ 60 s after the attacker stops) | same test: owner gets 429, then 200 one window later |
| 8 | Reveals account existence? | Not through the limiter: identical status and message for existing and unknown emails. Separately (pre-existing): unknown emails skip Argon2 (timing), and registration's 409 discloses existence (accepted as S7) | `test_lockout_responses_do_not_reveal_whether_the_account_exists`, `test_lockout_unknown_accounts_skip_argon2` |
| 9 | Registration? | Its own scope: exhausting `/auth/register` for an email blocks registering that email, not logging in | `test_lockout_registration_and_login_budgets_are_separate` |
| 10 | Concurrency? | Exact: 20 simultaneous attempts with a limit of 3 give exactly 3 × 401 and 17 × 429 (real uvicorn process) | `test_concurrent_attempts_on_one_account_cannot_overshoot_the_budget`; store level `test_concurrent_attempts_are_counted_exactly_once_each` |
| 11 | Counter store unavailable? | 503 with `Retry-After: 30`, credentials never checked; also when only the account write fails after the address write passed | `test_an_unreachable_store_fails_closed_with_503`, `test_lockout_an_account_counter_failure_fails_closed_after_the_address_passed` |
| 12 | Shared across instances? | Yes, one table and one key derivation (same `JWT_SECRET`): an account exhausted on one process is refused on another | `test_the_account_budget_is_shared_by_separate_application_processes`, `test_two_application_instances_share_counters` |

### Numbers that matter

- **Argon2id cost**: `m=65536 KiB, t=3, p=4` (argon2-cffi defaults); about 97 ms per verify on an 8-core
  development machine (re-measured 2026-11-03: 129 ms median for hash and verify; 64 MiB peak growth each,
  509 MiB for 8 at once). `render.yaml` declares the `free` plan (not checked against the dashboard). If so,
  each concurrent hash needs 64 MiB, so roughly seven simultaneous hashes fill a 512 MB instance. Memory,
  not CPU, is the binding hash-exhaustion limit.
- **The account budget is a burst limit, not a guessing defence**: 10 per minute is 14,400 guesses per
  account per day, enough to work through a large common-password list against one known account.
- **Credential stuffing** (one guess per account across many accounts) is not limited by the account
  budget at all; only the address budget limits it, and that is forgeable in production today.

## 2. Threats (current design, production flags assumed)

| Threat | Current design |
| --- | --- |
| Targeted victim lockout | **Trivial.** 11 requests a minute from anywhere, no password needed; cheap for the attacker (over-budget requests do no hashing) |
| Distributed guessing | 10/min per account regardless of addresses (good), but 14,400/day per account; stuffing across accounts is limited only by the forgeable address budget |
| Password-hashing exhaustion | Login: ≤ 10 hashes/min per *existing* account, unbounded across many known accounts. Registration: one hash per attempt with a fresh email each time; only the forgeable address budget limits it. *Since 2026-11-03 (local only):* concurrent Argon2 is capped per process (§5), so memory can't be exhausted this way, but saturating the cap refuses sign-in for everyone (503) |
| Account enumeration | Limiter uniform. Pre-existing: timing (unknown email skips Argon2), registration 409 |
| Legitimate access | Owner locked out during an attack |
| Shared networks | The account budget isolates accounts. The address budget is shared by NAT users, but only once IP identity is trustworthy; today it is forgeable |
| Concurrent requests | No overshoot (atomic upsert, measured) |
| Database failures | Fail closed (503). The users table lives in the same database, so this adds no new outage mode |

## 3. Options compared

### Option 1: count only failed attempts

Two ways to build it:

- **1a, check then increment on failure**: a read before Argon2, an upsert after a failure. *Not atomic*:
  N concurrent requests all pass the read, so up to `limit + concurrency − 1` passwords get verified per
  window. Rejected.
- **1b, reserve then refund**: keep today's atomic pre-auth increment, and on success decrement the same
  row (`count = count − 1`; the `count ≥ 1` CHECK needs `GREATEST`, or a delete when the count reaches
  zero). Exact under concurrency, because in-flight attempts hold a reservation. If the refund fails, the
  budget is over-counted, which is the safe direction.

| Threat | Option 1b |
| --- | --- |
| Targeted lockout | **Unchanged**: the attacker only produces failures |
| Distributed guessing | Unchanged |
| Hashing exhaustion | Unchanged |
| Enumeration | No new signal (the refund happens only on success, which the caller already sees) |
| Legitimate access | Better only for users who sign in often; no help during an attack |
| Shared networks | Unchanged |
| Concurrency | Exact (1b) |
| DB failure | Unchanged; a refund failure is logged and ignored |

A small, safe improvement that does **not** address the main threat.

### Option 2: account-plus-address budget, account-wide ceiling, address budget

Hard budget on (account, client bucket); a larger account-wide ceiling; the existing address budget.

- With a **trustworthy** client IP: an attacker must share the owner's address bucket to lock them out.
  Guessing is bounded by (per-pair budget × attacker addresses), so an account-wide ceiling is still
  needed. If the ceiling is hard, lockout returns, but it now costs the attacker many real addresses.
- With **today's forgeable** IP: rotating forged addresses yields unlimited (account, address) pairs. The
  pair budget means nothing and only the account-wide ceiling protects the account, which is today's
  design.
- Shared networks: the per-pair key keeps one student's typos from affecting classmates' accounts. The
  address budget remains the shared-NAT risk (see the threshold discussion in the plan).

**Blocked on the Render verification.** Useful afterwards, but only as an addition.

### Option 3: progressive delays or challenges

- **Server-side sleeps** hold one of uvicorn's ~40 worker threads per delayed request: a self-inflicted
  denial of service. Rejected.
- **Escalating `Retry-After` windows** (5 failures → 1 min, 10 → 5 min, …) slow guessing considerably but
  make targeted lockout *longer*. Rejected while lockout is trivial.
- **CAPTCHA step-up** once an account is over budget would let a human owner through and make guessing
  cost a solve. But solving services are cheap, it needs a third-party provider (privacy review, new
  dependency, a cross-origin script under the planned CSP), and it harms accessibility (visual and audio
  challenges exclude some users). **Not justified at the current scale; needs approval in any case.**
- **Proof-of-work** challenges need no third party, but they cost attackers with GPUs little and
  low-end phones a lot. Not recommended.

### Option 4: let a correct password through after exhaustion

Verify Argon2 even when over budget; return 200 on a match, 429 otherwise.

| Threat | Option 4 |
| --- | --- |
| Targeted lockout | Solved |
| Distributed guessing | **Broken**: an over-budget guess is still checked and a success is visible, so the budget no longer limits guessing at all |
| Hashing exhaustion | **Worse**: every request against a known account costs an Argon2 (64 MiB), unbounded |
| Enumeration | New timing signal: over-budget requests hash for existing accounts and not for unknown ones |

**Rejected as stated.** A sound variant exists only if the over-budget path is limited to clients that
prove something an attacker lacks. That is Option 5.

### Option 5 (recommended target): device cookies plus the current account budget

The OWASP "device cookie" pattern. After a successful login the server sets a long-lived,
HMAC-signed cookie bound to the user id and a random nonce. On each attempt:

- **Valid device cookie for the email's account**: limited by a *per-cookie* budget (for example
  10 per minute), **not** by the account-wide budget. The owner signs in from a known device during an attack.
- **No valid cookie** (new device, or an attacker): today's account-wide budget plus the address budget.
- The cookie signature is checked with HMAC **before** any database lookup or Argon2, so forged cookies
  cost microseconds. Cookies can be revoked by rotating a per-user nonce (fits the M1b sessions table).

| Threat | Option 5 |
| --- | --- |
| Targeted lockout | Only blocks *new* devices for that account; known devices keep working |
| Distributed guessing | Same cap as today for cookie-less clients; a stolen cookie gives at most its own budget |
| Hashing exhaustion | Login bounded as today; per-cookie budgets bound the trusted path |
| Enumeration | No new signal: an invalid or other-user cookie is treated as no cookie, and responses stay uniform |
| Legitimate access | Owner on a known device: yes. Owner on a new device: still locked for the window (acceptable residual risk) |
| Shared networks | Independent of client IP; works before the Render fix |
| Concurrency | The same atomic upserts on a new scope |
| DB failure | Fail closed, as today |

It needs no new dependency (stdlib `hmac`). It **does** need cookies, which the API does not use yet
(bearer tokens in `localStorage`). M1b plans cookie sessions, so build it there, together with the CSRF
controls that cookies require.

## 4. Recommendation

1. **Now (approval needed, small):** Option 1b (reserve then refund), so successful logins stop using up
   the budget. Low risk, exact under concurrency. Optional; it does not fix lockout.
2. **Implemented locally 2026-11-03 (not deployed):** bound registration and login hashing (§5). A
   per-process gate refuses rather than queues, and registration checks the email before hashing.
3. **Still do not** add a dummy Argon2 for unknown emails. Memory is now bounded, but every unknown-email
   login would then hold a slot for a full Argon2 run, making the capacity-saturation denial of service in
   §5 cheaper. It remains a separate decision.
4. **With M1b (cookie sessions):** Option 5, device cookies. This is the design that removes trivial
   targeted lockout without relying on client IP.
5. **After the Render verification:** reconsider Option 2's per-pair budget and the address threshold
   using the telemetry in the plan (§F.8).

Rejected: 1a (not atomic), 3 (sleeps, escalating windows, CAPTCHA, proof-of-work, for now), 4 as stated.

## 5. Argon2 capacity and the registration pre-check (implemented locally 2026-11-03)

Not a policy change: budgets, thresholds, 401/409/429 responses, JWTs, password rules and Argon2
parameters are unchanged. Tests: `backend/tests/test_password_hash_capacity.py`.

- **Gate:** `app/core/security.py` admits at most `ARGON2_MAX_CONCURRENCY` (default 2, allowed 1–16)
  Argon2 operations at once per process. Every `hash_password` and `verify_password` passes it. There is
  no queue: a request finding the gate full is refused at once with 503 (`Retry-After: 2`, "The service is
  busy…") and does no Argon2 work.
- **Login isolation (revised 2026-11-03, same day):** there is one counter set under one lock, not two
  pools.
  - Registration hashing may hold at most `ARGON2_REGISTRATION_MAX_CONCURRENCY` slots (default 1, at most
    the total), so total minus that share serves only sign-in.
  - Login may use any free slot, including registration's unused share. Registration never borrows login's.
  - With a total of 1 nothing can be reserved: both share the slot, as before.
  - Refusals carry `limit=total` or `limit=registration` in telemetry.
  - Reproduced before the change: two held registrations made a correct-password login get 503.
    `test_registration_saturation_can_no_longer_refuse_sign_in` pins the fix.
- **Slot lifetime:** the slot belongs to the worker thread. Cancelling the request does not free it early:
  measured with anyio 4.15, the awaiting task returns while the thread runs on, and the slot stays taken
  until Argon2 ends.
- **Login boundary (revised):**
  - Before the account lookup, login checks whether it *could* be admitted, without reserving, and refuses
    a saturated service at once. Known and unknown emails get the same 503, before anything is looked up.
  - The slot itself is taken only around the verification. Until then the login held a slot through its
    lookup, so parked unknown-email lookups could fill the gate with no Argon2 work (reproduced).
  - **Residual leak:** if the gate fills between the check and the verification (a lookup's length), a
    known email can be refused where an unknown one would get 401. This is statistical and needs the
    attacker to keep the gate at its edge. It is much weaker than the existing timing difference (unknown
    emails skip a ~130 ms Argon2) and registration's 409, both already documented.
- **Registration:** looks the email up first, using exactly the value the unique constraint compares, and a
  known email gets its 409 without hashing. The constraint still settles races: two concurrent
  registrations can both pass the lookup, and the loser's insert fails inside its savepoint (409, session
  usable).
- **Database outage:** a lookup failure is 503 and never hashes.
- **Default:** two slots is 128 MiB of hashing on top of about 82 MiB idle RSS, measured locally under one
  uvicorn worker. That fits a 512 MB container with margin, but the live memory limit is unverified. The
  cap is per process: total = slots × uvicorn workers (`--workers`, or `WEB_CONCURRENCY` if set) ×
  instances. The checked-in start command passes no `--workers`.
- **Availability trade-offs (with the default 2/1):**
  - **Registration floods** now only hurt registration: one registration hashes at a time per process
    (about 7 a second), so fresh-email abuse refuses other people's sign-ups with 503, not sign-in.
  - **Login floods** can still fill both slots. That needs about 15 verifications a second against *existing*
    accounts. The account budget caps each email at 10 a minute, so roughly 90 known or attacker-registered
    accounts are needed, slower to prepare now that registration is throttled to one at a time.
  - **When both slots are held by logins,** every login and registration gets 503 until one finishes.
  - All of this is preferable to the prior failure mode (memory exhaustion of the whole process). Closing
    R1, and then a trustworthy address budget, is what limits it further.
- **Telemetry:** `password_hash_capacity_exhausted` (endpoint, operation `hash`/`verify`, limit
  `total`/`registration`) records each refusal. It is not counted as an `auth_failure`. Counters are
  per process and reset on restart; see the plan, §F.8.
