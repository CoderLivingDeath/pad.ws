"""Unit tests for the workspace router and Coder API error mapping."""

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import cache.redis_client as redis_client_module
import coder as coder_module
import database.database as db_module
from dependencies import UserSession
from domain.session import Session
from routers import workspace_router


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
def workspace_client(patched_user_session, fakeredis_client, monkeypatch):
    app = FastAPI()
    app.include_router(workspace_router.workspace_router, prefix="/api/workspace")

    # Seed session
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

    return TestClient(app)


@pytest.fixture
def mock_coder_api(monkeypatch):
    """Patch CoderAPI class methods so get_coder_api returns a usable mock."""
    monkeypatch.setattr(coder_module.CoderAPI, "__init__", lambda self, *args, **kwargs: None)
    monkeypatch.setattr(coder_module.CoderAPI, "get_user_by_email", lambda self, email: {"username": "user", "email": email})
    monkeypatch.setattr(coder_module.CoderAPI, "get_workspace_status_for_user", lambda self, username: None)
    monkeypatch.setattr(coder_module.CoderAPI, "start_workspace", lambda self, ws_id: {"id": "build-1"})
    monkeypatch.setattr(coder_module.CoderAPI, "stop_workspace", lambda self, ws_id: {"id": "build-2"})
    return coder_module.CoderAPI


def _auth_header():
    return {"Cookie": "session_id=valid-session"}


# ---------------------------------------------------------------------------
# /state
# ---------------------------------------------------------------------------

def test_get_workspace_state_no_workspace(workspace_client, mock_coder_api):
    response = workspace_client.get("/api/workspace/state", headers=_auth_header())
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "stopped"


def test_get_workspace_state_running(workspace_client, mock_coder_api, monkeypatch):
    monkeypatch.setattr(coder_module.CoderAPI, "get_workspace_status_for_user", lambda self, username: {
        "id": "ws-1",
        "latest_build": {"status": "running", "workspace_name": "ubuntu"},
    })
    response = workspace_client.get("/api/workspace/state", headers=_auth_header())
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "running"
    assert data["id"] == "ws-1"


def test_get_workspace_state_coder_unavailable(workspace_client, mock_coder_api, monkeypatch):
    def _raise(*args, **kwargs):
        raise Exception("connection refused")
    monkeypatch.setattr(coder_module.CoderAPI, "get_user_by_email", _raise)
    response = workspace_client.get("/api/workspace/state", headers=_auth_header())
    assert response.status_code == 503


def test_get_workspace_state_user_not_found(workspace_client, mock_coder_api, monkeypatch):
    monkeypatch.setattr(coder_module.CoderAPI, "get_user_by_email", lambda self, email: None)
    response = workspace_client.get("/api/workspace/state", headers=_auth_header())
    assert response.status_code == 404


def test_get_workspace_state_missing_username(workspace_client, mock_coder_api, monkeypatch):
    monkeypatch.setattr(coder_module.CoderAPI, "get_user_by_email", lambda self, email: {"email": email})
    response = workspace_client.get("/api/workspace/state", headers=_auth_header())
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------

def test_start_workspace(workspace_client, mock_coder_api, monkeypatch):
    monkeypatch.setattr(coder_module.CoderAPI, "get_workspace_status_for_user", lambda self, username: {
        "id": "ws-1",
        "latest_build": {"status": "stopped", "workspace_name": "ubuntu"},
    })
    response = workspace_client.post("/api/workspace/start", headers=_auth_header())
    assert response.status_code == 200


def test_start_workspace_no_provision(workspace_client, mock_coder_api, monkeypatch):
    monkeypatch.setattr(coder_module.CoderAPI, "get_workspace_status_for_user", lambda self, username: None)
    response = workspace_client.post("/api/workspace/start", headers=_auth_header())
    assert response.status_code == 409


def test_start_workspace_error(workspace_client, mock_coder_api, monkeypatch):
    monkeypatch.setattr(coder_module.CoderAPI, "get_workspace_status_for_user", lambda self, username: {
        "id": "ws-1",
        "latest_build": {"status": "stopped", "workspace_name": "ubuntu"},
    })
    monkeypatch.setattr(coder_module.CoderAPI, "start_workspace", lambda self, ws_id: (_ for _ in ()).throw(Exception("boom")))
    response = workspace_client.post("/api/workspace/start", headers=_auth_header())
    assert response.status_code == 503


# ---------------------------------------------------------------------------
# /stop
# ---------------------------------------------------------------------------

def test_stop_workspace(workspace_client, mock_coder_api, monkeypatch):
    monkeypatch.setattr(coder_module.CoderAPI, "get_workspace_status_for_user", lambda self, username: {
        "id": "ws-1",
        "latest_build": {"status": "running", "workspace_name": "ubuntu"},
    })
    response = workspace_client.post("/api/workspace/stop", headers=_auth_header())
    assert response.status_code == 200


def test_stop_workspace_no_provision(workspace_client, mock_coder_api, monkeypatch):
    monkeypatch.setattr(coder_module.CoderAPI, "get_workspace_status_for_user", lambda self, username: None)
    response = workspace_client.post("/api/workspace/stop", headers=_auth_header())
    assert response.status_code == 409
