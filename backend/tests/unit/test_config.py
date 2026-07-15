# unit tests for Settings path resolution and validation
from __future__ import annotations

import math
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from app.core.config import BACKEND_ROOT, Settings, clear_settings_cache, get_settings
from pydantic import ValidationError
from tests.conftest import REPO_ROOT, make_valid_layout, settings_from_layout


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    clear_settings_cache()
    yield
    clear_settings_cache()


def test_windows_style_simulator_path_resolves(tmp_path: Path) -> None:
    layout = make_valid_layout(tmp_path)
    settings = settings_from_layout(layout)
    assert settings.sim_binary.is_file()
    assert settings.sim_binary.name == "sim_core.exe"
    assert settings.sim_binary.is_absolute()


def test_project_root_and_scenario_dir_resolve(tmp_path: Path) -> None:
    layout = make_valid_layout(tmp_path)
    settings = settings_from_layout(layout)
    assert settings.project_root.is_dir()
    assert settings.scenario_dir.is_dir()
    assert settings.scenario_dir.is_relative_to(settings.project_root)


def test_missing_runs_directory_is_created(tmp_path: Path) -> None:
    layout = make_valid_layout(tmp_path)
    runs_dir = tmp_path / "new_runs"
    assert not runs_dir.exists()
    settings = settings_from_layout(layout, runs_dir=runs_dir)
    assert settings.runs_dir.is_dir()
    assert settings.runs_dir == runs_dir.resolve()


def test_runs_directory_is_writable(tmp_path: Path) -> None:
    layout = make_valid_layout(tmp_path)
    settings = settings_from_layout(layout)
    probe = settings.runs_dir / "post_create.txt"
    probe.write_text("ok", encoding="utf-8")
    assert probe.read_text(encoding="utf-8") == "ok"


@pytest.mark.parametrize("timeout", [0.1, 1.0, 30.0, 120])
def test_timeout_accepts_positive_finite(tmp_path: Path, timeout: float) -> None:
    layout = make_valid_layout(tmp_path)
    settings = settings_from_layout(layout, sim_timeout_seconds=timeout)
    assert settings.sim_timeout_seconds == float(timeout)


@pytest.mark.parametrize("concurrency", [1, 2, 8])
def test_concurrency_accepts_positive_integers(tmp_path: Path, concurrency: int) -> None:
    layout = make_valid_layout(tmp_path)
    settings = settings_from_layout(layout, max_concurrent_runs=concurrency)
    assert settings.max_concurrent_runs == concurrency


@pytest.mark.parametrize("level", ["DEBUG", "info", "Warning", "ERROR", "CRITICAL"])
def test_valid_log_levels_accepted(tmp_path: Path, level: str) -> None:
    layout = make_valid_layout(tmp_path)
    settings = settings_from_layout(layout, log_level=level)
    assert settings.log_level == level.upper()


def test_relative_paths_resolve_independently_of_cwd(tmp_path: Path) -> None:
    original = Path.cwd()
    relative_kwargs = {
        "project_root": Path(".."),
        "sim_binary": Path("../Simulator/build/sim_core.exe"),
        "scenario_dir": Path("../scenarios"),
        "runs_dir": tmp_path / "cwd_runs",
        "sim_timeout_seconds": 30.0,
        "max_concurrent_runs": 2,
        "log_level": "INFO",
    }
    try:
        os.chdir(REPO_ROOT)
        from_repo = Settings(_env_file=None, **relative_kwargs)
        os.chdir(BACKEND_ROOT)
        from_backend = Settings(_env_file=None, **relative_kwargs)
        os.chdir(tmp_path)
        from_tmp = Settings(_env_file=None, **relative_kwargs)
    finally:
        os.chdir(original)

    assert from_repo.project_root == from_backend.project_root == from_tmp.project_root
    assert from_repo.sim_binary == from_backend.sim_binary == from_tmp.sim_binary
    assert from_repo.scenario_dir == from_backend.scenario_dir == from_tmp.scenario_dir
    assert from_repo.runs_dir == from_backend.runs_dir == from_tmp.runs_dir


def test_settings_from_kwargs_without_env_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ARES_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("ARES_SIM_BINARY", raising=False)
    layout = make_valid_layout(tmp_path)
    settings = settings_from_layout(layout)
    assert settings.project_root == layout["project_root"].resolve()
    assert "ARES_PROJECT_ROOT" not in os.environ


def test_missing_project_root_rejected(tmp_path: Path) -> None:
    layout = make_valid_layout(tmp_path)
    with pytest.raises(ValidationError):
        settings_from_layout(layout, project_root=tmp_path / "missing_root")


def test_project_root_file_rejected(tmp_path: Path) -> None:
    layout = make_valid_layout(tmp_path)
    as_file = tmp_path / "project_as_file"
    as_file.write_text("x", encoding="utf-8")
    with pytest.raises(ValidationError):
        settings_from_layout(layout, project_root=as_file)


