"""Central application configuration.

All configurable values (§115) are read from environment variables via
pydantic-settings. Nothing here is a secret's default that would be safe to
ship — the values in .env.example are local-dev placeholders only.
"""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
