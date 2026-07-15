# integration tests for application factory and OpenAPI scope
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.config import Settings, clear_settings_cache
from app.main import create_app
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from tests.conftest import make_valid_layout, settings_from_layout


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Any:
    clear_settings_cache()
    yield
    clear_settings_cache()


def test_create_app_returns_fastapi(valid_settings: Settings) -> None:
    app = create_app(settings_override=valid_settings)
    assert isinstance(app, FastAPI)


def test_create_app_uses_settings_override(tmp_path: Any, valid_settings: Settings) -> None:
    other_layout = make_valid_layout(tmp_path / "other")
    other = settings_from_layout(other_layout)
    app = create_app(settings_override=other)
    assert app.state.settings is other
    assert app.state.settings is not valid_settings


def test_lifespan_starts_with_valid_prerequisites(valid_settings: Settings) -> None:
    app = create_app(settings_override=valid_settings)
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert app.state.startup_readiness.ready is True


def test_startup_does_not_call_create_subprocess_exec(
    valid_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = MagicMock(side_effect=AssertionError("subprocess must not run"))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)
    app = create_app(settings_override=valid_settings)
    with TestClient(app) as client:
        client.get("/api/health")
    spy.assert_not_called()


def test_docs_and_openapi_available(valid_settings: Settings) -> None:
    app = create_app(settings_override=valid_settings)
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 200
        openapi = client.get("/openapi.json")
        assert openapi.status_code == 200
        payload = openapi.json()
        paths = payload["paths"]
        assert "/api/health" in paths
        assert "/api/sim/run" in paths
        assert payload["info"]["title"] == "ARES-1 Phase 1 Backend"
        assert payload["info"]["version"] == "0.1.0"
        description = payload["info"].get("description", "").lower()
        assert "nvidia" not in description
        assert "rag" not in description
        assert "websocket" not in description
        sim_post = paths["/api/sim/run"]["post"]
        assert "failure" in sim_post.get("description", "").lower()
        assert "rejected" in sim_post.get("description", "").lower()


def test_no_wildcard_cors_middleware(valid_settings: Settings) -> None:
    app = create_app(settings_override=valid_settings)
    cors_middlewares = [
        m for m in app.user_middleware if m.cls is CORSMiddleware
    ]
    assert cors_middlewares == []
    for middleware in app.user_middleware:
        options = getattr(middleware, "kwargs", {}) or {}
        assert options.get("allow_origins") != ["*"]
