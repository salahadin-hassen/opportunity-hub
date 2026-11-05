# Opportunity Hub — Speaker script

About four and a half minutes, one section per slide. The same text is in each slide's speaker notes.
The live demo steps (sign in, check, add a date of birth, re-check) are in `../DEMO_RUNBOOK.md`.

## Slide 1 · Title and vision (0:00–0:30)

Think about the last time you looked for a scholarship or an internship. You find a promising program, open its eligibility page, and meet a list of conditions written in that program's own words.

Opportunity Hub is opportunity discovery that tells you where you stand. It's live right now at opportunities.sahelyon.com. Every rule in it is copied word for word from an official page, and every answer comes with its evidence.

## Slide 2 · The problem (0:30–1:15)

Eligibility isn't hard because students are careless. It's hard because every program writes its rules differently. One gives a GPA on a 4-point scale. Another sets an age limit on a specific date two years away. Another excludes groups no form field can capture.

So students either spend hours decoding each page or apply anyway and find out later they never qualified. Either way, their most limited resource, time, goes into applications that couldn't succeed. These quotes are real, copied from the official pages.

## Slide 3 · Our solution (1:15–2:15)

Here's the product. A student browses real programs: CERN, KAUST, NASA, GitHub, ETH Zurich and more. Each listing shows its rules, and every rule is footnoted to the sentence on the official page it came from.

They create one short profile and run one check. Every program gets a verdict, and where a fact is missing, like a date of birth or a GPA, the app says exactly which fact, which programs depend on it, and lets them add it right there. The first two screens are the live site; the third is the release build with our demo account.

## Slide 4 · Technology and innovation (2:15–3:15)

Under the hood it's deliberately simple and checkable. A React and TypeScript web app talks to a FastAPI backend with PostgreSQL, deployed on Render.

Each requirement is a structured rule (a GPA threshold on a stated scale, a citizenship list, a degree level, an age on a given date) stored next to its official quote. The engine checks each rule against the profile: met, not met, missing, or needs review. Then the program takes the first verdict that applies, in this order.

There's no AI deciding anyone's future: the same profile and rules always give the same answer. Where it can't be sure, like a GPA on a 10-point scale against a 4-point threshold, it hands the call to the student instead of guessing. And Eligible means every published rule is met. It is never an admission: the organization decides.

## Slide 5 · Demonstration, impact and next steps (3:15–4:30)

This is the moment we demo live. Our fictional student Mekdes runs a check. The GitHub Student Developer Pack comes back as a Potential match: nothing rules her out, but one rule, at least 13 years old, can't be checked because her profile has no date of birth. It's marked missing, not failed.

She adds her date of birth and re-checks. The real engine re-evaluates only the affected programs, and the verdict becomes Eligible, with the rule marked 'was missing, now met'.

It's tested: 572 backend tests and 21 browser tests on the real stack passed at release. Today it covers 12 hand-checked programs. Next come curator tools to grow coverage without losing accuracy, more profile facts so fewer answers stop at needs review, and deadline alerts.

Every student should spend their time on applications they can actually win. Try it at opportunities.sahelyon.com.
