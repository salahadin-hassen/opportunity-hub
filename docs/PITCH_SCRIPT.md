# Opportunity Hub — Five-minute pitch

Spoken script with stage directions. Words in *italics* are directions; everything else is said aloud. It's
about 650 spoken words, which fits five minutes at a calm pace. Rehearse with a timer.
The click-by-click steps and expected results are in `docs/DEMO_RUNBOOK.md`.

---

## 0:00–0:45 · The problem

*Landing page on screen, not yet scrolled.*

Think about the last time you looked for a scholarship or an internship.

You find a promising program. Then you open the eligibility page: a long list of conditions. Citizenship,
degree level, GPA on some scale, age on some date, "enrolled in an eligible institution". Some are clear,
some aren't, and they're written differently on every site.

So students do one of two things. They spend hours decoding rules, program by program. Or they apply anyway
and find out later they were never eligible. Either way, the most limited resource a student has, their time,
goes into applications that couldn't succeed.

## 0:45–1:30 · The solution

*Scroll slowly through the hero to "Open right now".*

Opportunity Hub is opportunity discovery that tells you where you stand.

These are real programs: CERN, KAUST, NASA, GitHub, ETH Zürich and more. For each one, every eligibility rule
is copied word for word from the official page and stored as a structured rule.

*Scroll to "How one rule becomes a clear answer".*

You create one short profile. Our engine checks it against each rule, one at a time, and every answer comes
with its evidence: what the rule requires, what your profile says, and the official sentence it came from.

## 1:30–3:30 · Live demonstration

*Sign in as the demo account.*

This is Mekdes, a fictional aerospace engineering student from Ethiopia. Her profile is missing two things,
on purpose: her date of birth and her GPA.

*Click "Check my eligibility".*

The real backend is now evaluating every open program against her profile. You can see the progress.

*Open Eligibility.*

Four kinds of answer. **Not eligible** means a mandatory rule fails: NASA's internships need U.S.
citizenship. **Needs review** means nothing we checked rules her out, but there's a condition a machine
shouldn't decide, like "not a current KAUST student". We list those for her instead of guessing.

*Open GitHub Student Developer Pack.*

And this one is a **Potential match**. Nothing rules her out, but one rule, "at least 13 years old", can't be
checked: her profile has no date of birth. It's marked *missing*, not *failed*. That difference matters.
A missing fact shouldn't close a door.

*Back to Eligibility. In "Fill the gaps", enter 18 April 2003 and click "Save and re-check".*

She adds the one fact. Only the affected programs are checked again.

*Point at the change summary.*

Potential match becomes **Eligible**, and it came from the real engine, not a canned animation.

*Open the GitHub Pack again.*

Both rules are met, each with its evidence. And notice the line at the bottom: a verdict compares her profile
with the published rules. It isn't an admission. GitHub still makes the decision. We're honest about that
everywhere.

## 3:30–4:15 · How it works

*Optional: switch to dark mode in passing, or stay on the detail page.*

Under the hood it's deliberately simple and checkable.

The frontend is React and TypeScript. The backend is FastAPI with PostgreSQL. Each requirement is stored as a
structured rule: a GPA threshold, a citizenship list, a degree level, an age on a specific date. Each rule is
kept next to its source quote.

The engine is deterministic: no scoring, no guessing, and no AI deciding your future. The same profile and the
same rules always give the same answer, and every answer can be traced back to a sentence on an official page.
Where it can't be sure, for example a GPA on a 10-point scale against a 4-point threshold, it says so and
hands the call to the student instead of inventing a conversion.

## 4:15–5:00 · Where this goes

*Return to the landing page, or end on the detail page.*

Today, Opportunity Hub covers twelve hand-checked programs. It's small, but every rule in it is verifiable.

The next steps are clear. First, tools that let curators turn an eligibility page into structured rules
faster, so coverage grows without losing accuracy. Second, reading more of a profile, like field of study and
year of study, so fewer answers stop at "needs review". Third, alerts when a deadline is close and you're
eligible.

The goal is simple: every student, wherever they are, should spend their time on applications they can
actually win.

Thank you.

---

### Timing checkpoints
- 0:45: you are scrolling the landing page.
- 1:30: you are signing in.
- 2:45: you click "Save and re-check".
- 3:30: the changed verdict has been shown.
- 4:15: you are on the vision.

### If time is short
Cut the dark-mode moment and the "how it works" details. Never cut steps 6–8 of the walkthrough: the
missing fact, adding it and the changed verdict are the pitch.
