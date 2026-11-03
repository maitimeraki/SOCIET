"""Auth endpoints under /api/v1/auth (R3: these are the canonical paths)."""

import datetime
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.limits import limiter
from src.audit import record as audit_record
from src.auth import reset, service, verify
from src.auth.cookies import (
    clear_csrf_cookie,
    clear_session_cookie,
    set_csrf_cookie,
    set_session_cookie,
    verify_csrf,
)
from src.auth.deps import cookie_session_id, current_user, require_owner
from src.billing.entitlements import resolve_entitlements
from src.config.settings import get_settings
from src.db.engine import get_db
from src.db.models import User, UserSession

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/auth", tags=["auth"], dependencies=[Depends(verify_csrf)]
)

# POST /api/v1/ws-ticket sits outside the /auth prefix (plan §3: the auth
# surface owns minting; the WS handshake redeems it in Task 4).
ws_ticket_router = APIRouter(
    prefix="/api/v1", tags=["auth"], dependencies=[Depends(verify_csrf)]
)


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=service.MIN_PASSWORD_LENGTH)
    accept_terms: bool
    age_confirmed: bool


class VerifyRequest(BaseModel):
    token: str


class ResetRequest(BaseModel):
    email: EmailStr


class ResetConfirmRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=service.MIN_PASSWORD_LENGTH)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=service.MIN_PASSWORD_LENGTH)


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    plan: str
    created_at: datetime.datetime

    @classmethod
    def from_user(cls, user: User, **extra) -> "UserOut":
        return cls(
            id=user.id,
            email=user.email,
            role=user.role,
            plan=user.plan_key,
            created_at=user.created_at,
            **extra,
        )


class EntitlementOut(BaseModel):
    max_agents: int
    max_rounds: int
    units_remaining: int
    period_end: datetime.datetime


class MeOut(UserOut):
    entitlements: EntitlementOut


class SessionOut(BaseModel):
    id: uuid.UUID
    created_at: datetime.datetime
    last_seen_at: datetime.datetime
    user_agent: str | None
    ip: str | None


class WsTicketOut(BaseModel):
    ticket: str
    expires_in: int


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _session_out(row: UserSession) -> SessionOut:
    # INET columns come back as ipaddress objects, which are not JSON-serializable.
    return SessionOut(
        id=row.id,
        created_at=row.created_at,
        last_seen_at=row.last_seen_at,
        user_agent=row.user_agent,
        ip=str(row.ip) if row.ip is not None else None,
    )


@router.post("/signup", response_model=UserOut, status_code=201)
@limiter.limit(lambda: get_settings().rate_limit_signup)
async def signup(
    body: SignupRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    user, session = await service.signup(
        db,
        body.email,
        body.password,
        user_agent=request.headers.get("user-agent"),
        ip=_client_ip(request),
        accept_terms=body.accept_terms,
        age_confirmed=body.age_confirmed,
    )
    set_session_cookie(response, session.id)
    set_csrf_cookie(response)
    try:
        await verify.send_verification_email(user)
    except Exception:
        # The account is real; a mail outage must not turn signup into a 500.
        logger.warning("Verification email failed for user %s", user.id, exc_info=True)
    return UserOut.from_user(user)


@router.post("/verify/send", status_code=204)
@limiter.limit(lambda: get_settings().rate_limit_email)
async def send_verification(
    request: Request,
    user: User = Depends(current_user),
) -> None:
    if user.email_verified_at is not None:
        return
    await verify.send_verification_email(user)


@router.post("/verify", status_code=204)
async def verify_email(
    body: VerifyRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    user_id = await verify.redeem_verification_token(body.token)
    if user_id is None:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_token",
                "message": "This link is invalid or has expired.",
            },
        )
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_token",
                "message": "This link is invalid or has expired.",
            },
        )
    if user.email_verified_at is None:
        user.email_verified_at = datetime.datetime.now(datetime.UTC)
        await db.commit()


@router.post("/reset/request", status_code=202)
@limiter.limit(lambda: get_settings().rate_limit_email)
async def request_password_reset(
    body: ResetRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Always 202: the response never reveals whether the email exists."""
    user = (
        await db.execute(
            select(User).where(User.email == service.normalize_email(body.email))
        )
    ).scalar_one_or_none()
    if user is not None and user.disabled_at is None:
        try:
            await reset.send_reset_email(user)
        except Exception:
            logger.warning("Reset email failed for user %s", user.id, exc_info=True)
    return {"status": "accepted"}


@router.post("/reset/confirm", status_code=204)
async def confirm_password_reset(
    body: ResetConfirmRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    user_id = await reset.redeem_reset_token(body.token)
    if user_id is None:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_token",
                "message": "This link is invalid or has expired.",
            },
        )
    await reset.reset_password(db, user_id, body.new_password)


@router.post("/login", response_model=UserOut)
@limiter.limit(lambda: get_settings().rate_limit_login)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    user, session = await service.login(
        db,
        body.email,
        body.password,
        user_agent=request.headers.get("user-agent"),
        ip=_client_ip(request),
    )
    set_session_cookie(response, session.id)
    set_csrf_cookie(response)
    await audit_record(db, "login", user_id=user.id, ip=_client_ip(request))
    return UserOut.from_user(user)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    sid = cookie_session_id(request)
    if sid is not None:
        await service.logout(db, sid)
    clear_session_cookie(response)
    clear_csrf_cookie(response)
    await audit_record(db, "logout", user_id=user.id, ip=_client_ip(request))


@router.get("/me", response_model=MeOut)
async def me(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> MeOut:
    entitlements = await resolve_entitlements(db, user=user)
    return MeOut.from_user(
        user,
        entitlements=EntitlementOut(
            max_agents=entitlements.plan.max_agents,
            max_rounds=entitlements.plan.max_rounds,
            units_remaining=entitlements.units_remaining,
            period_end=entitlements.period_end,
        ),
    )


@router.post("/password", status_code=204)
async def change_password(
    body: PasswordChangeRequest,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await service.change_password(
        db,
        user.id,
        body.current_password,
        body.new_password,
        keep_session_id=cookie_session_id(request),
    )
    await audit_record(db, "password_change", user_id=user.id, ip=_client_ip(request))


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> list[SessionOut]:
    rows = await service.list_sessions(db, user.id)
    return [_session_out(row) for row in rows]


@router.delete("/sessions/{session_id}", status_code=204)
async def revoke_session(
    session_id: uuid.UUID,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    row = await db.get(UserSession, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found.")
    await require_owner(row.user_id, user)
    await service.revoke_session(db, row)
    await audit_record(
        db,
        "session_revoke",
        user_id=user.id,
        target=str(session_id),
        ip=_client_ip(request),
    )


@ws_ticket_router.post("/ws-ticket", response_model=WsTicketOut)
async def create_ws_ticket(
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> WsTicketOut:
    """Mint a fresh single-use ticket for the WebSocket handshake (R4)."""
    ttl = get_settings().ws_ticket_ttl_seconds
    ticket = await service.issue_ws_ticket(user.id, ttl_seconds=ttl)
    await audit_record(db, "ws_ticket_issue", user_id=user.id, ip=_client_ip(request))
    return WsTicketOut(ticket=ticket, expires_in=ttl)
