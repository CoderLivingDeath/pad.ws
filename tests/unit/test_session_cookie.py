"""Unit tests for session cookie security attributes."""

import pytest
from fastapi.responses import RedirectResponse

from routers import auth_router


@pytest.fixture(autouse=True)
def ensure_cookie_config(monkeypatch):
    """Make sure the imported config values are the ones this suite asserts."""
    monkeypatch.setattr(auth_router, "SESSION_COOKIE_NAME", "session_id")
    monkeypatch.setattr(auth_router, "COOKIE_DOMAIN", ".pad.test")


def _parse_set_cookie(response):
    """Return the first Set-Cookie header value."""
    value = response.headers.get("set-cookie")
    if value is None:
        pytest.fail("No Set-Cookie header present")
    return value


def test_set_session_cookie_has_required_attributes():
    response = RedirectResponse("/")
    auth_router._set_session_cookie(response, "opaque_session_value", 3600)
    cookie = _parse_set_cookie(response)

    assert "session_id=opaque_session_value" in cookie
    assert "Secure" in cookie
    assert "HttpOnly" in cookie
    assert "samesite=lax" in cookie.lower()
    assert "Domain=.pad.test" in cookie
    assert "Path=/" in cookie
    assert "Max-Age=3600" in cookie


def test_set_session_cookie_contains_no_token_material():
    response = RedirectResponse("/")
    auth_router._set_session_cookie(
        response,
        "opaque_session_value",
        3600,
    )
    cookie = _parse_set_cookie(response)

    # The cookie value must be an opaque identifier, never token content.
    assert "access_token" not in cookie
    assert "refresh_token" not in cookie
    assert "id_token" not in cookie
    assert "eyJ" not in cookie  # no JWT material


def test_clear_session_cookie_uses_same_scope():
    response = RedirectResponse("/")
    auth_router._clear_session_cookie(response)
    cookie = _parse_set_cookie(response)

    assert "session_id=" in cookie
    assert "Secure" in cookie
    assert "HttpOnly" in cookie
    assert "samesite=lax" in cookie.lower()
    assert "Domain=.pad.test" in cookie
    assert "Path=/" in cookie
    # Deletion is expressed by an empty value / expired max-age.
    assert "Max-Age=0" in cookie or 'session_id=""' in cookie


def test_cookie_domain_is_optional(monkeypatch):
    """When COOKIE_DOMAIN is unset the attribute must not be present."""
    monkeypatch.setattr(auth_router, "COOKIE_DOMAIN", None)
    response = RedirectResponse("/")
    auth_router._set_session_cookie(response, "opaque_session_value", 3600)
    cookie = _parse_set_cookie(response)
    assert "Domain=" not in cookie
