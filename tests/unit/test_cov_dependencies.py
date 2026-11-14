"""Unit tests for authentication dependencies, verify helpers and pad access."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request

import dependencies
import cache.redis_client as redis_client_module
from dependencies import (
    AuthDependency,
    UserSession,
    get_identity_headers,
    get_verified_user,
    optional_auth,
    require_admin,
    require_auth,
    require_pad_access,
    require_pad_owner,
)
from domain.pad import Pad
from domain.session import Session


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_redis_singleton(fakeredis_client, monkeypatch):
    """Replace the Redis singleton with a fakeredis client for every test."""
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
def signed_jwt():
    """Return a token string that UserSession will accept after patching decode."""
    return "header.payload.signature"


@pytest.fixture
def patched_user_session(monkeypatch, sample_token_data):
    """Patch UserSession so it accepts any token and returns sample data."""
    original_init = UserSession.__init__
    original_is_expired = Session.is_token_expired

    def _init(self, access_token, token_data, session_domain, user_id=None):
        self.access_token = access_token
        self._user_data = None
        self._session_domain = session_domain
        # Always use the synthetic token data so property assertions work.
        self.token_data = sample_token_data

    monkeypatch.setattr(UserSession, "__init__", _init)
    monkeypatch.setattr(Session, "is_token_expired", lambda self, data: False)
    yield
    monkeypatch.setattr(UserSession, "__init__", original_init)
    monkeypatch.setattr(Session, "is_token_expired", original_is_expired)


@pytest.fixture
def fake_session_domain(fakeredis_client):
    return Session(fakeredis_client, {
        "server_url": "https://auth.pad.test",
        "internal_url": "http://keycloak:8080",
        "realm": "pad",
        "client_id": "pad",
        "client_secret": "secret",
        "redirect_uri": "https://pad.pad.test/api/auth/callback",
    })


@pytest.fixture
def auth_request():
    return Request(scope={
        "type": "http",
        "method": "GET",
        "headers": [],
        "path": "/",
    })


def _set_cookie(request: Request, name: str, value: str) -> None:
    """Set a cookie on a Starlette Request via the Cookie header."""
    cookie_header = f"{name}={value}".encode("latin-1")
    request.scope["headers"] = [(b"cookie", cookie_header)]
    # Force re-parse on next access.
    request.scope.pop("cookies", None)


# ---------------------------------------------------------------------------
# AuthDependency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_require_auth_missing_session_returns_401(auth_request, monkeypatch):
    monkeypatch.setattr(dependencies, "SESSION_COOKIE_NAME", "session_id")
    auth = AuthDependency(auto_error=True)
    with pytest.raises(HTTPException) as exc_info:
        await auth(auth_request)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_require_auth_invalid_session_returns_401(auth_request, fake_session_domain, monkeypatch):
    monkeypatch.setattr(dependencies, "SESSION_COOKIE_NAME", "session_id")
    auth_request.scope["cookies"] = {"session_id": "no-such-session"}
    auth = AuthDependency(auto_error=True)
    with pytest.raises(HTTPException) as exc_info:
        await auth(auth_request)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_require_auth_valid_session(
    auth_request, fake_session_domain, signed_jwt, sample_token_data, patched_user_session, monkeypatch
):
    monkeypatch.setattr(dependencies, "SESSION_COOKIE_NAME", "session_id")
    session_id = "valid-session"
    _set_cookie(auth_request, "session_id", session_id)

    await fake_session_domain.set(session_id, {
        "access_token": signed_jwt,
        "refresh_token": "refresh",
        "refresh_expires_in": 3600,
    }, 3600)

    auth = AuthDependency(auto_error=True)
    result = await auth(auth_request)
    assert isinstance(result, UserSession)
    assert result.email == sample_token_data["email"]


@pytest.mark.asyncio
async def test_require_auth_expired_session_refresh_success(
    auth_request, fake_session_domain, signed_jwt, sample_token_data, patched_user_session, monkeypatch
):
    monkeypatch.setattr(dependencies, "SESSION_COOKIE_NAME", "session_id")
    session_id = "expired-session"
    _set_cookie(auth_request, "session_id", session_id)

    monkeypatch.setattr(fake_session_domain, "is_token_expired", lambda data: True)
    monkeypatch.setattr(
        fake_session_domain,
        "refresh_token_with_lock",
        AsyncMock(return_value=(True, {
            "access_token": "new-token",
            "refresh_token": "new-refresh",
            "refresh_expires_in": 3600,
        })),
    )

    await fake_session_domain.set(session_id, {
        "access_token": signed_jwt,
        "refresh_token": "refresh",
        "refresh_expires_in": 3600,
    }, 3600)

    auth = AuthDependency(auto_error=True)
    result = await auth(auth_request)
    assert isinstance(result, UserSession)


@pytest.mark.asyncio
async def test_require_auth_refresh_failure_returns_401(
    auth_request, fake_session_domain, signed_jwt, monkeypatch
):
    monkeypatch.setattr(dependencies, "SESSION_COOKIE_NAME", "session_id")
    session_id = "refresh-fail"
    _set_cookie(auth_request, "session_id", session_id)

    monkeypatch.setattr(fake_session_domain, "is_token_expired", lambda data: True)
    monkeypatch.setattr(
        fake_session_domain,
        "refresh_token_with_lock",
        AsyncMock(return_value=(False, {})),
    )

    await fake_session_domain.set(session_id, {
        "access_token": signed_jwt,
        "refresh_token": "refresh",
        "refresh_expires_in": 3600,
    }, 3600)

    auth = AuthDependency(auto_error=True)
    with pytest.raises(HTTPException) as exc_info:
        await auth(auth_request)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_require_admin_forbidden_for_non_admin(
    auth_request, fake_session_domain, signed_jwt, sample_token_data, patched_user_session, monkeypatch
):
    monkeypatch.setattr(dependencies, "SESSION_COOKIE_NAME", "session_id")
    session_id = "non-admin"
    _set_cookie(auth_request, "session_id", session_id)

    await fake_session_domain.set(session_id, {
        "access_token": signed_jwt,
        "refresh_token": "refresh",
        "refresh_expires_in": 3600,
    }, 3600)

    auth = AuthDependency(auto_error=True, require_admin=True)
    with pytest.raises(HTTPException) as exc_info:
        await auth(auth_request)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_optional_auth_missing_cookie_returns_none(auth_request, monkeypatch):
    monkeypatch.setattr(dependencies, "SESSION_COOKIE_NAME", "session_id")
    result = await optional_auth(auth_request)
    assert result is None


# ---------------------------------------------------------------------------
# get_verified_user
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_verified_user_unauthenticated_no_cookie(auth_request):
    status, user = await get_verified_user(auth_request)
    assert status == "unauthenticated"
    assert user is None


@pytest.mark.asyncio
async def test_get_verified_user_unprovisioned(
    auth_request, fake_session_domain, signed_jwt, sample_token_data, patched_user_session, monkeypatch
):
    monkeypatch.setattr(dependencies, "SESSION_COOKIE_NAME", "session_id")
    monkeypatch.setattr(dependencies, "PAD_ALLOWED_ROLES", ["pad-user"])
    session_id = "unprovisioned"
    _set_cookie(auth_request, "session_id", session_id)

    sample_token_data["realm_access"] = {"roles": ["other-role"]}
    await fake_session_domain.set(session_id, {
        "access_token": signed_jwt,
        "refresh_token": "refresh",
        "refresh_expires_in": 3600,
    }, 3600)

    status, user = await get_verified_user(auth_request)
    assert status == "forbidden"
    assert user is None


@pytest.mark.asyncio
async def test_get_verified_user_ok(
    auth_request, fake_session_domain, signed_jwt, sample_token_data, patched_user_session, monkeypatch
):
    monkeypatch.setattr(dependencies, "SESSION_COOKIE_NAME", "session_id")
    session_id = "verified"
    _set_cookie(auth_request, "session_id", session_id)

    await fake_session_domain.set(session_id, {
        "access_token": signed_jwt,
        "refresh_token": "refresh",
        "refresh_expires_in": 3600,
    }, 3600)

    status, user = await get_verified_user(auth_request)
    assert status == "ok"
    assert isinstance(user, UserSession)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_get_identity_headers():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.roles = ["pad-user", "admin"]
    user.is_admin = True
    headers = get_identity_headers(user)
    assert headers["X-Pad-User"] == str(user.id)
    assert headers["X-Pad-Roles"] == "pad-user,admin"
    assert headers["X-Pad-Admin"] == "true"
    assert headers["Cache-Control"] == "no-store"


# ---------------------------------------------------------------------------
# UserSession properties
# ---------------------------------------------------------------------------

def test_user_session_properties(sample_token_data, monkeypatch):
    original_init = UserSession.__init__
    monkeypatch.setattr(UserSession, "__init__", lambda self, *args, **kwargs: None)
    session = UserSession.__new__(UserSession)
    session.access_token = "token"
    session.token_data = sample_token_data
    session._session_domain = None

    assert session.is_authenticated is True
    assert str(session.id) == sample_token_data["sub"]
    assert session.email == sample_token_data["email"]
    assert session.username == sample_token_data["preferred_username"]
    assert session.name == sample_token_data["name"]
    assert session.roles == sample_token_data["realm_access"]["roles"]
    assert session.is_admin is False

    sample_token_data["realm_access"]["roles"].append("admin")
    assert session.is_admin is True
    monkeypatch.setattr(UserSession, "__init__", original_init)


# ---------------------------------------------------------------------------
# PadAccess
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_require_pad_access_allows_owner(sample_token_data, monkeypatch):
    pad = MagicMock(spec=Pad)
    pad.can_access = MagicMock(return_value=True)
    pad.owner_id = sample_token_data["sub"]

    async def _get_pad(*args, **kwargs):
        return pad

    monkeypatch.setattr(Pad, "get_by_id", _get_pad)

    user = MagicMock()
    user.id = uuid.UUID(sample_token_data["sub"])
    session = MagicMock()

    result = await require_pad_access(uuid.UUID(sample_token_data["sub"]), user, session)
    assert result == (pad, user)


@pytest.mark.asyncio
async def test_require_pad_owner_rejects_non_owner(sample_token_data, monkeypatch):
    pad = MagicMock(spec=Pad)
    pad.can_access = MagicMock(return_value=True)
    pad.owner_id = uuid.uuid4()

    async def _get_pad(*args, **kwargs):
        return pad

    monkeypatch.setattr(Pad, "get_by_id", _get_pad)

    user = MagicMock()
    user.id = uuid.UUID(sample_token_data["sub"])
    session = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await require_pad_owner(uuid.UUID(sample_token_data["sub"]), user, session)
    assert exc_info.value.status_code == 403
