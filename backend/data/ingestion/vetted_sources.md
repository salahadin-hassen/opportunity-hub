# Vetted sources: decisions and terms review

`vetted_sources.json` lists official programme pages for the ingestion pipeline
(`docs/architecture/INGESTION_PIPELINE.md`); `terms_reviews.json` records the terms decision for each.
Every page was found through the organisation's own site and probed live with the pipeline's user agent
(robots.txt, status, server-rendered text) before it was kept. Nothing on these pages is guessed: the
pipeline publishes only fields it can quote from the page.

Last checked: 2026-11-22. 37 sources.

`ingest-starter-sync` (or "Import starter sources" in the curator workspace) creates new sources and updates
existing ones whose declaration changed; an updated source goes back to testing and must be approved again.

## Sources

| Source | Category | Pages |
|---|---|---|
| Commonwealth Scholarship Commission in the UK | government | 5 |
| Mitacs programs | research institution | 10 |
| Manaaki New Zealand Scholarships | government | 5 |
| Study in Japan: government scholarships | government | 2 |
| Türkiye Scholarships | government | 4 |
| Chevening Scholarships | government | 1 |
| Joint Japan/World Bank Graduate Scholarship Program | international organization | 1 |
| MIT Summer Research Program (MSRP) | university | 1 |
| Outreachy internships | foundation | 1 |
| Rhodes Scholarship | foundation | 1 |
| Stipendium Hungaricum | government | 1 |
| CERN student and graduate programmes | research institution | 10 |
| JSPS fellowships for international researchers | government | 6 |
| DAAD RISE research internships | scholarship provider | 3 |
| Marie Skłodowska-Curie Actions | international organization | 2 |
| European Central Bank traineeships and graduate programme | international organization | 2 |
| Swedish Institute scholarships | government | 2 |
| France Excellence Eiffel Scholarship | government | 1 |
| NL Scholarship | government | 1 |
| Government of Ireland International Education Scholarships | government | 1 |
| Gates Cambridge Scholarship | foundation | 1 |
| Marshall Scholarship | government | 1 |
| Hertz Fellowship | foundation | 1 |
| Google PhD Fellowship | employer | 1 |
| Google Summer of Code | employer | 1 |
| WHO internship programme | international organization | 1 |
| EMBL International PhD Programme | research institution | 1 |
| Marine Biological Laboratory advanced research training courses | research institution | 29 |
| NAWA scholarships for international students | government | 4 |
| DOE Office of Science workforce programmes (SULI, CCI, SCGSR, Einstein) | government | 4 |
| WIPO internship program | international organization | 1 |
| Hong Kong PhD Fellowship Scheme | government | 1 |
| UKRI funding finder | government | index (15 listing pages) |
| NWO calls for proposals | government | index (10 listing pages) |
| DFG individual funding programmes | government | 10 |
| Research Ireland funding programmes | government | 16 |
| NSF funding opportunities | government | 307 |

## Removed, and why (add by hand in the curator workspace if wanted)

| Programme | Reason |
|---|---|
| Australia Awards (DFAT) | The site aborts automated connections, including robots.txt |
| Oxford Clarendon | The site answers automated readers with HTTP 403 |
| Mastercard Foundation Scholars | No direct application: applicants apply through partner universities |
| Heidelberg Laureate Forum | The young-researchers page has no application details |
| Fulbright Foreign Student Program | Run by in-country Fulbright commissions; no central deadline. Replaced by the FLTA programme on the same site |

| Fulbright U.S. Student Program, Fulbright FLTA | IIE's terms forbid automated cataloguing |
| Humboldt Foundation, Schwarzman, UNICEF, Royal Academy of Engineering | Terms restrict reuse (see below) |
| Keystone Symposia | Conference pages carry no eligibility rules, so automation would hold every one |
| Euraxess | Paginated listings return an anti-bot page; not worked around |
| Gordon Research Conferences | The site answers automated readers with a CAPTCHA |
| Fulbright Scholar awards | Award search pagination is disallowed by robots.txt; the sitemap omits award pages |
| Erasmus Mundus catalogue | Each programme lives on its own consortium site (about 200 separate terms reviews) |

## Terms of use: decisions

The pipeline stores each page privately and publishes facts with short verbatim quotes of eligibility rules,
attributed and linked to the official page. Opportunity Hub is non-commercial (confirmed by the owner,
2026-11-22), which is the basis for accepting sources licensed for non-commercial reuse only.

