# Gold evaluation set, v1

`opportunities.json` is the baseline the opportunity intelligence pipeline is measured against (plan task
M2-T16). It is **generated**, so don't edit it by hand:

```bash
cd backend
python -m scripts.build_gold_set          # rebuild from scripts/seed_demo.py
python -m scripts.build_gold_set --check  # fail if the committed file is stale (also enforced by tests)
```

## What it contains
- **Records:** 14, one per opportunity curated by hand in `scripts/seed_demo.py`, valid as of 2026-10-30.
- **Scored fields:** title, provider, official URL, deadline, deadline type and listing status.
- **Unscored fields:** opportunity type, location mode, countries, languages and tags. These are curator
  classifications with no supporting quote, so they're kept under `reference` only.
- **Requirements:** 43 eligibility statements, each with its verbatim quote, source URL, category,
  mandatory flag and curated rule (`kind` + `params`, normalised by the same validator the API uses).

## Needs manual review (12 requirements)
These curated rules rest on an interpretation that the automated pipeline must not reproduce. They're
excluded from rule-conversion scoring until a person resolves them:

| Flag | Count | Meaning |
| --- | --- | --- |
| `table_cells_quote` | 4 | The quote joins two table cells (`header \| cell`). It never appears verbatim in page text, so quote verification can't match it. |
| `or_equivalent_wording` | 3 | The wording says "or equivalent", but the curated rule is structured. The pipeline policy treats this as ambiguous. |
| `retrieval_date_reference` | 2 | An age rule checked against the retrieval date, because the page gives no reference date. |
| `derived_reference_date` | 3 | An age rule whose reference date the curator worked out; it isn't stated in the quote. |

`GoldSet.manual_review_items()` lists them by id.

## Limitations
- **No page snapshots.** Quote verification against page text needs the fetcher (M2-T7/T8). The next
  dataset version should add snapshot references.
- **Facts may be outdated.** Deadlines and statuses on the live pages may have changed since 2026-10-30.
- **The set is small.** With 14 records it shows systematic errors, not reliable accuracy rates.
  DEC-26 proposes about 50 labelled pages.
