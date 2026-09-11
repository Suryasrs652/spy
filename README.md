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

**Produces a Spy Score** from the stored evidence — a versioned
(`spy-score-v1.0`), reproducible number with per-component sub-scores, the
weights actually used, and a confidence value derived from crawl coverage. The
evidence is kept so any score can be re-derived and argued with.

**Scores AEO and GEO**, not just SEO:

- *AEO* — how extractable the content is for answer engines: schema coverage,
  heading hygiene, question coverage, structured content, authorship.
- *GEO* — how clearly the site defines its entity for generative engines:
  organization markup and its field completeness, name consistency across
  pages, citation readiness.

**Ranks the fixes.** Findings become recommendations scored by
`impact × confidence ÷ effort` and grouped into Do Now / This Week / This Month
/ Monitor, so the list is ordered by leverage rather than by severity.

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
