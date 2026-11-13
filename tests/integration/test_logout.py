"""Integration tests for logout and session revocation."""

import pytest

from conftest import BASE_URL, TEST_USERS, keycloak_code_flow

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_logout_deletes_session_and_replays_fail(
    http_client, keycloak_client, redis_client
):
    session_id = await keycloak_code_flow(
        http_client, keycloak_client, "user", TEST_USERS["user"]
    )

    # Confirm the session exists before logout.
    before = await redis_client.get(f"session:{session_id}")
    assert before is not None

    # Logout must be idempotent and clear the cookie.
    logout_resp = await http_client.get(
        f"{BASE_URL}/api/auth/logout",
        cookies={"session_id": session_id},
    )
    assert logout_resp.status_code == 200
    assert logout_resp.json().get("status") == "success"
    assert "session_id=" in logout_resp.headers.get("set-cookie", "")

    # Server-side session must be gone.
    after = await redis_client.get(f"session:{session_id}")
    assert after is None

    # Replaying the old cookie to verify must fail.
    replay = await http_client.get(
        f"{BASE_URL}/api/auth/verify",
        headers={"Accept": "application/json"},
        cookies={"session_id": session_id},
    )
    assert replay.status_code == 401
