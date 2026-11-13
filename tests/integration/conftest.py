"""Shared fixtures and environment setup for integration tests.

These tests exercise the real Pad backend together with PostgreSQL, Redis and
Keycloak.  They are marked with ``@pytest.mark.integration`` and skip with a
clear message when the stack is unavailable.
"""

import os
import re
import sys
from urllib.parse import parse_qs, urlparse

import pytest


# ---------------------------------------------------------------------------
# Environment configuration
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("PAD_BASE_URL", "http://pad:8000")
OIDC_INTERNAL_URL = os.environ.get("OIDC_INTERNAL_URL", "http://keycloak:8080")
OIDC_SERVER_URL = os.environ.get("OIDC_SERVER_URL", "https://auth.pad.test")
OIDC_REALM = os.environ.get("OIDC_REALM", "pad")
OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "pad")
OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", None)
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://pad.pad.test")
REDIRECT_URI = os.environ.get("REDIRECT_URI", f"{FRONTEND_URL}/api/auth/callback")

TEST_USERS = {
    "admin": "Password123!",
    "user": "Password123!",
    "unprovisioned": "Password123!",
}


# ---------------------------------------------------------------------------
# Make src/backend importable if needed
# ---------------------------------------------------------------------------

_BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "src", "backend")
sys.path.insert(0, os.path.abspath(_BACKEND_DIR))


# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------

def pytest_configure(config):
    try:
        import httpx  # noqa: F401
        import redis.asyncio  # noqa: F401
    except Exception as exc:
        raise pytest.UsageError(
            f"Integration tests require httpx and redis packages: {exc}"
        )


@pytest.fixture(scope="session", autouse=True)
def require_stack():
    """Fail fast with a clear message when the stack is not reachable."""
    import httpx

    if not OIDC_CLIENT_SECRET:
        pytest.skip(
            "OIDC_CLIENT_SECRET is not set; integration tests require the test stack"
        )

    try:
        httpx.get(f"{BASE_URL}/api/auth/verify", follow_redirects=False, timeout=5)
    except Exception as exc:  # pragma: no cover - stack availability guard
        pytest.skip(f"Pad backend is not reachable at {BASE_URL}: {exc}")


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def http_client():
    """A single httpx client that shares cookies across Pad and Keycloak."""
    import httpx

    async with httpx.AsyncClient(follow_redirects=False, timeout=30) as client:
        yield client


@pytest.fixture
async def redis_client():
    """Direct Redis connection for seeding / inspecting sessions."""
    import redis.asyncio as aioredis

    client = aioredis.from_url(
        f"redis://{REDIS_HOST}:{REDIS_PORT}",
        password=REDIS_PASSWORD,
        decode_responses=True,
    )
    try:
        yield client
    finally:
        await client.close()


@pytest.fixture
async def keycloak_client():
    """Keycloak-facing httpx client (used for discovery / forms)."""
    import httpx

    async with httpx.AsyncClient(base_url=OIDC_INTERNAL_URL, follow_redirects=False, timeout=30) as client:
        yield client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def keycloak_code_flow(
    http_client,
    keycloak_client,
    username: str,
    password: str,
):
    """Complete an OIDC authorization-code login and return the session cookie.

    The test realm disables the resource-owner password grant, so we drive the
    browser form flow with httpx.  The returned ``session_id`` cookie can be
    used to call Pad's authenticated endpoints.
    """
    import httpx

    # 1. Start the Pad login transaction.
    login_resp = await http_client.get(
        f"{BASE_URL}/api/auth/login?rd=/",
        follow_redirects=False,
    )
    assert login_resp.status_code == 302, f"login did not redirect: {login_resp.status_code}"
    keycloak_url = login_resp.headers["location"]
    assert "oidc_state" in login_resp.cookies, "oidc_state cookie was not set"
    oidc_state = login_resp.cookies["oidc_state"]

    # 2. Fetch the Keycloak login form using the internal URL so tests do not
    #    require public DNS inside the compose network.
    keycloak_internal_url = keycloak_url.replace(OIDC_SERVER_URL, OIDC_INTERNAL_URL)
    auth_resp = await http_client.get(keycloak_internal_url, follow_redirects=False)
    if auth_resp.status_code != 200:
        raise RuntimeError(
            f"Keycloak auth endpoint returned {auth_resp.status_code}: {auth_resp.text[:500]}"
        )

    # 3. Parse the login form action and hidden inputs.
    html = auth_resp.text
    form_match = re.search(
        r'<form[^>]*action="([^"]*)"[^>]*>(.*?)</form>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if not form_match:
        raise RuntimeError("Could not find Keycloak login form in response")

    action = form_match.group(1)
    form_html = form_match.group(2)

    hidden = {}
    for match in re.finditer(
        r'<input[^>]*type=["\']hidden["\'][^>]*name=["\']([^"\']*)["\'][^>]*value=["\']([^"\']*)["\']',
        form_html,
        re.IGNORECASE,
    ):
        hidden[match.group(1)] = match.group(2)

    # Resolve relative form action.
    if action.startswith("/"):
        action = f"{OIDC_INTERNAL_URL}{action}"
    elif not action.startswith("http"):
        base = keycloak_url.rsplit("/", 1)[0]
        action = f"{base}/{action}"

    # 4. Submit credentials.
    data = {**hidden, "username": username, "password": password}
    submit_resp = await http_client.post(action, data=data, follow_redirects=False)
    if submit_resp.status_code != 302:
        raise RuntimeError(
            f"Keycloak login submission failed ({submit_resp.status_code}): {submit_resp.text[:500]}"
        )

    callback_url = submit_resp.headers["location"]
    assert "/api/auth/callback" in callback_url, f"unexpected callback URL: {callback_url}"

    # 5. Follow the callback on the internal Pad URL so public DNS is not required.
    callback_url_internal = callback_url.replace(FRONTEND_URL, BASE_URL)
    callback_resp = await http_client.get(callback_url_internal, follow_redirects=False)
    assert callback_resp.status_code == 302, (
        f"callback did not redirect after login: {callback_resp.status_code} {callback_resp.text[:500]}"
    )
    assert "session_id" in callback_resp.cookies, "session_id cookie was not issued"

    return callback_resp.cookies["session_id"]


async def get_session_data(redis_client, session_id: str):
    """Return the Redis JSON blob stored by the backend for a session."""
    import json

    raw = await redis_client.get(f"session:{session_id}")
    if raw is None:
        return None
    return json.loads(raw)


async def set_session_data(redis_client, session_id: str, data: dict, ttl: int = 3600):
    """Write a session blob in the same shape the backend uses."""
    import json

    await redis_client.setex(f"session:{session_id}", ttl, json.dumps(data))
