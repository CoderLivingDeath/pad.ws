"""Integration tests for token refresh failure modes."""

import json
import secrets

import pytest

from conftest import BASE_URL, FRONTEND_URL, TEST_USERS, get_session_data, keycloak_code_flow, set_session_data

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_expired_refresh_returns_401(
    http_client, keycloak_client, redis_client
):
    """When the refresh token is unusable, /api/auth/refresh fails closed."""
    session_id = await keycloak_code_flow(
        http_client, keycloak_client, "user", TEST_USERS["user"]
    )

    # Corrupt the stored refresh token so refresh is guaranteed to fail.
    data = await get_session_data(redis_client, session_id)
    assert data is not None
    data["refresh_token"] = "expired-or-revoked-refresh-token"
    data["access_token"] = "expired-access-token"
    await set_session_data(
        redis_client,
        session_id,
        data,
        ttl=data.get("refresh_expires_in", 3600),
    )

    resp = await http_client.post(
        f"{BASE_URL}/api/auth/refresh",
        cookies={"session_id": session_id},
        headers={"Origin": FRONTEND_URL},
    )
    assert resp.status_code == 401, resp.text
