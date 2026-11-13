"""WebSocket origin-validation tests."""

from __future__ import annotations

import uuid

import httpx
import pytest

from tests.conftest import PAD_BASE_URL, require_stack, stack_url

pytestmark = pytest.mark.security


def test_cross_origin_websocket_handshake_rejected(client: httpx.Client) -> None:
    """A WebSocket upgrade from a foreign origin must not be accepted."""
    require_stack(client)
    pad_id = uuid.uuid4()
    url = stack_url(f"/ws/pad/{pad_id}", PAD_BASE_URL)
    resp = client.get(
        url,
        headers={
            "Host": "pad.pad.test",
            "Origin": "https://attacker.example.com",
            "Connection": "Upgrade",
            "Upgrade": "websocket",
            "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
            "Sec-WebSocket-Version": "13",
        },
    )
    # FastAPI closes the websocket with an origin error before accept, so the
    # HTTP response is not a 101 Switching Protocols.
    assert resp.status_code != 101
    # Caddy may reject the unauthenticated handshake with 401 before Pad runs
    # its Origin check; with a session Pad returns 400/403.
    assert resp.status_code in (400, 401, 403)
