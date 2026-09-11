---
name: spy-audit
description: >
  Operate the Spy site auditor in this repo: boot the stack, create a project, run a crawl, and pull
  scores, issues, page inventory and recommendations back out. Use for any request to audit, crawl,
  score or analyse a website with Spy, to check an SEO/AEO/GEO score, or to investigate why an audit
  failed or reported something surprising. Also covers validating findings before reporting them,
  which this tool needs more than most.
---

# Operating Spy

Spy crawls a site and scores it deterministically for SEO, AEO and GEO. There
is no authentication — every request resolves to one local workspace — so the
API can be driven with plain `curl`.

## Prerequisites

The stack must be running:

```bash
docker compose up -d
docker compose ps --format "table {{.Name}}\t{{.Status}}"
```

Wait for `spy-api-1` to report `healthy`. On a cold start the images build and
a Chromium runtime is pulled, which takes a few minutes; after that a 70-page
crawl finishes in about 20 seconds.

If Docker itself isn't running, start Docker Desktop and wait for the daemon —
`docker info` succeeding is the signal.

## Running an audit

Everything goes through the same-origin proxy on port 3000. `BASE` below is
`http://localhost:3000/api/proxy` (substitute your own host if you changed it).

**1. Create the project.** One project per site; creating a duplicate origin
returns a conflict, so reuse the existing id when there is one.

```bash
curl -s -X POST "$BASE/projects" -H "Content-Type: application/json" \
  -d '{"name":"Example","url":"https://example.com"}'
curl -s "$BASE/projects"                       # list existing
```

The URL passes through an SSRF guard. Private, loopback, link-local and
cloud-metadata addresses are rejected with `BLOCKED_TARGET` — that is correct
behaviour, not a bug to work around.

**2. Start the audit** and keep the returned id:

```bash
curl -s -X POST "$BASE/audits" -H "Content-Type: application/json" \
  -d '{"project_id":"<project-id>"}'
```

**3. Poll until terminal.** Crawling is asynchronous:

```bash
curl -s "$BASE/audits/<audit-id>/progress"
```

Status walks `QUEUED → CRAWLING → ANALYZING → SCORING → GENERATING_REPORT →
COMPLETED`, or lands on `FAILED`/`CANCELLED`. Poll every 10-15s rather than
tightly; a real crawl takes tens of seconds. On `FAILED`, `error_code` carries
the reason (`WORKER_ERROR`, `DNS_FAILURE`, `ROBOTS_BLOCKED`, `BLOCKED_TARGET`…).

**4. Pull the results:**

| Endpoint | Contents |
| --- | --- |
| `GET $BASE/audits/<id>` | Scores plus the `evidence` blob they were derived from |
| `GET $BASE/audits/<id>/issues` | Findings: severity, rule_id, affected_count, description, recommendation |
| `GET $BASE/audits/<id>/pages` | Per-page inventory — status, indexability, depth, word count, schema types, response time, internal PageRank |
| `GET $BASE/audits/<id>/recommendations` | The same findings ranked by `impact × confidence ÷ effort`, grouped Do Now / This Week / This Month / Monitor |
| `GET $BASE/audits/<id>/report/download` | `{url, expires_in_seconds}` — a short-lived signed PDF link |

## Reading the scores

`spy_score` is a weighted composite; the sub-scores are `technical`, `seo`,
`content`, `performance`, `authority`, `aeo`, `geo`. Every one is derived from
the stored `evidence`, so any number can be traced back rather than taken on
faith. `confidence` reflects crawl coverage.

`authority_score` is commonly `null`. That means *not measured*, not zero —
Spy's backlink index only contains links seen during its own crawls, so it is
empty on a fresh install. Report it as "no data", never as a bad score.

The same applies inside `evidence`: `aeo` and `geo` may carry a `reason` field
instead of numbers when there was nothing scoreable. Pass that reason through.

## Validate before reporting

This matters more here than the score does. Findings come from 101 rules run
over crawl evidence, and a rule can be wrong about a specific site. Before
telling anyone their site has a problem, check the claim against the live site —
it costs one `curl` and it is the difference between a useful report and a
confident wrong one:

```bash
curl -sI https://example.com/              # headers: HSTS, CSP, X-Frame-Options
curl -s  https://example.com/robots.txt
curl -s  https://example.com/sitemap.xml | head -20
curl -s  https://example.com/ | grep -oE '<title>[^<]*</title>|application/ld\+json'
```

Findings worth checking specifically, because they have been wrong before:

- **Anything about structured data.** Confirm with a real fetch that the JSON-LD
  is genuinely absent before reporting it missing.
- **Broken external links.** A `301`, `403` or `429` usually means the target
  bot-gates automated clients (LinkedIn, Cloudflare), not that the link is dead.
  Only `404`/`410` prove absence.
- **Sitemap and hreflang findings.** Fetch the sitemap and read the `hreflang`
  tags yourself.
- **Title/description length** on non-Latin scripts.

When a finding does not survive that check, say so and exclude it from the
recommendations rather than quietly dropping it — a false positive is itself
worth reporting, because it points at a rule that needs fixing.

## Interpreting for a human

Rank by leverage, not severity. A `LOW` finding on 89 pages that is one line of
config usually beats a `HIGH` on two pages that needs a content rewrite; the
`recommendations` endpoint already does this ordering.

Separate *is broken* from *is missing*: a site with no backlinks and no author
bylines has a growth problem, not a defect list. Say which constraint actually
binds instead of listing everything the scanner noticed.

## When something goes wrong

- **Audit `FAILED` with `WORKER_ERROR`** — check `docker compose logs worker --tail 50`.
  After changing model or crawler code, restart the worker; it holds the old
  code otherwise (`docker compose restart worker api`).
- **`Project not found`** — the project was removed, or you are pointed at a
  different workspace. List projects and re-create.
- **Connection refused** — the stack is down. `docker compose up -d`.
