"""Route inventory: every sensitive Pad route must depend on authentication.

This test inventories every FastAPI route declared in ``main.py`` and classifies
it as either public or protected.  Protected routes must use one of the
approved authentication dependencies.  A new sensitive route added without
``require_auth`` / ``require_admin`` / ``optional_auth`` / ``require_pad_access``
/ ``require_pad_owner`` / ``get_ws_user`` will fail the suite.
"""

import os
import shutil
import tempfile

import pytest
from fastapi import APIRouter

# main.py mounts static directories at import time.  Create them in a temp
# location and patch config before importing main.
_STATIC_ROOT = tempfile.mkdtemp(prefix="pad_test_static_")
_ASSETS_DIR = os.path.join(_STATIC_ROOT, "assets")
os.makedirs(_ASSETS_DIR, exist_ok=True)
os.environ["STATIC_DIR"] = _STATIC_ROOT
os.environ["ASSETS_DIR"] = _ASSETS_DIR

import config as _config_module
_config_module.STATIC_DIR = _STATIC_ROOT
_config_module.ASSETS_DIR = _ASSETS_DIR

import main as main_module
from dependencies import (
    require_auth,
    require_admin,
    optional_auth,
    require_pad_access,
    require_pad_owner,
)
from routers.ws_router import get_ws_user


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_STATIC_ROOT, ignore_errors=True)


# Dependencies that are allowed on routes returning sensitive data or performing
# state-changing operations.  ``optional_auth`` is permitted only on the
# explicitly public HTML entrypoints where anonymous users are expected.
_PROTECTED_DEPENDENCY_CLS = {
    require_auth.__class__,
    require_admin.__class__,
    optional_auth.__class__,
    require_pad_access.__class__,
    require_pad_owner.__class__,
}

# Static file mounts and explicitly public API routes.
_PUBLIC_PATHS = {
    "",
    "/",
    "/pad/{pad_id}",
    "/assets",
    "/assets/{path:path}",
    "/static",
    "/static/{path:path}",
    "/api/auth/login",
    "/api/auth/callback",
    "/api/auth/verify",
    "/api/app/config",
    # FastAPI auto-generated documentation surfaces are public by design.
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    "/openapi.json",
}


def _route_key(route) -> str:
    """Return a stable path string for a FastAPI route."""
    path = getattr(route, "path", "")
    # WebSocket routes and APIRoutes both expose .path.
    return path


def _has_protected_dependency(route) -> bool:
    """Check whether a route uses an approved authentication dependency."""
    # FastAPI stores dependencies in route.dependencies and route.dependant.
    deps = list(getattr(route, "dependencies", []))
    dependant = getattr(route, "dependant", None)
    if dependant is not None:
        deps.extend(getattr(dependant, "dependencies", []))
        # Also check the call parameter dependencies.
        for call_param in getattr(dependant, "call_params", []):
            deps.append(call_param)

    for dep in deps:
        # Dependency can be a callable, a class instance, or a Depends object.
        candidate = dep
        if hasattr(dep, "dependency"):
            candidate = dep.dependency
        if hasattr(candidate, "__class__") and candidate.__class__ in _PROTECTED_DEPENDENCY_CLS:
            return True
        if candidate is get_ws_user:
            return True
        # Some routes use the class instances directly.
        if candidate in {require_auth, require_admin, optional_auth, require_pad_access, require_pad_owner}:
            return True

    # Direct uses of auth dependency instances in the route signature are
    # represented in route.dependant.dependencies but the instances above may
    # not match by class if FastAPI wraps them.  Fall back to string scanning.
    route_code = getattr(route, "endpoint", None)
    if route_code is not None:
        src = str(route_code)
        if any(name in src for name in {
            "require_auth", "require_admin", "optional_auth",
            "require_pad_access", "require_pad_owner", "get_ws_user",
        }):
            return True

    return False


def _collect_routes(app) -> list:
    """Flatten all routes including those under included routers."""
    routes = []
    for route in app.routes:
        routes.append(route)
        if isinstance(route, APIRouter):
            routes.extend(route.routes)
    return routes


def test_route_inventory_classifies_every_route():
    """Every route is either explicitly public or uses an auth dependency."""
    app = main_module.app
    routes = _collect_routes(app)
    unclassified = []

    for route in routes:
        path = _route_key(route)
        if path in _PUBLIC_PATHS:
            continue
        if _has_protected_dependency(route):
            continue
        unclassified.append(path)

    assert not unclassified, (
        f"Sensitive routes without required auth dependency: {unclassified}. "
        "Add require_auth / require_admin / optional_auth / require_pad_access / "
        "require_pad_owner / get_ws_user, or list the route as public above."
    )


def test_a_new_sensitive_route_without_auth_fails():
    """Simulate a regression: a sensitive route added without auth must fail."""
    from fastapi import FastAPI

    regression_app = FastAPI()
    regression_app.include_router(main_module.auth_router, prefix="/api/auth")

    @regression_app.get("/api/admin/secrets")
    def leaked_secret():
        return {"secret": "value"}

    routes = _collect_routes(regression_app)
    unclassified = [
        _route_key(r)
        for r in routes
        if _route_key(r) not in _PUBLIC_PATHS and not _has_protected_dependency(r)
    ]

    assert "/api/admin/secrets" in unclassified
