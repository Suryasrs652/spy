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

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://spy:spy@localhost:5432/spy"
    )
    database_url_sync: str = Field(
        default="postgresql+psycopg://spy:spy@localhost:5432/spy"
    )
    # Test-only: pytest-asyncio tears down and recreates the event loop
    # between test functions, but SQLAlchemy's default async pool keeps
    # asyncpg connections bound to whichever loop was running when they were
    # opened — reusing one from a dead loop raises "attached to a different
    # loop". NullPool opens a fresh physical connection per checkout and
    # closes it on checkin, sidestepping cross-loop reuse entirely; this
    # never applies outside the test process (conftest.py sets the env var).
    use_null_pool: bool = False

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
