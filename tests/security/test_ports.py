"""Direct-access tests for internal service ports from the test host."""

from __future__ import annotations

import socket

import httpx
import pytest

from tests.conftest import require_stack

pytestmark = pytest.mark.security


# Service ports that must NOT be reachable from the host in the production
# topology.  Caddy is the only published ingress.
_INTERNAL_PORTS = [
    ("localhost", 5432, "PostgreSQL"),
    ("localhost", 6379, "Redis"),
    ("localhost", 8000, "Pad"),
    ("localhost", 8080, "Keycloak"),
    ("localhost", 7080, "Coder"),
]


def _can_connect(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (ConnectionRefusedError, OSError, TimeoutError):
        return False


def test_internal_ports_are_not_published(client: httpx.Client) -> None:
    """Only Caddy (80/443) should be reachable from the host."""
    require_stack(client)
    for host, port, name in _INTERNAL_PORTS:
        if _can_connect(host, port):
            pytest.fail(
                f"{name} port {port} on {host} is reachable from the host; "
                "it must not be published"
            )
