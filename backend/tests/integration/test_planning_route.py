# Phase 5 Step 3 POST /api/missions/{session_id}/plan integration tests
from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from app.core.config import clear_settings_cache
from app.main import create_app
from app.schemas.api import ErrorCode, SimulationRunRequest, SimulationRunResponse
from app.schemas.planning_validation import PlanningSimulationResponse
from app.schemas.result import SimulationResult
from app.services.mission_plan_simulation_service import MissionPlanSimulationService
from fastapi.testclient import TestClient
from tests.conftest import (
    RELEASE_SCENARIO_ID,
    RELEASE_SCENARIO_PATH,
    make_mission_settings,
    make_multi_action_retrieval_result,
)
from tests.unit.test_mission_plan_simulation_service import (
    PersistingFakeSimulationService,
    _candidate_result_data,
)
from tests.unit.test_mission_planning_service import (
    FakeRetrievalService,
    _fake_generate,
)

FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "telemetry_history",
        "system_prompt",
        "user_prompt",
        "raw_response",
        "vectors",
        "survival_probability",
    },
)


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Any:
    clear_settings_cache()
    yield
    clear_settings_cache()


def _baseline_response(baseline_result_data: Any) -> SimulationRunResponse:
    return SimulationRunResponse(
        run_id="00000000-0000-4000-8000-000000000001",
        duration_ms=25,
        result=SimulationResult.model_validate(baseline_result_data),
    )


def _planning_client(
    tmp_path: Path,
    *,
    baseline_result_data: Any,
    sample_plan_data: Any,
    candidate_outcome: str = "STABILIZED",
    raise_server_exceptions: bool = False,
) -> tuple[TestClient, Any]:
    from app.services.run_store import RunStore

    settings = make_mission_settings(tmp_path)
    retrieval = FakeRetrievalService(result=make_multi_action_retrieval_result())
    provider = AsyncMock()
    provider.generate_plan = AsyncMock(side_effect=_fake_generate(sample_plan_data))

    run_store_holder: dict[str, RunStore] = {}

    class LifecycleSimulationAdapter:
        def __init__(self) -> None:
            self._baseline = _baseline_response(baseline_result_data)

        async def run_simulation(self, request: SimulationRunRequest) -> SimulationRunResponse:
            if request.plan is None:
                store = RunStore(settings.runs_dir)
                run_store_holder["store"] = store
                workspace = store.create_workspace(request, RELEASE_SCENARIO_PATH)
                result_bytes = json.dumps(
                    baseline_result_data,
                    ensure_ascii=False,
                    indent=2,
                    separators=(", ", ": "),
                ).encode("utf-8") + b"\n"
                workspace.result_path.write_bytes(result_bytes)
                from app.services.run_store import sha256_file

                store.write_completed_metadata(
                    workspace,
                    result_sha256=sha256_file(workspace.result_path),
                    process_exit_code=0,
                    duration_ms=25,
                    outcome=baseline_result_data["outcome"],
                )
                return SimulationRunResponse(
                    run_id=workspace.run_id,
                    duration_ms=25,
                    result=SimulationResult.model_validate(baseline_result_data),
                )
            store = run_store_holder.get("store") or RunStore(settings.runs_dir)
            candidate_data = _candidate_result_data(
                baseline_result_data,
                outcome=candidate_outcome,
                plan_id=sample_plan_data["plan_id"],
            )
            fake = PersistingFakeSimulationService(store, result_data=candidate_data)
            return await fake.run_simulation(request)

    lifecycle_sim = LifecycleSimulationAdapter()
    app = create_app(
        settings_override=settings,
        simulation_service_override=lifecycle_sim,
        procedure_retrieval_service_override=retrieval,
        planner_provider_override=provider,
    )
    client = TestClient(app, raise_server_exceptions=raise_server_exceptions)
    client.__enter__()
    return client, app


def _close(client: TestClient) -> None:
    client.__exit__(None, None, None)


def _prepare_replaying_session(client: TestClient) -> str:
    create = client.post("/api/missions", json={"scenario_id": RELEASE_SCENARIO_ID})
    assert create.status_code == 201
    session_id = create.json()["session"]["session_id"]
    accident = client.post(f"/api/missions/{session_id}/accident")
    assert accident.status_code == 200
    replay = client.post(f"/api/missions/{session_id}/replay", json={"restart": False})
    assert replay.status_code == 200
    return session_id


def test_plan_route_returns_200(
    tmp_path: Path,
    baseline_result_data: Any,
    sample_plan_data: Any,
) -> None:
    client, app = _planning_client(
        tmp_path,
        baseline_result_data=baseline_result_data,
        sample_plan_data=sample_plan_data,
    )
    try:
        session_id = _prepare_replaying_session(client)
        response = client.post(f"/api/missions/{session_id}/plan")
        assert response.status_code == 200
        payload = PlanningSimulationResponse.model_validate(response.json())
        assert payload.validation.status.value == "SIMULATION_COMPLETE"
        assert payload.candidate_result_path.startswith("/api/sim/result/")
        assert payload.baseline_result_path.startswith("/api/sim/result/")
        assert isinstance(app.state.mission_plan_simulation_service, MissionPlanSimulationService)
        flattened = json.dumps(response.json())
        for key in FORBIDDEN_PAYLOAD_KEYS:
            assert key not in flattened
    finally:
        _close(client)


