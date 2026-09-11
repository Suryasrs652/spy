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
  `ENVIRONMENT=production` and `AUTH_SECRET`/`INTERNAL_SERVICE_TOKEN`/
  `TOKEN_ENCRYPTION_KEY` still hold their shipped placeholder values
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
   - `AUTH_SECRET` / `NEXTAUTH_SECRET`: 32+ random bytes (`openssl rand -base64 32`). These are conceptually the same secret (Auth.js's JWT and FastAPI's JWT) but are separate config keys — set both.
   - `INTERNAL_SERVICE_TOKEN`: 32+ random bytes, shared only between the web and api services.
   - `TOKEN_ENCRYPTION_KEY`: a Fernet key — `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
   - `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET`/`RAZORPAY_WEBHOOK_SECRET`, `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`: from those providers' real (not test-mode, for production) consoles.
   - Store these in whatever secrets manager the host provides — never in a committed file. `ENVIRONMENT=production` will refuse to boot if the three checked ones are still placeholders (see above), but that check can't see the payment/OAuth secrets, so review `.env.example` line by line.
2. **Point at real infrastructure**: managed Postgres, managed Redis, and an S3-compatible bucket (or real MinIO) reachable from wherever the api/worker/beat processes run. Set `DATABASE_URL`/`DATABASE_URL_SYNC`/`REDIS_URL`/`CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND`/`STORAGE_*` accordingly.
3. **Size the DB connection pool** (`DB_POOL_SIZE`/`DB_MAX_OVERFLOW`, `app/core/config.py`) against the managed Postgres's actual `max_connections` and how many processes (api replicas × worker replicas × beat) will share it — see `services/api/loadtest/README.md` finding #2 for why this matters and what the default assumes.
4. **Set `TRUST_PROXY_HEADERS=true`** only if a real reverse proxy/load balancer sits in front and is configured to strip any client-supplied `X-Forwarded-For` before setting its own — otherwise leave it `false` (the default); see `app/core/ratelimit.py`.
5. **DNS + TLS**: `WEB_BASE_URL`/`NEXTAUTH_URL`/`API_BASE_URL`/`GOOGLE_GSC_REDIRECT_UI` all need to point at real hostnames with valid certificates (Google OAuth and Razorpay webhooks both require HTTPS in production).
6. **Update the OAuth/webhook consoles**: Google Cloud Console's authorized redirect URIs and Razorpay's webhook URL both need the real production hostnames — done outside this repo, in each provider's dashboard.

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
- Sign up a real (or disposable) account through the actual web UI, verify the free-audit entitlement is granted, run one audit against a real small site end to end.
- Check `GET /api/v1/admin/queue` (as a super admin — set `is_super_admin` on one user's row directly in the DB after the first deploy; there is no signup-time way to grant it, deliberately) for `stuck_jobs` — should be empty on a clean start.
- Tail api/worker logs for the first few minutes for anything unexpected.

## Rolling back

- **App code**: redeploy the previous image tag for api/web/worker/beat. Since migrations are additive (never destructive within a milestone) and alembic tracks the applied revision in the DB, an old image talking to a DB that's ahead of it works for anything that doesn't touch the new columns/tables — but confirm this holds for the specific migration before relying on it; if in doubt, `alembic downgrade -1` first (matching the M1 verification step: migrations are only truly reversible if you've tested the specific downgrade).
- **Data**: restore from the most recent `scripts/backup.sh` snapshot per `scripts/README.md` if a rollback needs to also undo data changes, not just code.

## Where this runs

**Backend: a single VPS**, via `docker-compose.prod.yml` — postgres, redis,
minio, api, worker, beat and a Caddy reverse proxy, all on one box. Caddy is
the only service with published ports (80/443) and gets Let's Encrypt certs
automatically per hostname. **Frontend: Vercel** (`apps/web`), reaching the
box over the public API hostname; to run it on the VPS instead, add
`--profile fullstack` and set `WEB_HOSTNAME`.

### First-time VPS setup

1. **Provision** a server (2 vCPU / 4 GB RAM is a sane floor — Playwright's
   Chromium and a 4-worker Celery pool are the memory drivers) and install
   Docker Engine + the compose plugin.
2. **DNS**: point `API_HOSTNAME` and `STORAGE_HOSTNAME` (plus `WEB_HOSTNAME`
   if running fullstack) at the box's public IP. Caddy can't issue certs
   until these resolve.
3. **Firewall**: allow 80/443 (and your SSH port) only. Nothing else needs
   to be reachable — postgres/redis/minio publish no host ports.
4. **Secrets**: `cp .env.production.example .env.production` on the server
   and fill it in; the generation one-liners are in that file's header.
5. **Boot**: `docker compose -f docker-compose.prod.yml up -d --build`.
   The api container runs `alembic upgrade head` on start (idempotent).
6. **Verify** per the section above, then set `is_super_admin` on your own
   user row to reach `/admin`.

### Updating

```
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

Compose recreates only what changed. Roll back by checking out the previous
commit and re-running the same command (see "Rolling back" above for the
migration caveat).

### What this deliberately trades away

One box means no redundancy: a host failure is downtime, and postgres lives
on a local volume, so `scripts/backup.sh` (and a *tested* restore) is the
only thing standing between a disk loss and total data loss — run it on a
schedule and keep copies off the box. Moving to managed Postgres/Redis and
a real object store later only changes `.env.production`; the app code
doesn't care.
