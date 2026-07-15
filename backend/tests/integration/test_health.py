# integration tests for GET /api/health ready and not-ready paths
from __future__ import annotations

import asyncio
import logging
import shutil
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from app.api.routes.health import RELEASE_SCENARIO_FILENAME
from app.core.config import Settings, clear_settings_cache
from app.main import create_app
from app.schemas.api import HealthResponse
from fastapi.testclient import TestClient
from tests.conftest import make_valid_layout, settings_from_layout


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    clear_settings_cache()
    yield
    clear_settings_cache()


def _assert_no_absolute_paths(payload: dict[str, object]) -> None:
    for value in payload.values():
        if isinstance(value, str):
            assert not value.startswith("/")
            assert ":\\" not in value
            assert not (len(value) >= 3 and value[1] == ":" and value[2] == "\\")


def test_ready_health_returns_200(valid_settings: Settings) -> None:
    app = create_app(settings_override=valid_settings)
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    body = HealthResponse.model_validate(response.json())
    assert body.status == "ok"
    assert body.simulator_ready is True
    _assert_no_absolute_paths(response.json())


def test_ready_health_does_not_launch_subprocess(
    valid_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = MagicMock(side_effect=AssertionError("subprocess must not run"))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)
    app = create_app(settings_override=valid_settings)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
    spy.assert_not_called()


def test_not_ready_when_binary_removed(
    valid_layout: dict[str, Path], caplog: pytest.LogCaptureFixture
) -> None:
    settings = settings_from_layout(valid_layout)
    app = create_app(settings_override=settings)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        settings.sim_binary.unlink()
        with caplog.at_level(logging.WARNING, logger="ares.health"):
            response = client.get("/api/health")
    assert response.status_code == 503
    body = HealthResponse.model_validate(response.json())
    assert body.status == "degraded"
    assert body.simulator_ready is False
    assert "simulator prerequisites unavailable" in body.message
    _assert_no_absolute_paths(response.json())
    assert "SIM_BINARY_MISSING" in caplog.text
    assert "Traceback" not in response.text


def test_not_ready_when_release_scenario_removed(valid_layout: dict[str, Path]) -> None:
    settings = settings_from_layout(valid_layout)
    app = create_app(settings_override=settings)
    scenario_file = settings.scenario_dir / RELEASE_SCENARIO_FILENAME
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        scenario_file.unlink()
        response = client.get("/api/health")
    assert response.status_code == 503
    body = HealthResponse.model_validate(response.json())
    assert body.status == "degraded"
    assert body.simulator_ready is False
    _assert_no_absolute_paths(response.json())


def test_not_ready_when_runs_dir_replaced_with_file(valid_layout: dict[str, Path]) -> None:
    settings = settings_from_layout(valid_layout)
    app = create_app(settings_override=settings)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        shutil.rmtree(settings.runs_dir)
        settings.runs_dir.write_text("not-a-dir", encoding="utf-8")
        response = client.get("/api/health")
    assert response.status_code == 503
    body = HealthResponse.model_validate(response.json())
    assert body.status == "degraded"
    assert body.simulator_ready is False
    _assert_no_absolute_paths(response.json())
    assert "OSError" not in response.text
    assert str(settings.runs_dir) not in response.text


def test_not_ready_does_not_launch_subprocess(
    valid_layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = settings_from_layout(valid_layout)
    spy = MagicMock(side_effect=AssertionError("subprocess must not run"))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)
    app = create_app(settings_override=settings)
    with TestClient(app) as client:
        settings.sim_binary.unlink()
        assert client.get("/api/health").status_code == 503
    spy.assert_not_called()


def test_layout_helper_smoke(tmp_path: Path) -> None:
    layout = make_valid_layout(tmp_path)
    assert (layout["scenario_dir"] / RELEASE_SCENARIO_FILENAME).is_file()
