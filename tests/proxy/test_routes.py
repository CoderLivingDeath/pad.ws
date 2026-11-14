"""Edge-proxy route-matrix tests.

Every assertion in this file is made against Caddy's public ingress.  Requests
must never be sent directly to Pad, Keycloak or Coder.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from typing import Set

import httpx
import pytest

from conftest import (
    AUTH_BASE_URL,
    CODER_BASE_URL,
    PAD_BASE_URL,
    SESSION_COOKIE_NAME,
    UNPROVISIONED_PASSWORD,
    UNPROVISIONED_USERNAME,
    keycloak_login,
    require_stack,
    stack_url,
)

pytestmark = pytest.mark.proxy


def _location(resp: httpx.Response) -> str:
    return resp.headers.get("location", "")


def _assert_security_headers(resp: httpx.Response, expect_hsts: bool | None = None) -> None:
    """Common headers emitted by the (security_headers) Caddy snippet.

    HSTS is intentionally omitted in the local *.pad.test profile; set
    EXPECT_HSTS=true when running against a production-like profile.
    """
    if expect_hsts is None:
        expect_hsts = os.getenv("EXPECT_HSTS", "false").lower() in ("1", "true", "yes")
    assert "X-Content-Type-Options" in resp.headers
    assert "Referrer-Policy" in resp.headers
    assert "Permissions-Policy" in resp.headers
    if expect_hsts:
        assert "Strict-Transport-Security" in resp.headers


# ---------------------------------------------------------------------------
# Pad host
# ---------------------------------------------------------------------------


def test_anonymous_pad_root_redirects_to_login(client: httpx.Client) -> None:
    require_stack(client)
    resp = client.get(
        stack_url("/", PAD_BASE_URL),
        headers={"Accept": "text/html"},
    )
    assert resp.status_code == 302
    loc = _location(resp)
    assert PAD_BASE_URL in loc and "/api/auth/login" in loc
    _assert_security_headers(resp)


def test_pad_api_json_unauthenticated_is_401(client: httpx.Client) -> None:
    require_stack(client)
    resp = client.get(
        stack_url("/api/auth/verify", PAD_BASE_URL),
        headers={"Accept": "application/json"},
    )
    assert resp.status_code == 401
    assert resp.headers.get("content-type", "").startswith("application/json")


def test_pad_api_star_unauthenticated_is_401(client: httpx.Client) -> None:
    require_stack(client)
    resp = client.get(
        stack_url("/api/auth/verify", PAD_BASE_URL),
        headers={"Accept": "*/*"},
    )
    assert resp.status_code == 401
    assert resp.headers.get("content-type", "").startswith("application/json")


def test_static_asset_is_public(client: httpx.Client) -> None:
    require_stack(client)
    # ``/static`` is served from the Pad image and is intentionally public so
    # that login/popup subresources load without a session.
    for path in ("/static/auth/popup-close.html", "/favicon.ico"):
        resp = client.get(stack_url(path, PAD_BASE_URL))
        assert resp.status_code == 200, f"{path} must be public, got {resp.status_code}"
        return
    pytest.fail("no public static asset is served")


# ---------------------------------------------------------------------------
# Coder host
# ---------------------------------------------------------------------------


def test_coder_ui_anonymous_redirects_to_pad_login(client: httpx.Client) -> None:
    require_stack(client)
    resp = client.get(
        stack_url("/", CODER_BASE_URL),
        headers={"Accept": "text/html"},
    )
    assert resp.status_code == 302
    loc = _location(resp)
    assert PAD_BASE_URL in loc and "/api/auth/login" in loc


def test_pad_logout_helper_clears_all_coder_cookies(client: httpx.Client) -> None:
    """/__pad/logout must clear every documented Coder cookie."""
    require_stack(client)
    resp = client.get(stack_url("/__pad/logout", CODER_BASE_URL))
    assert resp.status_code == 204
    set_cookie_names = {
        cookie.split("=", 1)[0] for cookie in resp.headers.get_list("set-cookie")
    }
    expected = {
        "coder_session_token",
        "coder_oauth_state",
        "oauth_state",
        "oauth_redirect",
        "oauth_pkce_verifier",
        "csrf_token",
    }
    assert expected.issubset(set_cookie_names), (
        f"Missing cookie clears: {expected - set_cookie_names}"
    )


def test_coder_api_without_pad_cookie_is_not_redirected(client: httpx.Client) -> None:
    """
    Machine-client paths (/api/v2/*) bypass Pad forward_auth.  A request with
    no Pad cookie must reach Coder and receive Coder's own 401, not a 302 to
    the Pad login page.
    """
    require_stack(client)
    resp = client.get(
        stack_url("/api/v2/users/me", CODER_BASE_URL),
        headers={"Accept": "application/json"},
    )
    assert resp.status_code != 302
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Keycloak host
# ---------------------------------------------------------------------------


def test_keycloak_oidc_public_paths_are_open(client: httpx.Client) -> None:
    require_stack(client)
    resp = client.get(
        stack_url("/realms/pad/.well-known/openid-configuration", AUTH_BASE_URL),
    )
    assert resp.status_code == 200
    assert "application/json" in resp.headers.get("content-type", "")


def test_keycloak_admin_anonymous_is_denied(client: httpx.Client) -> None:
    require_stack(client)
    resp = client.get(
        stack_url("/admin/", AUTH_BASE_URL),
        headers={"Accept": "text/html"},
    )
    assert resp.status_code != 200
    assert resp.status_code in (302, 303, 307, 308, 401, 403)


# ---------------------------------------------------------------------------
# Header spoofing and unknown hosts
# ---------------------------------------------------------------------------


def test_forged_pad_identity_headers_do_not_grant_access(client: httpx.Client) -> None:
    require_stack(client)
    headers = {
        "Accept": "application/json",
        "X-Pad-User": "00000000-0000-0000-0000-000000000000",
        "X-Pad-Roles": "admin",
        "X-Pad-Admin": "true",
    }
    resp = client.get(stack_url("/api/pad", PAD_BASE_URL), headers=headers)
    assert resp.status_code in (302, 401)


def test_forged_pad_headers_on_coder_ui_do_not_grant_access(client: httpx.Client) -> None:
    require_stack(client)
    headers = {
        "Accept": "text/html",
        "X-Pad-User": "00000000-0000-0000-0000-000000000000",
        "X-Pad-Roles": "admin",
        "X-Pad-Admin": "true",
    }
    resp = client.get(stack_url("/", CODER_BASE_URL), headers=headers)
    assert resp.status_code == 302
    assert CODER_BASE_URL not in _location(resp)


def test_unknown_host_is_not_proxied(client: httpx.Client) -> None:
    """A Host header with no matching site must not reach a configured backend."""
    require_stack(client)
    resp = client.get(
        stack_url("/", PAD_BASE_URL),
        headers={"Host": "attacker.example.com"},
    )
    body = resp.text.lower()
    assert resp.status_code != 200 or (
        "pad" not in body
        and "keycloak" not in body
        and "coder" not in body
    )


# ---------------------------------------------------------------------------
# Body limit and security headers
# ---------------------------------------------------------------------------


def test_request_body_over_limit_returns_413(client: httpx.Client) -> None:
    """Caddy's request_body max_size (10 MB) must reject oversized payloads."""
    require_stack(client)
    if os.getenv("SKIP_HEAVY_TESTS"):
        pytest.skip("SKIP_HEAVY_TESTS is set")
    # 10 MB + 100 bytes
    big_body = b"x" * (10 * 1024 * 1024 + 100)
    resp = client.post(
        stack_url("/api/auth/status", PAD_BASE_URL),
        content=big_body,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert resp.status_code == 413


def test_security_headers_present_on_pad_response(client: httpx.Client) -> None:
    require_stack(client)
    # Local *.pad.test uses tls internal and deliberately omits HSTS.
    local_mode = PAD_BASE_URL.endswith(".test") or os.getenv("CADDYFILE", "").endswith(".local")
    resp = client.get(stack_url("/api/auth/status", PAD_BASE_URL))
    _assert_security_headers(resp, expect_hsts=not local_mode)


# ---------------------------------------------------------------------------
# Log redaction
# ---------------------------------------------------------------------------


def test_callback_log_redaction(client: httpx.Client) -> None:
    """
    After a successful login callback the Caddy access log must not contain
    literal session_id, OIDC code or OIDC state values.
    """
    require_stack(client)
    try:
        result = keycloak_login(client, UNPROVISIONED_USERNAME, UNPROVISIONED_PASSWORD)
    except Exception as exc:
        pytest.skip(f"Could not perform a login callback for log inspection: {exc}")

    # We need the sensitive values that were exchanged during the flow.  If the
    # unprovisioned user got a session cookie the login succeeded (the user is
    # just forbidden by Pad later); either way, capture whatever we can.
    session_value = result.cookies.get(SESSION_COOKIE_NAME, "") if result else ""

    # Reconstruct the callback request so we can search for its query values.
    callback_url = stack_url("/api/auth/callback", PAD_BASE_URL)
    # The code/state were carried in the final Keycloak redirect; they are not
    # present on the client unless we captured them, so search broadly for the
    # literal cookie value and known query parameter names.
    since = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 120))
    try:
        logs = subprocess.run(
            ["docker", "compose", "logs", "--since", since, "caddy"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        ).stdout
    except Exception as exc:
        pytest.skip(f"Could not read Caddy logs: {exc}")

    forbidden_patterns: Set[str] = set()
    if session_value:
        forbidden_patterns.add(session_value)
    if result and result.code:
        forbidden_patterns.add(result.code)
    if result and result.state:
        forbidden_patterns.add(result.state)
    # A fresh code/state should not appear literally; this is a coarse guard
    # that fails only if the log line contains a code=... or state=... value.
    for line in logs.splitlines():
        for param in ("code", "state"):
            match = re.search(rf"{param}[:=]([^\s&\"]+)", line, re.IGNORECASE)
            if match:
                forbidden_patterns.add(match.group(1))

    for token in forbidden_patterns:
        assert token not in logs, f"Caddy log contains sensitive value: {token[:20]}..."
