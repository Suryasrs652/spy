---
name: geo-signals
description: >
  Interpret Spy's GEO (Generative Engine Optimization) score and evidence — organization entity
  markup, field completeness, entity-name consistency and citation readiness. Use when analysing
  geo_score, explaining how clearly a site defines who it is for AI systems, or deciding what
  structured data to add to become a recognisable entity.
---

# Reading Spy's GEO output

GEO measures whether a generative engine can work out **who this site is** and
cite it consistently. Where AEO is about extracting an answer, GEO is about
identifying the entity behind it.

Read `evidence.geo` on the audit object.

## The six signals

| Field | Means |
| --- | --- |
| `has_organization_schema` | An Organization-family entity is declared somewhere |
| `org_field_completeness_pct` | Share of `name`, `url`, `logo`, `sameAs` present on those entities |
| `entity_name_consistency_pct` | 100 if every declared entity uses one name, 0 if they disagree |
| `schema_coverage_pct` | Share of indexable pages carrying any JSON-LD |
| `has_person_or_product_schema` | Person, Product or Service entities are declared |
| `citation_readiness_pct` | Share of indexable pages carrying outbound citations |

`null` on the two percentage fields means no organization entity was found, so
completeness and consistency could not be computed. That is "not measured".

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

## What good looks like

The strongest entity signal is one `@graph` on the homepage carrying the
organization with `name`, `url`, `logo`, a postal address, `areaServed`, and
`sameAs` pointing at profiles the business actually controls. `sameAs` is what
lets an engine connect the site to independent corroboration, which is the
whole game — an entity nobody else references is hard to cite confidently.

Then: the same name everywhere. A brand that calls itself three slightly
different things across its pages is an ambiguous entity, and inconsistency
costs more than a missing optional field.

## What to recommend when it is weak

1. **No organization entity at all** — add it to the homepage first. Everything
   else in GEO depends on there being an entity to describe.
2. **Low field completeness** — `logo` and `sameAs` are the two that carry real
   weight; `name` and `url` are usually already there.
3. **Name inconsistency** — pick one legal-ish name and use it in every markup
   block, even where the visible branding varies.
4. **No Person/Product/Service** — declare the services offered as `Service`
   entities, which also helps AEO.

## Honesty constraints

GEO measures how *recognisable* an entity is, not whether any model recognises
it. Spy has no visibility into model training data or retrieval behaviour. Do
not phrase GEO improvements as guaranteed inclusion, and do not imply a score
of 100 means AI systems know the brand — it means the markup gives them what
they need to.
