---
name: geo-signals
description: >
  Interpret Spy's GEO (Generative Engine Optimization) score and its ten dimensions — entity
  recognition, citation readiness, fact density, brand consistency, source attribution, knowledge
  graph signals, topical authority, author transparency, AI-readable structure and original
  information gain. Use when analysing geo_score, explaining how clearly a site defines who it is
  for AI systems, or deciding what to add to become a citable entity.
---

# Reading Spy's GEO output

GEO measures whether a generative engine can work out **who this site is** and
reuse what it says. Where AEO is about extracting an answer, GEO is about
identifying and trusting the entity behind it.

Read `evidence.geo.components` on the audit object, and
`evidence.geo.weights_used` to see which dimensions were actually in the
average.

## The ten dimensions

| Component | Weight | Means |
| --- | --- | --- |
| `entity_recognition` | 0.15 | Half for declaring an Organization anywhere, half for how much of the site carries any identifiable entity |
| `citation_readiness` | 0.12 | Share of prose that survives being lifted out of context and quoted whole |
| `fact_density` | 0.12 | Pages stating at least two checkable figures |
| `brand_consistency` | 0.10 | Share of named Organization blocks using the **most common** name |
| `source_attribution` | 0.10 | Pages linking out to a source that isn't sitewide chrome |
| `knowledge_graph_signals` | 0.10 | Share of `@id`, `sameAs`, `url`, `logo` present on the declared entities |
| `topical_authority` | 0.10 | On-site depth × breadth — substantial pages, and enough of them |
| `author_transparency` | 0.08 | Pages with a detectable author byline |
| `ai_readable_structure` | 0.08 | Mean of schema coverage, heading hygiene and structured content |
| `original_information_gain` | 0.05 | **Always null.** See below |

`citation_readiness`, `fact_density`, `source_attribution` and
`author_transparency` are the same measurements the ACRS engine makes, taken
once and shared — so GEO's "fact density" and the ACRS section cannot print
different numbers under the same name. If they ever disagree, that is a bug.

## What is deliberately not measured

`original_information_gain` carries a weight so that its omission is on the
record rather than looking like an oversight, and is **always** dropped from
the average. Establishing that information appears nowhere else requires a
corpus to compare against; no amount of markup analysis gets there. Report it
as not measured. Never estimate it.

`brand_consistency` and `knowledge_graph_signals` are null when no
Organization schema declares a name or exists at all. Null is "not measured",
not zero — `evidence.geo.not_measured` lists which and why.

`topical_authority` measures **only the on-site half**: does this site cover
its subject in depth, across enough pages to constitute coverage. Whether the
wider web treats the site as an authority needs a backlink corpus Spy does not
have, and `evidence.geo.topical_authority_caveat` says so. Quote the caveat
when reporting the number.

An `evidence.geo.reason` field instead of components means one of two things:
`"no pages were crawled"` (unmeasurable, score `null`) or `"no indexable
pages…"` (measured, score `0`).

## Organization is a family, not a literal type

`ORGANIZATION_TYPES` in `app/core/schema_org.py` holds the subtypes that count:
`Organization`, `LocalBusiness`, `ProfessionalService`, `Corporation`, `NGO`,
`EducationalOrganization`, `NewsMediaOrganization` and others Google documents
as valid organization markup.

This matters when reading a site's own markup: a studio declaring
`ProfessionalService` or a shop declaring `LocalBusiness` **has** an
organization entity, and a more specific one is better than a bare
`Organization`, not worse. If a finding claims no organization schema while the
page clearly declares a subtype, the finding is wrong.

## Brand consistency is a share, not a verdict

One stray name variant on a forty-page site is a 97%-consistent brand. A site
genuinely split between two names lands near 50%. The check used to return 0
for any disagreement at all, which made a typo look identical to a real
identity problem — read the number, not just whether it is 100.

## What good looks like

The strongest entity signal is one `@graph` on the homepage carrying the
organization with `@id`, `name`, `url`, `logo`, a postal address, `areaServed`,
and `sameAs` pointing at profiles the business actually controls. `sameAs` is
what lets an engine connect the site to independent corroboration, which is the
whole game — an entity nobody else references is hard to cite confidently.

Then: the same name everywhere, real bylines, and prose that states checkable
things rather than ambitions.

## What to recommend when it is weak

1. **No organization entity at all** — add it to the homepage first. Everything
   else in GEO depends on there being an entity to describe.
2. **Low `knowledge_graph_signals`** — `@id` and `sameAs` are the two that carry
   real weight; `name` and `url` are usually already there.
3. **Low `fact_density` / `citation_readiness`** — this is a writing problem, not
   a markup one. Add figures, name sources, and open paragraphs with the
   subject so they stand alone.
4. **Name inconsistency** — pick one name and use it in every markup block, even
   where the visible branding varies.
5. **Low `topical_authority`** — more substantial pages on the subject, not more
   pages.

## Honesty constraints

GEO measures how *recognisable and reusable* a site is, not whether any model
recognises it. Spy has no visibility into model training data or retrieval
behaviour. Do not phrase GEO improvements as guaranteed inclusion, and do not
imply a score of 100 means AI systems know the brand — it means the markup and
the prose give them what they need to.
