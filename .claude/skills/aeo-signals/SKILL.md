---
name: aeo-signals
description: >
  Interpret Spy's AEO (Answer Engine Optimization) score and evidence — schema coverage, heading
  hygiene, question coverage, structured content and authorship. Use when analysing aeo_score,
  explaining why a site is or isn't extractable by AI answer engines, or deciding what to change to
  become a better citation candidate.
---

# Reading Spy's AEO output

AEO measures whether a page's content can be **extracted and cited** by an
answer engine — ChatGPT, Perplexity, Google's AI surfaces. It is about
structure and attribution, not persuasion.

The score is a pure function of stored crawl evidence. Read
`evidence.aeo` on the audit object rather than inferring from the number.

## The six signals

| Field | Means | Fix when low |
| --- | --- | --- |
| `schema_coverage_pct` | Share of indexable pages carrying any JSON-LD | Add schema; `Article`, `Service`, `FAQPage` as the content warrants |
| `clean_heading_pct` | Pages with exactly one H1 **and** no skipped ranks below it | Repair the outline — H1 → H2 → H3, never H1 → H3 |
| `question_coverage_pct` | Pages with at least one question-shaped heading | Add real questions users ask, as headings, answered directly beneath |
| `structured_content_pct` | Pages using lists, tables or definition lists | Break dense prose into extractable structures |
| `byline_coverage_pct` | Pages with a detectable author byline | Add named authors and bios |
| `has_faq_schema` | Whether `FAQPage` appears anywhere | Mark up existing Q&A blocks |

A `reason` field instead of numbers means there was nothing scoreable — no
indexable pages. Pass that through as "not measured".

## What matters most

**Authorship is usually the biggest lever and the most neglected.** A site can
score well on every structural signal and still sit at 0% bylines. Answer
engines weight named, credentialed authorship when choosing whose claim to
repeat; an unattributed article is a weaker citation candidate than an
identical one with a real person behind it. It is also a content decision, not
an engineering one, which is why it lingers.

**Question coverage is the cheapest real win** on sites that already use FAQ
schema somewhere — the habit exists, it just hasn't been extended. Questions
are the literal unit an answer engine matches against.

**Schema coverage below 100% on a site that has schema at all** usually means
one template is missing it rather than a site-wide gap. Check `schema_types`
per page in the `/pages` response to find which.

## Per-page evidence

`/audits/<id>/pages` carries the raw inputs, so you can name the pages rather
than quoting percentages:

`question_heading_count`, `list_count`, `table_count`, `has_definition_list`,
`has_author_byline`, `heading_order_valid`, `has_schema`, `schema_types`.

## Honesty constraints

AEO measures **readiness to be cited**, never citation itself. Spy cannot
observe whether an answer engine actually quoted a site, and nothing in this
score should be phrased as a promise of placement or visibility in AI answers.
"Better positioned to be cited" is accurate; "will appear in ChatGPT" is not.

If schema coverage reads 0%, verify it before reporting — fetch a page and grep
for `application/ld+json`. Schema detection in this scanner has been wrong
before, and a false zero here drags the whole score down.
