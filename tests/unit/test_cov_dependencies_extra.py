"""Additional unit coverage for token decoding, pad access and verify branches."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException, Request

import dependencies
import cache.redis_client as redis_client_module
from dependencies import (
    PadAccess,
    UserSession,
    get_verified_user,
    require_pad_access,
    require_pad_owner,
)
from domain.pad import Pad


@pytest.fixture(autouse=True)
def reset_redis_singleton(fakeredis_client):
    redis_client_module.RedisClient._client = fakeredis_client
    redis_client_module.RedisClient._instance = None
    yield
    redis_client_module.RedisClient._client = None
    redis_client_module.RedisClient._instance = None


@pytest.fixture
def sample_token_data():
    return {
        "sub": str(uuid.uuid4()),
        "email": "user@pad.test",
        "preferred_username": "user",
        "name": "Test User",
        "realm_access": {"roles": ["pad-user"]},
        "exp": datetime.now(timezone.utc).timestamp() + 3600,
    }


@pytest.fixture
def session_domain():
    domain = MagicMock()
    domain._get_jwks_client.return_value.get_signing_key_from_jwt.return_value = MagicMock(key="public-key")
    domain.get_issuer.return_value = "https://auth.pad.test/realms/pad"
    return domain


def _request_with_cookie(name: str, value: str) -> Request:
    request = Request(scope={"type": "http", "method": "GET", "headers": [], "path": "/"})
    request.scope["headers"] = [(b"cookie", f"{name}={value}".encode("latin-1"))]
    return request


# ---------------------------------------------------------------------------
# UserSession token decoding
# ---------------------------------------------------------------------------

def test_user_session_decodes_and_exposes_claims(sample_token_data, session_domain):
    with patch("dependencies.jwt.decode", return_value=sample_token_data) as decode:
        session = UserSession("header.payload.signature", {}, session_domain)

    assert session.token_data == sample_token_data
    assert decode.call_args.kwargs["algorithms"] == ["RS256"]
    assert session.is_authenticated is True
    assert session.id == uuid.UUID(sample_token_data["sub"])
    assert session.roles == ["pad-user"]
    assert session.is_admin is False


def test_user_session_rejects_invalid_token(session_domain):
    with patch("dependencies.jwt.decode", side_effect=jwt.InvalidTokenError("bad signature")):
        with pytest.raises(ValueError, match="Invalid authentication token"):
            UserSession("header.payload.signature", {}, session_domain)


def test_user_session_admin_role(sample_token_data, session_domain):
    admin_data = {**sample_token_data, "realm_access": {"roles": ["pad-user", "admin"]}}
    with patch("dependencies.jwt.decode", return_value=admin_data):
        session = UserSession("header.payload.signature", {}, session_domain)

    assert session.is_admin is True


def test_user_session_without_sub_is_not_authenticated(sample_token_data, session_domain):
    with patch("dependencies.jwt.decode", return_value={**sample_token_data, "sub": None}):
        session = UserSession("header.payload.signature", {}, session_domain)

    # Both ``id`` and ``is_authenticated`` rely on the ``sub`` claim.
    with pytest.raises((TypeError, ValueError)):
        _ = session.id
    with pytest.raises((TypeError, ValueError)):
        _ = session.is_authenticated


# ---------------------------------------------------------------------------
# PadAccess
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_require_pad_access_missing_pad(sample_token_data, monkeypatch):
    async def _missing(*args, **kwargs):
        return None

    monkeypatch.setattr(Pad, "get_by_id", _missing)
    user = MagicMock()
    user.id = uuid.UUID(sample_token_data["sub"])

    with pytest.raises(HTTPException) as exc_info:
        await require_pad_access(uuid.uuid4(), user, MagicMock())
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_require_pad_access_rejects_non_member(sample_token_data, monkeypatch):
    pad = MagicMock(spec=Pad)
    pad.can_access = MagicMock(return_value=False)

    async def _get_pad(*args, **kwargs):
        return pad

    monkeypatch.setattr(Pad, "get_by_id", _get_pad)
    user = MagicMock()
    user.id = uuid.UUID(sample_token_data["sub"])

    with pytest.raises(HTTPException) as exc_info:
        await require_pad_access(uuid.uuid4(), user, MagicMock())
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_require_pad_owner_accepts_owner(sample_token_data, monkeypatch):
    pad = MagicMock(spec=Pad)
    pad.can_access = MagicMock(return_value=True)
    pad.owner_id = uuid.UUID(sample_token_data["sub"])

    async def _get_pad(*args, **kwargs):
        return pad

    monkeypatch.setattr(Pad, "get_by_id", _get_pad)
    user = MagicMock()
    user.id = uuid.UUID(sample_token_data["sub"])

    result = await require_pad_owner(uuid.UUID(sample_token_data["sub"]), user, MagicMock())
    assert result == (pad, user)


def test_pad_access_defaults_are_distinct_instances():
    assert isinstance(require_pad_access, PadAccess)
    assert require_pad_access.require_owner is False
    assert require_pad_owner.require_owner is True


# ---------------------------------------------------------------------------
# get_verified_user branches
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_verified_user_refresh_failure(fakeredis_client, monkeypatch):
    domain = MagicMock()
    domain.get = AsyncMock(return_value={"access_token": "token"})
    domain.is_token_expired = MagicMock(return_value=True)
    domain.refresh_token_with_lock = AsyncMock(return_value=(False, None))
    monkeypatch.setattr(dependencies, "get_session_domain", AsyncMock(return_value=domain))

    request = _request_with_cookie("session_id", "session-1")
    status, user = await get_verified_user(request)

    assert status == "unauthenticated"
    assert user is None


@pytest.mark.asyncio
async def test_get_verified_user_invalid_token(fakeredis_client, monkeypatch):
    domain = MagicMock()
    domain.get = AsyncMock(return_value={"access_token": "token"})
    domain.is_token_expired = MagicMock(return_value=False)
    monkeypatch.setattr(dependencies, "get_session_domain", AsyncMock(return_value=domain))

    with patch("dependencies.UserSession", side_effect=ValueError("bad token")):
        request = _request_with_cookie("session_id", "session-1")
        status, user = await get_verified_user(request)

    assert status == "unauthenticated"
    assert user is None
