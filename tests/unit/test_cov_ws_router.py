"""Unit tests for the WebSocket router and collaboration helpers."""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.testclient import TestClient

import cache.redis_client as redis_client_module
from dependencies import UserSession
from domain.session import Session
from routers import ws_router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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
def mock_user(sample_token_data):
    user = MagicMock(spec=UserSession)
    user.id = uuid.UUID(sample_token_data["sub"])
    user.username = sample_token_data["preferred_username"]
    user.token_data = sample_token_data
    return user


class _FakeWebSocket:
    """Minimal WebSocket double for isolated helper tests."""
    def __init__(self, connected=True):
        self.client_state = MagicMock()
        self.client_state.CONNECTED = connected
        self.headers = {}
        self.cookies = {}
        self.close = AsyncMock()
        self.send_text = AsyncMock()
        self.receive_text = AsyncMock()


# ---------------------------------------------------------------------------
# WebSocketMessage model
# ---------------------------------------------------------------------------

def test_websocket_message_serialization():
    msg = ws_router.WebSocketMessage(
        type="test",
        pad_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        user_id="user-1",
        data={"x": 1},
    )
    dumped = msg.model_dump_json()
    parsed = json.loads(dumped)
    assert parsed["type"] == "test"
    assert parsed["data"]["x"] == 1
    assert parsed["timestamp"].endswith("Z")


def test_websocket_message_timestamp_validator():
    raw = {
        "type": "test",
        "timestamp": "2024-01-01T00:00:00Z",
    }
    msg = ws_router.WebSocketMessage(**raw)
    assert msg.timestamp.year == 2024


# ---------------------------------------------------------------------------
# get_ws_user
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_ws_user_no_cookie():
    websocket = _FakeWebSocket()
    assert await ws_router.get_ws_user(websocket) is None


@pytest.mark.asyncio
async def test_get_ws_user_missing_session(fake_session_domain, monkeypatch):
    monkeypatch.setattr(ws_router, "get_session_domain", AsyncMock(return_value=fake_session_domain))
    websocket = _FakeWebSocket()
    websocket.cookies["session_id"] = "missing"
    assert await ws_router.get_ws_user(websocket) is None


@pytest.mark.asyncio
async def test_get_ws_user_expired_and_refresh_fails(fake_session_domain, monkeypatch):
    monkeypatch.setattr(ws_router, "get_session_domain", AsyncMock(return_value=fake_session_domain))
    monkeypatch.setattr(Session, "is_token_expired", lambda self, data: True)
    monkeypatch.setattr(fake_session_domain, "refresh_token_with_lock", AsyncMock(return_value=(False, None)))

    websocket = _FakeWebSocket()
    websocket.cookies["session_id"] = "expired"
    await fake_session_domain.set("expired", {"access_token": "x"}, 60)
    assert await ws_router.get_ws_user(websocket) is None


@pytest.mark.asyncio
async def test_get_ws_user_unprovisioned(fake_session_domain, monkeypatch, patched_user_session):
    monkeypatch.setattr(ws_router, "get_session_domain", AsyncMock(return_value=fake_session_domain))
    monkeypatch.setattr(ws_router, "is_user_provisioned", lambda data: False)

    websocket = _FakeWebSocket()
    websocket.cookies["session_id"] = "valid"
    await fake_session_domain.set("valid", {"access_token": "x"}, 60)
    assert await ws_router.get_ws_user(websocket) is None


@pytest.mark.asyncio
async def test_get_ws_user_success(fake_session_domain, monkeypatch, patched_user_session, sample_token_data):
    monkeypatch.setattr(ws_router, "get_session_domain", AsyncMock(return_value=fake_session_domain))
    monkeypatch.setattr(ws_router, "is_user_provisioned", lambda data: True)

    websocket = _FakeWebSocket()
    websocket.cookies["session_id"] = "valid"
    await fake_session_domain.set("valid", {"access_token": "x", "sub": sample_token_data["sub"]}, 60)
    user = await ws_router.get_ws_user(websocket)
    assert user is not None
    assert str(user.id) == sample_token_data["sub"]


# ---------------------------------------------------------------------------
# Publishing helpers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_publish_event_to_redis(fakeredis_client):
    msg = ws_router.WebSocketMessage(
        type="user_joined",
        pad_id=str(uuid.uuid4()),
        user_id="user-1",
        data={"username": "alice"},
    )
    await ws_router.publish_event_to_redis(fakeredis_client, "pad:stream:test", msg)
    streams = await fakeredis_client.xread({"pad:stream:test": "0"}, count=10)
    assert len(streams) == 1


