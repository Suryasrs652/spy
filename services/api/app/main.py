"""FastAPI application factory — wires middleware, exception handlers, and
every module's router under /api/v1 (§87)."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.core.errors import (
    AppError,
    app_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware

settings = get_settings()
configure_logging(json_logs=settings.is_production)

app = FastAPI(title="Spy API", version="1.0.0")

# Order matters: middleware runs outside-in on the request, inside-out on
# the response, so SecurityHeadersMiddleware (added second) sees the
# response last and can safely no-op on a header RequestContextMiddleware
# or a route already set (setdefault).
app.add_middleware(RequestContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


@app.get("/health/live", tags=["health"])
async def health_live() -> dict:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def health_ready() -> dict:
    from sqlalchemy import text

    from app.db.redis import get_redis
    from app.db.session import AsyncSessionLocal

    checks = {}

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {exc}"

    try:
        await get_redis().ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {exc}"

    healthy = all(v == "ok" for v in checks.values())
    return {"status": "ok" if healthy else "degraded", "checks": checks}


API_PREFIX = "/api/v1"

from app.modules.admin.router import router as admin_router  # noqa: E402
from app.modules.audits.router import router as audits_router  # noqa: E402
from app.modules.auth.internal_router import router as auth_internal_router  # noqa: E402
from app.modules.auth.router import router as auth_router  # noqa: E402
from app.modules.backlinks.router import router as backlinks_router  # noqa: E402
from app.modules.billing.router import router as billing_router  # noqa: E402
from app.modules.entitlements.router import router as entitlements_router  # noqa: E402
from app.modules.gsc.router import router as gsc_router  # noqa: E402
from app.modules.keywords.router import router as keywords_router  # noqa: E402
from app.modules.notifications.router import router as notifications_router  # noqa: E402
from app.modules.organizations.router import router as organizations_router  # noqa: E402
from app.modules.projects.router import router as projects_router  # noqa: E402
from app.modules.reports.router import router as reports_router  # noqa: E402

app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(auth_internal_router)  # already carries its own /internal/auth prefix, unversioned on purpose
app.include_router(organizations_router, prefix=API_PREFIX)
app.include_router(projects_router, prefix=API_PREFIX)
app.include_router(entitlements_router, prefix=API_PREFIX)
app.include_router(audits_router, prefix=API_PREFIX)
app.include_router(reports_router, prefix=API_PREFIX)
app.include_router(billing_router, prefix=API_PREFIX)
app.include_router(gsc_router, prefix=API_PREFIX)
app.include_router(admin_router, prefix=API_PREFIX)
app.include_router(notifications_router, prefix=API_PREFIX)
app.include_router(backlinks_router, prefix=API_PREFIX)
app.include_router(keywords_router, prefix=API_PREFIX)
