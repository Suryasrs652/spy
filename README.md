# Spy

A self-hosted site auditor that crawls a site you own and scores it for search
engines, answer engines and generative engines — SEO, AEO and GEO in one pass.

You run it on your own machine. There is no sign-up, no account, no billing and
no usage limit, and nothing about your sites leaves your hardware.

```bash
git clone https://github.com/Suryasrs652/spy.git
cd spy
cp .env.example .env
docker compose up -d --build
```

Then open **http://localhost:3000**, add a project, and hit *Run Audit*.

First boot builds the images and pulls a Chromium runtime for PDF rendering, so
give it a few minutes. After that a 70-page crawl finishes in about 20 seconds.

---

## What it actually does

**Crawls the site for real.** An async crawler walks the site from the homepage
and from its sitemaps, honouring `robots.txt` and `crawl-delay`, with per-host
concurrency limits and a polite user agent. It expands sitemap indexes, skips
media and binary assets rather than downloading them, and every request — the
crawl, sitemap fetches, external link checks — goes through one SSRF-guarded
HTTP client that re-validates every redirect hop against private, loopback,
link-local and cloud-metadata ranges.

**Applies 101 deterministic rules** across metadata, indexability, headings,
content quality, images, links, structured data, internationalisation,
crawlability, performance and security headers. Every finding carries a
severity, the pages it affects, why it matters and how to fix it. No model is
asked to guess; identical input produces identical output.

**Produces three scores, not one.** They answer different questions, so
folding them into a single number hides which one you have a problem with:

| | Asks |
| --- | --- |
| **SEO** | Can a search engine crawl, index and rank this? |
| **AEO** | Can an answer engine lift an answer out of it? |
| **GEO** | Can a generative system tell who wrote it and reuse it? |

The **Overall Digital Search Score** combines them at 60/20/20. SEO is itself
seven components out of 100 — technical 25, on-page 20, content 20, internal
links 10, structured data 10, performance 10, authority 5. AEO has seven
sub-scores and GEO has ten, and each one is reported with the weight it
actually carried.

Every score is versioned (`spy-score-v2.0`) and reproducible: identical crawl
evidence always yields an identical number, the evidence is stored alongside
it, and a completed audit's score is never recomputed. Two audits scored under
different versions are refused rather than silently diffed — the same column
can mean different things across versions.

**Scores AI citation readiness (ACRS)** — whether a generative system could
quote a page as an answer and attribute it: checkable figures, a visible date,
named sources, a byline, and prose that survives being lifted out of context.
Its signals are measured once and shared with AEO and GEO, so the same thing
cannot be reported as two different numbers in two sections of one report.

**Says what it did not measure.** A component with no evidence has its weight
redistributed and is reported as *not measured*, never as zero — because "we
didn't look" and "you failed" are different claims. Authority reads as
unmeasured until Spy's own crawl index finds a referring domain; GEO's
*original information gain* is always unmeasured, because establishing that
information appears nowhere else needs a corpus to compare against. It carries
a weight anyway, so the omission is on the record rather than looking like an
oversight. The one thing that is *not* treated as unmeasurable: a site where
nothing is indexable scores zero, because that is a measurement.

**Ranks the fixes.** Findings become recommendations scored by
`impact × confidence × reach ÷ effort` and grouped into Do Now / This Week /
This Month / Monitor, so the list is ordered by leverage rather than by
severity. Confidence is declared per rule: a check that reads a tag off the
page is certain, a threshold heuristic is not, and the ranking says so.

**Renders a PDF report** through headless Chromium into S3-compatible storage,
served back as a short-lived signed URL.

### Per-project views

| View | What it shows |
| --- | --- |
| Site Explorer | Every crawled URL: status, indexability, depth, response time, internal PageRank |
| Content Explorer | Per-page content signals — word count, heading structure, schema types, alt-text gaps |
| AEO / GEO | The evidence behind each score, with an honest "no data" when there isn't any |
| Backlinks | Links into the site discovered across Spy's own crawl history |
| Competitors | A lighter crawl of a rival site, scored on the same scale |
| Reports | PDF downloads for every completed audit |

### Optional: Google Search Console

Leave `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` blank and everything above
works. Fill them in and connect a property to unlock three more views —
Search Console (clicks, impressions, CTR, position, plus striking-distance,
low-CTR, cannibalisation and rank-movement analysis), Keywords (the queries the
site actually ranks for), and Rank Tracker (position history for keywords you
choose). Rank tracking reads real Search Console data rather than scraping
results pages, so it reports "no data" instead of inventing a position.

---

## How it's put together

A modular monolith, not microservices. One Python image runs as three
processes; the frontend is separate.

```
apps/web            Next.js 16 (App Router, TypeScript, Tailwind)
services/api        FastAPI + SQLAlchemy 2.0 async, Python 3.12
  app/modules/      audits, crawler, seo, scoring, recommendations,
                    reports, gsc, backlinks, keywords, competitors,
                    projects, notifications, admin
  app/workers/      Celery tasks (crawl, sync, retention)
  alembic/          migrations, including the seeded rule thresholds
infra/docker/       Dockerfiles
```

`docker compose up` starts Postgres 16, Redis 7, MinIO, MailHog, the API
(`:8000`), a Celery worker, a beat scheduler, and the web app (`:3000`).

The browser never calls the API directly — requests go through a same-origin
Next.js proxy route, so the API container needs no public exposure.

**There is no authentication.** Spy resolves every request to a single local
workspace that provisions itself on first use
(`services/api/app/core/local_workspace.py`). The multi-tenant schema is still
underneath — every table carries an `organization_id` and every endpoint
resolves through a tenancy dependency — so adding real multi-user auth means
changing that one module rather than rewriting every query. Because there is no
auth, **don't expose this to the internet as-is.**

