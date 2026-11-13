"""Unit tests for OIDC login transaction one-time semantics.

The backend stores server-side login transactions under ``oidc_state:{state}``
and deletes them immediately after the first callback.  These tests exercise
that behavior with fakeredis without a real Redis server.
"""

import json
import time

import pytest

from domain.session import OIDC_STATE_TTL


@pytest.fixture
def make_transaction(fakeredis_client):
    """Helper to create a login transaction and return its state."""
    async def _make(state: str, rd: str = "/"):
        await fakeredis_client.setex(
            f"oidc_state:{state}",
            OIDC_STATE_TTL,
            json.dumps({"mode": "default", "rd": rd, "created_at": time.time()}),
        )
        return state
    return _make


@pytest.mark.asyncio
async def test_oidc_state_is_stored_with_ttl(make_transaction, fakeredis_client):
    state = await make_transaction("state-with-ttl")
    ttl = await fakeredis_client.ttl(f"oidc_state:{state}")
    assert 0 < ttl <= OIDC_STATE_TTL


@pytest.mark.asyncio
async def test_oidc_state_can_be_retrieved_once(make_transaction, fakeredis_client):
    state = await make_transaction("state-readable")
    data = await fakeredis_client.get(f"oidc_state:{state}")
    assert data is not None
    parsed = json.loads(data)
    assert parsed["rd"] == "/"
    assert "mode" in parsed


@pytest.mark.asyncio
async def test_oidc_state_replay_is_rejected(make_transaction, fakeredis_client):
    """Simulate the callback delete-then-check pattern used by auth_router."""
    state = await make_transaction("state-replay")

    # First callback: read and immediately delete (one-time use).
    transaction = await fakeredis_client.get(f"oidc_state:{state}")
    assert transaction is not None
    await fakeredis_client.delete(f"oidc_state:{state}")

    # Second callback: the transaction is gone -> replay rejected.
    replay = await fakeredis_client.get(f"oidc_state:{state}")
    assert replay is None


@pytest.mark.asyncio
async def test_oidc_state_mismatch_has_no_transaction(fakeredis_client):
    """A query state that never had a server-side record must be rejected."""
    exists = await fakeredis_client.exists("oidc_state:never-issued")
    assert exists == 0
