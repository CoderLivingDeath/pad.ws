"""Integration tests for the Caddy forward_auth verify contract."""

import pytest

from conftest import BASE_URL, TEST_USERS, keycloak_code_flow

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_verify_without_session_returns_401(http_client):
    resp = await http_client.get(f"{BASE_URL}/api/auth/verify")
    assert resp.status_code == 401
    assert resp.json().get("detail")
    # Verify never emits a Set-Cookie header.
    assert "set-cookie" not in resp.headers


@pytest.mark.asyncio
async def test_verify_navigation_without_session_redirects_to_login(http_client):
    resp = await http_client.get(
        f"{BASE_URL}/api/auth/verify",
        headers={
            "Sec-Fetch-Mode": "navigate",
            "Accept": "text/html",
            "X-Original-Host": "pad.pad.test",
            "X-Original-URI": "/pad/123",
        },
    )
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert "/api/auth/login" in location


@pytest.mark.asyncio
async def test_verify_with_valid_session_returns_identity_headers(
    http_client, keycloak_client, redis_client
):
    session_id = await keycloak_code_flow(
        http_client, keycloak_client, "user", TEST_USERS["user"]
    )

    resp = await http_client.get(
        f"{BASE_URL}/api/auth/verify",
        headers={"Accept": "application/json"},
        cookies={"session_id": session_id},
    )
    assert resp.status_code == 200
    assert resp.json().get("authenticated") is True

    assert "X-Pad-User" in resp.headers
    assert "X-Pad-Roles" in resp.headers
    assert resp.headers.get("X-Pad-Admin") in ("true", "false")
    assert resp.headers.get("Cache-Control") == "no-store"
    assert "set-cookie" not in resp.headers