| Source | What was checked |
|---|---|
| Commonwealth Scholarship Commission in the UK | cscuk.fcdo.gov.uk/copyright-notice: content is CSC copyright; no reuse prohibition stated. No reuse restriction found on the site's legal/terms pages (checked 2026-11-22). We store the page privately and publish facts with short verbatim quotes of eligibility rules, attributed and linked to the official page. |
| Mitacs programs | No reuse restriction found on the site's legal/terms pages (checked 2026-11-22). We store the page privately and publish facts with short verbatim quotes of eligibility rules, attributed and linked to the official page. |
| Manaaki New Zealand Scholarships | No reuse restriction found on the site's legal/terms pages (checked 2026-11-22). We store the page privately and publish facts with short verbatim quotes of eligibility rules, attributed and linked to the official page. |
| Study in Japan: government scholarships | No reuse restriction found on the site's legal/terms pages (checked 2026-11-22). We store the page privately and publish facts with short verbatim quotes of eligibility rules, attributed and linked to the official page. |
| Türkiye Scholarships | No reuse restriction found on the site's legal/terms pages (checked 2026-11-22). We store the page privately and publish facts with short verbatim quotes of eligibility rules, attributed and linked to the official page. |
| Chevening Scholarships | No reuse restriction found on the site's legal/terms pages (checked 2026-11-22). We store the page privately and publish facts with short verbatim quotes of eligibility rules, attributed and linked to the official page. |
| Joint Japan/World Bank Graduate Scholarship Program | worldbank.org terms: informational, non-commercial use (checked 2026-11-20). Owner confirmed Opportunity Hub is non-commercial (2026-11-22); re-review if that changes. |
| MIT Summer Research Program (MSRP) | No reuse restriction found on the site's legal/terms pages (checked 2026-11-22). We store the page privately and publish facts with short verbatim quotes of eligibility rules, attributed and linked to the official page. |
| Outreachy internships | Footer: Creative Commons CC-BY (checked 2026-11-20). |
| Rhodes Scholarship | No reuse restriction found on the site's legal/terms pages (checked 2026-11-22). We store the page privately and publish facts with short verbatim quotes of eligibility rules, attributed and linked to the official page. |
| Stipendium Hungaricum | No reuse restriction found on the site's legal/terms pages (checked 2026-11-22). We store the page privately and publish facts with short verbatim quotes of eligibility rules, attributed and linked to the official page. |
| CERN student and graduate programmes | No reuse restriction found on the site's legal/terms pages (checked 2026-11-22). We store the page privately and publish facts with short verbatim quotes of eligibility rules, attributed and linked to the official page. |
| JSPS fellowships for international researchers | No reuse restriction found on the site's legal/terms pages (checked 2026-11-22). We store the page privately and publish facts with short verbatim quotes of eligibility rules, attributed and linked to the official page. |
| DAAD RISE research internships | No reuse restriction found on the site's legal/terms pages (checked 2026-11-22). We store the page privately and publish facts with short verbatim quotes of eligibility rules, attributed and linked to the official page. |
| Marie Skłodowska-Curie Actions | commission.europa.eu/legal-notice: EU content licensed CC BY 4.0, reuse allowed with credit (checked 2026-11-22). |
| European Central Bank traineeships and graduate programme | ecb.europa.eu disclaimer: information may be reproduced if accurate and the ECB is cited as the source (checked 2026-11-22). |
| Swedish Institute scholarships | No reuse restriction found on the site's legal/terms pages (checked 2026-11-22). We store the page privately and publish facts with short verbatim quotes of eligibility rules, attributed and linked to the official page. |
| France Excellence Eiffel Scholarship | No reuse restriction found on the site's legal/terms pages (checked 2026-11-22). We store the page privately and publish facts with short verbatim quotes of eligibility rules, attributed and linked to the official page. |
| NL Scholarship | studyinnl.org/copyright: content CC BY-NC 4.0 (checked 2026-11-22). Owner confirmed Opportunity Hub is non-commercial (2026-11-22); re-review if that changes. |
| Government of Ireland International Education Scholarships | hea.ie cites the Re-Use of Public Sector Information Regulations (checked 2026-11-22). No reuse restriction found on the site's legal/terms pages (checked 2026-11-22). We store the page privately and publish facts with short verbatim quotes of eligibility rules, attributed and linked to the official page. |
| Gates Cambridge Scholarship | No reuse restriction found on the site's legal/terms pages (checked 2026-11-22). We store the page privately and publish facts with short verbatim quotes of eligibility rules, attributed and linked to the official page. |
| Marshall Scholarship | No reuse restriction found on the site's legal/terms pages (checked 2026-11-22). We store the page privately and publish facts with short verbatim quotes of eligibility rules, attributed and linked to the official page. |
| Hertz Fellowship | No reuse restriction found on the site's legal/terms pages (checked 2026-11-22). We store the page privately and publish facts with short verbatim quotes of eligibility rules, attributed and linked to the official page. |
| Google PhD Fellowship | No reuse restriction found on the site's legal/terms pages (checked 2026-11-22). We store the page privately and publish facts with short verbatim quotes of eligibility rules, attributed and linked to the official page. |
| Google Summer of Code | No reuse restriction found on the site's legal/terms pages (checked 2026-11-22). We store the page privately and publish facts with short verbatim quotes of eligibility rules, attributed and linked to the official page. |
| WHO internship programme | who.int terms-of-use: extracts may be reproduced for non-commercial/educational purposes (checked 2026-11-22). Owner confirmed Opportunity Hub is non-commercial (2026-11-22); re-review if that changes. |
| EMBL International PhD Programme | No reuse restriction found on the site's legal/terms pages (checked 2026-11-22). We store the page privately and publish facts with short verbatim quotes of eligibility rules, attributed and linked to the official page. |
| Marine Biological Laboratory advanced research training courses | No reuse restriction found on the site's legal/terms pages (checked 2026-11-22). We store the page privately and publish facts with short verbatim quotes of eligibility rules, attributed and linked to the official page. |
| NAWA scholarships for international students | No reuse restriction found on the site's legal/terms pages (checked 2026-11-22). We store the page privately and publish facts with short verbatim quotes of eligibility rules, attributed and linked to the official page. |
| DOE Office of Science workforce programmes (SULI, CCI, SCGSR, Einstein) | science.osti.gov/Web-Policies: Office of Science materials are in the public domain; DOE asks for acknowledgement (checked 2026-11-22). |
| WIPO internship program | No reuse restriction found on the site's legal/terms pages (checked 2026-11-22). We store the page privately and publish facts with short verbatim quotes of eligibility rules, attributed and linked to the official page. |
| Hong Kong PhD Fellowship Scheme | No reuse restriction found on the site's legal/terms pages (checked 2026-11-22). We store the page privately and publish facts with short verbatim quotes of eligibility rules, attributed and linked to the official page. |
| UKRI funding finder | ukri.org/who-we-are/terms-of-use: most content CC BY-NC-SA 4.0; non-commercial reuse permitted (checked 2026-11-22). Owner confirmed Opportunity Hub is non-commercial (2026-11-22); re-review if that changes. |
| NWO calls for proposals | No reuse restriction found on the site's legal/terms pages (checked 2026-11-22). We store the page privately and publish facts with short verbatim quotes of eligibility rules, attributed and linked to the official page. |
| DFG individual funding programmes | dfg.de imprint: reproduction for educational/scientific purposes permitted with source acknowledged; commercial use needs consent (checked 2026-11-22). Owner confirmed Opportunity Hub is non-commercial (2026-11-22); re-review if that changes. |
| Research Ireland funding programmes | research.ie policies cite the Re-Use of Public Sector Information Regulations (checked 2026-11-22). No reuse restriction found on the site's legal/terms pages (checked 2026-11-22). We store the page privately and publish facts with short verbatim quotes of eligibility rules, attributed and linked to the official page. |
| NSF funding opportunities | NSF-authored pages are U.S. federal government works (17 U.S.C. 105, public domain); no site restriction found (checked 2026-11-22). |

### Excluded on their terms

| Source | Why |
|---|---|
| Fulbright Foreign Language Teaching Assistant (FLTA) Program | IIE terms (iie.org/terms-and-conditions) forbid spiders/robots cataloguing or reproducing content |
| Fulbright U.S. Student Program | IIE terms (iie.org/terms-and-conditions) forbid spiders/robots cataloguing or reproducing content |
| Amgen Scholars Program | amgen.com/terms-of-use: copying solely for your own use |
| Knight-Hennessy Scholars | stanford.edu/site/terms: personal, non-commercial use only; no republishing |
| Swiss Government Excellence Scholarships | admin.ch terms: any reproduction requires prior written consent |
| Alexander von Humboldt Foundation fellowships | humboldt-foundation.de/en/imprint: copying only for private, non-commercial use; other exploitation needs written agreement |
| Schwarzman Scholars | schwarzmanscholars.org/terms-of-use: personal licence for internal use only |
| UNICEF internships | unicef.org/legal: reproduction for wider dissemination needs prior written permission |
| Royal Academy of Engineering programmes | raeng.org.uk/disclaimer: reproduction or storage in any other work is expressly prohibited |
