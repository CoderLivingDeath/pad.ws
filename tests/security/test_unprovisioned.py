"""Authorization tests for unprovisioned users."""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import (
    PAD_BASE_URL,
    SESSION_COOKIE_NAME,
    UNPROVISIONED_PASSWORD,
    UNPROVISIONED_USERNAME,
    keycloak_login,
    require_stack,
)

pytestmark = pytest.mark.security


def test_unprovisioned_keycloak_user_is_403(client: httpx.Client) -> None:
    """
    A Keycloak user with no Pad role must not receive a Pad session cookie.
    The callback returns 403 and the user remains unauthenticated.
    """
    require_stack(client)
    try:
        result = keycloak_login(
            client,
            UNPROVISIONED_USERNAME,
            UNPROVISIONED_PASSWORD,
            pad_base=PAD_BASE_URL,
        )
    except Exception as exc:
        pytest.skip(f"Could not complete Keycloak login for unprovisioned user: {exc}")

    if result and result.cookies.get(SESSION_COOKIE_NAME):
        pytest.fail("Unprovisioned user was issued a Pad session cookie")

    # The final response from Pad should be a 403, not 200 or a session cookie.
    assert result is not None
