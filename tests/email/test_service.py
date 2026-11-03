"""Transactional email: log sink in dev, fail-closed in prod, one POST with a key."""

import logging
from types import SimpleNamespace

import pytest

from src.config.settings import Settings, get_settings
from src.email import service
from src.email.service import EmailMessage, EmailNotConfigured


@pytest.fixture(autouse=True)
def _fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_missing_key_in_dev_logs_and_sends_nothing(monkeypatch, caplog):
    monkeypatch.delenv("EMAIL_API_KEY", raising=False)
    monkeypatch.setenv("ENV", "dev")
    get_settings.cache_clear()

    def _boom(*args, **kwargs):
        raise AssertionError("no HTTP call without a key")

    monkeypatch.setattr(service, "httpx", SimpleNamespace(AsyncClient=_boom))

    with caplog.at_level(logging.INFO, logger="src.email.service"):
        await service.send(EmailMessage(to="to@example.com", subject="Hi", text="Body"))

    assert any("email (not sent)" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_missing_key_in_prod_raises(monkeypatch):
    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: SimpleNamespace(env="prod", email_api_key=None),
    )

    with pytest.raises(EmailNotConfigured):
        await service.send(EmailMessage(to="to@example.com", subject="Hi", text="Body"))


def test_settings_refuse_prod_without_an_email_key():
    with pytest.raises(ValueError, match="EMAIL_API_KEY"):
        Settings(env="prod")


@pytest.mark.asyncio
async def test_send_posts_one_authorized_message(monkeypatch):
    monkeypatch.setenv("EMAIL_API_KEY", "test-key")
    monkeypatch.setenv("EMAIL_API_URL", "http://mail.test/send")
    monkeypatch.setenv("EMAIL_FROM", "no-reply@test.local")
    get_settings.cache_clear()

    calls: list[tuple] = []

    class _FakeResponse:
        def raise_for_status(self):
            return None

    class _FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

        async def post(self, url, json=None, headers=None):
            calls.append((url, json, headers, self.kwargs))
            return _FakeResponse()

    monkeypatch.setattr(service, "httpx", SimpleNamespace(AsyncClient=_FakeClient))

    await service.send(
        EmailMessage(to="to@example.com", subject="Subject", text="Body text")
    )

    assert len(calls) == 1
    url, payload, headers, kwargs = calls[0]
    assert url == "http://mail.test/send"
    assert payload == {
        "from": "no-reply@test.local",
        "to": ["to@example.com"],
        "subject": "Subject",
        "text": "Body text",
    }
    assert headers == {"Authorization": "Bearer test-key"}
    assert kwargs["timeout"] == 10


def test_messages_carry_link_and_expiry():
    verification = service.verification_message(
        to="to@example.com", link="https://app.test/auth/verify?token=abc"
    )
    reset = service.reset_message(
        to="to@example.com", link="https://app.test/auth/reset?token=xyz"
    )

    assert "expires in 24 hours" in verification.text
    assert "expires in 1 hour" in reset.text
    for message, link in (
        (verification, "https://app.test/auth/verify?token=abc"),
        (reset, "https://app.test/auth/reset?token=xyz"),
    ):
        assert link in message.text
        assert "ignore it" in message.text
