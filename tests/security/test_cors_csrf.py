"""CORS and CSRF origin validation tests."""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import PAD_BASE_URL, require_stack, stack_url

pytestmark = pytest.mark.security


def test_foreign_cors_origin_gets_no_allow_origin(client: httpx.Client) -> None:
    """A request from an untrusted origin must not receive CORS allow headers."""
    require_stack(client)
    resp = client.get(
        stack_url("/api/auth/status", PAD_BASE_URL),
        headers={"Origin": "https://attacker.example.com"},
    )
    assert "Access-Control-Allow-Origin" not in resp.headers


def test_state_change_missing_origin_is_403(client: httpx.Client) -> None:
    """A POST without Origin or Referer must be rejected before reaching the app."""
    require_stack(client)
    resp = client.post(
        stack_url("/api/auth/refresh", PAD_BASE_URL),
        headers={"Accept": "application/json"},
    )
    assert resp.status_code == 403


def test_state_change_foreign_origin_is_403(client: httpx.Client) -> None:
    """A POST from a foreign origin must be rejected."""
    require_stack(client)
    resp = client.post(
        stack_url("/api/auth/refresh", PAD_BASE_URL),
        headers={
            "Accept": "application/json",
            "Origin": "https://attacker.example.com",
        },
    )
    assert resp.status_code == 403


def test_state_change_allowed_origin_reaches_endpoint(client: httpx.Client) -> None:
    """A same-origin state-changing request is not blocked by CSRF middleware."""
    require_stack(client)
    origin = PAD_BASE_URL
    resp = client.post(
        stack_url("/api/auth/refresh", PAD_BASE_URL),
        headers={
            "Accept": "application/json",
            "Origin": origin,
        },
    )
    # The CSRF check passed; without a session the endpoint returns 401.
    assert resp.status_code == 401
