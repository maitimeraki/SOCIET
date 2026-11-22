"""Transactional email over a bare httpx POST.

The provider is chosen by URL, not by SDK. With no API key, dev and staging
log the message instead of sending; prod treats the missing key as a startup
error (the settings validator) and a runtime send as a hard failure. Keys and
full recipient lists never reach the logs.
"""

import logging
from dataclasses import dataclass
from html import escape

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
    #: Optional HTML alternative; providers render it when present.
    html: str | None = None
    #: Optional Reply-To; a welcome mail should reach a monitored mailbox.
    reply_to: str | None = None
    #: Optional provider idempotency key, so a retried send is not a second mail.
    idempotency_key: str | None = None


def _redact(address: str) -> str:
    """`a***@example.com` — enough to debug a sink, never the full address."""
    local, separator, domain = address.partition("@")
    if not separator or not domain:
        return "<redacted>"
    return f"{local[:1]}***@{domain}"


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
                "email (not sent) to=%s subject=%s",
                _redact(message.to),
                message.subject,
            )
            return
        raise EmailNotConfigured("EMAIL_API_KEY is not configured")

    payload = {
        "from": settings.email_from,
        "to": [message.to],
        "subject": message.subject,
        "text": message.text,
    }
    if message.html is not None:
        payload["html"] = message.html
    if message.reply_to is not None:
        payload["reply_to"] = message.reply_to

    headers = {"Authorization": f"Bearer {settings.email_api_key}"}
    if message.idempotency_key is not None:
        headers["Idempotency-Key"] = message.idempotency_key

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            settings.email_api_url,
            json=payload,
            headers=headers,
        )
        response.raise_for_status()


def verification_message(
    *, to: str, link: str, code: str | None = None
) -> EmailMessage:
    code_line = ""
    if code is not None:
        code_line = (
            f"Your confirmation code is {code}. "
            f"It expires in {_duration(get_settings().email_code_ttl_seconds)}.\n\n"
        )
    return EmailMessage(
        to=to,
        subject="Verify your email address",
        text=(
            f"{code_line}"
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


def welcome_message(
    *, to: str, link: str, support_email: str, user_id: str
) -> EmailMessage:
    """The after-signup welcome: what Societas does and the first three steps.

    Both parts are static except the configured link and support address, so
    nothing the user typed is reflected into the mail. The idempotency key is
    per account, so a retried signup cannot produce a second welcome.
    """
    subject = "Welcome to Societas"
    text = (
        "Hi,\n\n"
        "Your Societas account is ready.\n\n"
        "Societas turns your material into a panel that argues a question and "
        "writes a verdict you can audit. To get your first decision:\n\n"
        "  1. Upload the documents that hold the evidence.\n"
        "  2. Ask the question the panel should settle.\n"
        "  3. Read the verdict; every claim is traced to its source.\n\n"
        f"Open your workspace:\n{link}\n\n"
        "Your free plan is active. If you have not confirmed your address yet, "
        "the verification link is in a separate email.\n\n"
        f"Questions? Write to {support_email}.\n\n"
        "— Societas\n"
    )
    safe_link = escape(link, quote=True)
    safe_support = escape(support_email, quote=True)
    html = (
        '<!doctype html><html><body style="margin:0;padding:0;'
        'background:#f7f4ee;">'
        '<div style="max-width:560px;margin:0 auto;padding:40px 24px;'
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,"
        'Arial,sans-serif;color:#1c1a17;font-size:16px;line-height:1.6;">'
        '<p style="margin:0 0 24px;font-size:12px;letter-spacing:.12em;'
        'text-transform:uppercase;color:#6f675e;">Societas</p>'
        '<h1 style="margin:0 0 16px;font-size:28px;line-height:1.2;'
        'font-weight:600;">Your account is ready.</h1>'
        '<p style="margin:0 0 16px;">Societas turns your material into a panel '
        "that argues a question and writes a verdict you can audit.</p>"
        '<ol style="margin:0 0 24px;padding-left:20px;">'
        "<li>Upload the documents that hold the evidence.</li>"
        "<li>Ask the question the panel should settle.</li>"
        "<li>Read the verdict; every claim is traced to its source.</li></ol>"
        f'<p style="margin:0 0 28px;"><a href="{safe_link}" '
        'style="display:inline-block;background:#1c1a17;color:#f7f4ee;'
        "text-decoration:none;padding:12px 20px;border-radius:4px;"
        'font-weight:600;">Open your workspace</a></p>'
        '<p style="margin:0 0 8px;">Your free plan is active.</p>'
        '<p style="margin:0 0 8px;color:#6f675e;font-size:14px;">If you have '
        "not confirmed your address yet, the verification link is in a "
        "separate email.</p>"
        '<hr style="border:0;border-top:1px solid #e2dbd1;margin:28px 0;">'
        '<p style="margin:0;color:#6f675e;font-size:13px;">Questions? Write to '
        f'<a href="mailto:{safe_support}" style="color:#b4552d;">'
        f"{safe_support}</a>.</p>"
        "</div></body></html>"
    )
    return EmailMessage(
        to=to,
        subject=subject,
        text=text,
        html=html,
        reply_to=support_email,
        idempotency_key=f"welcome-{user_id}",
    )
