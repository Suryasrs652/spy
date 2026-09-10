"""Minimal transactional email sender (§134).

Dev/staging: points at MailHog (SMTP with no auth/TLS). Swapping to a real
provider means changing SMTP_HOST/PORT (and adding auth) — the call site
never changes.
"""
from __future__ import annotations

import structlog
from aiosmtplib import send
from email.message import EmailMessage

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


async def send_email(*, to: str, subject: str, body: str) -> None:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    try:
        await send(message, hostname=settings.smtp_host, port=settings.smtp_port)
    except Exception:  # noqa: BLE001
        # Email delivery must never fail the request that triggered it
        # (signup, password reset) — log and move on.
        logger.error("email_send_failed", to=to, subject=subject, exc_info=True)


def verification_email_body(verify_url: str) -> str:
    return (
        "Welcome to Spy.\n\n"
        f"Verify your email to unlock your free audit: {verify_url}\n\n"
        "This link expires in 24 hours."
    )


def password_reset_email_body(reset_url: str) -> str:
    return (
        "A password reset was requested for your Spy account.\n\n"
        f"Reset your password: {reset_url}\n\n"
        "If you didn't request this, you can ignore this email."
    )
