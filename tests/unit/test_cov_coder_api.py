"""Unit tests for the Coder API client error handling and helpers."""

from datetime import datetime, timedelta

import pytest
from unittest.mock import MagicMock, patch

import coder as coder_module


@pytest.fixture(autouse=True)
def set_coder_env(monkeypatch):
    """Provide enough configuration for CoderAPI construction."""
    monkeypatch.setattr(coder_module, "CODER_API_KEY", "test-api-key")
    monkeypatch.setattr(coder_module, "CODER_INTERNAL_URL", "http://coder:7080")
    monkeypatch.setattr(coder_module, "CODER_TEMPLATE_ID", "template-uuid")
    monkeypatch.setattr(coder_module, "CODER_DEFAULT_ORGANIZATION", "org-uuid")
    monkeypatch.setattr(coder_module, "CODER_WORKSPACE_NAME", "ubuntu")


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

def test_coder_api_requires_key_and_url(monkeypatch):
    monkeypatch.setattr(coder_module, "CODER_API_KEY", "")
    monkeypatch.setattr(coder_module, "CODER_INTERNAL_URL", "")
    with pytest.raises(ValueError):
        coder_module.CoderAPI()


def test_coder_api_headers(set_coder_env):
    api = coder_module.CoderAPI()
    assert api.headers["Coder-Session-Token"] == "test-api-key"
    assert api.headers["Accept"] == "application/json"


# ---------------------------------------------------------------------------
# User helpers
# ---------------------------------------------------------------------------

def test_get_users_builds_params_and_extracts_users(set_coder_env):
    api = coder_module.CoderAPI()
    with patch.object(api, "_get_all_templates", return_value=[]):  # not used here
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: {"users": [{"username": "alice"}]},
            )
            users = api.get_users(query="alice", limit=5, offset=0)
    assert users == [{"username": "alice"}]
    call_kwargs = mock_get.call_args.kwargs
    assert call_kwargs["params"]["q"] == "alice"
    assert call_kwargs["params"]["limit"] == 5
    assert "offset" not in call_kwargs["params"]


def test_get_user_by_email_found(set_coder_env):
    api = coder_module.CoderAPI()
    with patch.object(api, "get_users", return_value=[{"email": "alice@pad.test", "username": "alice"}]):
        user = api.get_user_by_email("alice@pad.test")
    assert user["username"] == "alice"


def test_get_user_by_email_not_found(set_coder_env):
    api = coder_module.CoderAPI()
    with patch.object(api, "get_users", return_value=[]):
        assert api.get_user_by_email("missing@pad.test") is None


def test_check_username_exists(set_coder_env):
    api = coder_module.CoderAPI()
    with patch.object(api, "get_users", return_value=[{"username": "alice"}]):
        assert api.check_username_exists("alice") is True
    with patch.object(api, "get_users", return_value=[]):
        assert api.check_username_exists("bob") is False


# ---------------------------------------------------------------------------
# ensure_user_exists
# ---------------------------------------------------------------------------

def test_ensure_user_exists_returns_existing(set_coder_env):
    api = coder_module.CoderAPI()
    existing = {"username": "alice"}
    with patch.object(api, "get_user_by_email", return_value=existing):
        user, created = api.ensure_user_exists({"email": "alice@pad.test"})
    assert user == existing
    assert created is False


def test_ensure_user_exists_creates_new_user(set_coder_env):
    api = coder_module.CoderAPI()
    with patch.object(api, "get_user_by_email", return_value=None):
        with patch.object(api, "check_username_exists", return_value=False):
            with patch.object(api, "create_user", return_value={"username": "alice"}) as create:
                user, created = api.ensure_user_exists({"email": "alice@pad.test", "name": "Alice"})
    assert created is True
    create.assert_called_once()


def test_ensure_user_exists_generates_unique_username(set_coder_env):
    api = coder_module.CoderAPI()
    with patch.object(api, "get_user_by_email", return_value=None):
        with patch.object(api, "check_username_exists", side_effect=[True, True, False]):
            with patch.object(api, "create_user", return_value={"username": "alice123"}) as create:
                api.ensure_user_exists({"email": "alice@pad.test"})
    assert create.call_args[0][0].startswith("alice")


# ---------------------------------------------------------------------------
# Workspace helpers
# ---------------------------------------------------------------------------

def test_get_workspace_status_for_user_found(set_coder_env):
    api = coder_module.CoderAPI()
    with patch("requests.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"id": "ws-1", "latest_build": {"status": "running"}},
        )
        ws = api.get_workspace_status_for_user("alice")
    assert ws["id"] == "ws-1"


