# shared fixture loaders for immutable Section 7 evidence
# Section 9 temp layout helpers for Settings / app tests
# Section 10/11 release-scenario helpers for registry and run-store tests
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from app.api.routes.health import RELEASE_SCENARIO_FILENAME
from app.core.config import Settings
from app.schemas.api import SimulationRunRequest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
RESULTS_DIR = BACKEND_ROOT / "tests" / "fixtures" / "results"
PLANS_DIR = REPO_ROOT / "plans"
SCENARIOS_DIR = REPO_ROOT / "scenarios"

RELEASE_SCENARIO_ID = "mars_hab_atmosphere_solar_failure"
RELEASE_SCENARIO_PATH = SCENARIOS_DIR / RELEASE_SCENARIO_FILENAME
SHARED_SIM_RESULT_PATH = REPO_ROOT / "results" / "sim_result.json"

BASELINE_SHA256 = "C9EAE8F26A37E6D3587038A49984548C0BFF2DEE8367D91C29CFEB76C13A4A79"
VALID_RESULT_SHA256 = "A2662DE223878CCB03723063DF5987D933251547B4D8F3FB96499CB3B2EB112C"
INVALID_RESULT_SHA256 = "7D9D09FCAC6A0D504F4EE8A9AF6AC89A837E3345B258940CB83A0C1A0AA05CC1"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# copy exact release scenario bytes into an isolated scenario directory
def install_release_scenario(scenario_dir: Path) -> Path:
    scenario_dir.mkdir(parents=True, exist_ok=True)
    dest = scenario_dir / RELEASE_SCENARIO_FILENAME
    shutil.copyfile(RELEASE_SCENARIO_PATH, dest)
    return dest


@pytest.fixture(scope="session")
def baseline_result_data() -> Any:
    return _load_json(RESULTS_DIR / "baseline_result.json")


@pytest.fixture(scope="session")
def valid_plan_result_data() -> Any:
    return _load_json(RESULTS_DIR / "valid_plan_result.json")


@pytest.fixture(scope="session")
def invalid_plan_result_data() -> Any:
    return _load_json(RESULTS_DIR / "invalid_plan_result.json")


@pytest.fixture(scope="session")
def sample_plan_data() -> Any:
    return _load_json(PLANS_DIR / "sample_plan.json")


@pytest.fixture(scope="session")
def invalid_plan_data() -> Any:
    return _load_json(PLANS_DIR / "invalid_plan.json")


@pytest.fixture(scope="session")
def all_result_data(
    baseline_result_data: Any,
    valid_plan_result_data: Any,
    invalid_plan_result_data: Any,
) -> list[Any]:
    return [baseline_result_data, valid_plan_result_data, invalid_plan_result_data]


@pytest.fixture(scope="session")
def release_scenario_bytes() -> bytes:
    return RELEASE_SCENARIO_PATH.read_bytes()


# build isolated project/simulator/scenario/runs tree under tmp_path
def make_valid_layout(root: Path) -> dict[str, Path]:
    project_root = root / "project"
    sim_binary = project_root / "Simulator" / "build" / "sim_core.exe"
    scenario_dir = project_root / "scenarios"
    runs_dir = root / "runs"
    sim_binary.parent.mkdir(parents=True, exist_ok=True)
    sim_binary.write_bytes(b"")
    scenario_dir.mkdir(parents=True, exist_ok=True)
    (scenario_dir / RELEASE_SCENARIO_FILENAME).write_text("{}", encoding="utf-8")
    runs_dir.mkdir(parents=True, exist_ok=True)
    return {
        "project_root": project_root,
        "sim_binary": sim_binary,
        "scenario_dir": scenario_dir,
        "runs_dir": runs_dir,
    }


# construct Settings from an isolated layout without reading process .env
def settings_from_layout(layout: dict[str, Path], **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "project_root": layout["project_root"],
        "sim_binary": layout["sim_binary"],
        "scenario_dir": layout["scenario_dir"],
        "runs_dir": layout["runs_dir"],
        "sim_timeout_seconds": 30.0,
        "max_concurrent_runs": 2,
        "log_level": "INFO",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def make_baseline_request() -> SimulationRunRequest:
    return SimulationRunRequest.model_validate(
        {"scenario_id": RELEASE_SCENARIO_ID}
    )


def make_plan_request(plan_data: Any) -> SimulationRunRequest:
    return SimulationRunRequest.model_validate(
        {"scenario_id": RELEASE_SCENARIO_ID, "plan": plan_data}
    )


@pytest.fixture
def valid_layout(tmp_path: Path) -> dict[str, Path]:
    return make_valid_layout(tmp_path)


@pytest.fixture
def valid_settings(valid_layout: dict[str, Path]) -> Settings:
    return settings_from_layout(valid_layout)
