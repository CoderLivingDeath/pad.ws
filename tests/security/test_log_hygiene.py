"""Log-hygiene test for the edge-authentication flow.

Performs a full login, callback and logout through Caddy and then inspects the
Caddy, Pad, Keycloak and Coder container logs for cookies, authorization
headers, OIDC codes/state values and Coder API keys.
"""

from __future__ import annotations

import os
import subprocess
import time

import httpx
import pytest

from tests.conftest import (
    PAD_BASE_URL,
    SESSION_COOKIE_NAME,
    TEST_PASSWORD,
    TEST_USERNAME,
    keycloak_login,
    require_stack,
)

pytestmark = pytest.mark.security


def _service_logs(since: str) -> str:
    """Fetch recent logs from the services that may see authentication secrets."""
    try:
        result = subprocess.run(
            ["docker", "compose", "logs", "--since", since, "caddy", "pad", "keycloak", "coder"],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except Exception as exc:  # pragma: no cover - stack availability guard
        pytest.skip(f"Could not read service logs: {exc}")

    return result.stdout + result.stderr


def test_login_callback_logout_leaves_no_secrets_in_logs(client: httpx.Client) -> None:
    """A complete auth flow must not write session secrets to any service log."""
    require_stack(client)

    start_time = time.time()
    result = keycloak_login(client, TEST_USERNAME, TEST_PASSWORD)
    if not result or not result.cookies.get(SESSION_COOKIE_NAME):
        pytest.skip("Login did not produce a session cookie")

    session_value = result.cookies[SESSION_COOKIE_NAME]

    # Logout to also exercise the Coder cookie-clearing path and end-session
    # redirect, both of which touch sensitive values.
    client.get(
        f"{PAD_BASE_URL}/api/auth/logout",
        cookies=result.cookies,
        follow_redirects=False,
    )

    # Give the containers a moment to flush log lines.
    time.sleep(1)

    since = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(start_time - 30))
    logs = _service_logs(since)

    forbidden_values: set[str] = set()
    for token in (session_value, result.code, result.state):
        if token:
            forbidden_values.add(token)

    # Environment secrets that must never appear in logs.
    for env_name in ("CODER_API_KEY", "OIDC_CLIENT_SECRET"):
        env_value = os.getenv(env_name)
        if env_value:
            forbidden_values.add(env_value)

    for token in forbidden_values:
        assert token not in logs, (
            f"Service logs contain sensitive value from the auth flow ({token[:10]}...)"
        )