---

## Driving it with Claude Code

The repo ships agents and skills in `.claude/`, so an audit can be run and
interpreted conversationally rather than by hand.

Analysis runs as a pipeline. Twelve specialists each look at one dimension,
a validator checks every finding against the live site, a resolver settles
disagreements between them, and only then is anything scored, sequenced and
written up.

```
                        ┌── technical-seo-analyst ──┐
                        ├── onpage-analyst ─────────┤
                        ├── content-analyst ────────┤
                        ├── schema-analyst ─────────┤
                        ├── entity-analyst ─────────┤
  URL ──► Crawl Engine ─┼── aeo-analyst ────────────┤
                        ├── geo-analyst ────────────┤
                        ├── citation-analyst ───────┤
                        ├── internal-link-analyst ──┤
                        ├── performance-analyst ────┤
                        ├── competitor-analyst ─────┤
                        └── gsc-analyst ────────────┘
                                      │
                                      ▼
                            evidence-validator
                                      │
                                      ▼
                           contradiction-resolver
                                      │
                                      ▼
                      Scoring Engine  (deterministic, in-repo)
                                      │
                                      ▼
                              strategy-agent
                                      │
                                      ▼
                               report-agent
```

The twelve analysts are independent and should be run in parallel. Everything
after them is strictly sequential, and the order is the point: nothing reaches
a human that hasn't been verified against the live site, and nothing is
sequenced before the analysts' disagreements are settled.

**The Scoring Engine is deliberately not an agent.** Scores come from
`services/api/app/modules/scoring/spy_score.py` — versioned, deterministic,
derived from stored crawl evidence. The same crawl always produces the same
score, which is what makes two audits of a site comparable and lets any number
be traced back to the evidence behind it. An agent scoring by judgement would
give a different answer each run and quietly break re-auditing.

| Agent | Does |
| --- | --- |
| `technical-seo-analyst` | Indexability, canonicals, robots, security headers, redirects, hreflang; also diagnoses failed crawls |
| `onpage-analyst` | Titles, descriptions, H1s, Open Graph, duplication |
| `content-analyst` | Thin and duplicate content, heading outline, depth, stuffing |
| `schema-analyst` | Which JSON-LD types are deployed, where, and what's missing |
| `entity-analyst` | Who the site says it is — identity, consistency, `sameAs`, authorship |
| `aeo-analyst` | Extractability for answer engines: questions, structure, bylines |
| `citation-analyst` | AI Citation Readiness (ACRS) — is the content quotable and attributable |
| `geo-analyst` | Entity definition for generative engines |
| `internal-link-analyst` | PageRank distribution, unlinked pages, dead ends |
| `performance-analyst` | Server response, weight, layout-shift risk — and what isn't measured |
| `competitor-analyst` | Score comparison and content gap against named rivals |
| `gsc-analyst` | Real Search Console performance and the opportunity engine |
| `evidence-validator` | Verifies every finding against the live site; sorts confirmed / refuted / unverified |
| `contradiction-resolver` | Settles disagreements between analysts; flags metrics that contradict their own data |
| `strategy-agent` | Names the binding constraint and sequences the work by leverage |
| `report-agent` | Writes the final report and publishes it |
| `rule-author` | Adds or fixes checks in the rule engine (development, not analysis) |

Skills carry the domain knowledge each agent loads — `spy-audit` for operating
the tool, one reference per dimension, plus `finding-validation`,
`contradiction-resolution` and `audit-reporting`. They are usable directly too:
ask about `schema-signals` without spawning an agent.

Two rules run through all of them: **verify before claiming**, and **"not
measured" is never "zero"**.

## Development

```bash
docker compose exec api pytest -q            # 162 tests
docker compose exec api ruff check .         # lint
docker compose exec api alembic upgrade head # migrations
docker compose exec web npm run lint
docker compose exec web npx tsc --noEmit
```

Tests provision and migrate their own `spy_test` database and drop it at the
start of each run, so they never touch your development data. They refuse to
run if pointed at the application's own database.

The suite uses a real Postgres, Redis and MinIO rather than mocks — the bugs
worth catching here (crawl behaviour, the SSRF guard, migration correctness)
are exactly the ones a mocked datastore hides.

### Configuration

`.env.example` is the full list and ships with working local defaults; only the
two Google credentials are blank, and they're optional. Worth knowing:

| Variable | Default | Notes |
| --- | --- | --- |
| `CRAWLER_MAX_CONCURRENCY_PER_HOST` | `4` | Politeness limit per host |
| `CRAWLER_GLOBAL_CONCURRENCY` | `20` | Total in-flight requests |
| `JS_RENDER_ENABLED` | `false` | Render JS-dependent pages via Chromium — slower |
| `TOKEN_ENCRYPTION_KEY` | placeholder | Encrypts stored Google refresh tokens |
| `TRUST_PROXY_HEADERS` | `false` | Only enable behind a proxy that sets `X-Forwarded-For` itself |

---

## What this deliberately isn't

Spy reports what it measured and says so when it measured nothing — an empty
result is shown as an empty result, never filled in with an estimate.

That means it has real limits. It has no web-scale backlink index: the
Backlinks view only knows about links it has seen while crawling, so on a fresh
install it is empty and the Authority score reads *no data* rather than
guessing. It has no keyword volume or difficulty estimates. It cannot promise
rankings or AI citations — AEO and GEO measure readiness to be cited, not the
citation itself.

## Licence

None yet — all rights reserved until one is added. If you want to use this for
something, open an issue.
