"""GitHub and Google OAuth 2.0 login, without an OAuth framework.

The flow is the authorization-code flow with PKCE: a random state and verifier
are stored server-side in Redis for one callback, the browser also carries the
state in a short-lived HttpOnly cookie (so a callback URL minted in an
attacker's browser cannot log a victim into the attacker's account), and the
provider's verified email is the only address the local account may adopt.

Identity rules:
- the provider's stable subject id — never the email — keys the link;
- only an email the provider marks verified can create or link an account;
- an existing local account with that verified email is linked, and any
  unverified local address becomes verified (the provider just proved control);
- a brand-new account requires recorded terms + 18+ consent from the start
  request, because the callback itself has no form to collect it.
"""

import base64
import datetime
import hashlib
import json
import logging
import secrets
import uuid
from dataclasses import dataclass
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.service import get_redis, open_session
from src.config.settings import get_settings
from src.db.models import OAuthAccount, User, UserSession

logger = logging.getLogger(__name__)

PROVIDERS = ("github", "google")
_STATE_PREFIX = "oauth_state"


class OAuthError(RuntimeError):
    """The provider flow could not prove an acceptable identity."""


class ProviderNotConfigured(OAuthError):
    """This provider has no client credentials in the environment."""


class ConsentRequired(OAuthError):
    """A new account tried to start without terms + age attestation."""


@dataclass(frozen=True)
class OAuthIdentity:
    provider: str
    subject: str
    email: str
    email_verified: bool
    name: str | None = None


def configured_providers() -> dict[str, bool]:
    settings = get_settings()
    return {
        "github": bool(settings.github_client_id and settings.github_client_secret),
        "google": bool(settings.google_client_id and settings.google_client_secret),
    }


def _credentials(provider: str) -> tuple[str, str]:
    settings = get_settings()
    client_id = getattr(settings, f"{provider}_client_id", None)
    client_secret = getattr(settings, f"{provider}_client_secret", None)
    if not client_id or not client_secret:
        raise ProviderNotConfigured(f"{provider} is not configured")
    return client_id, client_secret


def redirect_uri(provider: str) -> str:
    settings = get_settings()
    base = (settings.oauth_redirect_base or settings.app_base_url).rstrip("/")
    return f"{base}/api/v1/auth/oauth/{provider}/callback"


def safe_next(raw: str | None) -> str:
    """Only a same-origin relative path may be the post-login destination."""
    if not raw or len(raw) > 512:
        return "/overview"
    if any(ord(char) <= 0x1F or ord(char) == 0x7F for char in raw):
        return "/overview"
    if not raw.startswith("/") or raw.startswith("//") or "\\" in raw:
        return "/overview"
    try:
        parts = urlsplit(raw)
    except ValueError:
        return "/overview"
    if parts.scheme or parts.netloc:
        return "/overview"
    return urlunsplit(("", "", parts.path or "/overview", parts.query, ""))


def new_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def authorize_url(provider: str, *, state: str, code_challenge: str) -> str:
    client_id, _ = _credentials(provider)
    common = {
        "client_id": client_id,
        "redirect_uri": redirect_uri(provider),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if provider == "github":
        return "https://github.com/login/oauth/authorize?" + urlencode(
            {**common, "scope": "read:user user:email"}
        )
    if provider == "google":
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
            {
                **common,
                "response_type": "code",
                "scope": "openid email profile",
                "access_type": "online",
                "prompt": "select_account",
            }
        )
    raise ProviderNotConfigured(provider)


async def store_state(
    state: str,
    *,
    provider: str,
    verifier: str,
    next_path: str,
    accept_terms: bool,
    age_confirmed: bool,
) -> None:
    await get_redis().setex(
        f"{_STATE_PREFIX}:{state}",
        get_settings().oauth_state_ttl_seconds,
        json.dumps(
            {
                "provider": provider,
                "verifier": verifier,
                "next": safe_next(next_path),
                "accept_terms": bool(accept_terms),
                "age_confirmed": bool(age_confirmed),
            }
        ),
    )


async def consume_state(state: str) -> dict | None:
    raw = await get_redis().getdel(f"{_STATE_PREFIX}:{state}")
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(payload, dict) or payload.get("provider") not in PROVIDERS:
        return None
    return payload


async def _token_request(provider: str, data: dict) -> str:
    if provider == "github":
        url = "https://github.com/login/oauth/access_token"
        headers = {"Accept": "application/json"}
    elif provider == "google":
        url = "https://oauth2.googleapis.com/token"
        headers = {"Accept": "application/json"}
    else:
        raise ProviderNotConfigured(provider)

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            response = await client.post(url, data=data, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OAuthError("provider token exchange failed") from exc

    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        raise OAuthError("provider returned no access token")
    return token


async def exchange_code(provider: str, code: str, code_verifier: str) -> str:
    client_id, client_secret = _credentials(provider)
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri(provider),
        "code_verifier": code_verifier,
    }
    if provider == "google":
        data["grant_type"] = "authorization_code"
    return await _token_request(provider, data)