@pytest.mark.asyncio
async def test_publish_pointer_update(fakeredis_client):
    pad_id = uuid.uuid4()
    msg = ws_router.WebSocketMessage(
        type="pointer_update",
        pad_id=str(pad_id),
        user_id="user-1",
        data={"x": 10, "y": 20},
    )
    pubsub = fakeredis_client.pubsub()
    await pubsub.subscribe(f"pad:pointer:updates:{pad_id}")
    await ws_router.publish_pointer_update(fakeredis_client, pad_id, msg)
    message = None
    for _ in range(20):
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
        if message:
            break
    assert message is not None
    await pubsub.unsubscribe()


# ---------------------------------------------------------------------------
# check_pad_access
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_pad_access_allowed(mock_user, monkeypatch):
    async def _access(*args, **kwargs):
        return (MagicMock(), None)
    monkeypatch.setattr(ws_router, "PadAccess", lambda: _access)
    allowed, reason = await ws_router.check_pad_access(uuid.uuid4(), mock_user, MagicMock())
    assert allowed is True
    assert reason is None


@pytest.mark.asyncio
async def test_check_pad_access_denied(mock_user, monkeypatch):
    async def _access(*args, **kwargs):
        raise HTTPException(status_code=403, detail="no access")
    monkeypatch.setattr(ws_router, "PadAccess", lambda: _access)
    allowed, reason = await ws_router.check_pad_access(uuid.uuid4(), mock_user, MagicMock())
    assert allowed is False
    assert reason == "no access"


# ---------------------------------------------------------------------------
# periodic_auth_check
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_periodic_auth_check_revokes_session(mock_user, monkeypatch, fakeredis_client):
    websocket = _FakeWebSocket(connected=True)

    async def _get_ws_user(ws):
        return None

    monkeypatch.setattr(ws_router, "get_ws_user", _get_ws_user)
    monkeypatch.setattr(ws_router, "_WS_SESSION_REVALIDATION_INTERVAL", 1)
    monkeypatch.setattr(ws_router, "check_pad_access", AsyncMock(return_value=(True, None)))
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    await ws_router.periodic_auth_check(
        websocket, uuid.uuid4(), mock_user, fakeredis_client, "pad:stream:test", "conn-1", MagicMock()
    )

    websocket.close.assert_awaited_once_with(code=4001, reason="Session expired or revoked")


@pytest.mark.asyncio
async def test_periodic_auth_check_loses_pad_access(mock_user, monkeypatch, fakeredis_client):
    websocket = _FakeWebSocket(connected=True)

    async def _get_ws_user(ws):
        return mock_user

    monkeypatch.setattr(ws_router, "get_ws_user", _get_ws_user)
    monkeypatch.setattr(ws_router, "_WS_SESSION_REVALIDATION_INTERVAL", 2)
    monkeypatch.setattr(ws_router, "check_pad_access", AsyncMock(return_value=(False, "access revoked")))
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    await ws_router.periodic_auth_check(
        websocket, uuid.uuid4(), mock_user, fakeredis_client, "pad:stream:test", "conn-1", MagicMock()
    )

    websocket.close.assert_awaited_once_with(code=4003, reason="access revoked")


# ---------------------------------------------------------------------------
# _handle_received_data
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_received_data_pointer_update(mock_user, fakeredis_client):
    pad_id = uuid.uuid4()
    raw = json.dumps({"type": "pointer_update", "data": {"x": 1}})
    await ws_router._handle_received_data(
        raw, pad_id, mock_user, fakeredis_client, "pad:stream:test", "conn-1", MagicMock()
    )
    # pointer updates go to pub/sub, not the stream
    streams = await fakeredis_client.xread({"pad:stream:test": "0"}, count=10)
    assert len(streams) == 0


@pytest.mark.asyncio
async def test_handle_received_data_app_event(mock_user, fakeredis_client):
    pad_id = uuid.uuid4()
    raw = json.dumps({"type": "appstate_update", "data": {"state": {}}})
    await ws_router._handle_received_data(
        raw, pad_id, mock_user, fakeredis_client, "pad:stream:test", "conn-1", MagicMock()
    )
    streams = await fakeredis_client.xread({"pad:stream:test": "0"}, count=10)
    assert len(streams) == 1