def test_get_workspace_status_for_user_not_found(set_coder_env):
    api = coder_module.CoderAPI()
    with patch("requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=404)
        assert api.get_workspace_status_for_user("alice") is None


def test_ensure_workspace_exists_creates_when_missing(set_coder_env):
    api = coder_module.CoderAPI()
    with patch.object(api, "get_workspace_status_for_user", return_value=None):
        with patch.object(api, "create_workspace", return_value={"id": "ws-1"}) as create:
            api.ensure_workspace_exists("alice")
    create.assert_called_once_with("alice")


# ---------------------------------------------------------------------------
# Start / stop
# ---------------------------------------------------------------------------

def test_start_workspace_success(set_coder_env):
    api = coder_module.CoderAPI()
    ws = {"id": "ws-1", "template_active_version_id": "v1"}
    with patch.object(api, "is_workspace_dormant", return_value=False):
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=200, json=lambda: ws)
            with patch("requests.post") as mock_post:
                mock_post.return_value = MagicMock(status_code=200, json=lambda: {"id": "build-1"})
                result = api.start_workspace("ws-1")
    assert result["id"] == "build-1"


def test_stop_workspace_success(set_coder_env):
    api = coder_module.CoderAPI()
    ws = {"id": "ws-1", "template_active_version_id": "v1"}
    with patch("requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: ws)
        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200, json=lambda: {"id": "build-2"})
            result = api.stop_workspace("ws-1")
    assert result["id"] == "build-2"


# ---------------------------------------------------------------------------
# Dormancy
# ---------------------------------------------------------------------------

def test_is_workspace_dormant_true(set_coder_env):
    api = coder_module.CoderAPI()
    with patch.object(api, "get_workspace_metadata", return_value={"dormant_at": "2024-01-01T00:00:00Z"}):
        assert api.is_workspace_dormant("ws-1") is True


def test_is_workspace_dormant_false(set_coder_env):
    api = coder_module.CoderAPI()
    with patch.object(api, "get_workspace_metadata", return_value={"dormant_at": None}):
        assert api.is_workspace_dormant("ws-1") is False


# ---------------------------------------------------------------------------
# create_workspace validation
# ---------------------------------------------------------------------------

def test_create_workspace_requires_template(set_coder_env, monkeypatch):
    monkeypatch.setattr(coder_module, "CODER_TEMPLATE_ID", "")
    api = coder_module.CoderAPI()
    with pytest.raises(ValueError):
        api.create_workspace("alice")


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------

def test_get_users_raises_on_http_error(set_coder_env):
    api = coder_module.CoderAPI()
    with patch("requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=500)
        mock_get.return_value.raise_for_status.side_effect = Exception("boom")
        with pytest.raises(Exception):
            api.get_users()


# ---------------------------------------------------------------------------
# _get_all_templates
# ---------------------------------------------------------------------------

def test_get_all_templates(set_coder_env):
    api = coder_module.CoderAPI()
    with patch("requests.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"templates": [{"id": "t1"}]},
        )
        templates = api._get_all_templates()
    assert templates == {"templates": [{"id": "t1"}]}


# ---------------------------------------------------------------------------
# create_user
# ---------------------------------------------------------------------------

def test_create_user(set_coder_env):
    api = coder_module.CoderAPI()
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=201,
            json=lambda: {"id": "user-1", "username": "alice"},
        )
        user = api.create_user("alice", "alice@pad.test", "Alice")
    assert user["username"] == "alice"
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["json"]["username"] == "alice"
    assert call_kwargs["json"]["email"] == "alice@pad.test"
    assert call_kwargs["json"]["name"] == "Alice"
    assert call_kwargs["headers"]["Content-Type"] == "application/json"


def test_create_user_without_name(set_coder_env):
    api = coder_module.CoderAPI()
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=201, json=lambda: {"id": "user-1"})
        api.create_user("alice", "alice@pad.test", None)
    assert "name" not in mock_post.call_args.kwargs["json"]


# ---------------------------------------------------------------------------
# ensure_user_exists edge cases
# ---------------------------------------------------------------------------

def test_ensure_user_exists_empty_username_base(set_coder_env):
    api = coder_module.CoderAPI()
    with patch.object(api, "get_user_by_email", return_value=None):
        with patch.object(api, "check_username_exists", return_value=False):
            with patch.object(api, "create_user", return_value={"username": "user123"}) as create:
                api.ensure_user_exists({"email": "@pad.test", "name": "No Local"})
    assert create.call_args[0][0].startswith("user")