async def _get_json(url: str, access_token: str) -> object:
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OAuthError("provider identity request failed") from exc


def identity_from_google(payload: object) -> OAuthIdentity:
    if not isinstance(payload, dict):
        raise OAuthError("google returned a non-object identity")
    subject = payload.get("sub")
    email = payload.get("email")
    verified = payload.get("email_verified")
    if not subject or not email or verified is not True:
        raise OAuthError("google returned no verified email")
    return OAuthIdentity(
        provider="google",
        subject=str(subject),
        email=str(email).strip().lower(),
        email_verified=True,
        name=payload.get("name") if isinstance(payload.get("name"), str) else None,
    )


def identity_from_github(user: object, emails: object) -> OAuthIdentity:
    if not isinstance(user, dict):
        raise OAuthError("github returned a non-object identity")
    subject = user.get("id")
    if subject is None:
        raise OAuthError("github returned no subject")
    verified_email = None
    if isinstance(emails, list):
        verified = [
            row
            for row in emails
            if isinstance(row, dict) and row.get("verified") is True and row.get("email")
        ]
        primary = next((row for row in verified if row.get("primary") is True), None)
        chosen = primary or (verified[0] if verified else None)
        if chosen is not None:
            verified_email = str(chosen["email"])
    if verified_email is None:
        raise OAuthError("github returned no verified email")
    return OAuthIdentity(
        provider="github",
        subject=str(subject),
        email=verified_email.strip().lower(),
        email_verified=True,
        name=user.get("name") if isinstance(user.get("name"), str) else None,
    )


async def fetch_identity(provider: str, access_token: str) -> OAuthIdentity:
    if provider == "google":
        return identity_from_google(
            await _get_json(
                "https://openidconnect.googleapis.com/v1/userinfo", access_token
            )
        )
    if provider == "github":
        user = await _get_json("https://api.github.com/user", access_token)
        emails = await _get_json("https://api.github.com/user/emails", access_token)
        return identity_from_github(user, emails)
    raise ProviderNotConfigured(provider)


async def _find_link(db: AsyncSession, provider: str, subject: str) -> OAuthAccount | None:
    return (
        await db.execute(
            select(OAuthAccount).where(
                OAuthAccount.provider == provider,
                OAuthAccount.provider_user_id == subject,
            )
        )
    ).scalar_one_or_none()


async def login_or_create(
    db: AsyncSession,
    identity: OAuthIdentity,
    *,
    accept_terms: bool,
    age_confirmed: bool,
    ip: str | None = None,
    user_agent: str | None = None,
) -> tuple[User, UserSession, bool]:
    """Resolve an external identity to a local account and open a session.

    Returns ``(user, session, created)``. Raises :class:`ConsentRequired` when a
    new account has no recorded terms/age acceptance.
    """
    link = await _find_link(db, identity.provider, identity.subject)
    if link is not None:
        user = await db.get(User, link.user_id)
        if user is None or user.disabled_at is not None:
            raise OAuthError("account is unavailable")
        session = await open_session(
            db, user.id, user_agent=user_agent, ip=ip
        )
        return user, session, False

    user = (
        await db.execute(select(User).where(User.email == identity.email))
    ).scalar_one_or_none()
    created = False

    if user is None:
        if not (accept_terms and age_confirmed):
            raise ConsentRequired("terms and age confirmation are required")
        from src.legal import service as legal_service

        now = datetime.datetime.now(datetime.UTC)
        user = User(
            email=identity.email,
            password_hash=None,
            email_verified_at=now,
            age_confirmed_at=now,
        )
        db.add(user)
        await db.flush()
        try:
            await legal_service.record_consents(
                db, user_id=user.id, ip=ip, user_agent=user_agent, commit=False
            )
        except Exception:
            await db.rollback()
            raise
        created = True
    elif user.disabled_at is not None:
        raise OAuthError("account is unavailable")
    elif user.email_verified_at is None:
        # The provider proved control of this address; the local account is now
        # verified rather than duplicated.
        user.email_verified_at = datetime.datetime.now(datetime.UTC)

    db.add(
        OAuthAccount(
            user_id=user.id,
            provider=identity.provider,
            provider_user_id=identity.subject,
            email=identity.email,
        )
    )
    try:
        await db.commit()
    except IntegrityError:
        # A concurrent callback created the same link first: reuse it.
        await db.rollback()
        link = await _find_link(db, identity.provider, identity.subject)
        if link is None:
            raise OAuthError("identity link conflicted") from None
        user = await db.get(User, link.user_id)
        if user is None or user.disabled_at is not None:
            raise OAuthError("account is unavailable")

    session = await open_session(db, user.id, user_agent=user_agent, ip=ip)
    return user, session, created


def audit_action(created: bool) -> str:
    return "oauth_signup" if created else "oauth_login"
