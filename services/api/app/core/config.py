"""Central application configuration.

All configurable values (§115) are read from environment variables via
pydantic-settings. Nothing here is a secret's default that would be safe to
ship — the values in .env.example are local-dev placeholders only, and
§104's production check below refuses to start if any of them are still in
effect when ENVIRONMENT=production.
"""
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Settings fields whose default value is a known, publicly-documented
# placeholder — safe for local dev, catastrophic if it ever reached a real
# deployment (an attacker who has read this file, which is a fair
# assumption for open-source-adjacent code, can forge sessions/tokens or
# call internal endpoints outright). Checked at startup, not just noted in
# a comment, per §104.
_INSECURE_DEFAULTS = {
    "auth_secret": "insecure-dev-secret-change-me",
    "internal_service_token": "insecure-dev-internal-token",
    "token_encryption_key": "0" * 43 + "=",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    api_base_url: str = "http://localhost:8000"
    web_base_url: str = "http://localhost:3000"
    # Which of the three processes docker-entrypoint.sh can start this is
    # ("api", "worker", or "beat") — read here (not just by the shell
    # script) because app/db/session.py needs it to pick a pooling
    # strategy; see USE_NULL_POOL below for why.
    run_mode: str = "api"

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://spy:spy@localhost:5432/spy"
    )
    database_url_sync: str = Field(
        default="postgresql+psycopg://spy:spy@localhost:5432/spy"
    )
    # asyncpg connections are bound to the event loop that opened them.
    # Reusing a pooled one from a *different, already-closed* loop raises
    # "attached to a different loop" — pytest-asyncio's function-scoped
    # loops hit this between test functions (conftest.py sets this env var
    # for the whole test process), and — found via the M4 load test, not
    # by inspection — Celery's `asyncio.run()`-per-task pattern in
    # app/workers/tasks/crawl.py hits the exact same failure the moment one
    # worker process handles a second task and the pool hands back a
    # connection opened during the first task's now-dead loop. `run_mode`
    # below forces NullPool for "worker"/"beat" unconditionally for that
    # reason, independent of this flag; this flag exists for the test
    # process (which runs as `run_mode="api"`) and for anyone who wants it
    # off in the api/web process too.
    use_null_pool: bool = False

    # §104 load-test finding: SQLAlchemy's un-configured default
    # (pool_size=5, max_overflow=10 -> 15 concurrent connections per
    # process) queues almost all of a realistic concurrent request burst
    # behind a handful of DB connections — 300 concurrent authenticated
    # reads measured a p99 of ~3s purely from that queuing, not slow
    # queries. Raised, and made explicitly tunable per deployment: this
    # process's actual ceiling is (pool_size + max_overflow) times however
    # many processes share one Postgres (api + worker + beat here), which
    # must stay under Postgres's own max_connections.
    db_pool_size: int = 10
    db_max_overflow: int = 10
    db_pool_timeout_seconds: int = 30

    # Redis / queue
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # §104 — X-Forwarded-For is attacker-controlled input unless something
    # in front of this process (a load balancer/reverse proxy) sets it
    # itself and strips any client-supplied copy first. Trusting it
    # unconditionally lets a caller mint a fresh rate-limit bucket on every
    # request just by changing the header. Off by default; a real
    # deployment behind a proxy that guarantees this opts in explicitly.
    trust_proxy_headers: bool = False

    # Auth
    auth_secret: str = "insecure-dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    internal_service_token: str = "insecure-dev-internal-token"

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_gsc_redirect_uri: str = "http://localhost:8000/api/v1/integrations/gsc/callback"

    # Razorpay
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # Storage
    storage_endpoint: str = "http://localhost:9000"
    storage_public_endpoint: str = "http://localhost:9000"
    storage_access_key: str = "spyminio"
    storage_secret_key: str = "spyminio123"
    storage_bucket: str = "spy-reports"
    storage_region: str = "us-east-1"

    # Encryption (Fernet key — 32 url-safe base64-encoded bytes)
    token_encryption_key: str = "0" * 43 + "="

    # Crawler
    crawler_user_agent: str = "SpyBot/1.0 (+http://localhost:3000/spybot)"
    crawler_max_concurrency_per_host: int = 4
    crawler_global_concurrency: int = 20
    js_render_enabled: bool = False

    # Email
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_from: str = "no-reply@spy.local"

    # §109 data retention — how long each kind of row is kept before a daily
    # job purges it. Audits themselves (scores/evidence/issue summaries) are
    # never purged by this job, only the heavy per-page crawl detail behind
    # them; see app/workers/tasks/retention.py.
    crawl_data_retention_days: int = 180
    audit_log_retention_days: int = 400
    idempotency_key_retention_days: int = 7

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @model_validator(mode="after")
    def _refuse_insecure_defaults_in_production(self) -> "Settings":
        if not self.is_production:
            return self
        leaked = [name for name, default in _INSECURE_DEFAULTS.items() if getattr(self, name) == default]
        if leaked:
            raise ValueError(
                "ENVIRONMENT=production but these settings still hold their insecure placeholder "
                f"default and MUST be set to a real, private value before starting: {', '.join(leaked)}."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
