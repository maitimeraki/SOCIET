"""Role dependency: in-memory users, no DB."""

import uuid

import pytest
from fastapi import HTTPException

from src.auth.deps import Role, require_role
from src.db.models import User


def _user(role: str) -> User:
    return User(
        id=uuid.uuid4(),
        email=f"{role}@example.com",
        password_hash="x",
        role=role,
    )


@pytest.mark.asyncio
async def test_admin_role_is_accepted():
    user = _user("admin")
    assert await require_role(Role.ADMIN)(user=user) is user


@pytest.mark.asyncio
async def test_user_role_is_denied_for_admin():
    with pytest.raises(HTTPException) as raised:
        await require_role(Role.ADMIN)(user=_user("user"))
    assert raised.value.status_code == 403


@pytest.mark.asyncio
async def test_support_and_admin_are_both_accepted():
    dep = require_role(Role.SUPPORT, Role.ADMIN)
    for role in ("support", "admin"):
        user = _user(role)
        assert await dep(user=user) is user


@pytest.mark.asyncio
async def test_user_role_is_denied_for_support():
    with pytest.raises(HTTPException) as raised:
        await require_role(Role.SUPPORT)(user=_user("user"))
    assert raised.value.status_code == 403
