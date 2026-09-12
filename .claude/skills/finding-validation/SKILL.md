---
name: finding-validation
description: >
  Verify audit findings against the live site before they reach a human — the known false-positive
  classes, the one-command check for each, and how to report a finding that doesn't hold up. Use
  before presenting any audit conclusions, when reviewing another agent's findings, or when a
  finding looks surprising.
---

# Validating findings before they become claims

A scanner finding is evidence, not a verdict. Every rule here is a
generalisation over crawl data, and a generalisation can be wrong about a
specific site. Checking costs one request; being confidently wrong costs
someone a wasted afternoon and the tool its credibility.

**The rule: do not report a problem you have not confirmed exists.**

## Known false-positive classes

Every one of these was a real finding this scanner produced about a real site,
confirmed wrong by hand. Three have been fixed; the pattern behind them has
not gone away, so check anything in these families every time.

| Finding | Check | What proves it wrong |
| --- | --- | --- |
| "No structured data / no Organization / no WebSite schema" | `curl -s <url> \| grep -c 'application/ld+json'` | Any hit. Also check `@graph` — entities nest inside it, and a subtype like `ProfessionalService` **is** an Organization |
| "Broken external links" | `curl -s -o /dev/null -w '%{http_code}' <target>` | Anything but 404/410. A 301/403/429 means the target bot-gates crawlers (LinkedIn, Cloudflare) — the link works for humans |
| "No XML sitemap found" | `curl -s <origin>/robots.txt`, then fetch the declared sitemap | A `<sitemapindex>` is a sitemap. So is a non-conventional path declared in robots.txt |
| "HTML lang and hreflang disagree" | `curl -s <url> \| grep -oE '<html[^>]*lang="[^"]*"\|hreflang="[^"]*"'` | `lang="ta-IN"` against an `hreflang="ta-IN"` self-entry agrees. `x-default` is a fallback marker, not a language |
| "Title/description length" on non-Latin text | Read the actual title | Measured by display width, which approximates but is not pixels. Borderline cases on Indic/CJK are advisory |
| "Missing security headers" | `curl -sI <url>` | Rarely wrong — but confirm anyway, it is one request |

## Start with the rule's own confidence

Every finding carries a `confidence` between 0 and 1, declared by the rule
that produced it (`services/api/app/modules/seo/rules/base.py`). It says how
much of the finding is observation and how much is inference:

- **1.0** — the rule read a fact off the page. There is no canonical tag;
  the header is absent; two pages hash identically. Check these when they
  surprise you, not as a matter of course.
- **below 1.0** — the rule inferred the problem from a threshold or a
  pattern. `SEO_CONTENT_008` (0.5) cannot tell keyword stuffing from a page
  that repeats its own product name; `SEO_LINK_002` (0.8) cannot see a link
  rendered by JavaScript. **Check every one of these before reporting it.**

Sort by confidence ascending and start at the top. The list is short — 21 of
the 101 rules declare anything below certainty — and it is exactly the list
of findings most likely to waste someone's afternoon.

## Recording the verdict

A check nobody can see gets repeated by the next reader. Write it back:

```bash
curl -s -X PATCH "$SPY_API/audits/$AUDIT_ID/issues/$ISSUE_ID/validation"   -H "Content-Type: application/json"   -d '{"validated": false, "note": "Canonical is present, injected by JS after load."}'
```

`validated` is `null` until someone checks — deliberately distinct from
`false`, which is a recorded verdict that the finding did not hold up. Never
report an unchecked finding as though it had been confirmed, and never mark
one `true` on the strength of the stored evidence alone; the point of the
field is that a human or an agent went and looked.

The verdict never edits the finding. Severity, confidence and the evidence
rows stay exactly as the rules produced them, so the audit stays re-derivable
from its own crawl.

## The general method

1. **Pick the specific page** the finding names, not a representative one.
2. **Fetch the thing the rule claims to have inspected** — headers for header
   rules, HTML for markup rules, the target URL for link rules.
3. **Look for the exact condition**, not something adjacent. "No FAQ schema"
   means grep for `FAQPage`, not for schema in general.
4. **Prefer the site's own response over the stored evidence** when they
   disagree, then work out which one is stale or wrong.

## When a finding does not hold up

Say so explicitly. Do not quietly drop it — a false positive is itself a
finding, because it means a rule needs fixing, and silently removing it means
the next audit of the next site repeats it.

Report it as: what the scanner claimed, what you checked, what you found, and
therefore which rule is suspect. If the rule id is known, name it.

## The other half: absence versus zero

Validation is not only about false positives. It is equally about not inventing
a number:

- `authority_score: null` means **not measured**. Spy's backlink index only
  contains links seen during its own crawls, so it is empty on a fresh install.
  It is not a score of zero and must never be presented as a weakness.
- `evidence.aeo` / `evidence.geo` carrying a `reason` instead of numbers means
  nothing was scoreable. Pass the reason through.
- `org_field_completeness_pct: null` means no entity was found to measure.
- A GSC section with no connected property is "not connected", not "no traffic".

Filling any of these with an estimate is a worse failure than a false positive,
because it is indistinguishable from data.
