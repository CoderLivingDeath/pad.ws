"""Machine-client path tests for Coder through Caddy.

The Coder CLI, workspace agents and IDE integrations call /api/v2/* with a
Coder token.  Those paths must bypass Pad ``forward_auth`` so that a missing
Pad cookie does not turn into a browser login redirect.

A valid Coder token requires a bootstrapped Coder instance (first user, API
key, etc.) and is therefore treated as a staging check.  The regression tests
below verify the negative cases that can be automated without Coder setup.
"""

from __future__ import annotations

import os

import httpx
import pytest

from conftest import CODER_BASE_URL, require_stack, stack_url

pytestmark = pytest.mark.proxy


def test_coder_api_without_pad_cookie_is_not_302(client: httpx.Client) -> None:
    """
    A token-authenticated machine client does not have a Pad session cookie.
    Caddy must still forward /api/v2/* to Coder and must not respond 302.
    """
    require_stack(client)
    resp = client.get(
        stack_url("/api/v2/users/me", CODER_BASE_URL),
        headers={"Accept": "application/json"},
    )
    assert resp.status_code != 302, (
        "Coder machine-client path returned a redirect; it may be behind Pad forward_auth"
    )
    assert resp.status_code == 401


def test_coder_api_with_invalid_token_is_401(client: httpx.Client) -> None:
    """An invalid Coder token must be rejected by Coder with 401, not 302."""
    require_stack(client)
    resp = client.get(
        stack_url("/api/v2/users/me", CODER_BASE_URL),
        headers={
            "Accept": "application/json",
            "Authorization": "Bearer invalid-token-for-proxy-test",
        },
    )
    assert resp.status_code != 302
    assert resp.status_code == 401


@pytest.mark.skip(reason="Requires a bootstrapped Coder instance; run in staging")
def test_coder_api_with_valid_token_succeeds(client: httpx.Client) -> None:
    """
    Staging gate: create a Coder API key and prove the CLI/agent path works.

    To enable this test set CODER_API_TOKEN to a valid token for the
    *.pad.test Coder deployment.
    """
    token = os.getenv("CODER_API_TOKEN")
    if not token:
        pytest.skip("CODER_API_TOKEN not set")
    resp = client.get(
        stack_url("/api/v2/users/me", CODER_BASE_URL),
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    assert resp.status_code == 200
