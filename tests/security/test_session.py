"""Session fixation and replay tests."""

from __future__ import annotations

import httpx
import pytest

from urllib.parse import urlparse

from tests.conftest import (
    PAD_BASE_URL,
    SESSION_COOKIE_NAME,
    TEST_PASSWORD,
    TEST_USERNAME,
    client_kwargs,
    keycloak_login,
    require_stack,
    stack_url,
)

pytestmark = pytest.mark.security


def test_replayed_random_cookie_is_401(client: httpx.Client) -> None:
    """A fabricated session cookie must not authenticate."""
    require_stack(client)
    pad_hostname = urlparse(PAD_BASE_URL).hostname or ""
    client.cookies.set(
        SESSION_COOKIE_NAME, "totally-fabricated-session-id", domain=pad_hostname
    )
    resp = client.get(
        stack_url("/api/auth/verify", PAD_BASE_URL),
        headers={"Accept": "application/json"},
    )
    assert resp.status_code == 401


def test_replayed_logged_out_cookie_is_401(client: httpx.Client) -> None:
    """A session cookie after explicit logout must be rejected."""
    require_stack(client)
    try:
        result = keycloak_login(client, TEST_USERNAME, TEST_PASSWORD)
    except Exception as exc:
        pytest.skip(f"Could not log in to obtain a session: {exc}")
    if not result or not result.cookies.get(SESSION_COOKIE_NAME):
        pytest.skip("Login did not produce a session cookie")

    # Log out through Caddy.
    logout_resp = client.get(
        stack_url("/api/auth/logout", PAD_BASE_URL),
        headers={"Accept": "application/json"},
    )
    assert logout_resp.status_code == 200

    # Replay the now-deleted session cookie.
    replay = httpx.Client(**client_kwargs())
    pad_hostname = urlparse(PAD_BASE_URL).hostname or ""
    replay.cookies.set(
        SESSION_COOKIE_NAME,
        result.cookies[SESSION_COOKIE_NAME],
        domain=pad_hostname,
    )
    resp = replay.get(
        stack_url("/api/auth/verify", PAD_BASE_URL),
        headers={"Accept": "application/json"},
    )
    assert resp.status_code == 401
    replay.close()
