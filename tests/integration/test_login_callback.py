"""Integration tests for login redirect and callback state validation."""

import pytest

from conftest import (
    BASE_URL,
    FRONTEND_URL,
    OIDC_INTERNAL_URL,
    OIDC_SERVER_URL,
    OIDC_REALM,
    OIDC_CLIENT_ID,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_login_redirects_to_keycloak_with_random_state(http_client, redis_client):
    resp = await http_client.get(f"{BASE_URL}/api/auth/login?rd=/pad/123", follow_redirects=False)
    assert resp.status_code == 302

    location = resp.headers["location"]
    assert OIDC_INTERNAL_URL in location or OIDC_SERVER_URL in location  # noqa: F821
    assert f"/realms/{OIDC_REALM}/protocol/openid-connect/auth" in location
    assert f"client_id={OIDC_CLIENT_ID}" in location

    # A random state must be present in the URL and in the cookie.
    from urllib.parse import parse_qs, urlparse

    query = parse_qs(urlparse(location).query)
    assert "state" in query
    state = query["state"][0]
    assert len(state) >= 16

    assert "oidc_state" in resp.cookies
    assert resp.cookies["oidc_state"] == state

    # The server-side transaction must exist with a TTL.
    transaction = await redis_client.get(f"oidc_state:{state}")
    assert transaction is not None
    ttl = await redis_client.ttl(f"oidc_state:{state}")
    assert ttl > 0


@pytest.mark.asyncio
async def test_callback_rejects_missing_state(http_client):
    resp = await http_client.get(f"{BASE_URL}/api/auth/callback?code=some-code", follow_redirects=False)
    assert resp.status_code == 400
    assert "state" in resp.json().get("detail", "").lower()


@pytest.mark.asyncio
async def test_callback_rejects_mismatched_state(http_client):
    resp = await http_client.get(
        f"{BASE_URL}/api/auth/callback?code=some-code&state=query-state",
        cookies={"oidc_state": "cookie-state"},
        follow_redirects=False,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_callback_rejects_replayed_state(http_client, redis_client):
    """A legitimate transaction consumed once must be rejected on reuse."""
    import json
    import time
    from domain.session import OIDC_STATE_TTL

    state = "replayed-state-test"
    await redis_client.setex(
        f"oidc_state:{state}",
        OIDC_STATE_TTL,
        json.dumps({"mode": "default", "rd": "/", "created_at": time.time()}),
    )

    # First callback deletes the transaction and then fails at code exchange.
    first = await http_client.get(
        f"{BASE_URL}/api/auth/callback?code=invalid&state={state}",
        cookies={"oidc_state": state},
        follow_redirects=False,
    )
    assert first.status_code == 400

    # Second callback must fail because the transaction no longer exists.
    second = await http_client.get(
        f"{BASE_URL}/api/auth/callback?code=invalid&state={state}",
        cookies={"oidc_state": state},
        follow_redirects=False,
    )
    assert second.status_code == 400
    assert "replay" in second.json().get("detail", "").lower() or "invalid" in second.json().get("detail", "").lower()


@pytest.mark.asyncio
async def test_login_and_callback_creates_session(http_client, keycloak_client, redis_client):
    from conftest import TEST_USERS, keycloak_code_flow

    session_id = await keycloak_code_flow(
        http_client, keycloak_client, "user", TEST_USERS["user"]
    )

    data = await redis_client.get(f"session:{session_id}")
    assert data is not None
    import json
    blob = json.loads(data)
    assert "access_token" in blob
    assert "refresh_token" in blob
