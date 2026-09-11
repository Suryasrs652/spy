# Deployment runbook (§116)

This covers what's provider-agnostic: what must be true before a deploy, how
to run one, how to verify it, and how to roll back. It does not name a
specific cloud/host — that's a decision for whoever owns the account and
budget, not something to bake into the app. See "Choosing where this
actually runs" at the bottom.

## What's already built for this

- **Production Docker images**: `infra/docker/Dockerfile.api` and
  `Dockerfile.web` are both multi-stage with a `production` target — a
  non-root user, no dev-only flags (`uvicorn --reload`, `next dev`'s hot
  reload), and (web) Next's `output: "standalone"` minimal server bundle.
  Build with `--target production`; `docker-compose.yml` explicitly
  targets `dev` so local development is unaffected.
- **A production secrets guard**: `Settings` refuses to start when
  `ENVIRONMENT=production` and `AUTH_SECRET`/`TOKEN_ENCRYPTION_KEY` still hold their shipped placeholder values
  (`app/core/config.py`). A misconfigured deploy fails at boot, not
  silently in production.
- **CI** (`.github/workflows/ci.yml`): tests, migrations, lint, type-check,
  and a production frontend build run against real Postgres/Redis/MinIO on
  every push. Has not been run against a real GitHub Actions runner in this
  environment (no git remote is configured here) — validated by hand
  (YAML parses; every command it runs has been exercised locally in this
  session against the same dependency versions) but not proven end-to-end.
- **Backup/restore** (`scripts/`): see `scripts/README.md`. Tested — see
  its "Verified" section.
- **Health checks**: `GET /health/live` (process is up) and
  `GET /health/ready` (Postgres + Redis reachable) already exist
  (`app/main.py`) — point a load balancer's health check at `/health/ready`.

## Before the first deploy to a given environment

1. **Generate real secrets** — never reuse the values in `.env.example`:
   - `AUTH_SECRET`: 32+ random bytes (`openssl rand -base64 32`). Signs the Google Search Console OAuth `state` parameter — the only JWT left now that there is no sign-in.
   - `TOKEN_ENCRYPTION_KEY`: a Fernet key — `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Encrypts stored Google refresh tokens.
   - `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`: from Google Cloud Console, and only if you want Search Console connected at all.
   - Store these in whatever secrets manager the host provides — never in a committed file. `ENVIRONMENT=production` refuses to boot while the checked ones are still placeholders (see above).
2. **Point at real infrastructure**: managed Postgres, managed Redis, and an S3-compatible bucket (or real MinIO) reachable from wherever the api/worker/beat processes run. Set `DATABASE_URL`/`DATABASE_URL_SYNC`/`REDIS_URL`/`CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND`/`STORAGE_*` accordingly.
3. **Size the DB connection pool** (`DB_POOL_SIZE`/`DB_MAX_OVERFLOW`, `app/core/config.py`) against the managed Postgres's actual `max_connections` and how many processes (api replicas × worker replicas × beat) will share it — see `services/api/loadtest/README.md` finding #2 for why this matters and what the default assumes.
4. **Set `TRUST_PROXY_HEADERS=true`** only if a real reverse proxy/load balancer sits in front and is configured to strip any client-supplied `X-Forwarded-For` before setting its own — otherwise leave it `false` (the default); see `app/core/ratelimit.py`.
5. **DNS + TLS**: `WEB_BASE_URL`/`API_BASE_URL`/`GOOGLE_GSC_REDIRECT_URI` all need to point at real hostnames with valid certificates (Google OAuth requires HTTPS).
6. **Update the OAuth console**: Google Cloud Console's authorized redirect URIs need the real production hostname — done outside this repo, in Google's dashboard.
7. **Put authentication in front of it.** Spy has none: every request resolves to one local workspace (`app/core/local_workspace.py`). Anything deployed where others can reach it needs a proxy-level gate — SSO, basic auth, an IP allowlist, a private network — or anyone who finds the hostname can crawl arbitrary sites from your infrastructure.

## Deploying

```
1. Build: docker build --target production -f infra/docker/Dockerfile.api services/api -t <registry>/spy-api:<tag>
          docker build --target production -f infra/docker/Dockerfile.web apps/web -t <registry>/spy-web:<tag>
2. Push both images to the registry the host pulls from.
3. Run migrations ONCE, before traffic shifts to the new version:
   docker run --rm -e DATABASE_URL_SYNC=... <registry>/spy-api:<tag> alembic upgrade head
   (docker-entrypoint.sh's `api` mode also runs this on every boot, which is
   safe/idempotent — alembic no-ops if already at head — but running it as
   an explicit one-off step first means a slow migration doesn't delay
   every replica's startup probe simultaneously.)
4. Start/update api, worker, and beat with RUN_MODE set per process — exactly
   one `beat` process must ever run at a time (a second one would double-fire
   every scheduled task).
5. Start/update web pointed at the new api.
6. Verify (see below) before considering the deploy complete.
```

## Verifying a deploy

- `curl https://<api-host>/health/ready` → `{"status": "ok", ...}` with every check `"ok"`.
- Add a project through the actual web UI and run one audit against a real small site end to end.
- Check `GET /api/v1/admin/queue` for `stuck_jobs` — should be empty on a clean start.
- Tail api/worker logs for the first few minutes for anything unexpected.

## Rolling back

- **App code**: redeploy the previous image tag for api/web/worker/beat. Since migrations are additive (never destructive within a milestone) and alembic tracks the applied revision in the DB, an old image talking to a DB that's ahead of it works for anything that doesn't touch the new columns/tables — but confirm this holds for the specific migration before relying on it; if in doubt, `alembic downgrade -1` first (matching the M1 verification step: migrations are only truly reversible if you've tested the specific downgrade).
- **Data**: restore from the most recent `scripts/backup.sh` snapshot per `scripts/README.md` if a rollback needs to also undo data changes, not just code.

## Choosing where this actually runs

Not decided in this repo: which cloud/PaaS, what the actual domain is, and
who holds the account credentials. Reasonable options for this stack
(FastAPI + Celery + Postgres + Redis + S3-compatible storage + Next.js) span
from a single VPS running the existing `docker-compose.yml` (swap `target:
dev` for `target: production` and point at managed Postgres/Redis/S3) to a
managed container platform (Railway, Render, Fly.io) to a full cloud
provider (AWS/GCP/Azure) with managed Postgres (RDS/Cloud SQL) and a
managed Redis. That choice determines the actual CI deploy step, DNS setup,
and secrets storage mechanism — none of which can be built here without
first knowing it.