@pytest.mark.asyncio
async def test_handle_received_data_invalid_json(mock_user, fakeredis_client):
    pad_id = uuid.uuid4()
    await ws_router._handle_received_data(
        "not-json", pad_id, mock_user, fakeredis_client, "pad:stream:test", "conn-1", MagicMock()
    )
    streams = await fakeredis_client.xread({"pad:stream:test": "0"}, count=10)
    assert len(streams) == 0


# ---------------------------------------------------------------------------
# consume_redis_stream
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_consume_redis_stream_forwards_messages(fakeredis_client, monkeypatch):
    websocket = _FakeWebSocket(connected=True)
    calls = []

    async def _send(text):
        calls.append(text)
        if len(calls) == 1:
            websocket.client_state.CONNECTED = False

    websocket.send_text = _send

    pad_id = uuid.uuid4()
    stream_key = f"pad:stream:{pad_id}"
    msg = ws_router.WebSocketMessage(
        type="user_joined",
        pad_id=str(pad_id),
        user_id="other",
        connection_id="other-conn",
        data={"username": "bob"},
    )
    await ws_router.publish_event_to_redis(fakeredis_client, stream_key, msg)

    task = asyncio.create_task(
        ws_router.consume_redis_stream(fakeredis_client, stream_key, websocket, "conn-1", last_id="0")
    )
    try:
        await asyncio.wait_for(task, timeout=3.0)
    except asyncio.TimeoutError:
        task.cancel()
        raise AssertionError("consume_redis_stream did not stop after the socket closed")

    assert len(calls) == 1
    data = json.loads(calls[0])
    assert data["type"] == "user_joined"


@pytest.mark.asyncio
async def test_consume_redis_stream_skips_own_messages(fakeredis_client, monkeypatch):
    websocket = _FakeWebSocket(connected=True)
    calls = []

    async def _send(text):
        calls.append(text)
        websocket.client_state.CONNECTED = False

    websocket.send_text = _send

    pad_id = uuid.uuid4()
    stream_key = f"pad:stream:{pad_id}"
    msg = ws_router.WebSocketMessage(
        type="user_joined",
        pad_id=str(pad_id),
        user_id="user-1",
        connection_id="conn-1",
        data={"username": "alice"},
    )
    await ws_router.publish_event_to_redis(fakeredis_client, stream_key, msg)

    task = asyncio.create_task(
        ws_router.consume_redis_stream(fakeredis_client, stream_key, websocket, "conn-1", last_id="0")
    )
    await asyncio.sleep(0.2)
    websocket.client_state.CONNECTED = False
    try:
        await asyncio.wait_for(task, timeout=3.0)
    except asyncio.TimeoutError:
        task.cancel()
    assert len(calls) == 0


# ---------------------------------------------------------------------------
# consume_pointer_updates
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_consume_pointer_updates_forwards_other_connections(fakeredis_client, monkeypatch):
    websocket = _FakeWebSocket(connected=True)
    calls = []

    async def _send(text):
        calls.append(text)
        websocket.client_state.CONNECTED = False

    websocket.send_text = _send

    pad_id = uuid.uuid4()
    channel = f"pad:pointer:updates:{pad_id}"
    pubsub = fakeredis_client.pubsub()
    await pubsub.subscribe(channel)

    task = asyncio.create_task(
        ws_router.consume_pointer_updates(fakeredis_client, pad_id, websocket, "conn-1")
    )

    msg = ws_router.WebSocketMessage(
        type="pointer_update",
        pad_id=str(pad_id),
        user_id="user-2",
        connection_id="conn-2",
        data={"x": 5},
    )
    await asyncio.sleep(0.05)
    await fakeredis_client.publish(channel, msg.model_dump_json())

    try:
        await asyncio.wait_for(task, timeout=1.0)
    except asyncio.TimeoutError:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Connection bookkeeping
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_connection_new(fakeredis_client):
    pad_id = uuid.uuid4()
    await ws_router.add_connection(fakeredis_client, pad_id, "user-1", "alice", "conn-1")
    data = await fakeredis_client.hget(f"pad:users:{pad_id}", "user-1")
    parsed = json.loads(data)
    assert parsed["username"] == "alice"
    assert parsed["connections"] == ["conn-1"]


