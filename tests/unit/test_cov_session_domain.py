"""Unit tests for the Session domain model."""

import json
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import jwt

import cache.redis_client as redis_client_module
from domain.session import Session, OIDC_STATE_TTL


@pytest.fixture(autouse=True)
def reset_redis_singleton(fakeredis_client, monkeypatch):
    """Replace the Redis singleton with a fakeredis client for every test."""
    redis_client_module.RedisClient._client = fakeredis_client
    redis_client_module.RedisClient._instance = None
    yield
    redis_client_module.RedisClient._client = None
    redis_client_module.RedisClient._instance = None


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
def sample_token_data():
    return {
        "access_token": "access",
        "refresh_token": "refresh",
        "refresh_expires_in": 3600,
    }


# ---------------------------------------------------------------------------
# Basic CRUD
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_session_get_set_delete(session, sample_token_data):
    session_id = "s1"
    assert await session.get(session_id) is None

    success = await session.set(session_id, sample_token_data, 3600)
    assert success is True

    data = await session.get(session_id)
    assert data == sample_token_data

    assert await session.delete(session_id) is True
    assert await session.get(session_id) is None


@pytest.mark.asyncio
async def test_session_get_handles_corrupt_data(session, fakeredis_client):
    await fakeredis_client.set("session:bad", "not-json")
    assert await session.get("bad") is None


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def test_session_url_helpers(session):
    assert session._server_url() == "https://auth.pad.test"
    assert session._internal_url() == "http://keycloak:8080"
    assert session.get_issuer() == "https://auth.pad.test/realms/pad"
    assert "client_id=pad" in session.get_auth_url()
    assert "response_type=code" in session.get_auth_url()
    assert session.get_token_url() == "http://keycloak:8080/realms/pad/protocol/openid-connect/token"


def test_session_internal_url_fallback(fakeredis_client):
    s = Session(fakeredis_client, {
        "server_url": "https://auth.pad.test",
        "realm": "pad",
        "client_id": "pad",
        "client_secret": "secret",
        "redirect_uri": "https://pad.pad.test/api/auth/callback",
    })
    assert s._internal_url() == "https://auth.pad.test"


# ---------------------------------------------------------------------------
# Token expiration
# ---------------------------------------------------------------------------

def test_is_token_expired_missing_token(session):
    assert session.is_token_expired({}) is True
    assert session.is_token_expired(None) is True


def test_is_token_expired_valid_token(session, monkeypatch):
    future_exp = int(time.time()) + 3600

    def _decode(*args, **kwargs):
        return {"exp": future_exp}

    monkeypatch.setattr(jwt, "decode", _decode)
    monkeypatch.setattr(session, "_get_jwks_client", lambda: MagicMock())

    assert session.is_token_expired({"access_token": "tok"}, buffer_seconds=30) is False


def test_is_token_expired_already_expired(session, monkeypatch):
    past_exp = int(time.time()) - 10

    def _decode(*args, **kwargs):
        return {"exp": past_exp}

    monkeypatch.setattr(jwt, "decode", _decode)
    monkeypatch.setattr(session, "_get_jwks_client", lambda: MagicMock())

    assert session.is_token_expired({"access_token": "tok"}) is True


def test_is_token_expired_decode_error(session, monkeypatch):
    monkeypatch.setattr(jwt, "decode", MagicMock(side_effect=Exception("boom")))
    monkeypatch.setattr(session, "_get_jwks_client", lambda: MagicMock())
    assert session.is_token_expired({"access_token": "tok"}) is True


# ---------------------------------------------------------------------------
# Refresh lock
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refresh_lock_acquire_and_release(session):
    assert await session.acquire_refresh_lock("lock1") is True
    assert await session.release_refresh_lock("lock1") is None


# ---------------------------------------------------------------------------
# Refresh token
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refresh_token_success(session, sample_token_data, monkeypatch):
    monkeypatch.setattr(session, "_get_jwks_client", lambda: MagicMock())

    async def _mock_post(*args, **kwargs):
        class Resp:
            status_code = 200
            def json(self):
                return {
                    "access_token": "new",
                    "refresh_token": "new-refresh",
                    "refresh_expires_in": 7200,
                }
        return Resp()

    with patch("httpx.AsyncClient.post", _mock_post):
        success, data = await session.refresh_token("s1", sample_token_data)

    assert success is True
    assert data["access_token"] == "new"
    stored = await session.get("s1")
    assert stored["access_token"] == "new"


@pytest.mark.asyncio
async def test_refresh_token_failure_status(session, sample_token_data, monkeypatch):
    monkeypatch.setattr(session, "_get_jwks_client", lambda: MagicMock())

    async def _mock_post(*args, **kwargs):
        class Resp:
            status_code = 400
            text = "bad request"
            def json(self):
                return {}
        return Resp()

    with patch("httpx.AsyncClient.post", _mock_post):
        success, data = await session.refresh_token("s1", sample_token_data)

    assert success is False


@pytest.mark.asyncio
async def test_refresh_token_no_refresh_token(session):
    success, data = await session.refresh_token("s1", {})
    assert success is False


# ---------------------------------------------------------------------------
# Refresh with lock
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refresh_token_with_lock_wins_lock(session, sample_token_data, monkeypatch):
    monkeypatch.setattr(session, "_get_jwks_client", lambda: MagicMock())
    monkeypatch.setattr(session, "is_token_expired", lambda data: True)

    async def _mock_post(*args, **kwargs):
        class Resp:
            status_code = 200
            def json(self):
                return {
                    "access_token": "new",
                    "refresh_token": "new-refresh",
                    "refresh_expires_in": 7200,
                }
        return Resp()

    with patch("httpx.AsyncClient.post", _mock_post):
        success, data = await session.refresh_token_with_lock("s1", sample_token_data)

    assert success is True
    assert data["access_token"] == "new"


@pytest.mark.asyncio
async def test_refresh_token_with_lock_already_fresh(session, sample_token_data, monkeypatch):
    await session.set("s1", sample_token_data, 3600)
    monkeypatch.setattr(session, "is_token_expired", lambda data: False)
    success, data = await session.refresh_token_with_lock("s1", sample_token_data)
    # Lock is acquired, current data is not expired in this path -> returns current.
    assert success is True
    assert data == sample_token_data


@pytest.mark.asyncio
async def test_refresh_token_with_lock_no_refresh_token(session):
    success, data = await session.refresh_token_with_lock("s1", {})
    assert success is False


# ---------------------------------------------------------------------------
# JWKS client
# ---------------------------------------------------------------------------

def test_get_jwks_client_caches(session):
    client1 = session._get_jwks_client()
    client2 = session._get_jwks_client()
    assert client1 is client2


# ---------------------------------------------------------------------------
# Event tracking
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_track_event_appends_event(session, sample_token_data):
    await session.set("s1", sample_token_data, 3600)
    assert await session.track_event("s1", "login", {"ip": "127.0.0.1"}) is True

    data = await session.get("s1")
    events = data.get("events", [])
    assert len(events) == 1
    assert events[0]["type"] == "login"
    assert events[0]["metadata"]["ip"] == "127.0.0.1"


@pytest.mark.asyncio
async def test_track_event_missing_session(session):
    assert await session.track_event("missing", "login") is False
