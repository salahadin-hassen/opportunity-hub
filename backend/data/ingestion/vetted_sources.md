# Vetted sources: decisions and terms review

`vetted_sources.json` is the first batch of official programme pages for the ingestion pipeline
(`docs/architecture/INGESTION_PIPELINE.md`). Every page was chosen by reading the programme's own
site, never guessed, and scored with the pipeline's own extractor before it was kept.

Last checked: 2026-11-20, in a clean local database at schema `7d3d9fa091ad`.
Result: 15 of 15 sources pass the live test (robots.txt, allowed hosts, fetch), and 15 of 15 candidates reach
`needs_review` (none rejected or expired). Average quality is 48 (first attempt: 10 of 16, average 37).

## How each page was chosen

| Source | Page | Why this page |
|---|---|---|
| Amgen Scholars | `amgenscholars.com/` | States the deadline (2027-02-01) and eligibility (quality 80) |
| Chevening | `/scholarships/application-timeline/` | Overview page has no dates; the timeline does |
| Commonwealth Master's | programme page | 15 quoted rules; deadline has no year, so a curator sets it |
| Fulbright FLTA | `/flta-program/flta-thinking-of-applying` | See "Replaced" below |
| Japan/World Bank (JJWBGSP) | eligible-countries page | Overview was flagged expired; this page carries the rules |
| Knight-Hennessy | `/admission/before-you-apply/eligibility` | Admission overview was rejected; eligibility page has 15 rules |
| MEXT | `/planning/scholarships/mext-scholarships/` | Found through the site's own navigation (the first address was a 404) |
| MIT MSRP | `/msrp/application/` | Deadline 2027-01-19 and 11 rules (overview scored 5) |
| Manaaki New Zealand | `/check-eligibility-criteria/` | 15 rules (home page scored 5) |
| Mitacs Globalink | programme page | Best page on the site (15 rules) |
| Outreachy | `/docs/applicant/` | Applicant guide with eligibility rules |
| Rhodes | `/scholarships/selection-criteria/` | Overview was flagged expired; criteria page has 12 rules |
| Stipendium Hungaricum | `/apply/` | Only application page |
| Swiss Government Excellence | programme page | Best page on the site |
| Türkiye Scholarships | `/scholarshipsprograms` | 12 rules (home page had 1) |

## Removed, and why (add by hand in the curator workspace if wanted)

| Programme | Reason |
|---|---|
| DAAD RISE Germany | robots.txt times out for automated clients; the pipeline treats that as "disallowed" |
| Australia Awards (DFAT) | The site aborts automated connections, including robots.txt |
| Oxford Clarendon | The site answers automated readers with HTTP 403 |
| Mastercard Foundation Scholars | No direct application: applicants apply through partner universities |
| Heidelberg Laureate Forum | The young-researchers page has no application details |
| Fulbright Foreign Student Program | Run by in-country Fulbright commissions; no central deadline. Replaced by the FLTA programme on the same site |

## Terms of use: what each site says (needs a human decision before approval in production)

The pipeline stores each page and shows short verbatim quotes of eligibility rules, with a link to the
source. Whether that fits each site's terms is a decision for the operator, not the pipeline. Quotes
below are from the sites' own terms pages, fetched 2026-11-20.

| Source | Terms page | What it says | Signal |
|---|---|---|---|
| Outreachy | footer of every page | "Free to share and remix: Creative Commons CC-BY" | Permissive |
| Japan/World Bank | worldbank.org/ext/en/legal/terms-conditions | "provided for informational and non-commercial purposes only"; "You may use the Site only for lawful, personal and non-commercial purposes." | Conditional: only if Opportunity Hub is non-commercial |
| Knight-Hennessy | stanford.edu/terms | "User may download material from the Sites only for User's own personal, non-commercial use. User may not otherwise copy, reproduce, retransmit, distribute, publish…" | Restrictive |
| Swiss Government Excellence | admin.ch/en/terms-and-conditions | "Any reproduction requires the prior written consent of the copyright holder." | Restrictive |
| Amgen Scholars | amgen.com/terms-of-use | A "personal, nonexclusive… license… to download, print and/or copy Amgen Content solely for your own use" | Restrictive |
| Chevening | footer: "© Crown copyright" | General site terms not found; the terms page found covers award holders, not the website | Check |
| Commonwealth Master's | cscuk.fcdo.gov.uk/copyright-notice/ | Page exists; no reuse wording was extracted. Read it in full | Check |
| Stipendium Hungaricum | stipendiumhungaricum.hu/impressum/ | Imprint only; no reuse terms found | Check |
| MEXT (Study in Japan) | studyinjapan.go.jp/en/about/policies.html | Covers privacy and analytics; no reuse terms found | Check |
| Mitacs | mitacs.ca/about/policies/ | Policy index; no reuse wording extracted | Check |
| Fulbright FLTA, Rhodes, Manaaki NZ, MIT MSRP, Türkiye | not found automatically | Look for "Terms", "Legal" or "Copyright" in each site's footer | Check |

Before approving a source in production, record what was checked in the terms review notes
(`ingest-source-terms … --notes "…"`), for example "Read stanford.edu/terms on <date>; permission requested" or
"CC-BY; attribution shown on the opportunity page".
