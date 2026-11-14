"""Unit tests for the pad router CRUD and authorization paths."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import cache.redis_client as redis_client_module
import database.database as db_module
from dependencies import UserSession
from domain.session import Session
from routers import pad_router


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
def pad_client(patched_user_session, fakeredis_client, monkeypatch):
    """TestClient for pad_router with mocked database session and a valid session cookie."""
    app = FastAPI()
    app.include_router(pad_router.pad_router, prefix="/api/pad")

    mock_session = AsyncMock()
    async def _get_session():
        return mock_session
    monkeypatch.setattr(db_module, "get_session", _get_session)
    monkeypatch.setattr(db_module, "async_session", MagicMock())

    # Seed a valid session in fakeredis so require_auth succeeds.
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
def mock_pad(monkeypatch, sample_token_data):
    from domain.pad import Pad
    from domain.user import User
    pad = MagicMock(spec=Pad)
    pad.id = uuid.uuid4()
    pad.owner_id = uuid.UUID(sample_token_data["sub"])
    pad.data = {"elements": [], "files": {}, "appState": {sample_token_data["sub"]: {}}}
    pad.can_access = MagicMock(return_value=True)
    pad.to_dict.return_value = {
        "id": str(pad.id),
        "display_name": "Test pad",
        "owner_id": str(pad.owner_id),
        "sharing_policy": "private",
        "data": pad.data,
    }
    async def _get_by_id(session, pad_id):
        return pad
    monkeypatch.setattr(Pad, "get_by_id", _get_by_id)

    user_obj = MagicMock(spec=User)
    user_obj.set_last_selected_pad = AsyncMock(return_value=None)
    async def _user_get_by_id(session, user_id):
        return user_obj
    monkeypatch.setattr(User, "get_by_id", _user_get_by_id)
    return pad


def _auth_header():
    return {"Cookie": "session_id=valid-session"}


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def test_create_new_pad(pad_client, mock_pad, monkeypatch):
    client, session = pad_client
    from domain.pad import Pad
    async def _create(*, session, owner_id, display_name):
        mock_pad.owner_id = owner_id
        return mock_pad
    monkeypatch.setattr(Pad, "create", _create)

    response = client.post("/api/pad/new", headers=_auth_header())
    assert response.status_code == 200
    assert response.json()["display_name"] == "Test pad"


def test_create_new_pad_error(pad_client, monkeypatch):
    client, session = pad_client
    from domain.pad import Pad
    async def _create(*, session, owner_id, display_name):
        raise Exception("db error")
    monkeypatch.setattr(Pad, "create", _create)

    response = client.post("/api/pad/new", headers=_auth_header())
    assert response.status_code == 500


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def test_get_pad(pad_client, mock_pad):
    client, session = pad_client
    response = client.get(f"/api/pad/{mock_pad.id}", headers=_auth_header())
    assert response.status_code == 200


def test_get_pad_not_found(pad_client, monkeypatch):
    client, session = pad_client
    from domain.pad import Pad
    async def _get_by_id(session, pad_id):
        return None
    monkeypatch.setattr(Pad, "get_by_id", _get_by_id)
    response = client.get(f"/api/pad/{uuid.uuid4()}", headers=_auth_header())
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Update data
# ---------------------------------------------------------------------------

def test_update_pad_data(pad_client, mock_pad):
    client, session = pad_client
    response = client.put(
        f"/api/pad/{mock_pad.id}/data",
        json={"elements": [{"id": "e1"}], "files": {}},
        headers=_auth_header(),
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_update_pad_data_error(pad_client, mock_pad):
    client, session = pad_client
    mock_pad.save.side_effect = Exception("db error")
    response = client.put(
        f"/api/pad/{mock_pad.id}/data",
        json={"elements": []},
        headers=_auth_header(),
    )
    assert response.status_code == 500


# ---------------------------------------------------------------------------
# Rename
# ---------------------------------------------------------------------------

def test_rename_pad(pad_client, mock_pad):
    client, session = pad_client
    response = client.put(
        f"/api/pad/{mock_pad.id}/rename",
        json={"display_name": "Renamed"},
        headers=_auth_header(),
    )
    assert response.status_code == 200


def test_rename_pad_not_owner(pad_client, mock_pad, monkeypatch):
    client, session = pad_client
    mock_pad.can_access.return_value = True
    mock_pad.owner_id = uuid.uuid4()  # Different from user
    response = client.put(
        f"/api/pad/{mock_pad.id}/rename",
        json={"display_name": "Renamed"},
        headers=_auth_header(),
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def test_delete_pad(pad_client, mock_pad):
    client, session = pad_client
    mock_pad.delete.return_value = True
    response = client.delete(f"/api/pad/{mock_pad.id}", headers=_auth_header())
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_delete_pad_failure(pad_client, mock_pad):
    client, session = pad_client
    mock_pad.delete.return_value = False
    response = client.delete(f"/api/pad/{mock_pad.id}", headers=_auth_header())
    assert response.status_code == 500


# ---------------------------------------------------------------------------
# Sharing
# ---------------------------------------------------------------------------

def test_update_sharing_policy(pad_client, mock_pad):
    client, session = pad_client
    response = client.put(
        f"/api/pad/{mock_pad.id}/sharing",
        json={"policy": "public"},
        headers=_auth_header(),
    )
    assert response.status_code == 200


def test_update_sharing_policy_invalid(pad_client, mock_pad):
    client, session = pad_client
    mock_pad.set_sharing_policy.side_effect = ValueError("invalid policy")
    response = client.put(
        f"/api/pad/{mock_pad.id}/sharing",
        json={"policy": "nope"},
        headers=_auth_header(),
    )
    assert response.status_code == 400


def test_add_to_whitelist(pad_client, mock_pad):
    client, session = pad_client
    response = client.post(
        f"/api/pad/{mock_pad.id}/whitelist",
        json={"user_id": str(uuid.uuid4())},
        headers=_auth_header(),
    )
    assert response.status_code == 200


def test_remove_from_whitelist(pad_client, mock_pad):
    client, session = pad_client
    response = client.delete(
        f"/api/pad/{mock_pad.id}/whitelist/{uuid.uuid4()}",
        headers=_auth_header(),
    )
    assert response.status_code == 200
