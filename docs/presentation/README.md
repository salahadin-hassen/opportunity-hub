# Opportunity Hub — Hackathon pitch deck

| File | What it is |
| --- | --- |
| `Opportunity_Hub_Hackathon_Pitch.pptx` | The editable deck: 5 slides, 16:9, speaker notes on every slide |
| `Opportunity_Hub_Hackathon_Pitch.pdf` | PDF export of the same deck (rendered with LibreOffice) |
| `SPEAKER_SCRIPT.md` | The speaker notes as one script, about 4 minutes spoken |

The deck uses Arial for headings and Calibri for body text, so it renders the same on any machine with
Office. Colours are the product's own palette (ink, ivory, cobalt, persimmon, lime and the four verdict
colours). Every screenshot is real (see Sources).

## Structure

| # | Slide | Purpose |
| --- | --- | --- |
| 1 | **Opportunity Hub** | Name, positioning ("Find the opportunities you actually qualify for, and see exactly why."), what it does, three verified facts, the live landing page and the URL |
| 2 | **Eligibility is written for each program, not for the student** | The problem: scattered, inconsistent rules found out too late, shown with three real quotes from official pages and the question each one leaves a student with |
| 3 | **One profile, checked against every published rule** | The solution: Discover → Read the rules → Check eligibility → Fill the gaps, with three real screens and the value to students |
| 4 | **Deterministic, evidence-based eligibility** | How a verdict is made (profile + structured rule → rule engine → per-rule outcome), the stack, and the four verdicts in their fixed order, with "Eligible is our verdict, not an approval" |
| 5 | **It works: one missing fact, one real change** | Proof: the GitHub Student Developer Pack goes from Potential match to Eligible after a date of birth is added. Release test results, next steps, the closing line and the URL. |

## Sources for every claim

- **Live product:** `https://opportunities.sahelyon.com` loads, and its API (`api.opportunities.sahelyon.com`)
  reported healthy and served 12 opportunities on 31 Oct 2026. Response headers show both are hosted on
  Render.
- **Screenshots:**
  - The landing page, the opportunity listing and the KAUST detail page were captured from the **live site**.
  - The signed-in screens (the Eligibility page and the GitHub Student Developer Pack before and after) were
    captured from the **local release build** (commit `b8da30f`) with the seeded demo account and the same
    12-program dataset. They're labelled that way on the slides.
  - The signed-in screens weren't captured on production, so the production demo account and data wouldn't
    change.
- **Quotes on slide 2** are copied from the seeded dataset, whose quotes were checked against the official
  pages (retrieved 30 Oct 2026). The Schwarzman quote is shortened with a marked ellipsis.
- **Test results on slide 5** (572 backend, 21 browser) are from the final verification run at the release
  commit (`docs/DEPLOYMENT.md`, section 6).
- **"7 rule types"** are the evaluators in `backend/app/services/matching/registry.py`: `numeric_threshold`,
  `set_membership`, `equality`, `boolean_flag`, `date_gate`, `skill_set` and `any_of`.
- **The verdict order and wording** follow `backend/app/services/matching/evaluate.py` and the app's own copy.

## Assumptions and deliberate omissions

- **No presenter or team names.** None are recorded in the repository or project documents. Add them to
  slide 1 if you want them.
- **The database host is not named.** The deployment guide plans Neon, but the live database provider can't be
  verified from outside, so the slide says "PostgreSQL".
- **Left out as unverifiable:** user numbers, adoption, accuracy rates, time saved, partnerships with any
  listed organization, revenue and a validated business model.
- **"Needs review" is presented honestly** as the right answer for conditions a machine can't check. The deck
  doesn't hide that most current programs have at least one such condition (see `docs/JUDGE_QA.md`).
- **The deck doesn't use the hackathon's name or date**; neither is recorded in the repository.
