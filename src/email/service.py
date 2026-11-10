"""Transactional email over a bare httpx POST.

The provider is chosen by URL, not by SDK. With no API key, dev and staging
log the message instead of sending; prod treats the missing key as a startup
error (the settings validator) and a runtime send as a hard failure. Keys and
full recipient lists never reach the logs.
"""

import logging
from dataclasses import dataclass

import httpx

from src.config.settings import get_settings

logger = logging.getLogger(__name__)


class EmailNotConfigured(RuntimeError):
    """A send was attempted in prod without EMAIL_API_KEY."""


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text: str


def _duration(seconds: int) -> str:
    if seconds < 3600:
        minutes = max(1, seconds // 60)
        return "1 minute" if minutes == 1 else f"{minutes} minutes"
    hours = seconds // 3600
    return "1 hour" if hours == 1 else f"{hours} hours"


async def send(message: EmailMessage) -> None:
    settings = get_settings()
    if not settings.email_api_key:
        if settings.env in ("dev", "staging"):
            logger.info(
                "email (not sent) to=%s subject=%s", message.to, message.subject
            )
            return
        raise EmailNotConfigured("EMAIL_API_KEY is not configured")

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            settings.email_api_url,
            json={
                "from": settings.email_from,
                "to": [message.to],
                "subject": message.subject,
                "text": message.text,
            },
            headers={"Authorization": f"Bearer {settings.email_api_key}"},
        )
        response.raise_for_status()


def verification_message(*, to: str, link: str) -> EmailMessage:
    return EmailMessage(
        to=to,
        subject="Verify your email address",
        text=(
            "Confirm your Societas email address by opening this link:\n\n"
            f"{link}\n\n"
            f"This link expires in {_duration(get_settings().email_verification_ttl_seconds)}. "
            "If you did not request this, ignore it.\n"
        ),
    )


def reset_message(*, to: str, link: str) -> EmailMessage:
    return EmailMessage(
        to=to,
        subject="Reset your Societas password",
        text=(
            "Choose a new Societas password by opening this link:\n\n"
            f"{link}\n\n"
            f"This link expires in {_duration(get_settings().password_reset_ttl_seconds)}. "
            "If you did not request this, ignore it.\n"
        ),
    )
