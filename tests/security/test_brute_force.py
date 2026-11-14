"""Keycloak brute-force protection verification.

Repeated failed logins for the same account must trigger a temporary lockout.
"""

from __future__ import annotations

from urllib.parse import urljoin, urlparse

import httpx
import pytest

from tests.conftest import (
    AUTH_BASE_URL,
    PAD_BASE_URL,
    extract_form,
    require_stack,
)

pytestmark = pytest.mark.security

BRUTE_USER = "brutetest"
BRUTE_PASSWORD = "Password123!"
MAX_FAILURES = 5


def _submit_keycloak_login(client: httpx.Client, username: str, password: str) -> httpx.Response:
    """Submit the Keycloak login form and return the raw response."""
    login_resp = client.get(
        f"{PAD_BASE_URL}/api/auth/login?rd=/",
        follow_redirects=False,
    )
    assert login_resp.status_code == 302, "Pad login did not redirect to Keycloak"
    auth_url = login_resp.headers["location"]

    auth_resp = client.get(auth_url, follow_redirects=False)
    assert auth_resp.status_code == 200, "Keycloak login page was not reachable"

    action, inputs = extract_form(auth_resp.text)
    inputs["username"] = username
    inputs["password"] = password
    submit_url = urljoin(auth_url, action)

    parsed_auth = urlparse(auth_url)
    return client.post(
        submit_url,
        data=inputs,
        headers={
            "Referer": auth_url,
            "Origin": f"{parsed_auth.scheme}://{parsed_auth.netloc}",
        },
        follow_redirects=False,
    )


def test_repeated_failed_logins_trigger_keycloak_lockout(client: httpx.Client) -> None:
    """After failureFactor failed attempts the account is temporarily disabled."""
    require_stack(client)

    for _ in range(MAX_FAILURES):
        resp = _submit_keycloak_login(client, BRUTE_USER, "wrong-password")
        # A failed login must not produce a Pad callback redirect.
        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("location", "")
            assert "/api/auth/callback" not in location, (
                "Failed login unexpectedly redirected to Pad callback"
            )

    # The same correct credentials must now be rejected because of lockout.
    resp = _submit_keycloak_login(client, BRUTE_USER, BRUTE_PASSWORD)
    assert resp.status_code != 302, "Locked account was still able to log in"
    body = resp.text.lower()
    assert any(
        phrase in body
        for phrase in (
            "account is disabled",
            "temporarily disabled",
            "invalid username or password",
        )
    ), f"Expected lockout message, got: {resp.status_code} {body[:200]}"
