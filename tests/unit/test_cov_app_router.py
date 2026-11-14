"""Unit tests for the app router runtime config endpoint."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import app_router


def test_get_app_config():
    app = FastAPI()
    app.include_router(app_router.app_router, prefix="/api/app")
    client = TestClient(app)
    response = client.get("/api/app/config")
    assert response.status_code == 200
    data = response.json()
    assert "coderUrl" in data
    assert "posthogKey" in data
    assert "posthogHost" in data
    assert "devMode" in data
