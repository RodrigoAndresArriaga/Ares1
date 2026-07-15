# orchestrate one simulation run across registry, store, and client
from __future__ import annotations

import logging
from typing import Any, NoReturn

from app.core.errors import AresBackendError, ArtifactStorageError
from app.core.logging import log_run_event
from app.schemas.api import SimulationRunRequest, SimulationRunResponse
from app.services.run_store import RunStore, RunWorkspace
from app.services.scenario_registry import ScenarioRegistry
from app.services.simulator_client import ProcessEvidence, SimulatorClient

logger = logging.getLogger("ares.simulation")


class SimulationService:
    def __init__(
        self,
        scenario_registry: ScenarioRegistry,
        run_store: RunStore,
        simulator_client: SimulatorClient,
    ) -> None:
        self._scenario_registry = scenario_registry
        self._run_store = run_store
        self._simulator_client = simulator_client

    async def run_simulation(
        self,
        request: SimulationRunRequest,
    ) -> SimulationRunResponse:
        scenario_path = self._scenario_registry.resolve_scenario(
            request.scenario_id,
        )
        workspace = self._run_store.create_workspace(request, scenario_path)
        mode = "plan" if request.plan is not None else "baseline"
        plan_id = request.plan.plan_id if request.plan is not None else None

        log_run_event(
            logger,
            logging.INFO,
            "simulation run created",
            event="simulation_run_created",
            run_id=workspace.run_id,
            scenario_id=request.scenario_id,
            plan_id=plan_id,
            mode=mode,
        )
        log_run_event(
            logger,
            logging.INFO,
            "simulator process started",
            event="simulator_process_started",
            run_id=workspace.run_id,
            scenario_id=request.scenario_id,
            plan_id=plan_id,
            mode=mode,
        )

        try:
            execution = await self._simulator_client.run(workspace)
        except AresBackendError as exc:
            self._finalize_failure(
                workspace,
                exc,
                scenario_id=request.scenario_id,
                plan_id=plan_id,
                mode=mode,
            )

        process = execution.process
        try:
            self._run_store.write_stdout(workspace, process.stdout_bytes)
            self._run_store.write_stderr(workspace, process.stderr_bytes)
            result_sha256 = self._run_store.hash_result_artifact(workspace)
            self._run_store.write_completed_metadata(
                workspace,
                result_sha256=result_sha256,
                process_exit_code=process.exit_code,
                duration_ms=process.duration_ms,
                outcome=execution.result.outcome.value,
            )
        except ArtifactStorageError as exc:
            attached = exc.with_run_id(workspace.run_id)
            log_run_event(
                logger,
                logging.ERROR,
                "simulation run failed",
                event="simulation_run_failed",
                run_id=workspace.run_id,
                scenario_id=request.scenario_id,
                plan_id=plan_id,
                mode=mode,
                error_code=attached.code.value,
            )
            raise attached from exc

        log_run_event(
            logger,
            logging.INFO,
            "simulator process completed",
            event="simulator_process_completed",
            run_id=workspace.run_id,
            scenario_id=request.scenario_id,
            plan_id=plan_id,
            mode=mode,
            duration_ms=process.duration_ms,
            process_exit_code=process.exit_code,
        )
        log_run_event(
            logger,
            logging.INFO,
            "simulator output validated",
            event="simulator_output_validated",
            run_id=workspace.run_id,
            scenario_id=request.scenario_id,
            plan_id=plan_id,
            mode=mode,
            outcome=execution.result.outcome.value,
        )
        log_run_event(
            logger,
            logging.INFO,
            "simulation run completed",
            event="simulation_run_completed",
            run_id=workspace.run_id,
            scenario_id=request.scenario_id,
            plan_id=plan_id,
            mode=mode,
            duration_ms=process.duration_ms,
            process_exit_code=process.exit_code,
            outcome=execution.result.outcome.value,
        )

        return SimulationRunResponse(
            run_id=workspace.run_id,
            duration_ms=process.duration_ms,
            result=execution.result,
        )

    def _finalize_failure(
        self,
        workspace: RunWorkspace,
        exc: AresBackendError,
        *,
        scenario_id: str,
        plan_id: str | None,
        mode: str,
    ) -> NoReturn:
        attached = exc.with_run_id(workspace.run_id)
        evidence = getattr(attached, "process_evidence", None)

        try:
            if evidence is not None:
                self._persist_process_evidence(workspace, evidence)
            result_sha256 = self._run_store.try_hash_result_artifact(workspace)
            exit_code, duration_ms = _evidence_fields(evidence)
            self._run_store.write_failed_metadata(
                workspace,
                error_code=attached.code.value,
                result_sha256=result_sha256,
                process_exit_code=exit_code,
                duration_ms=duration_ms,
                outcome=None,
            )
        except ArtifactStorageError as storage_exc:
            chained = storage_exc.with_run_id(workspace.run_id)
            log_run_event(
                logger,
                logging.ERROR,
                "simulation run failed",
                event="simulation_run_failed",
                run_id=workspace.run_id,
                scenario_id=scenario_id,
                plan_id=plan_id,
                mode=mode,
                error_code=chained.code.value,
            )
            raise chained from attached

        exit_code, duration_ms = _evidence_fields(evidence)
        log_run_event(
            logger,
            logging.ERROR,
            "simulation run failed",
            event="simulation_run_failed",
            run_id=workspace.run_id,
            scenario_id=scenario_id,
            plan_id=plan_id,
            mode=mode,
            error_code=attached.code.value,
            duration_ms=duration_ms,
            process_exit_code=exit_code,
        )
        if attached is exc:
            raise attached
        raise attached from exc

    def _persist_process_evidence(
        self,
        workspace: RunWorkspace,
        evidence: ProcessEvidence,
    ) -> None:
        self._run_store.write_stdout(workspace, evidence.stdout_bytes)
        self._run_store.write_stderr(workspace, evidence.stderr_bytes)


def _evidence_fields(
    evidence: Any | None,
) -> tuple[int | None, int | None]:
    if evidence is None:
        return None, None
    exit_code = getattr(evidence, "exit_code", None)
    duration_ms = getattr(evidence, "duration_ms", None)
    if not isinstance(exit_code, int) and exit_code is not None:
        exit_code = None
    if not isinstance(duration_ms, int) and duration_ms is not None:
        duration_ms = None
    return exit_code, duration_ms
