"""Unit tests for post-login redirect allowlist validation."""

import pytest

from routers.auth_router import validate_redirect


@pytest.mark.parametrize(
    "rd,expected",
    [
        # Empty / whitespace input falls back to root.
        (None, "/"),
        ("", "/"),
        ("   ", "/"),

        # Local absolute paths are accepted unchanged.
        ("/", "/"),
        ("/pad/123", "/pad/123"),
        ("/pad/123?foo=bar&baz=qux", "/pad/123?foo=bar&baz=qux"),
        ("/pad/123#section", "/pad/123#section"),

        # Scheme-relative and protocol-relative paths are rejected.
        ("//attacker.example", "/"),
        ("//evil.test/pad", "/"),

        # Backslashes and encoded separators are rejected.
        ("\\windows\\path", "/"),
        ("/mixed\\path", "/"),
        ("/foo%2Fbar", "/"),
        ("/foo%2fbar", "/"),
        ("/foo%5Cbar", "/"),
        ("/foo%5cbar", "/"),

        # Control / null bytes are rejected.
        ("/foo\x00bar", "/"),
        ("/foo\x1fbar", "/"),

        # Plain HTTP is rejected.
        ("http://pad.pad.test/", "/"),
        ("http://auth.pad.test/admin", "/"),

        # HTTPS URLs on allowed hosts are accepted.
        ("https://pad.pad.test/", "https://pad.pad.test/"),
        ("https://pad.pad.test/pad/123", "https://pad.pad.test/pad/123"),
        ("https://auth.pad.test/admin", "https://auth.pad.test/admin"),
        ("https://coder.pad.test/", "https://coder.pad.test/"),

        # HTTPS URLs on external hosts are rejected.
        ("https://attacker.example/", "/"),
        ("https://evil.test/pad", "/"),

        # Userinfo tricks are rejected.
        ("https://pad.pad.test@evil.example/", "/"),
        ("https://user:pass@pad.pad.test/", "/"),
        ("https://pad.pad.test.evil.example/", "/"),

        # Ports on allowed hosts are accepted (host extraction strips port).
        ("https://pad.pad.test:8443/", "https://pad.pad.test:8443/"),
    ],
)
def test_validate_redirect(rd, expected):
    assert validate_redirect(rd) == expected
