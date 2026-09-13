---
name: schema-signals
description: >
  Read and assess a site's structured data through Spy — which JSON-LD types are deployed, how
  @graph nests them, what each type earns in search results, and what's missing. Use when analysing
  schema coverage, deciding what markup to add, or checking a structured-data finding.
---

# Reading structured data

Spy stores every JSON-LD block it parses. `/audits/<id>/pages` carries
`has_schema` and `schema_types` per page; the audit's `evidence` carries the
coverage percentages.

## How the markup is usually shaped

Most real sites emit one `<script type="application/ld+json">` per page
containing a `@graph` array of several entities, not one entity per tag. The
wrapper itself has no `@type` — the entities are inside it. Any tooling that
reads only the top level sees nothing, which is a mistake this scanner made for
its entire history before it was fixed.

When checking a page by hand:

```bash
curl -s <url> | grep -o 'application/ld+json' | wc -l     # blocks present
curl -s <url> | python3 -c "import sys,re,json
h=sys.stdin.read()
for b in re.findall(r'<script[^>]*ld\+json[^>]*>(.*?)</script>', h, re.S):
    d=json.loads(b)
    items=d.get('@graph', d if isinstance(d,list) else [d])
    print([i.get('@type') for i in items if isinstance(i,dict)])"
```

## What each type earns

| Type | Earns |
| --- | --- |
| `Organization` / `LocalBusiness` / `ProfessionalService` | The entity itself — knowledge panel, entity recognition |
| `WebSite` | Sitelinks search box |
| `BreadcrumbList` | Breadcrumb trail in results |
| `FAQPage` | Direct extraction by answer engines; FAQ rich results |
| `HowTo` | Step-based rich results |
| `VideoObject` | Video rich results and video search surfaces |
| `Article` / `BlogPosting` | Article surfaces — needs a real `author` to be worth much |
| `Product` / `Offer` | Price, availability, review stars |
| `Service` | Service-level definition; supports the entity |
| `WebPage` / `ContactPage` | Page typing; modest on its own |

## Reading coverage honestly

`schema_coverage_pct` is the share of **indexable** pages with any JSON-LD.
100% means every page has *something*, not that every page has the *right*
thing — a site can hit 100% on `BreadcrumbList` alone. Always look at
`schema_types` distribution, not just the percentage.

Conversely, a type appearing on few pages is not automatically a gap:
`WebSite` and the organization entity belong on the homepage, not everywhere.
Judge each type against where it *should* appear.

## Gaps worth reporting

- **`BlogPosting` with no `author`**, or an author that is the organization
  rather than a person. Common, and it undercuts the article markup entirely.
- **`VideoObject` with no video sitemap** — the markup is there but the videos
  aren't submitted, so they compete for nothing.
- **A page type with no matching schema** — services without `Service`,
  articles without `Article`, products without `Product`.
- **Invalid JSON** — `schema_errors` on the parsed page records parse failures.

Before reporting any type as absent, fetch the page and check. Schema findings
have been wrong here before.
