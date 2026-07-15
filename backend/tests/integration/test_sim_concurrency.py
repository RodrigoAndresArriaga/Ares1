# real concurrent HTTP isolation under a shared SimulatorClient semaphore
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from app.core.config import clear_settings_cache
from app.main import create_app
from app.schemas.plan import RecoveryPlan
from app.services.simulator_client import SimulatorClient
from tests.conftest import (
    RELEASE_SCENARIO_ID,
    SHARED_SIM_RESULT_PATH,
    make_real_app_settings,
    require_real_simulator,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.real_simulator,
]


@pytest.fixture(autouse=True)
def _require_binary() -> None:
    require_real_simulator()


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.mark.asyncio
async def test_concurrent_http_isolation(
    tmp_path: Path,
    sample_plan_data: Any,
    invalid_plan_data: Any,
    release_scenario_bytes: bytes,
) -> None:
    shared_before = (
        SHARED_SIM_RESULT_PATH.read_bytes()
        if SHARED_SIM_RESULT_PATH.is_file()
        else None
    )
    settings = make_real_app_settings(tmp_path, max_concurrent_runs=2)
    app = create_app(settings_override=settings)

    # lifespan builds the shared client; wrap spawn for active-process accounting
    async with app.router.lifespan_context(app):
        client: SimulatorClient = app.state.simulator_client
        assert client._semaphore._value == 2
        original_spawn = client._spawn
        active = 0
        peak = 0
        lock = asyncio.Lock()

        async def counting_spawn(
            *cmd: str,
            stdout: Any = None,
            stderr: Any = None,
            **kwargs: Any,
        ) -> Any:
            nonlocal active, peak
            async with lock:
                active += 1
                peak = max(peak, active)
                assert active <= settings.max_concurrent_runs
            try:
                return await original_spawn(
                    *cmd,
                    stdout=stdout,
                    stderr=stderr,
                    **kwargs,
                )
            finally:
                async with lock:
                    active -= 1

        client._spawn = counting_spawn

        baseline_payload = {"scenario_id": RELEASE_SCENARIO_ID}
        valid_payload = {
            "scenario_id": RELEASE_SCENARIO_ID,
            "plan": sample_plan_data,
        }
        invalid_payload = {
            "scenario_id": RELEASE_SCENARIO_ID,
            "plan": invalid_plan_data,
        }
        payloads = [
            ("baseline", baseline_payload),
            ("valid", valid_payload),
            ("invalid", invalid_payload),
            ("valid_repeat", valid_payload),
        ]

        probe_done = asyncio.Event()

        async def event_loop_probe() -> None:
            await asyncio.sleep(0)
            probe_done.set()

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as http:
            probe_task = asyncio.create_task(event_loop_probe())
            responses = await asyncio.gather(
                *[
                    http.post("/api/sim/run", json=payload)
                    for _, payload in payloads
                ],
                probe_task,
            )

        http_responses = responses[:-1]
        assert probe_done.is_set()
        assert peak <= settings.max_concurrent_runs
        assert peak >= 1
        assert client._semaphore._value == 2

        bodies: list[dict[str, Any]] = []
        for response in http_responses:
            assert response.status_code == 200
            bodies.append(response.json())

        run_ids = [body["run_id"] for body in bodies]
        assert len(set(run_ids)) == 4

        expected_outcomes = {
            "baseline": "FAILURE",
            "valid": "STABILIZED",
            "invalid": "REJECTED",
            "valid_repeat": "STABILIZED",
        }
        for (label, payload), body in zip(payloads, bodies, strict=True):
            assert body["result"]["outcome"] == expected_outcomes[label]
            run_dir = settings.runs_dir / body["run_id"]
            assert run_dir.is_dir()
            assert (run_dir / "scenario.json").read_bytes() == release_scenario_bytes
            assert (run_dir / "result.json").is_file()
            assert (run_dir / "stdout.log").is_file()
            assert (run_dir / "stderr.log").is_file()
            assert (run_dir / "metadata.json").is_file()
            request_on_disk = json.loads(
                (run_dir / "request.json").read_text(encoding="utf-8"),
            )
            if label == "baseline":
                assert request_on_disk == payload
                assert not (run_dir / "plan.json").exists()
            else:
                assert request_on_disk["scenario_id"] == payload["scenario_id"]
                plan_on_disk = json.loads(
                    (run_dir / "plan.json").read_text(encoding="utf-8"),
                )
                assert RecoveryPlan.model_validate(plan_on_disk).model_dump(
                    mode="json",
                ) == RecoveryPlan.model_validate(payload["plan"]).model_dump(
                    mode="json",
                )

        if shared_before is not None:
            assert SHARED_SIM_RESULT_PATH.read_bytes() == shared_before
