"""OAuth login routes: provider discovery, start, and callback.

The callback is a browser navigation, not a JSON API: every failure ends in a
302 back to the sign-in page with a stable error code, never a provider body or
a stack trace. The session cookie is set on the redirect response, which is the
only place a new browser session is minted outside the password flow.
"""

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.limits import limiter
from src.audit import client_ip, record as audit_record
from src.auth import oauth
from src.auth.cookies import set_csrf_cookie, set_session_cookie
from src.config.settings import get_settings
from src.db.engine import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth/oauth", tags=["auth"])

STATE_COOKIE = "oauth_state"
STATE_COOKIE_PATH = "/api/v1/auth/oauth"


def _app_base() -> str:
    return get_settings().app_base_url.rstrip("/")


def _failure(provider: str | None, code: str) -> RedirectResponse:
    target = f"{_app_base()}/auth/signin?error={code}"
    if provider:
        target += f"&provider={provider}"
    response = RedirectResponse(target, status_code=303)
    response.delete_cookie(STATE_COOKIE, path=STATE_COOKIE_PATH)
    return response


def _bool_param(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


@router.get("/providers")
async def providers() -> dict[str, bool]:
    """Which providers an operator has configured; no secret or client id."""
    return oauth.configured_providers()


@router.get("/{provider}/start")
@limiter.limit(lambda: get_settings().rate_limit_oauth)
async def start(
    provider: str,
    request: Request,
    next: str | None = None,
    accept_terms: str | None = None,
    age_confirmed: str | None = None,
) -> RedirectResponse:
    if provider not in oauth.PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown provider.")
    if not oauth.configured_providers().get(provider):
        raise HTTPException(
            status_code=503,
            detail={"code": "provider_unavailable", "message": "This sign-in provider is not configured."},
        )

    state = secrets.token_urlsafe(32)
    verifier, challenge = oauth.new_pkce_pair()
    await oauth.store_state(
        state,
        provider=provider,
        verifier=verifier,
        next_path=oauth.safe_next(next),
        accept_terms=_bool_param(accept_terms),
        age_confirmed=_bool_param(age_confirmed),
    )

    response = RedirectResponse(
        oauth.authorize_url(provider, state=state, code_challenge=challenge),
        status_code=302,
    )
    response.set_cookie(
        STATE_COOKIE,
        state,
        max_age=get_settings().oauth_state_ttl_seconds,
        path=STATE_COOKIE_PATH,
        httponly=True,
        samesite="lax",
        secure=get_settings().cookie_secure,
    )
    return response


@router.get("/{provider}/callback")
@limiter.limit(lambda: get_settings().rate_limit_oauth)
async def callback(
    provider: str,
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    if provider not in oauth.PROVIDERS:
        return _failure(None, "oauth_failed")
    if error:
        return _failure(provider, "oauth_denied")

    cookie_state = request.cookies.get(STATE_COOKIE)
    if not state or not cookie_state or not secrets.compare_digest(
        state, cookie_state
    ):
        return _failure(provider, "oauth_state")

    payload = await oauth.consume_state(state)
    if payload is None or payload.get("provider") != provider:
        return _failure(provider, "oauth_state")
    if not code:
        return _failure(provider, "oauth_failed")

    try:
        access_token = await oauth.exchange_code(
            provider, code, str(payload.get("verifier") or "")
        )
        identity = await oauth.fetch_identity(provider, access_token)
        user, session, created = await oauth.login_or_create(
            db,
            identity,
            accept_terms=bool(payload.get("accept_terms")),
            age_confirmed=bool(payload.get("age_confirmed")),
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except oauth.ConsentRequired:
        return _failure(provider, "consent_required")
    except oauth.ProviderNotConfigured:
        return _failure(provider, "provider_unavailable")
    except oauth.OAuthError as exc:
        logger.warning("OAuth %s failed: %s", provider, exc)
        return _failure(provider, "oauth_failed")
    except Exception:
        logger.exception("OAuth %s callback crashed", provider)
        return _failure(provider, "oauth_failed")

    await audit_record(
        db,
        oauth.audit_action(created),
        user_id=user.id,
        ip=client_ip(request),
        meta={"provider": provider},
    )

    response = RedirectResponse(
        f"{_app_base()}{oauth.safe_next(str(payload.get('next') or '/overview'))}",
        status_code=303,
    )
    set_session_cookie(response, str(session.id))
    set_csrf_cookie(response)
    response.delete_cookie(STATE_COOKIE, path=STATE_COOKIE_PATH)
    return response
