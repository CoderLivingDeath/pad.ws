"""Unit tests for the authentication router."""

import json
import secrets
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

import cache.redis_client as redis_client_module
import routers.auth_router as auth_router_module
from dependencies import UserSession
from domain.session import Session


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
        "exp": time.time() + 3600,
    }


@pytest.fixture
def patched_user_session(monkeypatch, sample_token_data):
    """Patch UserSession so it accepts any token and returns sample data."""
    original_init = UserSession.__init__
    original_is_expired = Session.is_token_expired

    def _init(self, access_token, token_data, session_domain, user_id=None):
        self.access_token = access_token
        self._user_data = None
        self._session_domain = session_domain
        self.token_data = sample_token_data

    monkeypatch.setattr(UserSession, "__init__", _init)
    monkeypatch.setattr(Session, "is_token_expired", lambda self, data: False)
    yield
    monkeypatch.setattr(UserSession, "__init__", original_init)
    monkeypatch.setattr(Session, "is_token_expired", original_is_expired)


@pytest.fixture
def session(fakeredis_client):
    return Session(fakeredis_client, {
        "server_url": "https://auth.pad.test",
        "internal_url": "http://keycloak:8080",
        "realm": "pad",
        "client_id": "pad",
        "client_secret": "secret",
        "redirect_uri": "https://pad.pad.test/api/auth/callback",
    })


@pytest.fixture
def coder_mock(monkeypatch):
    """Provide a configurable CoderAPI mock by patching the class methods."""
    import coder as coder_module
    monkeypatch.setattr(coder_module.CoderAPI, "__init__", lambda self, *args, **kwargs: None)
    monkeypatch.setattr(coder_module.CoderAPI, "ensure_user_exists", lambda self, info: ({"username": "user"}, False))
    monkeypatch.setattr(coder_module.CoderAPI, "ensure_workspace_exists", lambda self, username: None)
    return coder_module.CoderAPI


@pytest.fixture
def client(patched_user_session, coder_mock):
    """Build a TestClient for auth_router only."""
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(auth_router_module.auth_router, prefix="/api/auth")
    return TestClient(app)


def _set_cookie(request: Request, name: str, value: str) -> None:
    request.scope["headers"] = [(b"cookie", f"{name}={value}".encode("latin-1"))]
    request.scope.pop("cookies", None)


# ---------------------------------------------------------------------------
# /login
# ---------------------------------------------------------------------------

