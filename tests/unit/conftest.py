"""Shared fixtures and environment setup for backend unit tests.

These tests import modules from ``src/backend`` and must therefore set all
environment variables that ``config.py`` reads at import time.  They also run
without PostgreSQL, Redis, Keycloak or Coder.
"""

import builtins
import os
import sys
from io import StringIO

import pytest


# ---------------------------------------------------------------------------
# Required environment for backend imports
# ---------------------------------------------------------------------------

def _setenv(name: str, value: str) -> None:
    os.environ.setdefault(name, value)

_setenv("FRONTEND_URL", "https://pad.pad.test")
_setenv("PAD_DOMAIN", "pad.pad.test")
_setenv("AUTH_DOMAIN", "auth.pad.test")
_setenv("CODER_DOMAIN", "coder.pad.test")
_setenv("COOKIE_DOMAIN", ".pad.test")
_setenv("SESSION_COOKIE_NAME", "session_id")
_setenv("OIDC_SERVER_URL", "https://auth.pad.test")
_setenv("OIDC_INTERNAL_URL", "http://keycloak:8080")
_setenv("OIDC_REALM", "pad")
_setenv("OIDC_CLIENT_ID", "pad")
_setenv("OIDC_CLIENT_SECRET", "test-only-secret")
_setenv("REDIRECT_URI", "https://pad.pad.test/api/auth/callback")
_setenv("STATIC_DIR", "/app/frontend/dist")
_setenv("ASSETS_DIR", "/app/frontend/dist/assets")
_setenv("REDIS_HOST", "localhost")
_setenv("REDIS_PORT", "6379")
_setenv("PAD_ALLOWED_ROLES", "")
_setenv("CODER_URL", "https://coder.pad.test")
_setenv("CODER_INTERNAL_URL", "http://coder:7080")
_setenv("TRUSTED_PROXY_IPS", "*")
_setenv("POSTGRES_USER", "postgres")
_setenv("POSTGRES_PASSWORD", "postgres")
_setenv("POSTGRES_DB", "pad")
_setenv("POSTGRES_HOST", "localhost")
_setenv("POSTGRES_PORT", "5432")
_setenv("CODER_API_KEY", "")
_setenv("CODER_TEMPLATE_ID", "")
_setenv("CODER_DEFAULT_ORGANIZATION", "")


# ---------------------------------------------------------------------------
# Stub templates/default.json so config.py can import without the real file
# ---------------------------------------------------------------------------

_REAL_OPEN = builtins.open


def _patched_open(file, *args, **kwargs):
    path = str(file)
    if path in ("templates/default.json", "./templates/default.json"):
        return StringIO('{"files": {}, "appState": {}}')
    return _REAL_OPEN(file, *args, **kwargs)


builtins.open = _patched_open


# ---------------------------------------------------------------------------
# Make src/backend importable as top-level modules
# ---------------------------------------------------------------------------

_BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "src", "backend")
sys.path.insert(0, os.path.abspath(_BACKEND_DIR))


def pytest_configure(config):
    """Global skip helpers for missing optional/test-only dependencies."""
    pass


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fakeredis_client():
    """A fresh fakeredis async client for each test."""
    try:
        import fakeredis.aioredis as fake_aioredis
    except Exception as exc:  # pragma: no cover - dependency guard
        pytest.skip(f"fakeredis is not available: {exc}")

    client = fake_aioredis.FakeRedis(decode_responses=True)
    yield client
    # Best-effort cleanup; FakeRedis supports close() in newer versions.
    try:
        import asyncio
        asyncio.get_event_loop().run_until_complete(client.close())
    except Exception:
        pass
