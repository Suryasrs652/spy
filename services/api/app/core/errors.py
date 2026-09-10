"""Application error taxonomy and the §98 JSON error envelope.

Every error surfaced to a client must be an AppError (or get wrapped into
one by the global handler). AppError never carries a stack trace, SQL text,
a filesystem path, or a secret — those go to the structured logs only.
"""
from __future__ import annotations

import uuid

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

import structlog

logger = structlog.get_logger(__name__)


class AppError(Exception):
    """Base class for all deliberately-raised, client-facing errors."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "BAD_REQUEST"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"


class ValidationAppError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "VALIDATION_ERROR"


class UnauthenticatedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "UNAUTHENTICATED"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "FORBIDDEN"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"


class RateLimitedError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "RATE_LIMITED"


class PaymentRequiredError(AppError):
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    code = "AUDIT_PAYMENT_REQUIRED"


class BlockedTargetError(AppError):
    """SSRF guard rejection (§107, §123)."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "BLOCKED_TARGET"


def _envelope(code: str, message: str, request_id: str) -> dict:
    return {"error": {"code": code, "message": message, "request_id": request_id}}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or str(uuid.uuid4())


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    request_id = _request_id(request)
    logger.info("app_error", code=exc.code, message=exc.message, request_id=request_id)
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(exc.code, exc.message, request_id),
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    request_id = _request_id(request)
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(f"HTTP_{exc.status_code}", detail, request_id),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    request_id = _request_id(request)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_envelope("VALIDATION_ERROR", "One or more fields are invalid.", request_id),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = _request_id(request)
    # Full detail goes to logs only — never to the client (§98).
    logger.error("unhandled_exception", error=str(exc), request_id=request_id, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_envelope("INTERNAL_ERROR", "An unexpected error occurred.", request_id),
    )