def test_login_redirect(client, monkeypatch):
    monkeypatch.setattr(auth_router_module, "FRONTEND_URL", "https://pad.pad.test")
    response = client.get("/api/auth/login?rd=/pad/123", follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["location"]
    assert "auth.pad.test" in location
    assert "state=" in location
    # OIDC state cookie scoped to /api/auth.
    assert "oidc_state=" in response.headers.get("set-cookie", "")


def test_login_rejects_malicious_redirect(client, monkeypatch):
    monkeypatch.setattr(auth_router_module, "FRONTEND_URL", "https://pad.pad.test")
    response = client.get("/api/auth/login?rd=https://evil.test", follow_redirects=False)
    location = response.headers["location"]
    # After login the destination should be the safe root, not evil.test.
    assert "https%3A//evil.test" not in location


# ---------------------------------------------------------------------------
# /callback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_callback_rejects_missing_state(session, monkeypatch):
    request = Request(scope={"type": "http", "method": "GET", "headers": [], "path": "/"})
    with pytest.raises(Exception):
        await auth_router_module.callback(request, code="code")


def test_callback_rejects_replayed_state(client, session):
    state = "replay-state"
    import asyncio
    asyncio.run(session.redis_client.setex(f"oidc_state:{state}", 600, json.dumps({"mode": "default", "rd": "/"})))
    asyncio.run(session.redis_client.delete(f"oidc_state:{state}"))

    response = client.get(
        f"/api/auth/callback?code=abc&state={state}",
        headers={"Cookie": f"oidc_state={state}"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_callback_success(client, session, coder_mock, sample_token_data, patched_user_session, monkeypatch):
    state = "valid-state"
    await session.redis_client.setex(f"oidc_state:{state}", 600, json.dumps({"mode": "default", "rd": "/pad/123"}))

    monkeypatch.setattr(auth_router_module, "is_user_provisioned", lambda data: True)

    async def _mock_post(*args, **kwargs):
        class Resp:
            status_code = 200
            def json(self):
                return {
                    "access_token": "access",
                    "refresh_token": "refresh",
                    "id_token": "id",
                    "refresh_expires_in": 3600,
                }
        return Resp()

    from domain.session import Session as SessionCls
    from domain.user import User
    monkeypatch.setattr(SessionCls, "_get_jwks_client", lambda self: MagicMock(get_signing_key_from_jwt=lambda token: MagicMock(key="key")))
    monkeypatch.setattr(auth_router_module.jwt, "decode", lambda token, key, **kwargs: sample_token_data)
    async def _ensure_exists(cls, session, user_info):
        return None
    monkeypatch.setattr(User, "ensure_exists", classmethod(_ensure_exists))

    with patch("httpx.AsyncClient.post", _mock_post):
        response = client.get(
            f"/api/auth/callback?code=abc&state={state}",
            headers={"Cookie": f"oidc_state={state}"},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert response.headers["location"] == "/pad/123"
    assert "session_id=" in response.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_callback_unprovisioned_user(client, session, coder_mock, sample_token_data, patched_user_session, monkeypatch):
    state = "unprovisioned-state"
    await session.redis_client.setex(f"oidc_state:{state}", 600, json.dumps({"mode": "default", "rd": "/"}))

    monkeypatch.setattr(auth_router_module, "is_user_provisioned", lambda data: False)

    async def _mock_post(*args, **kwargs):
        class Resp:
            status_code = 200
            def json(self):
                return {
                    "access_token": "access",
                    "refresh_token": "refresh",
                    "refresh_expires_in": 3600,
                }
        return Resp()

    from domain.session import Session as SessionCls
    monkeypatch.setattr(SessionCls, "_get_jwks_client", lambda self: MagicMock(get_signing_key_from_jwt=lambda token: MagicMock(key="key")))

    with patch("httpx.AsyncClient.post", _mock_post), patch.object(jwt, "decode", return_value=sample_token_data):
        response = client.get(
            f"/api/auth/callback?code=abc&state={state}",
            headers={"Cookie": f"oidc_state={state}"},
        )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# /verify
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_verify_api_unauthenticated_returns_401(client):
    response = client.get("/api/auth/verify", headers={"Accept": "application/json"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_verify_navigation_redirects_to_login(client, monkeypatch):
    monkeypatch.setattr(auth_router_module, "FRONTEND_URL", "https://pad.pad.test")
    response = client.get(
        "/api/auth/verify",
        headers={
            "Accept": "text/html",
            "X-Original-Host": "pad.pad.test",
            "X-Original-URI": "/pad/123",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/api/auth/login" in response.headers["location"]


@pytest.mark.asyncio
async def test_verify_authenticated_returns_identity_headers(
    client, session, patched_user_session, monkeypatch
):
    session_id = "verify-session"
    await session.set(session_id, {"access_token": "access", "refresh_token": "refresh", "refresh_expires_in": 3600}, 3600)

    response = client.get(
        "/api/auth/verify",
        headers={"Cookie": f"session_id={session_id}", "Accept": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    assert "X-Pad-User" in response.headers


# ---------------------------------------------------------------------------
# /logout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_logout_clears_session_and_returns_end_session_url(client, session, patched_user_session, monkeypatch):
    session_id = "logout-session"
    await session.set(session_id, {"access_token": "access", "id_token": "id", "refresh_expires_in": 3600}, 3600)
    monkeypatch.setattr(auth_router_module, "FRONTEND_URL", "https://pad.pad.test")
    monkeypatch.setattr(auth_router_module, "CODER_DOMAIN", "coder.pad.test")

    response = client.get("/api/auth/logout", headers={"Cookie": f"session_id={session_id}"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "logout" in data["logout_url"]
    assert "coder_logout_url" in data

    # Session is deleted server-side.
    assert await session.get(session_id) is None


# ---------------------------------------------------------------------------
# /status
# ---------------------------------------------------------------------------

def test_status_unauthenticated(client):
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    assert response.json()["authenticated"] is False


def test_status_authenticated(client, session, patched_user_session):
    session_id = "status-session"
    # Use asyncio.run because the fixture is sync.
    import asyncio
    asyncio.run(session.set(session_id, {"access_token": "access", "refresh_expires_in": 3600}, 3600))
    response = client.get("/api/auth/status", headers={"Cookie": f"session_id={session_id}"})
    assert response.status_code == 200
    assert response.json()["authenticated"] is True


# ---------------------------------------------------------------------------
# /refresh
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refresh_no_cookie(client):
    response = client.post("/api/auth/refresh")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_success(client, session, patched_user_session, monkeypatch):
    from domain.session import Session as SessionCls
    session_id = "refresh-session"
    await session.set(session_id, {"access_token": "access", "refresh_token": "refresh", "refresh_expires_in": 3600}, 3600)
    monkeypatch.setattr(SessionCls, "refresh_token_with_lock", AsyncMock(return_value=(True, {"expires_in": 3600})))

    response = client.post("/api/auth/refresh", headers={"Cookie": f"session_id={session_id}"})
    assert response.status_code == 200
    assert response.json()["expires_in"] == 3600


@pytest.mark.asyncio
async def test_refresh_failure(client, session, patched_user_session, monkeypatch):
    from domain.session import Session as SessionCls
    session_id = "refresh-fail-session"
    await session.set(session_id, {"access_token": "access", "refresh_token": "refresh", "refresh_expires_in": 3600}, 3600)
    monkeypatch.setattr(SessionCls, "refresh_token_with_lock", AsyncMock(return_value=(False, {})))

    response = client.post("/api/auth/refresh", headers={"Cookie": f"session_id={session_id}"})
    assert response.status_code == 401
