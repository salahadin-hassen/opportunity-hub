# Opportunity Hub — Demo runbook

Everything a presenter needs on the day. The spoken script is in `docs/PITCH_SCRIPT.md`; answers to likely
questions are in `docs/JUDGE_QA.md`.

There are three ways to run the demo, best first:

| | Where | When to use it |
| --- | --- | --- |
| **A. Live** | the public URLs below | Normally |
| **B. Local** | this laptop (section 6) | The venue's internet or the host is down |
| **C. Recorded** | `docs/demo-backup/` | Nothing can run. Say clearly that it's a recording. |

---

## 1. Addresses

| | URL |
| --- | --- |
| Application | `https://opportunity-hub.onrender.com` *(fill in after deployment if Render added a suffix)* |
| API health | `https://opportunity-hub-api.onrender.com/health` returns `{"status":"ok"}` |

## 2. The demo account

| | |
| --- | --- |
| Email | `demo@example.org` |
| Password | in `.release/production-demo-password.txt` on the release laptop (git-ignored, owner-only). Never in the repository, the frontend or slides. |

The demo profile is fictional: Mekdes Tadesse, Ethiopian citizen, bachelor's in Aerospace Engineering at
Addis Ababa University, currently enrolled, skills Python, MATLAB, CAD and Git. It deliberately has **no date
of birth and no GPA**.

**Reset it before every presentation** (it puts the profile back to the start and touches nothing else):

```bash
cd backend
APP_ENV=production JWT_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')" \
DATABASE_URL='<Neon connection string>' DEMO_PASSWORD="$(cat ../.release/production-demo-password.txt)" \
.venv/bin/python -m scripts.seed_demo --allow-production --demo-user-only
```

---

## 3. Presenter checklist (10 minutes before)

1. Reset the demo account (section 2).
2. Open the API health URL and wait for `{"status":"ok"}`. **The free API sleeps after 15 idle minutes and
   takes about a minute to wake**, so do this 2–3 minutes before you go on.
3. Open the application in a fresh browser window. Check that the landing page loads and is in the light
   theme (the toggle is the sun icon).
4. Sign in as the demo account once, then sign out, so you know the password works.
5. Keep `docs/demo-backup/` open in another window in case you need it.
6. Zoom the browser to about 110% so the room can read it.

---

## 4. The walkthrough (about three minutes of the five)

| # | Do | Say (short) | You should see |
| --- | --- | --- | --- |
| 1 | Landing page, scroll to **Open right now** | "Real programs, each with rules quoted from its official page." | 12 programs |
| 2 | Scroll to **How one rule becomes a clear answer** | "The engine checks one rule at a time, against your profile." | The five-step story |
| 3 | **Sign in** as the demo account | | Discover |
| 4 | **Check my eligibility** | "Every program, evaluated now, by the real backend." | Live progress, then verdicts |
| 5 | Open **Eligibility** | "Four answers, in a fixed order." | Table below |
| 6 | Open **GitHub Student Developer Pack** | "Potential match: nothing rules her out, but one fact is missing." | Rule 2, "At least 13 years old", **Missing**, with the official wording |
| 7 | Back to Eligibility. In **Fill the gaps**, enter date of birth `18 Apr 2003`, then **Save and re-check** | "Add one fact; only the affected programs are checked again." | "Your update changed 1 verdict: **Potential match → Eligible**" |
| 8 | Open the GitHub Pack again | "Every rule is now met, with evidence. And it's still GitHub's decision." | Both rules met; "Was missing, now met"; the scope note |

**Expected verdicts after step 4** (demo profile, current dataset):

| Verdict | Count | Opportunities |
| --- | --- | --- |
| Eligible | 0 | none |
| Potential match | 1 | GitHub Student Developer Pack (date of birth missing) |
| Needs review | 8 | CERN, KAUST VSRP, KAUST Master's, Schwarzman, Gates Cambridge, Google Summer of Code, Summer@EPFL, ETH SSRF |
| Not eligible | 3 | NASA OSTEM Summer and Fall 2027 (U.S. citizenship), Amelia Earhart Fellowship (doctoral students only) |

**After step 7:** GitHub Student Developer Pack is **Eligible**, so the counts are 1 / 0 / 8 / 3.
Schwarzman's two age rules turn to met but stay Needs review, because its undergraduate-degree condition still
needs a person.

Optional, if time allows: add a GPA of `3.72` **of 4.0**. KAUST VSRP's GPA rule turns met, and the verdict
stays Needs review because of "not a KAUST alumnus". Then show `8.4` **of 10** on the Profile page: the
engine sends it to review instead of converting scales.

**Honesty points to keep:** "Eligible" means every published rule was checked and met. It is not an
admission or an award. Needs review is the honest answer for conditions a machine can't check.

---

## 5. If something goes wrong

| What happens | What to do |
| --- | --- |
| The page loads but opportunities don't ("Can't reach the server") | The API is waking up. Open the health URL, wait up to a minute, then reload. |
| "Your session expired" | Sessions last 30 minutes. Sign in again: you return to the page you were on. |
| The check stops part-way or one request fails | Press **Re-check all**. Checks are repeatable and safe. |
| The demo profile already has a date of birth (someone rehearsed) | Reset the demo account (section 2). If you can't, do step 7 with the GPA instead and narrate the Needs review honesty point. |
| "Too many attempts" when signing in | The login limit is 10 per minute per network. Wait one minute. |
| The live site is down | Switch to **B. Local** (section 6), then to **C. Recorded** if that fails too. Tell the audience which one you're showing. |

---

## 6. Running locally (fallback B)

From the repository on the release laptop. Allow 5 minutes; rehearse it once.

```bash
scripts/dev-db.sh start                                   # local Postgres on :5433
cd backend && .venv/bin/python -m scripts.seed_demo       # resets the local demo data
.venv/bin/uvicorn app.main:app --port 8000                # terminal 1
cd frontend && npm run dev                                # terminal 2, then open http://localhost:5173
```

The local demo account is `demo@example.org` with the development password `ohub-demo-2026` (local only).
**Use the local demo account** on the sign-in page fills it in for you.

## 7. Recorded backup (fallback C)

`docs/demo-backup/` holds a screen recording of steps 1–8 (`walkthrough-backup.webm`, opens in any browser)
and numbered stills `01`–`09` of the same flow. Introduce it as "a recording of the live product". It's a
backup, not the product.

## 8. Known limitations to mention if asked

- 12 listed opportunities, hand-curated, with every rule quoted verbatim from its official page. Coverage is
  small by design.
- Most real programs publish conditions a machine can't check, so 8 of 12 come out as Needs review. That's
  the engine being honest.
- The engine reads GPA (on its own scale), citizenship, degree level, enrolment, date of birth and skills.
  Languages, residence, interests and test scores are stored but never used.
- Free hosting: the first request after 15 idle minutes takes about a minute.
- Sessions last 30 minutes, with no refresh. Account deletion isn't self-service yet.
