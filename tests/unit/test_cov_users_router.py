"""Unit tests for the users router."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import cache.redis_client as redis_client_module
import database.database as db_module
from dependencies import UserSession
from domain.session import Session
from routers import users_router


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
    }


@pytest.fixture
def patched_user_session(monkeypatch, sample_token_data):
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
def users_client(patched_user_session, fakeredis_client, monkeypatch):
    app = FastAPI()
    app.include_router(users_router.users_router, prefix="/api/users")

    mock_session = AsyncMock()
    async def _get_session():
        return mock_session
    monkeypatch.setattr(db_module, "get_session", _get_session)

    from domain.session import Session
    session_domain = Session(fakeredis_client, {
        "server_url": "https://auth.pad.test",
        "internal_url": "http://keycloak:8080",
        "realm": "pad",
        "client_id": "pad",
        "client_secret": "secret",
        "redirect_uri": "https://pad.pad.test/api/auth/callback",
    })
    import asyncio
    asyncio.run(session_domain.set("valid-session", {"access_token": "access", "refresh_token": "refresh", "refresh_expires_in": 3600}, 3600))

    return TestClient(app), mock_session


@pytest.fixture
def mock_user(monkeypatch, sample_token_data):
    from domain.user import User
    user = MagicMock(spec=User)
    user.id = uuid.UUID(sample_token_data["sub"])
    user.last_selected_pad = None
    user._store = MagicMock()
    user._store.open_pads = []
    user.save = AsyncMock(return_value=None)
    user.set_last_selected_pad = AsyncMock(return_value=None)
    user.remove_open_pad = AsyncMock(return_value=None)

    async def _get_by_id(session, user_id):
        return user
    monkeypatch.setattr(User, "get_by_id", _get_by_id)
    monkeypatch.setattr(User, "get_open_pads", AsyncMock(return_value=[]))
    return user


def _auth_header():
    return {"Cookie": "session_id=valid-session"}


# ---------------------------------------------------------------------------
# /me
# ---------------------------------------------------------------------------

def test_get_user_info(users_client, mock_user, monkeypatch):
    client, session = users_client
    response = client.get("/api/users/me", headers=_auth_header())
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "user@pad.test"
    assert "pads" in data


def test_get_user_info_with_pending_pad(users_client, mock_user, monkeypatch):
    client, session = users_client
    from domain.pad import Pad
    pad_id = uuid.uuid4()
    pad = MagicMock(spec=Pad)
    pad.id = pad_id
    pad.can_access = MagicMock(return_value=True)
    async def _get_by_id(session, pid):
        return pad
    monkeypatch.setattr(Pad, "get_by_id", _get_by_id)

    response = client.get(f"/api/users/me", headers={"Cookie": f"session_id=valid-session; pending_pad_id={pad_id}"})
    assert response.status_code == 200


def test_get_user_info_posthog(users_client, mock_user, monkeypatch):
    client, session = users_client
    mock_posthog = MagicMock()
    monkeypatch.setattr(users_router, "posthog", mock_posthog)
    import os
    monkeypatch.setattr(os, "getenv", lambda key, default=None: "test-key" if key == "VITE_PUBLIC_POSTHOG_KEY" else default)
    response = client.get("/api/users/me", headers=_auth_header())
    assert response.status_code == 200
    mock_posthog.identify.assert_called_once()


# ---------------------------------------------------------------------------
# /online (admin only)
# ---------------------------------------------------------------------------

def test_online_users_requires_admin(users_client, monkeypatch):
    client, session = users_client
    response = client.get("/api/users/online", headers=_auth_header())
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# /close/{pad_id}
# ---------------------------------------------------------------------------

def test_close_pad(users_client, mock_user):
    client, session = users_client
    pad_id = uuid.uuid4()
    response = client.delete(f"/api/users/close/{pad_id}", headers=_auth_header())
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_close_pad_user_not_found(users_client, monkeypatch):
    client, session = users_client
    from domain.user import User
    async def _get_by_id(session, user_id):
        return None
    monkeypatch.setattr(User, "get_by_id", _get_by_id)
    response = client.delete(f"/api/users/close/{uuid.uuid4()}", headers=_auth_header())
    assert response.status_code == 404