@pytest.mark.asyncio
async def test_add_connection_existing(fakeredis_client):
    pad_id = uuid.uuid4()
    await ws_router.add_connection(fakeredis_client, pad_id, "user-1", "alice", "conn-1")
    await ws_router.add_connection(fakeredis_client, pad_id, "user-1", "alice", "conn-2")
    data = await fakeredis_client.hget(f"pad:users:{pad_id}", "user-1")
    parsed = json.loads(data)
    assert "conn-1" in parsed["connections"]
    assert "conn-2" in parsed["connections"]


@pytest.mark.asyncio
async def test_remove_connection(fakeredis_client):
    pad_id = uuid.uuid4()
    await ws_router.add_connection(fakeredis_client, pad_id, "user-1", "alice", "conn-1")
    await ws_router.remove_connection(fakeredis_client, pad_id, "user-1", "conn-1")
    assert await fakeredis_client.exists(f"pad:users:{pad_id}") == 0


# ---------------------------------------------------------------------------
# Origin validation
# ---------------------------------------------------------------------------

def test_is_allowed_origin_accepts_configured_origin(monkeypatch):
    monkeypatch.setattr(ws_router, "FRONTEND_URL", "https://pad.pad.test")
    monkeypatch.setattr(ws_router, "PAD_DEV_MODE", False)
    assert ws_router._is_allowed_origin("https://pad.pad.test") is True


def test_is_allowed_origin_rejects_unknown_origin(monkeypatch):
    monkeypatch.setattr(ws_router, "FRONTEND_URL", "https://pad.pad.test")
    monkeypatch.setattr(ws_router, "PAD_DEV_MODE", False)
    assert ws_router._is_allowed_origin("https://evil.test") is False
    assert ws_router._is_allowed_origin(None) is False


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@pytest.fixture
def ws_client(mock_user, monkeypatch, fakeredis_client, patched_user_session):
    app = FastAPI()
    app.include_router(ws_router.ws_router, prefix="/api")

    # ``Depends(get_ws_user)`` captured the function object at import time, so the
    # dependency must be overridden on the app rather than patched on the module.
    app.dependency_overrides[ws_router.get_ws_user] = lambda: mock_user

    class FakeAsyncSession:
        async def __aenter__(self):
            return MagicMock()
        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(ws_router, "async_session", FakeAsyncSession)

    class FakePadAccess:
        async def __call__(self, pad_id, user, session):
            pad = MagicMock()
            pad.get_connected_users = AsyncMock(return_value=[])
            return (pad, None)

    monkeypatch.setattr(ws_router, "PadAccess", FakePadAccess)
    monkeypatch.setattr(ws_router, "RedisClient", MagicMock())
    ws_router.RedisClient.get_instance = AsyncMock(return_value=fakeredis_client)

    return TestClient(app)


def test_websocket_endpoint_rejects_invalid_origin(ws_client):
    with pytest.raises(Exception):
        with ws_client.websocket_connect("/api/ws/pad/" + str(uuid.uuid4()), headers={"Origin": "https://evil.test"}):
            pass


def test_websocket_endpoint_rejects_unauthenticated(mock_user, monkeypatch):
    app = FastAPI()
    app.include_router(ws_router.ws_router, prefix="/api")
    app.dependency_overrides[ws_router.get_ws_user] = lambda: None

    client = TestClient(app)
    with pytest.raises(Exception):
        with client.websocket_connect(
            "/api/ws/pad/" + str(uuid.uuid4()),
            headers={"Origin": "https://pad.pad.test"},
        ):
            pass


def test_websocket_endpoint_denies_pad_access(mock_user, monkeypatch):
    app = FastAPI()
    app.include_router(ws_router.ws_router, prefix="/api")
    app.dependency_overrides[ws_router.get_ws_user] = lambda: mock_user

    class FakePadAccess:
        async def __call__(self, pad_id, user, session):
            raise HTTPException(status_code=403, detail="no access")

    monkeypatch.setattr(ws_router, "PadAccess", FakePadAccess)

    client = TestClient(app)
    with pytest.raises(Exception):
        with client.websocket_connect(
            "/api/ws/pad/" + str(uuid.uuid4()),
            headers={"Origin": "https://pad.pad.test"},
        ):
            pass


