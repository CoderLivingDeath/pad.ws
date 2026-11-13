"""Shared test helpers and fixtures for the whole test suite."""

from __future__ import annotations

import html
import os
import re
from typing import Dict, NamedTuple, Optional
from urllib.parse import parse_qs, quote, urljoin, urlparse

import httpx
import pytest

PAD_BASE_URL = os.getenv("PAD_BASE_URL", "https://pad.pad.test").rstrip("/")
AUTH_BASE_URL = os.getenv("AUTH_BASE_URL", "https://auth.pad.test").rstrip("/")
CODER_BASE_URL = os.getenv("CODER_BASE_URL", "https://coder.pad.test").rstrip("/")

SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "session_id")
VERIFY_TLS = os.getenv("VERIFY_TLS", "true").lower() not in ("0", "false", "no", "")
CA_BUNDLE = os.getenv("CA_BUNDLE")

# Test identities from deploy/keycloak/realm-export.json
TEST_USERNAME = os.getenv("PAD_TEST_USERNAME", "admin")
TEST_PASSWORD = os.getenv("PAD_TEST_PASSWORD", "Password123!")
UNPROVISIONED_USERNAME = os.getenv("PAD_UNPROVISIONED_USERNAME", "unprovisioned")
UNPROVISIONED_PASSWORD = os.getenv("PAD_UNPROVISIONED_PASSWORD", "Password123!")


def client_verify():
    """Return the ``verify`` value to use for httpx clients in this suite."""
    if not VERIFY_TLS:
        return False
    if CA_BUNDLE:
        return CA_BUNDLE
    return True


def client_kwargs():
    return {"verify": client_verify(), "follow_redirects": False, "timeout": 30.0}


def stack_url(path: str = "/", base: str = PAD_BASE_URL) -> str:
    return urljoin(base + "/", path)


def is_reachable(client: httpx.Client, url: Optional[str] = None, timeout: float = 5.0) -> bool:
    url = url or stack_url("/api/auth/status")
    try:
        resp = client.get(url, timeout=timeout, follow_redirects=False)
        return resp.status_code < 500
    except Exception:
        return False


def require_stack(client: httpx.Client) -> None:
    if not is_reachable(client):
        pytest.skip(
            f"Caddy/Pad stack is not reachable at {PAD_BASE_URL}. "
            "Start the test topology (e.g. docker compose -f docker-compose.prod.yml up) "
            "or set PAD_BASE_URL/AUTH_BASE_URL/CODER_BASE_URL."
        )


def extract_form(html_text: str) -> tuple[str, Dict[str, str]]:
    match = re.search(r'<form[^>]*action="([^"]*)"[^>]*>', html_text, re.IGNORECASE)
    if not match:
        raise RuntimeError("No login form found in Keycloak response")
    action = html.unescape(match.group(1))

    inputs: Dict[str, str] = {}
    for input_tag in re.findall(r'<input[^>]*>', html_text, re.IGNORECASE):
        name_match = re.search(r'name="([^"]*)"', input_tag, re.IGNORECASE)
        value_match = re.search(r'value="([^"]*)"', input_tag, re.IGNORECASE)
        if name_match:
            inputs[name_match.group(1)] = value_match.group(1) if value_match else ""
    return action, inputs


class LoginResult(NamedTuple):
    cookies: httpx.Cookies
    code: Optional[str] = None
    state: Optional[str] = None


def keycloak_login(
    client: httpx.Client,
    username: str,
    password: str,
    pad_base: str = PAD_BASE_URL,
    auth_base: str = AUTH_BASE_URL,
    rd: str = "/",
) -> Optional[LoginResult]:
    """Browser-style OIDC login through Caddy; returns Pad session cookies."""
    resp = client.get(f"{pad_base}/api/auth/login?rd={quote(rd, safe='')}", follow_redirects=False)
    if resp.status_code not in (302, 301):
        raise RuntimeError(f"Expected login redirect, got {resp.status_code}")
    location = resp.headers.get("location")
    if not location:
        raise RuntimeError("Login redirect did not provide a Location header")
    auth_url = urljoin(pad_base + "/", location)

    resp = client.get(auth_url, follow_redirects=False)
    if resp.status_code != 200:
        raise RuntimeError(f"Keycloak login page returned {resp.status_code}")
    form_action, form_inputs = extract_form(resp.text)

    form_inputs["username"] = username
    form_inputs["password"] = password
    submit_url = urljoin(auth_url, form_action)
    resp = client.post(
        submit_url,
        data=form_inputs,
        headers={
            "Referer": auth_url,
            "Origin": f"{urlparse(auth_url).scheme}://{urlparse(auth_url).netloc}",
        },
        follow_redirects=False,
    )

    callback_code: Optional[str] = None
    callback_state: Optional[str] = None
    for _ in range(8):
        if resp.status_code not in (301, 302, 303, 307, 308):
            break
        location = resp.headers.get("location")
        if not location:
            break
        next_url = urljoin(pad_base + "/", location)
        if next_url.startswith("http://"):
            next_url = next_url.replace("http://", "https://", 1)
        parsed = urlparse(next_url)
        if "/api/auth/callback" in parsed.path:
            callback_code = parse_qs(parsed.query).get("code", [None])[0]
            callback_state = parse_qs(parsed.query).get("state", [None])[0]
        resp = client.get(next_url, follow_redirects=False)

    return LoginResult(cookies=client.cookies, code=callback_code, state=callback_state)


@pytest.fixture(scope="session")
def base_urls():
    return {
        "pad": PAD_BASE_URL,
        "auth": AUTH_BASE_URL,
        "coder": CODER_BASE_URL,
    }


@pytest.fixture(scope="function")
def client():
    with httpx.Client(**client_kwargs()) as c:
        yield c


@pytest.fixture(scope="function")
def auth_session_cookies(client: httpx.Client) -> httpx.Cookies:
    """A logged-in Pad session, skipping if the stack or login is unavailable."""
    require_stack(client)
    try:
        result = keycloak_login(client, TEST_USERNAME, TEST_PASSWORD)
    except Exception as exc:
        pytest.skip(f"Could not log in test user: {exc}")
    if not result or not result.cookies.get(SESSION_COOKIE_NAME):
        pytest.skip("Login completed but no Pad session cookie was issued")
    return result.cookies