@pytest.mark.parametrize("outcome", ["STABILIZED", "FAILURE", "REJECTED"])
def test_plan_route_accepts_simulator_outcomes(
    tmp_path: Path,
    baseline_result_data: Any,
    sample_plan_data: Any,
    outcome: str,
) -> None:
    data = copy.deepcopy(baseline_result_data)
    client, _ = _planning_client(
        tmp_path,
        baseline_result_data=data,
        sample_plan_data=sample_plan_data,
        candidate_outcome=outcome,
    )
    try:
        session_id = _prepare_replaying_session(client)
        response = client.post(f"/api/missions/{session_id}/plan")
        assert response.status_code == 200
        assert response.json()["validation"]["candidate"]["outcome"] == outcome
    finally:
        _close(client)


def test_plan_route_unavailable_without_prerequisites(tmp_path: Path) -> None:
    settings = make_mission_settings(tmp_path)
    app = create_app(settings_override=settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            f"/api/missions/{'00000000-0000-4000-8000-000000000001'}/plan",
        )
        assert response.status_code == 503
        assert response.json()["code"] == ErrorCode.PLANNING_SERVICE_UNAVAILABLE.value


def test_plan_route_invalid_session_id(
    tmp_path: Path,
    baseline_result_data: Any,
    sample_plan_data: Any,
) -> None:
    client, _ = _planning_client(
        tmp_path,
        baseline_result_data=baseline_result_data,
        sample_plan_data=sample_plan_data,
        raise_server_exceptions=False,
    )
    try:
        response = client.post("/api/missions/not-a-uuid/plan")
        assert response.status_code == 400
        assert response.json()["code"] == ErrorCode.MISSION_SESSION_ID_INVALID.value
    finally:
        _close(client)


def test_plan_route_unknown_session(
    tmp_path: Path,
    baseline_result_data: Any,
    sample_plan_data: Any,
) -> None:
    client, _ = _planning_client(
        tmp_path,
        baseline_result_data=baseline_result_data,
        sample_plan_data=sample_plan_data,
        raise_server_exceptions=False,
    )
    try:
        response = client.post(
            "/api/missions/00000000-0000-4000-8000-0000000000aa/plan",
        )
        assert response.status_code == 404
        assert response.json()["code"] == ErrorCode.MISSION_SESSION_NOT_FOUND.value
    finally:
        _close(client)


def test_plan_route_not_available_before_replay(
    tmp_path: Path,
    baseline_result_data: Any,
    sample_plan_data: Any,
) -> None:
    client, _ = _planning_client(
        tmp_path,
        baseline_result_data=baseline_result_data,
        sample_plan_data=sample_plan_data,
        raise_server_exceptions=False,
    )
    try:
        create = client.post("/api/missions", json={"scenario_id": RELEASE_SCENARIO_ID})
        session_id = create.json()["session"]["session_id"]
        response = client.post(f"/api/missions/{session_id}/plan")
        assert response.status_code == 409
        assert response.json()["code"] == ErrorCode.PLANNING_NOT_AVAILABLE.value
    finally:
        _close(client)


@pytest.mark.asyncio
async def test_plan_route_same_session_concurrent_one_409(
    tmp_path: Path,
    baseline_result_data: Any,
    sample_plan_data: Any,
) -> None:
    settings = make_mission_settings(tmp_path)
    retrieval = FakeRetrievalService(result=make_multi_action_retrieval_result())
    provider = AsyncMock()
    provider.generate_plan = AsyncMock(side_effect=_fake_generate(sample_plan_data))
    gate = asyncio.Event()

    from app.services.run_store import RunStore

    run_store = RunStore(settings.runs_dir)

    class GatedSimulation(PersistingFakeSimulationService):
        async def run_simulation(self, request: SimulationRunRequest) -> SimulationRunResponse:
            if request.plan is not None:
                await gate.wait()
            return await super().run_simulation(request)

    class LifecycleSimulationAdapter:
        async def run_simulation(self, request: SimulationRunRequest) -> SimulationRunResponse:
            if request.plan is None:
                workspace = run_store.create_workspace(request, RELEASE_SCENARIO_PATH)
                result_bytes = json.dumps(
                    baseline_result_data,
                    ensure_ascii=False,
                    indent=2,
                    separators=(", ", ": "),
                ).encode("utf-8") + b"\n"
                workspace.result_path.write_bytes(result_bytes)
                from app.services.run_store import sha256_file

                run_store.write_completed_metadata(
                    workspace,
                    result_sha256=sha256_file(workspace.result_path),
                    process_exit_code=0,
                    duration_ms=25,
                    outcome=baseline_result_data["outcome"],
                )
                return SimulationRunResponse(
                    run_id=workspace.run_id,
                    duration_ms=25,
                    result=SimulationResult.model_validate(baseline_result_data),
                )
            fake = GatedSimulation(
                run_store,
                result_data=_candidate_result_data(
                    baseline_result_data,
                    outcome="STABILIZED",
                    plan_id=sample_plan_data["plan_id"],
                ),
                gate=gate,
            )
            return await fake.run_simulation(request)

    app = create_app(
        settings_override=settings,
        simulation_service_override=LifecycleSimulationAdapter(),
        procedure_retrieval_service_override=retrieval,
        planner_provider_override=provider,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        async with app.router.lifespan_context(app):
            create = await http_client.post(
                "/api/missions",
                json={"scenario_id": RELEASE_SCENARIO_ID},
            )
            session_id = create.json()["session"]["session_id"]
            await http_client.post(f"/api/missions/{session_id}/accident")
            await http_client.post(
                f"/api/missions/{session_id}/replay",
                json={"restart": False},
            )
            first = asyncio.create_task(http_client.post(f"/api/missions/{session_id}/plan"))
            await asyncio.sleep(0.05)
            second = await http_client.post(f"/api/missions/{session_id}/plan")
            assert second.status_code == 409
            assert second.json()["code"] == ErrorCode.PLANNING_IN_PROGRESS.value
            gate.set()
            first_response = await first
            assert first_response.status_code == 200