@pytest.mark.asyncio
async def test_websocket_endpoint_direct_lifecycle(mock_user, monkeypatch, fakeredis_client, patched_user_session):
    """Exercise the endpoint body without TestClient's portal thread."""
    pad_id = uuid.uuid4()
    disconnected = asyncio.Event()

    class FakeWS:
        def __init__(self):
            self.headers = {"origin": "https://pad.pad.test"}
            self.cookies = {}
            self.client_state = MagicMock()
            self.client_state.CONNECTED = True
            self.sent = []
            self.accepted = False
            self.close_args = None
            self.incoming = ['{"type": "pointer_update", "data": {"x": 1}}', 'bad-json', 'boom']

        async def accept(self):
            self.accepted = True

        async def send_text(self, text):
            self.sent.append(text)

        async def receive_text(self):
            if self.incoming:
                return self.incoming.pop(0)
            await disconnected.wait()
            raise WebSocketDisconnect()

        async def close(self, code=1000, reason=""):
            self.close_args = (code, reason)
            self.client_state.CONNECTED = False

    ws = FakeWS()
    pad = MagicMock()
    pad.get_connected_users = AsyncMock(return_value=[])

    class FakePadAccess:
        async def __call__(self, pad_id, user, session):
            return (pad, None)

    class FakeAsyncSession:
        async def __aenter__(self):
            return MagicMock()

        async def __aexit__(self, *args):
            pass

    original_handle = ws_router._handle_received_data
    calls = {"n": 0}

    async def _flaky_handle(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return await original_handle(*args, **kwargs)
        if calls["n"] == 2:
            raise json.JSONDecodeError("bad", "bad-json", 0)
        raise ValueError("boom")

    monkeypatch.setattr(ws_router, "PadAccess", FakePadAccess)
    monkeypatch.setattr(ws_router, "async_session", FakeAsyncSession)
    monkeypatch.setattr(ws_router, "_handle_received_data", _flaky_handle)
    monkeypatch.setattr(ws_router, "RedisClient", MagicMock())
    ws_router.RedisClient.get_instance = AsyncMock(return_value=fakeredis_client)

    task = asyncio.create_task(ws_router.websocket_endpoint(ws, pad_id, user=mock_user))
    for _ in range(100):
        await asyncio.sleep(0.02)
        if ws.accepted and ws.sent:
            break

    assert ws.accepted is True
    assert json.loads(ws.sent[0])["type"] == "connected"

    disconnected.set()
    await asyncio.wait_for(task, timeout=5)

@pytest.mark.asyncio
async def test_periodic_auth_check_logs_revalidation_errors(mock_user, monkeypatch, fakeredis_client, capsys):
    websocket = _FakeWebSocket(connected=True)

    async def _boom(ws):
        raise RuntimeError("session lookup failed")

    monkeypatch.setattr(ws_router, "get_ws_user", _boom)
    monkeypatch.setattr(ws_router, "_WS_SESSION_REVALIDATION_INTERVAL", 1)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    await ws_router.periodic_auth_check(
        websocket, uuid.uuid4(), mock_user, fakeredis_client, "pad:stream:test", "conn-1", MagicMock()
    )

    assert "Error in periodic auth check" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_consume_redis_stream_logs_read_errors(fakeredis_client, capsys):
    websocket = _FakeWebSocket(connected=True)
    redis_client = MagicMock()
    redis_client.xread = AsyncMock(side_effect=RuntimeError("stream down"))

    await ws_router.consume_redis_stream(redis_client, "pad:stream:test", websocket, "conn-1", last_id="0")

    assert "Error in Redis stream consumer" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_remove_connection_keeps_other_connections(fakeredis_client):
    pad_id = uuid.uuid4()
    await ws_router.add_connection(fakeredis_client, pad_id, "user-1", "alice", "conn-1")
    await ws_router.add_connection(fakeredis_client, pad_id, "user-1", "alice", "conn-2")

    await ws_router.remove_connection(fakeredis_client, pad_id, "user-1", "conn-1")

    remaining = json.loads(await fakeredis_client.hget(f"pad:users:{pad_id}", "user-1"))
    assert remaining["connections"] == ["conn-2"]
    assert await fakeredis_client.exists(f"pad:users:{pad_id}") == 1


@pytest.mark.asyncio
async def test_remove_connection_unknown_user_is_noop(fakeredis_client):
    pad_id = uuid.uuid4()
    await ws_router.remove_connection(fakeredis_client, pad_id, "ghost", "conn-1")
    assert await fakeredis_client.exists(f"pad:users:{pad_id}") == 0