def test_missing_simulator_binary_rejected(tmp_path: Path) -> None:
    layout = make_valid_layout(tmp_path)
    missing = layout["sim_binary"].parent / "missing_sim.exe"
    with pytest.raises(ValidationError):
        settings_from_layout(layout, sim_binary=missing)


def test_simulator_path_directory_rejected(tmp_path: Path) -> None:
    layout = make_valid_layout(tmp_path)
    with pytest.raises(ValidationError):
        settings_from_layout(layout, sim_binary=layout["sim_binary"].parent)


def test_missing_scenario_directory_rejected(tmp_path: Path) -> None:
    layout = make_valid_layout(tmp_path)
    with pytest.raises(ValidationError):
        settings_from_layout(layout, scenario_dir=tmp_path / "no_scenarios")


def test_scenario_path_file_rejected(tmp_path: Path) -> None:
    layout = make_valid_layout(tmp_path)
    as_file = tmp_path / "scenario_file"
    as_file.write_text("x", encoding="utf-8")
    with pytest.raises(ValidationError):
        settings_from_layout(layout, scenario_dir=as_file)


def test_runs_path_collides_with_file(tmp_path: Path) -> None:
    layout = make_valid_layout(tmp_path)
    as_file = tmp_path / "runs_as_file"
    as_file.write_text("x", encoding="utf-8")
    with pytest.raises(ValidationError):
        settings_from_layout(layout, runs_dir=as_file)


def test_unwritable_runs_rejected_via_probe_mock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = make_valid_layout(tmp_path)
    runs_dir = tmp_path / "locked_runs"
    runs_dir.mkdir()

    original_write_text = Path.write_text

    def _fail_probe(self: Path, *args: object, **kwargs: object) -> None:
        if self.parent == runs_dir.resolve() and self.name.startswith(".ares_write_probe_"):
            raise OSError("simulated unwritable")
        original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", _fail_probe)
    with pytest.raises(ValidationError):
        settings_from_layout(layout, runs_dir=runs_dir)


@pytest.mark.parametrize("timeout", [0, -1.0, float("nan"), float("inf"), -float("inf")])
def test_timeout_rejects_invalid(tmp_path: Path, timeout: float) -> None:
    layout = make_valid_layout(tmp_path)
    with pytest.raises(ValidationError):
        settings_from_layout(layout, sim_timeout_seconds=timeout)


def test_timeout_rejects_nan_string(tmp_path: Path) -> None:
    layout = make_valid_layout(tmp_path)
    with pytest.raises(ValidationError):
        settings_from_layout(layout, sim_timeout_seconds="nan")


@pytest.mark.parametrize("concurrency", [0, -1, True, False, 1.5, "2.0"])
def test_concurrency_rejects_invalid(tmp_path: Path, concurrency: object) -> None:
    layout = make_valid_layout(tmp_path)
    with pytest.raises(ValidationError):
        settings_from_layout(layout, max_concurrent_runs=concurrency)


def test_invalid_log_level_rejected(tmp_path: Path) -> None:
    layout = make_valid_layout(tmp_path)
    with pytest.raises(ValidationError):
        settings_from_layout(layout, log_level="VERBOSE")


def test_wrong_configured_path_does_not_fallback(tmp_path: Path) -> None:
    layout = make_valid_layout(tmp_path)
    wrong = tmp_path / "wrong" / "sim_core.exe"
    wrong.parent.mkdir(parents=True)
    # do not create the file; real layout binary remains valid elsewhere
    with pytest.raises(ValidationError):
        settings_from_layout(layout, sim_binary=wrong)


def test_settings_are_frozen(tmp_path: Path) -> None:
    layout = make_valid_layout(tmp_path)
    settings = settings_from_layout(layout)
    with pytest.raises(ValidationError):
        settings.log_level = "DEBUG"  # type: ignore[misc]


def test_get_settings_cache_roundtrip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    layout = make_valid_layout(tmp_path)
    monkeypatch.setenv("ARES_PROJECT_ROOT", str(layout["project_root"]))
    monkeypatch.setenv("ARES_SIM_BINARY", str(layout["sim_binary"]))
    monkeypatch.setenv("ARES_SCENARIO_DIR", str(layout["scenario_dir"]))
    monkeypatch.setenv("ARES_RUNS_DIR", str(layout["runs_dir"]))
    monkeypatch.setenv("ARES_SIM_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("ARES_MAX_CONCURRENT_RUNS", "2")
    monkeypatch.setenv("ARES_LOG_LEVEL", "INFO")
    clear_settings_cache()
    first = get_settings()
    second = get_settings()
    assert first is second
    assert math.isclose(first.sim_timeout_seconds, 30.0)
