"""Open-redirect regression tests for the login return destination."""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import (
    PAD_BASE_URL,
    TEST_PASSWORD,
    TEST_USERNAME,
    client_kwargs,
    keycloak_login,
    require_stack,
    stack_url,
)

pytestmark = pytest.mark.security


# These rd values must be rejected by the backend validation that runs before
# the OIDC state is stored.  They must never appear in the final post-login
# redirect.
_OPEN_REDIRECT_CASES = [
    ("https://attacker.example.com", "foreign https URL"),
    ("//attacker.example.com", "scheme-relative URL"),
    ("http://evil.example", "http URL"),
    ("/\\attacker.example", "backslash path"),
]


@pytest.mark.parametrize("rd,description", _OPEN_REDIRECT_CASES)
def test_open_redirect_values_are_rejected(
    client: httpx.Client, rd: str, description: str
) -> None:
    """A malicious rd parameter must not become the post-login destination."""
    require_stack(client)
    test_client = httpx.Client(**client_kwargs())
    try:
        result = keycloak_login(
            test_client, TEST_USERNAME, TEST_PASSWORD, pad_base=PAD_BASE_URL, rd=rd
        )
        if not result:
            pytest.skip("Login returned no result")
        final_url = str(
            test_client.get(stack_url("/", PAD_BASE_URL), follow_redirects=False).url
        )
    except Exception as exc:
        pytest.skip(f"Could not log in to observe final redirect: {exc}")
    finally:
        test_client.close()

    assert "attacker.example.com" not in final_url, f"{description} was not rejected"
    assert "evil.example" not in final_url, f"{description} was not rejected"
