# Opportunity Hub — Judges' Q&A

Short, honest answers. Every number here comes from the codebase or the dataset, not from estimates.
Where we don't know something, the answer says so.

---

### How accurate is it?
The engine's accuracy has two parts.

- **Applying rules correctly.** The rule logic is covered by about 570 automated backend tests. These include
  every rule type, the GPA-scale cases and the verdict order. The same profile and rules always produce the
  same verdict.
- **Encoding rules correctly.** This is where errors could come in, so each rule is stored next to the exact
  sentence it came from. A fact-check compared every quote against the live official pages; we corrected or
  removed what didn't match (one program was dropped because its page couldn't be verified). Anyone can open
  a rule and read the source.

We haven't measured accuracy against real applicants' outcomes, and we don't claim an accuracy rate.

### How is eligibility calculated?
Each requirement is a structured rule: a GPA threshold on a stated scale, a citizenship list, a degree level,
current enrolment, an age on a stated date, or a set of skills, plus "any of" combinations. Each rule
resolves to **met**, **not met**, **missing** (your profile lacks the fact) or **needs review** (a person
must confirm). The opportunity then takes the first verdict that applies, in this order:

1. any mandatory rule not met: **Not eligible**;
2. otherwise, anything needs review: **Needs review**;
3. otherwise, a fact is missing: **Potential match**;
4. otherwise: **Eligible**.

### Is this AI?
No. It's deterministic rule evaluation. Nothing is predicted or scored, and every verdict can be traced to
specific rules and quotes.

### How do you verify official sources?
Rules are copied from each program's official page. The quote, the page URL and the retrieval date are
stored with the rule and shown to the user. Deadlines appear only where the official page publishes one;
otherwise the app says "See official page".

### What happens when information is missing?
The rule is marked *missing*, never *failed*, and the opportunity becomes a **Potential match**. The app shows
which fact is missing, how many opportunities depend on it, and an inline field to add it. Saving re-checks
only the affected opportunities and shows exactly which verdicts changed.

### How do you handle different GPA scales?
A GPA threshold is compared only against a GPA on the same scale. A GPA on a different scale (8.4 out of 10
against a 3.5-out-of-4 rule) goes to **needs review** instead of being converted, because conversions between
grading systems aren't standard. Students enter their GPA together with its scale (4, 5, 10 or 100).

### Why do so many results say "Needs review"?
Real eligibility pages include conditions no profile field can answer: field of study, years completed,
"not a current student of this university". Rather than ignore them and claim "Eligible", we list them for
the student to confirm. With the current data, 8 of the 12 listed programs have at least one such condition.
Reading more profile facts is our next step for reducing that number honestly.

### Does "Eligible" mean I'll be accepted?
No. It means your profile meets every published rule we could check. Selection, awards and approvals are
always the organization's decision, and the app says this wherever a verdict appears.

### What about data privacy?
- We store the account email and an Argon2id password hash, the profile facts rules read (citizenship, date
  of birth, degree level, enrolment, GPA and scale, skills), a few profile-only facts (name, institution,
  field, residence, optional test scores), and eligibility results.
- No documents are uploaded. Nothing is shared with the listed organizations. There are no advertising or
  analytics trackers.
- Account deletion isn't self-service yet, and we say so on the privacy page. We make no legal-compliance
  claims.
- Security basics: hashed passwords, 30-minute signed tokens, an explicit CORS allow-list, limits on login
  and registration attempts, and curator-only writes disabled in production.

### How many opportunities do you cover?
12 open programs (plus 2 whose current cycle has closed): scholarships, internships, research programs,
fellowships and an open-source program, from organizations including CERN, KAUST, NASA, GitHub, ETH Zürich,
EPFL, the Gates Cambridge Trust, Schwarzman Scholars, Zonta International and Google. We have no
partnerships with any of them.

### What are the current limitations?
- Coverage is small and hand-curated.
- Six profile facts are evaluated; field of study and year of study are not yet.
- No account deletion, and no session refresh (sessions last 30 minutes).
- The free hosting tier sleeps when idle; the first visit after a quiet period takes about a minute.
- No application tracking or deadline reminders yet.

### How would you scale coverage?
With curator tooling that turns an eligibility page into draft structured rules and quotes for a person to
approve. Accuracy depends on a human checking the encoding, so the goal is to make that check fast, not to
remove it. The data model already stores sources, retrieval dates and curator notes for this.

### What's the business model?
We haven't validated one. Options we'd test:
- licensing to university career and scholarship offices, which advise many students on the same programs;
- organizations paying to have their eligibility rules structured and verified, so they get fewer ineligible
  applications;
- staying free for students in all cases.

### Why would organizations care?
Ineligible applications cost reviewers time too. A clear, verifiable statement of who qualifies helps both
sides. That's a hypothesis we'd want to test with real programs.

### What's next?
1. Curator tooling for faster, verified rule encoding.
2. More profile facts (field and year of study) to reduce "needs review".
3. Deadline alerts for opportunities a student qualifies for.
4. Self-service account deletion and data export.
