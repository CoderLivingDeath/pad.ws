"""Integration test for bounded WebSocket revocation."""

from __future__ import annotations

import asyncio
import json

import pytest
import websockets

from conftest import BASE_URL, FRONTEND_URL, TEST_USERS, keycloak_code_flow

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_logout_closes_open_websocket(
    http_client, keycloak_client, redis_client
):
    """An open Pad WebSocket must close immediately when its session is revoked."""
    session_id = await keycloak_code_flow(
        http_client, keycloak_client, "user", TEST_USERS["user"]
    )

    # Create a pad so the WebSocket has a valid object to collaborate on.
    new_resp = await http_client.post(
        f"{BASE_URL}/api/pad/new",
        cookies={"session_id": session_id},
        follow_redirects=False,
    )
    assert new_resp.status_code == 200, f"Failed to create pad: {new_resp.text[:200]}"
    pad_id = new_resp.json()["id"]

    ws_url = f"ws://pad:8000/ws/pad/{pad_id}"
    async with websockets.connect(
        ws_url,
        extra_headers={
            "Cookie": f"session_id={session_id}",
            "Origin": FRONTEND_URL,
        },
    ) as ws:
        # Wait for the server to accept the connection.
        raw = await asyncio.wait_for(ws.recv(), timeout=5)
        msg = json.loads(raw)
        assert msg["type"] == "connected"

        # Revoke the session through Pad's logout endpoint.
        logout_resp = await http_client.get(
            f"{BASE_URL}/api/auth/logout",
            cookies={"session_id": session_id},
        )
        assert logout_resp.status_code == 200

        # The revocation listener should close the socket well before the
        # periodic revalidation interval.
        try:
            await asyncio.wait_for(ws.wait_closed(), timeout=5)
        except asyncio.TimeoutError:  # pragma: no cover - failure path
            pytest.fail("WebSocket remained open after logout")
