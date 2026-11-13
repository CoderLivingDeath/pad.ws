"""Unit tests for the provisioned-user authorization predicate."""

import pytest

import dependencies
from dependencies import is_user_provisioned


@pytest.mark.parametrize(
    "allowed_roles,token_roles,expected",
    [
        # Empty allowlist means any authenticated user is provisioned.
        ([], [], True),
        ([], ["pad-user"], True),
        ([], ["admin", "pad-user"], True),

        # Matching role grants access.
        (["pad-user"], ["pad-user"], True),
        (["pad-user", "admin"], ["pad-user"], True),
        (["admin"], ["admin", "pad-user"], True),

        # Non-matching roles are rejected.
        (["pad-user"], ["admin"], False),
        (["pad-user"], ["other-role"], False),
        (["pad-user", "admin"], ["other-role"], False),

        # Missing realm_access / roles is rejected when allowlist is set.
        (["pad-user"], [], False),
        (["pad-user"], {}, False),
        (["pad-user"], {"realm_access": {}}, False),
    ],
)
def test_is_user_provisioned(monkeypatch, allowed_roles, token_roles, expected):
    monkeypatch.setattr(dependencies, "PAD_ALLOWED_ROLES", allowed_roles)

    if isinstance(token_roles, list):
        token_data = {"realm_access": {"roles": token_roles}}
    elif isinstance(token_roles, dict):
        token_data = token_roles
    else:
        token_data = {}

    assert is_user_provisioned(token_data) is expected
