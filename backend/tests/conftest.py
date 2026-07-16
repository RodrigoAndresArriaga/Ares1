# shared fixture loaders for immutable Section 7 evidence
# Section 9 temp layout helpers for Settings / app tests
# Section 10/11 release-scenario helpers for registry and run-store tests
from __future__ import annotations

import hashlib
import json
import os
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
REAL_BINARY = REPO_ROOT / "Simulator" / "build" / "sim_core.exe"

BASELINE_SHA256 = "C9EAE8F26A37E6D3587038A49984548C0BFF2DEE8367D91C29CFEB76C13A4A79"
VALID_RESULT_SHA256 = "A2662DE223878CCB03723063DF5987D933251547B4D8F3FB96499CB3B2EB112C"
INVALID_RESULT_SHA256 = "7D9D09FCAC6A0D504F4EE8A9AF6AC89A837E3345B258940CB83A0C1A0AA05CC1"

FIXTURE_SHA256_BY_NAME = {
    "baseline_result.json": BASELINE_SHA256,
    "valid_plan_result.json": VALID_RESULT_SHA256,
    "invalid_plan_result.json": INVALID_RESULT_SHA256,
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# uppercase SHA-256 of file bytes
def sha256_hex_upper(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest().upper()


# true when frozen release executable exists and is non-empty
def real_binary_available() -> bool:
    return REAL_BINARY.is_file() and REAL_BINARY.stat().st_size > 0


# skip unless binary present; fail hard when release gate requires it
def require_real_simulator() -> None:
    if real_binary_available():
        return
    if os.environ.get("ARES_REQUIRE_REAL_SIMULATOR") == "1":
        pytest.fail(
            "ARES_REQUIRE_REAL_SIMULATOR=1 but frozen simulator "
            f"executable is missing: {REAL_BINARY}",
        )
    pytest.skip("frozen simulator executable not present")


# resolve NVIDIA API key from env or backend/.env without printing it
def resolve_nvidia_api_key() -> str | None:
    from_env = os.environ.get("ARES_NVIDIA_API_KEY")
    if from_env is not None and from_env.strip():
        return from_env.strip()
    env_path = BACKEND_ROOT / ".env"
    if not env_path.is_file():
        return None
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        for prefix in (
            "ARES_NVIDIA_API_KEY=",
            "nvidia_api_key=",
            "NVIDIA_API_KEY=",
            "ARES_NVIDIA_API_KEY:",
            "nvidia_api_key:",
            "NVIDIA_API_KEY:",
        ):
            if line.startswith(prefix):
                value = line[len(prefix) :].strip().strip('"').strip("'")
                return value if value else None
    return None


# true when a usable NVIDIA API key is configured
def real_nim_available() -> bool:
    return resolve_nvidia_api_key() is not None


# skip unless API key present; fail hard when release gate requires it
def require_real_nim() -> None:
    if real_nim_available():
        return
    if os.environ.get("ARES_REQUIRE_REAL_NIM") == "1":
        pytest.fail(
            "ARES_REQUIRE_REAL_NIM=1 but NVIDIA API key not configured",
        )
    pytest.skip("NVIDIA API key not configured")


# copy exact release scenario bytes into an isolated scenario directory
def install_release_scenario(scenario_dir: Path) -> Path:
    scenario_dir.mkdir(parents=True, exist_ok=True)
    dest = scenario_dir / RELEASE_SCENARIO_FILENAME
    shutil.copyfile(RELEASE_SCENARIO_PATH, dest)
    return dest


# isolated Settings wired to the frozen release binary under tmp_path
def make_real_app_settings(
    tmp_path: Path,
    *,
    max_concurrent_runs: int = 1,
    sim_timeout_seconds: float = 120.0,
) -> Settings:
    project_root = tmp_path / "project"
    scenario_dir = project_root / "scenarios"
    install_release_scenario(scenario_dir)
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    return Settings(
        _env_file=None,
        project_root=project_root,
        sim_binary=REAL_BINARY,
        scenario_dir=scenario_dir,
        runs_dir=runs_dir,
        sessions_dir=sessions_dir,
        sim_timeout_seconds=sim_timeout_seconds,
        max_concurrent_runs=max_concurrent_runs,
        log_level="INFO",
    )


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
    sessions_dir = root / "sessions"
    sim_binary.parent.mkdir(parents=True, exist_ok=True)
    sim_binary.write_bytes(b"")
    scenario_dir.mkdir(parents=True, exist_ok=True)
    (scenario_dir / RELEASE_SCENARIO_FILENAME).write_text("{}", encoding="utf-8")
    runs_dir.mkdir(parents=True, exist_ok=True)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    return {
        "project_root": project_root,
        "sim_binary": sim_binary,
        "scenario_dir": scenario_dir,
        "runs_dir": runs_dir,
        "sessions_dir": sessions_dir,
    }


# construct Settings from an isolated layout without reading process .env
def settings_from_layout(layout: dict[str, Path], **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "project_root": layout["project_root"],
        "sim_binary": layout["sim_binary"],
        "scenario_dir": layout["scenario_dir"],
        "runs_dir": layout["runs_dir"],
        "sessions_dir": layout["sessions_dir"],
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


# Settings with the real release scenario bytes (mission create needs resolve)
def make_mission_settings(tmp_path: Path, **overrides: Any) -> Settings:
    layout = make_valid_layout(tmp_path)
    install_release_scenario(layout["scenario_dir"])
    return settings_from_layout(layout, **overrides)


# AsyncMock SimulationService that returns a fixture-backed run response
def make_fake_simulation_service(
    result_data: Any,
    *,
    run_id: str = "00000000-0000-4000-8000-000000000001",
    duration_ms: int = 25,
) -> Any:
    from unittest.mock import AsyncMock

    from app.schemas.api import SimulationRunResponse
    from app.schemas.result import SimulationResult
    from app.services.simulation_service import SimulationService

    service = AsyncMock(spec=SimulationService)
    service.run_simulation = AsyncMock(
        return_value=SimulationRunResponse(
            run_id=run_id,
            duration_ms=duration_ms,
            result=SimulationResult.model_validate(result_data),
        ),
    )
    return service


# seed a completed run workspace for persisted-result HTTP tests
def seed_completed_run(
    store: Any,
    result_fixture: Path,
    *,
    request: Any | None = None,
) -> Any:
    from app.services.run_store import sha256_file

    req = request if request is not None else make_baseline_request()
    workspace = store.create_workspace(req, RELEASE_SCENARIO_PATH)
    result_bytes = result_fixture.read_bytes()
    workspace.result_path.write_bytes(result_bytes)
    outcome = json.loads(result_bytes.decode("utf-8"))["outcome"]
    store.write_completed_metadata(
        workspace,
        result_sha256=sha256_file(workspace.result_path),
        process_exit_code=0,
        duration_ms=1,
        outcome=outcome,
    )
    return workspace


PLANNER_SESSION_ID = "00000000-0000-4000-8000-000000000010"
PLANNER_BASELINE_RUN_ID = "00000000-0000-4000-8000-000000000001"


def make_planner_model_metadata() -> Any:
    from app.schemas.planner import PlannerModelMetadata

    return PlannerModelMetadata(
        provider="nvidia",
        model_id="nvidia/llama-3.3-nemotron-super-49b-v1",
        model_revision="1.0",
    )


def make_planner_retrieval_result(**overrides: Any) -> Any:
    from app.schemas.actions import ActionType
    from app.schemas.embedding import EmbeddingModelDescriptor, RerankerModelDescriptor
    from app.schemas.retrieval import (
        CORPUS_SCHEMA_VERSION,
        EvidenceReference,
        ProcedureChunk,
        ProcedureStatus,
        SourceClassification,
    )
    from app.schemas.retrieval_query import (
        RETRIEVAL_QUERY_SCHEMA_VERSION,
        ProcedureRetrievalMatch,
        ProcedureRetrievalResult,
    )

    sha = "a" * 64
    sha_b = "b" * 64
    sha_c = "c" * 64
    sha_d = "d" * 64
    sha_e = "e" * 64
    chunk = ProcedureChunk.model_validate(
        {
            "schema_version": CORPUS_SCHEMA_VERSION,
            "chunk_id": sha,
            "procedure_id": "ARES-PROC-OXY-001",
            "procedure_title": "Oxygen Leak Response",
            "manual_path": "docs/procedures/manuals/oxygen_leak.md",
            "section_path": ("Purpose",),
            "section_title": "Purpose",
            "chunk_index": 0,
            "content": "Verify cabin pressure and isolate affected module.",
            "embedding_text": "Procedure: Oxygen Leak Response\n\nVerify cabin pressure.",
            "content_sha256": sha_b,
            "manual_sha256": sha_c,
            "source_classifications": (SourceClassification.ARES_ASSUMPTION,),
            "evidence_references": (
                EvidenceReference(
                    evidence_id="EVID-ARES_ASM-001",
                    classification=SourceClassification.ARES_ASSUMPTION,
                    source_title="Test",
                    locator="unit-test",
                    supports="Unit test evidence.",
                    url="",
                ),
            ),
            "allowed_actions": (ActionType.ISOLATE_MODULE,),
            "procedure_status": ProcedureStatus.PARTIAL_EVIDENCE,
        },
    )
    match = ProcedureRetrievalMatch.model_validate(
        {
            "rank": 1,
            "similarity": 0.91,
            "rerank_score": 2.5,
            "index_position": 0,
            "chunk_id": chunk.chunk_id,
            "chunk": chunk,
        },
    )
    payload: dict[str, Any] = {
        "schema_version": RETRIEVAL_QUERY_SCHEMA_VERSION,
        "query": "oxygen leak isolate module",
        "requested_top_k": 1,
        "returned_count": 1,
        "embedding_model": EmbeddingModelDescriptor(
            provider="nvidia",
            model_id="nvidia/llama-nemotron-embed-1b-v2",
            model_revision=None,
            dimensions=2048,
        ),
        "reranker_model": RerankerModelDescriptor(
            provider="nvidia",
            model_id="nvidia/llama-nemotron-rerank-1b-v2",
            model_revision=None,
        ),
        "corpus_sha256": sha_d,
        "index_sha256": sha_e,
        "matches": (match,),
    }
    payload.update(overrides)
    return ProcedureRetrievalResult.model_validate(payload)


def make_planner_mission_context(
    baseline_result_data: Any,
    *,
    sample_index: int = 0,
) -> Any:
    from app.schemas.planner import PlannerMissionContext
    from app.schemas.result import OutcomeStatus, SimulationMetrics
    from app.schemas.telemetry import TelemetrySample

    history = baseline_result_data["telemetry_history"]
    return PlannerMissionContext(
        session_id=PLANNER_SESSION_ID,
        scenario_id=baseline_result_data["scenario_id"],
        baseline_run_id=PLANNER_BASELINE_RUN_ID,
        baseline_outcome=OutcomeStatus(baseline_result_data["outcome"]),
        baseline_failure_reasons=list(baseline_result_data["failure_reasons"]),
        baseline_metrics=SimulationMetrics.model_validate(baseline_result_data["metrics"]),
        current_sample_index=sample_index,
        telemetry_sample_count=len(history),
        current_telemetry=TelemetrySample.model_validate(history[sample_index]),
    )


def make_planner_prompt_input(
    baseline_result_data: Any,
    *,
    sample_index: int = 0,
    retrieval_overrides: dict[str, Any] | None = None,
) -> Any:
    from app.schemas.planner import PlannerPromptInput

    retrieval_kwargs = retrieval_overrides or {}
    return PlannerPromptInput(
        mission_context=make_planner_mission_context(
            baseline_result_data,
            sample_index=sample_index,
        ),
        retrieval_result=make_planner_retrieval_result(**retrieval_kwargs),
    )
