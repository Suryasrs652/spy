---
name: aeo-signals
description: >
  Interpret Spy's AEO (Answer Engine Optimization) score and its seven sub-scores — answerability,
  question coverage, passage extraction, structured answers, schema support, FAQ implementation and
  entity clarity. Use when analysing aeo_score, explaining why a site is or isn't extractable by AI
  answer engines, or deciding what to change to become a better citation candidate.
---

# Reading Spy's AEO output

AEO asks one question: **could an answer engine lift an answer out of this
site?** It is about structure and attribution, not persuasion, and it is
scored separately from SEO because a technically immaculate site can still
give a machine nothing to work with.

The score is a pure function of stored crawl evidence. Read
`evidence.aeo.components` on the audit object rather than inferring from the
number, and `evidence.aeo.weights_used` to see which components were actually
in the average.

## The seven sub-scores

| Component | Weight | Means | Fix when low |
| --- | --- | --- | --- |
| `answerability` | 0.20 | Pages that both pose something (question heading, definition list, table) **and** carry at least one self-contained paragraph | Answer the question directly under the heading, in prose that stands alone |
| `question_coverage` | 0.15 | Pages with at least one question-shaped heading | Add real questions users ask, as headings |
| `passage_extraction` | 0.15 | Share of prose that survives being lifted out of context | Open paragraphs with the subject, not "This means that…" |
| `structured_answers` | 0.15 | Pages using lists, tables or definition lists | Break dense prose into extractable structures |
| `schema_support` | 0.15 | Share of indexable pages carrying any JSON-LD | Add schema; `Article`, `Service`, `FAQPage` as the content warrants |
| `faq_implementation` | 0.10 | **Of the pages that pose questions**, how many mark them up (`FAQPage`/`QAPage`/`HowTo`) | Mark up the Q&A blocks that already exist |
| `entity_clarity` | 0.10 | Pages whose schema names a recognisable entity type | Declare what the page is *about*, not just that it is a page |

`answerability` is deliberately a conjunction. A question with only
context-dependent prose under it cannot be quoted, and a liftable paragraph
nobody asked a question about will not be matched to a query. Either half
alone is not an answer, which is why the two most common "we added an FAQ and
nothing happened" cases both show up here.

## Reading "not measured"

`faq_implementation` is `null` when no page on the site poses a question in a
heading — there is no Q&A content for FAQ markup to be missing from, and a
product catalogue is not worse for lacking `FAQPage`. When it is null it is
dropped from the average and its weight redistributed; `evidence.aeo.not_measured`
says so. Report it as not measured, never as zero.

An `evidence.aeo.reason` field instead of components means one of two things,
and they are different:

- `"no pages were crawled"` — unmeasurable, score is `null`.
- `"no indexable pages…"` — measured, score is `0`. Nothing on the site can be
  read or cited, and that is a finding, not a gap.

## What matters most

**Answerability is the lever, and it is usually mis-diagnosed.** Sites that
score badly here have almost always added headings without changing the prose
underneath. Check `passage_extraction` alongside it — when answerability is
low and question coverage is high, the paragraphs are the problem.

**`faq_implementation` at 0% with high `question_coverage`** is the cheapest
real win in the whole score: the content exists, the markup does not.

**Schema coverage below 100% on a site that has schema at all** usually means
one template is missing it rather than a site-wide gap. Check `schema_types`
per page in the `/pages` response to find which.

## Per-page evidence

`/audits/<id>/pages` carries the raw inputs, so you can name the pages rather
than quoting percentages:

`question_heading_count`, `list_count`, `table_count`, `has_definition_list`,
`paragraph_count`, `self_contained_paragraph_count`, `has_author_byline`,
`heading_order_valid`, `has_schema`, `schema_types`.

## Honesty constraints

AEO measures **readiness to be cited**, never citation itself. Spy cannot
observe whether an answer engine actually quoted a site, and nothing in this
score should be phrased as a promise of placement or visibility in AI answers.
"Better positioned to be cited" is accurate; "will appear in ChatGPT" is not.

If schema coverage reads 0%, verify it before reporting — fetch a page and grep
for `application/ld+json`. Schema detection in this scanner has been wrong
before, and a false zero here drags the whole score down.

Heading hygiene moved: it is part of GEO's `ai_readable_structure` now, not an
AEO component. See [geo-signals](../geo-signals/SKILL.md).