def test_ensure_user_exists_exhausted_username_attempts(set_coder_env):
    api = coder_module.CoderAPI()
    with patch.object(api, "get_user_by_email", return_value=None):
        with patch.object(api, "check_username_exists", return_value=True):
            with pytest.raises(Exception, match="failed to create unique username"):
                api.ensure_user_exists({"email": "alice@pad.test"})


# ---------------------------------------------------------------------------
# Workspace metadata
# ---------------------------------------------------------------------------

def test_get_workspace_metadata(set_coder_env):
    api = coder_module.CoderAPI()
    with patch("requests.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"id": "ws-1", "dormant_at": None},
        )
        metadata = api.get_workspace_metadata("ws-1")
    assert metadata["id"] == "ws-1"


# ---------------------------------------------------------------------------
# ensure_workspace_exists
# ---------------------------------------------------------------------------

def test_ensure_workspace_exists_when_present(set_coder_env):
    api = coder_module.CoderAPI()
    with patch.object(api, "get_workspace_status_for_user", return_value={"id": "ws-1"}):
        with patch.object(api, "create_workspace") as create:
            api.ensure_workspace_exists("alice")
    create.assert_not_called()


# ---------------------------------------------------------------------------
# Start workspace dormancy
# ---------------------------------------------------------------------------

def test_start_workspace_wakes_dormant_workspace(set_coder_env):
    api = coder_module.CoderAPI()
    ws = {"id": "ws-1", "template_active_version_id": "v1"}
    with patch.object(api, "is_workspace_dormant", return_value=True):
        with patch.object(api, "set_workspace_dormancy") as set_dormant:
            with patch("requests.get") as mock_get:
                mock_get.return_value = MagicMock(status_code=200, json=lambda: ws)
                with patch("requests.post") as mock_post:
                    mock_post.return_value = MagicMock(status_code=200, json=lambda: {"id": "build-1"})
                    result = api.start_workspace("ws-1")
    assert result["id"] == "build-1"
    set_dormant.assert_called_once_with("ws-1", False)


# ---------------------------------------------------------------------------
# create_workspace success
# ---------------------------------------------------------------------------

def test_create_workspace_success(set_coder_env):
    api = coder_module.CoderAPI()
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=201,
            json=lambda: {"id": "ws-1", "name": "ubuntu"},
        )
        ws = api.create_workspace("alice", parameter_values=[{"name": "region", "value": "us"}])
    assert ws["id"] == "ws-1"
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["json"]["name"] == "ubuntu"
    assert call_kwargs["json"]["template_id"] == "template-uuid"
    assert call_kwargs["json"]["rich_parameter_values"] == [{"name": "region", "value": "us"}]


# ---------------------------------------------------------------------------
# set_workspace_dormancy
# ---------------------------------------------------------------------------

def test_set_workspace_dormancy(set_coder_env):
    api = coder_module.CoderAPI()
    with patch("requests.put") as mock_put:
        mock_put.return_value = MagicMock(
            status_code=200,
            json=lambda: {"dormant": True},
        )
        result = api.set_workspace_dormancy("ws-1", True)
    assert result["dormant"] is True


# ---------------------------------------------------------------------------
# list_workspaces
# ---------------------------------------------------------------------------

def test_list_workspaces(set_coder_env):
    api = coder_module.CoderAPI()
    with patch("requests.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"workspaces": [{"id": "ws-1"}]},
        )
        result = api.list_workspaces(query="alice", limit=10, offset=5)
    assert result["workspaces"][0]["id"] == "ws-1"
    call_kwargs = mock_get.call_args.kwargs
    assert call_kwargs["params"] == {"q": "alice", "limit": 10, "offset": 5}


# ---------------------------------------------------------------------------
# delete_workspace
# ---------------------------------------------------------------------------

def test_delete_workspace(set_coder_env):
    api = coder_module.CoderAPI()
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"id": "build-delete"},
        )
        result = api.delete_workspace("ws-1")
    assert result["id"] == "build-delete"
    assert mock_post.call_args.kwargs["json"]["transition"] == "delete"


# ---------------------------------------------------------------------------
# cleanse_workspaces
# ---------------------------------------------------------------------------

def test_cleanse_workspaces_deletes_due_workspaces(set_coder_env):
    api = coder_module.CoderAPI()
    future = datetime.now() + timedelta(days=-1)
    workspaces = {
        "workspaces": [
            {
                "id": "ws-old",
                "owner_name": "alice",
                "deleting_at": future.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            }
        ]
    }
    with patch.object(api, "list_workspaces", return_value=workspaces):
        with patch.object(api, "delete_workspace") as delete:
            api.cleanse_workspaces(days_until_deleting=30)
    delete.assert_called_once_with("ws-old")
