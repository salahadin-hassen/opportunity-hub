# Vetted sources: decisions and terms review

`vetted_sources.json` lists official programme pages for the ingestion pipeline
(`docs/architecture/INGESTION_PIPELINE.md`); `terms_reviews.json` records the terms decision for each.
Every page was found through the organisation's own site and probed live with the pipeline's user agent
(robots.txt, status, server-rendered text) before it was kept. Nothing on these pages is guessed: the
pipeline publishes only fields it can quote from the page.

Last checked: 2026-11-22. 116 sources.

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

### Batch 2: single programme pages (79 sources)

These official URLs came from the local development dataset, whose listing **content was not used**: a check
on 2026-11-22 found none of its quoted rules on the official pages (0 of 30 sampled) and 76 of its URLs
returning 404. Only the URLs were kept, and only where the page exists (HTTP 200 on the same host), robots.txt
allows our agent, and the page has server-rendered text. 261 sites were probed: 104 usable, 24 excluded on
terms (automated scan, deliberately conservative), 1 unreadable. The pipeline reads each page itself and
publishes only what it can quote.

| Source | Category | Pages |
|---|---|---|
| NASA (www.nasa.gov) | government | 1 |
| Korea Advanced Institute of Science and Technology (admission.kaist.ac.kr) | university | 1 |
| European Commission (erasmus-plus.ec.europa.eu) | government | 1 |
| Zonta International (www.zonta.org) | research institution | 1 |
| Brooke Owens Fellowship (www.brookeowensfellowship.org) | research institution | 1 |
| Google (developers.google.com) | employer | 2 |
| King Abdullah University of Science and Technology (admissions.kaust.edu.sa) | university | 1 |
| King Abdullah University of Science and Technology (www.kaust.edu.sa) | university | 1 |
| P.E.O. International (www.peointernational.org) | research institution | 1 |
| McCall MacBain Foundation & McGill University (mccallmacbainscholars.org) | university | 1 |
| Cambridge Trust (www.cambridgetrust.org) | foundation | 1 |
| University of Toronto (future.utoronto.ca) | university | 1 |
| Government of Canada (vanier.gc.ca) | government | 1 |
| King Fahd University of Petroleum & Minerals (cgis.kfupm.edu.sa) | university | 1 |
| The Beit Trust (beittrust.org.uk) | foundation | 1 |
| The Mandela Rhodes Foundation (www.mandelarhodes.org) | foundation | 1 |
| Fundación Carolina (www.fundacioncarolina.es) | foundation | 1 |
| Programa Nacional de Becas y Crédito Educativo (PRONABEC) (www.gob.pe) | government | 1 |
| Friedrich-Ebert-Stiftung (www.fes.de) | foundation | 1 |
| POSCO TJ Park Foundation (www.postf.org) | foundation | 1 |
| Said Foundation (saidfoundation.org) | foundation | 1 |
| African University of Science and Technology (AUST) (aust.edu.ng) | university | 1 |
| University of Oslo (www.uio.no) | university | 1 |
| University of Groningen (www.rug.nl) | university | 1 |
| Aalto University (www.aalto.fi) | university | 1 |
| Sciences Po Paris (www.sciencespo.fr) | research institution | 1 |
| United Nations Youth Office (www.un.org) | international organization | 1 |
| Mo Ibrahim Foundation (mo.ibrahim.foundation) | foundation | 1 |
| Human Rights Watch (www.hrw.org) | research institution | 1 |
| Microsoft (careers.microsoft.com) | employer | 1 |
| Jane Street Capital (www.janestreet.com) | employer | 1 |
| Santa Fe Institute (www.santafe.edu) | university | 1 |
| Schmidt Sciences & Rhodes Trust (schmidtsciencefellows.org) | foundation | 1 |
| Apple Inc. (www.apple.com) | employer | 1 |
| Amazon (www.amazon.jobs) | employer | 1 |
| Adobe Inc. (research.adobe.com) | employer | 1 |
| Bloomberg LP (www.bloomberg.com) | research institution | 1 |
| Google DeepMind (deepmind.google) | employer | 1 |
| OpenAI (openai.com) | research institution | 1 |
| Anthropic (www.anthropic.com) | research institution | 1 |
| European Research Council (erc.europa.eu) | government | 1 |
| Wellcome Trust (wellcome.org) | foundation | 2 |
| Balliol College, University of Oxford (www.balliol.ox.ac.uk) | university | 1 |
| Trinity College, University of Cambridge (www.trin.cam.ac.uk) | university | 1 |
| Howard Hughes Medical Institute (www.hhmi.org) | research institution | 1 |
| Echoing Green (echoinggreen.org) | research institution | 1 |
| London School of Economics and Political Science (www.lse.ac.uk) | university | 1 |
| Cornell University (societyhumanities.as.cornell.edu) | university | 1 |
| University of California, Berkeley (miller.berkeley.edu) | university | 1 |
| Alfred P. Sloan Foundation (sloan.org) | foundation | 1 |
| Fulbright Foreign Scholarship Board (fulbrightscholars.org) | research institution | 1 |
| Max Planck Society (photonics.maxplanckschools.org) | research institution | 1 |
| Lawrence Berkeley National Laboratory (education.lbl.gov) | government | 1 |
| Brookhaven National Laboratory (www.bnl.gov) | government | 1 |
| European Southern Observatory (www.eso.org) | research institution | 1 |
| Institut Pasteur (www.pasteur.fr) | research institution | 1 |
| RIKEN Center for Brain Science (cbs.riken.jp) | research institution | 1 |
| Cold Spring Harbor Laboratory (www.cshl.edu) | university | 1 |
| National Institute for Materials Science (NIMS) (www.nims.go.jp) | government | 1 |
| Utrecht Network (utrecht-network.org) | research institution | 1 |
| Massachusetts Institute of Technology (urop.mit.edu) | university | 1 |
| Mayo Clinic College of Medicine and Science (college.mayo.edu) | university | 1 |
| Broad Institute of MIT and Harvard (www.broadinstitute.org) | research institution | 1 |
| Y Combinator (www.ycombinator.com) | research institution | 1 |
| Falling Walls Foundation (falling-walls.com) | foundation | 1 |
| The Thiel Foundation (thielfellowship.org) | foundation | 1 |
| D-Prize (d-prize.org) | research institution | 1 |
| International Olympiad in Informatics (ioinformatics.org) | research institution | 1 |
| EIT Climate-KIC (www.climate-kic.org) | research institution | 1 |
| EIT Health (eithealth.eu) | research institution | 1 |
| European Organization for Nuclear Research (CERN) (home.cern) | international organization | 1 |
| Hult Prize Foundation (www.hultprize.org) | foundation | 1 |
| Massachusetts Institute of Technology (cep.mit.edu) | university | 1 |
| European Organization for Nuclear Research (CERN) (beamlineforschools.cern) | international organization | 1 |
| Lindau Nobel Laureate Meetings Council (www.lindau-nobel.org) | research institution | 1 |
| Harvard Summer School (summer.harvard.edu) | university | 1 |
| Utrecht University (utrechtsummerschool.nl) | university | 1 |
| Max Planck Institute for Legal History and Legal Theory (www.lhlt.mpg.de) | research institution | 1 |
| Bucerius Law School (www.law-school.de) | research institution | 1 |

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
| GitHub Education (education.github.com) | Terms appear restrictive (automated scan, conservative): You may not assign or delegate any rights or obligations under the Terms of Service or Privacy Statement without our prior written consent, and any unauthorized assignment and dele |
| ETH Zurich (ethz.ch) | Terms appear restrictive (automated scan, conservative): Without prior written consent from ETH Zurich it is not permissible for the documents and web pages and parts thereof to be either copied or stored on other servers, input into new |
| Asian Development Bank (www.adb.org) | Terms appear restrictive (automated scan, conservative): You may not claim or imply that ADB endorses your use of project data, nor may you use ADB's logo in conjunction with such use, unless you have received prior written permission fr |
| Islamic Development Bank (www.isdb.org) | Terms appear restrictive (automated scan, conservative): The use or misuse of these trademarks or any other materials, except as permitted herein, is expressly prohibited and may be in violation of copyright, trademark or other intellect |
| OPEC Fund for International Development (opecfund.org) | Terms appear restrictive (automated scan, conservative): Our prior consent is required before they are permitted to transfer responsibility for processing personal data to a third party. |
| Narotam Sekhsaria Foundation (pg.nsfoundation.co.in) | Terms appear restrictive (automated scan, conservative): Commercial use of any of the contents on the Site in any manner is prohibited, without prior written permission from an authorised NSF person. |
| Abdulla Al Ghurair Foundation for Education (www.alghurairfoundation.org) | Terms appear restrictive (automated scan, conservative): Material contained on the Website may be downloaded, viewed and printed for personal use only and provided that no trademark, copyright or other proprietary notices contained in or |
| Radboud University (www.ru.nl) | Terms appear restrictive (automated scan, conservative): This is possible only with the prior written consent of Radboud University. |
| International Committee of the Red Cross (careers.icrc.org) | Terms appear restrictive (automated scan, conservative): using automated means to access content from any of our services in violation of the machine-readable instructions on our web pages (for example, robots.txt files that disallow cra |
| ETH Zurich (inf.ethz.ch) | Terms appear restrictive (automated scan, conservative): Without prior written consent from ETH Zurich it is not permissible for the documents and web pages and parts thereof to be either copied or stored on other servers, input into new |
| NVIDIA Corporation (www.nvidia.com) | Terms appear restrictive (automated scan, conservative): You may not use NVIDIA's trademarks without NVIDIA’s prior written permission, and nothing in these Terms will be construed as granting such permission. |
| Two Sigma Investments (www.twosigma.com) | Terms appear restrictive (automated scan, conservative): You may not use any data mining, robots or similar data gathering and extraction programs or methods, whether automated or manual, to access, acquire, copy or monitor any portion o |
| National Academies of Sciences, Engineering, and Medicine (www.nationalacademies.org) | Terms appear restrictive (automated scan, conservative): Therefore, reproduction, modification, storage in a retrieval system or retransmission, in any form or by any means, electronic, mechanical, or otherwise, for reasons other than pe |
| Open Society Foundations (www.opensocietyfoundations.org) | Terms appear restrictive (automated scan, conservative): Other than as specifically described in the preceding paragraph, you may not copy, reproduce, distribute, modify, display, republish, transmit, repost, or otherwise use the content |
| Stanford University (stanfordsciencefellows.stanford.edu) | Terms appear restrictive (automated scan, conservative): User may download material from the Sites only for User’s own personal, non-commercial use. |
| The University of Tokyo (www.u-tokyo.ac.jp) | Terms appear restrictive (automated scan, conservative): Content may not be copied, reproduced or altered without permission. |
| National Geographic Society (www.nationalgeographic.org) | Terms appear restrictive (automated scan, conservative): 3.1 Prohibition on Data Scraping​ |
| Microsoft (imaginecup.microsoft.com) | Terms appear restrictive (automated scan, conservative): Any reproduction or redistribution of the Software not in accordance with the License Agreement is expressly prohibited by law, and may result in severe civil and criminal penaltie |
| XPRIZE Foundation (www.xprize.org) | Terms appear restrictive (automated scan, conservative): These Terms of Use permit you to use the Website for personal, non-commercial use only. |
| Institution of Mechanical Engineers (IMechE) (www.imeche.org) | Terms appear restrictive (automated scan, conservative): 2.5 No text or data mining, or web scraping |
| Breakthrough Prize Foundation (breakthroughjuniorchallenge.org) | Terms appear restrictive (automated scan, conservative): No such Content can be copied, publicly displayed, modified, sold, licensed or distributed in any way by You without such owner's prior written consent. |
| Red Dot GmbH & Co. KG (www.red-dot.org) | Terms appear restrictive (automated scan, conservative): Any duplication or reproduction of them in whole or in part is subject to the prior written permission of Red Dot GmbH & Co. |
| University of California, Berkeley (summer.berkeley.edu) | Terms appear restrictive (automated scan, conservative): These records are confidential, and in most circumstances, may be released to third parties only with your prior consent. |
| King's College London (www.kcl.ac.uk) | Terms appear restrictive (automated scan, conservative): The content of this website may be viewed, printed or downloaded for personal, non-commercial use only. |
