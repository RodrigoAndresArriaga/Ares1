# Phase 5 Step 3 full planning→simulation orchestration
# one grounded candidate through SimulationService with validation persistence
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from app.core.errors import (
    AresBackendError,
    PlanningInProgressError,
    PlanningSimulationIntegrityError,
    PlanningValidationStorageError,
)
from app.core.logging import log_run_event
from app.schemas.api import ErrorCode, SimulationRunRequest
from app.schemas.planning import PlanningAttempt
from app.schemas.planning_validation import (
    PLANNING_VALIDATION_SCHEMA_VERSION,
    PlanningResultSummary,
    PlanningSimulationResponse,
    PlanningValidationRecord,
    PlanningValidationStatus,
    build_planning_result_comparison,
    canonical_plan_sha256,
)
from app.schemas.result import SimulationResult
from app.schemas.run import RunArtifactMetadata, validate_canonical_run_id
from app.services.mission_lifecycle_service import utc_now
from app.services.mission_planning_service import MissionPlanningService
from app.services.planning_attempt_store import PlanningAttemptStore
from app.services.planning_validation_store import PlanningValidationStore
from app.services.run_store import RunStore, sha256_file
from app.services.simulation_service import SimulationService

logger = logging.getLogger("ares.mission_plan_simulation")

_RESULT_FILENAME = "result.json"


class MissionPlanSimulationService:
    # Orchestrate candidate generation, simulator execution, and validation persistence.

    def __init__(
        self,
        *,
        mission_planning_service: MissionPlanningService,
        planning_attempt_store: PlanningAttemptStore,
        validation_store: PlanningValidationStore,
        run_store: RunStore,
        simulation_service: SimulationService,
        now_provider: Callable[[], datetime] = utc_now,
    ) -> None:
        self._mission_planning_service = mission_planning_service
        self._planning_attempt_store = planning_attempt_store
        self._validation_store = validation_store
        self._run_store = run_store
        self._simulation_service = simulation_service
        self._now_provider = now_provider
        self._guard_lock = asyncio.Lock()
        self._active_sessions: set[str] = set()

    async def generate_and_simulate(self, session_id: str) -> PlanningSimulationResponse:
        acquired = False
        attempt: PlanningAttempt | None = None
        simulating_persisted = False
        candidate_run_id: str | None = None
        try:
            await self._acquire_full_guard(session_id)
            acquired = True
            log_run_event(
                logger,
                logging.INFO,
                "full planning operation started",
                event="planning_simulation_started",
                session_id=session_id,
            )

            attempt = await self._mission_planning_service.generate_candidate(session_id)
            log_run_event(
                logger,
                logging.INFO,
                "candidate attempt linked",
                event="planning_attempt_linked",
                session_id=session_id,
                attempt_id=attempt.attempt_id,
            )

            baseline_result, baseline_metadata = self._read_and_validate_baseline(attempt)
            baseline_summary = self._build_result_summary(
                run_id=attempt.baseline_run_id,
                metadata=baseline_metadata,
                result=baseline_result,
            )
            plan_hash = canonical_plan_sha256(attempt.generation_result.plan)
            started_at = self._require_aware_now()

            simulating_record = PlanningValidationRecord(
                schema_version=PLANNING_VALIDATION_SCHEMA_VERSION,
                attempt_id=attempt.attempt_id,
                session_id=attempt.session_id,
                scenario_id=attempt.scenario_id,
                baseline_run_id=attempt.baseline_run_id,
                attempt_preflight_sha256=attempt.preflight.preflight_sha256,
                candidate_plan_sha256=plan_hash,
                status=PlanningValidationStatus.SIMULATING,
                started_at=started_at,
                completed_at=None,
                baseline=baseline_summary,
                candidate=None,
                comparison=None,
                error_code=None,
            )
            self._validation_store.create_validation(simulating_record)
            simulating_persisted = True
            log_run_event(
                logger,
                logging.INFO,
                "SIMULATING persisted",
                event="planning_validation_simulating",
                session_id=session_id,
                attempt_id=attempt.attempt_id,
            )

            request = SimulationRunRequest(
                scenario_id=attempt.scenario_id,
                plan=attempt.generation_result.plan,
            )
            log_run_event(
                logger,
                logging.INFO,
                "simulator call started",
                event="planning_simulator_started",
                session_id=session_id,
                attempt_id=attempt.attempt_id,
                scenario_id=attempt.scenario_id,
                action_count=len(attempt.generation_result.plan.actions),
            )
            response = await self._simulation_service.run_simulation(request)
            candidate_run_id = response.run_id
            log_run_event(
                logger,
                logging.INFO,
                "simulator result received",
                event="planning_simulator_completed",
                session_id=session_id,
                attempt_id=attempt.attempt_id,
                candidate_run_id=candidate_run_id,
                candidate_outcome=response.result.outcome.value,
                candidate_valid_plan=response.result.valid_plan,
            )

            candidate_metadata = self._run_store.read_metadata(candidate_run_id)
            self._validate_candidate_integrity(
                attempt=attempt,
                run_id=candidate_run_id,
                metadata=candidate_metadata,
                result=response.result,
            )
            candidate_summary = self._build_result_summary(
                run_id=candidate_run_id,
                metadata=candidate_metadata,
                result=response.result,
            )
            comparison = build_planning_result_comparison(baseline_summary, candidate_summary)
            log_run_event(
                logger,
                logging.INFO,
                "comparison constructed",
                event="planning_comparison_constructed",
                session_id=session_id,
                attempt_id=attempt.attempt_id,
                outcome_changed=comparison.outcome_changed,
            )

            completed_at = self._require_aware_now()
            if completed_at < started_at:
                completed_at = started_at + timedelta(microseconds=1)
            complete_record = PlanningValidationRecord(
                schema_version=PLANNING_VALIDATION_SCHEMA_VERSION,
                attempt_id=attempt.attempt_id,
                session_id=attempt.session_id,
                scenario_id=attempt.scenario_id,
                baseline_run_id=attempt.baseline_run_id,
                attempt_preflight_sha256=attempt.preflight.preflight_sha256,
                candidate_plan_sha256=plan_hash,
                status=PlanningValidationStatus.SIMULATION_COMPLETE,
                started_at=started_at,
                completed_at=completed_at,
                baseline=baseline_summary,
                candidate=candidate_summary,
                comparison=comparison,
                error_code=None,
            )
            validation = self._validation_store.replace_validation(
                complete_record,
                expected_status=PlanningValidationStatus.SIMULATING,
            )
            log_run_event(
                logger,
                logging.INFO,
                "SIMULATION_COMPLETE persisted",
                event="planning_validation_complete",
                session_id=session_id,
                attempt_id=attempt.attempt_id,
                candidate_run_id=candidate_run_id,
            )

            return PlanningSimulationResponse(
                attempt=attempt,
                validation=validation,
                baseline_result_path=f"/api/sim/result/{attempt.baseline_run_id}",
                candidate_result_path=f"/api/sim/result/{candidate_run_id}",
            )
        except asyncio.CancelledError:
            log_run_event(
                logger,
                logging.INFO,
                "planning simulation cancelled",
                event="planning_simulation_cancelled",
                session_id=session_id,
                attempt_id=attempt.attempt_id if attempt is not None else None,
            )
            if simulating_persisted and attempt is not None:
                self._best_effort_error_transition(
                    attempt=attempt,
                    error_code=ErrorCode.PLANNING_SIMULATION_CANCELLED.value,
                )
            raise
        except AresBackendError as exc:
            if simulating_persisted and attempt is not None and not isinstance(
                exc,
                (PlanningSimulationIntegrityError, PlanningValidationStorageError),
            ):
                self._best_effort_error_transition(
                    attempt=attempt,
                    error_code=exc.code.value,
                )
            raise
        except Exception:
            if simulating_persisted and attempt is not None:
                self._best_effort_error_transition(
                    attempt=attempt,
                    error_code=ErrorCode.INTERNAL_SERVER_ERROR.value,
                )
            raise
        finally:
            if acquired:
                await self._release_full_guard(session_id)

    async def _acquire_full_guard(self, session_id: str) -> None:
        async with self._guard_lock:
            if session_id in self._active_sessions:
                log_run_event(
                    logger,
                    logging.INFO,
                    "full planning in progress",
                    event="planning_simulation_in_progress",
                    session_id=session_id,
                    error_code=ErrorCode.PLANNING_IN_PROGRESS.value,
                )
                raise PlanningInProgressError(
                    "Planning simulation operation already in progress for this session",
                    session_id=session_id,
                )
            self._active_sessions.add(session_id)

    async def _release_full_guard(self, session_id: str) -> None:
        async with self._guard_lock:
            self._active_sessions.discard(session_id)

    def _read_and_validate_baseline(
        self,
        attempt: PlanningAttempt,
    ) -> tuple[SimulationResult, RunArtifactMetadata]:
        baseline_run_id = attempt.baseline_run_id
        result = self._run_store.read_result(baseline_run_id)
        metadata = self._run_store.read_metadata(baseline_run_id)
        self._validate_run_linkage(
            attempt=attempt,
            run_id=baseline_run_id,
            metadata=metadata,
            result=result,
            expected_plan_id=result.plan_id,
            context_failure_reasons=attempt.mission_context.baseline_failure_reasons,
            context_metrics=attempt.mission_context.baseline_metrics,
            context_outcome=attempt.mission_context.baseline_outcome,
            context_sample_count=attempt.mission_context.telemetry_sample_count,
            require_completed=True,
        )
        return result, metadata

    def _validate_candidate_integrity(
        self,
        *,
        attempt: PlanningAttempt,
        run_id: str,
        metadata: RunArtifactMetadata,
        result: SimulationResult,
    ) -> None:
        self._validate_run_linkage(
            attempt=attempt,
            run_id=run_id,
            metadata=metadata,
            result=result,
            expected_plan_id=attempt.generation_result.plan.plan_id,
            context_failure_reasons=None,
            context_metrics=None,
            context_outcome=None,
            context_sample_count=None,
            require_completed=True,
        )

    def _validate_run_linkage(
        self,
        *,
        attempt: PlanningAttempt,
        run_id: str,
        metadata: RunArtifactMetadata,
        result: SimulationResult,
        expected_plan_id: str,
        context_failure_reasons: list[str] | None,
        context_metrics: object | None,
        context_outcome: object | None,
        context_sample_count: int | None,
        require_completed: bool,
    ) -> None:
        if metadata.run_id != run_id:
            raise PlanningSimulationIntegrityError(
                "Run metadata run_id does not match requested run",
                session_id=attempt.session_id,
                attempt_id=attempt.attempt_id,
                run_id=run_id,
            )
        if result.scenario_id != attempt.scenario_id:
            raise PlanningSimulationIntegrityError(
                "Result scenario_id does not match planning attempt",
                session_id=attempt.session_id,
                attempt_id=attempt.attempt_id,
                run_id=run_id,
            )
        if result.plan_id != expected_plan_id:
            raise PlanningSimulationIntegrityError(
                "Result plan_id does not match expected plan",
                session_id=attempt.session_id,
                attempt_id=attempt.attempt_id,
                run_id=run_id,
            )
        if metadata.scenario_id != result.scenario_id:
            raise PlanningSimulationIntegrityError(
                "Metadata scenario_id does not match result",
                session_id=attempt.session_id,
                attempt_id=attempt.attempt_id,
                run_id=run_id,
            )
        if metadata.outcome is not None and metadata.outcome != result.outcome.value:
            raise PlanningSimulationIntegrityError(
                "Metadata outcome does not match result",
                session_id=attempt.session_id,
                attempt_id=attempt.attempt_id,
                run_id=run_id,
            )
        if metadata.plan_id is not None and metadata.plan_id != result.plan_id:
            raise PlanningSimulationIntegrityError(
                "Metadata plan_id does not match result",
                session_id=attempt.session_id,
                attempt_id=attempt.attempt_id,
                run_id=run_id,
            )
        if require_completed and metadata.status != "completed":
            raise PlanningSimulationIntegrityError(
                "Run metadata status is not completed",
                session_id=attempt.session_id,
                attempt_id=attempt.attempt_id,
                run_id=run_id,
            )
        if metadata.result_sha256 is None:
            raise PlanningSimulationIntegrityError(
                "Run metadata result_sha256 is missing",
                session_id=attempt.session_id,
                attempt_id=attempt.attempt_id,
                run_id=run_id,
            )
        actual_hash = self._hash_persisted_result(run_id)
        if metadata.result_sha256 != actual_hash:
            raise PlanningSimulationIntegrityError(
                "Run metadata result_sha256 does not match persisted result",
                session_id=attempt.session_id,
                attempt_id=attempt.attempt_id,
                run_id=run_id,
            )
        sample_count = len(result.telemetry_history)
        if sample_count <= 0:
            raise PlanningSimulationIntegrityError(
                "Result telemetry history must be nonempty",
                session_id=attempt.session_id,
                attempt_id=attempt.attempt_id,
                run_id=run_id,
            )
        if context_outcome is not None and result.outcome != context_outcome:
            raise PlanningSimulationIntegrityError(
                "Baseline result outcome does not match planning context",
                session_id=attempt.session_id,
                attempt_id=attempt.attempt_id,
                run_id=run_id,
            )
        if (
            context_failure_reasons is not None
            and result.failure_reasons != context_failure_reasons
        ):
            raise PlanningSimulationIntegrityError(
                "Baseline failure reasons do not match planning context",
                session_id=attempt.session_id,
                attempt_id=attempt.attempt_id,
                run_id=run_id,
            )
        if context_metrics is not None and result.metrics != context_metrics:
            raise PlanningSimulationIntegrityError(
                "Baseline metrics do not match planning context",
                session_id=attempt.session_id,
                attempt_id=attempt.attempt_id,
                run_id=run_id,
            )
        if context_sample_count is not None and sample_count != context_sample_count:
            raise PlanningSimulationIntegrityError(
                "Baseline telemetry sample count does not match planning context",
                session_id=attempt.session_id,
                attempt_id=attempt.attempt_id,
                run_id=run_id,
            )

    def _hash_persisted_result(self, run_id: str) -> str:
        canonical = validate_canonical_run_id(run_id)
        runs_root = self._run_store._runs_root
        candidate = runs_root / canonical
        resolved = candidate.resolve()
        if not resolved.is_relative_to(runs_root):
            raise PlanningSimulationIntegrityError(
                "Result path escapes runs root",
                run_id=canonical,
            )
        if not resolved.is_dir():
            raise PlanningSimulationIntegrityError(
                "Run directory not found for result hash",
                run_id=canonical,
            )
        result_path = resolved / _RESULT_FILENAME
        if result_path.is_symlink():
            target = result_path.resolve()
            if not target.is_relative_to(resolved):
                raise PlanningSimulationIntegrityError(
                    "Result artifact escapes run directory",
                    run_id=canonical,
                )
            result_path = target
        return sha256_file(result_path)

    def _build_result_summary(
        self,
        *,
        run_id: str,
        metadata: RunArtifactMetadata,
        result: SimulationResult,
    ) -> PlanningResultSummary:
        assert metadata.result_sha256 is not None
        return PlanningResultSummary(
            run_id=run_id,
            result_sha256=metadata.result_sha256,
            scenario_id=result.scenario_id,
            plan_id=result.plan_id,
            outcome=result.outcome,
            valid_plan=result.valid_plan,
            failure_reasons=list(result.failure_reasons),
            metrics=result.metrics,
            telemetry_sample_count=len(result.telemetry_history),
        )

    def _best_effort_error_transition(
        self,
        *,
        attempt: PlanningAttempt,
        error_code: str,
    ) -> None:
        try:
            current = self._validation_store.read_validation(attempt.attempt_id)
            if current.status != PlanningValidationStatus.SIMULATING:
                return
            completed_at = self._require_aware_now()
            if completed_at < current.started_at:
                completed_at = current.started_at + timedelta(microseconds=1)
            error_record = PlanningValidationRecord(
                schema_version=current.schema_version,
                attempt_id=current.attempt_id,
                session_id=current.session_id,
                scenario_id=current.scenario_id,
                baseline_run_id=current.baseline_run_id,
                attempt_preflight_sha256=current.attempt_preflight_sha256,
                candidate_plan_sha256=current.candidate_plan_sha256,
                status=PlanningValidationStatus.ERROR,
                started_at=current.started_at,
                completed_at=completed_at,
                baseline=current.baseline,
                candidate=current.candidate,
                comparison=current.comparison,
                error_code=error_code,
            )
            self._validation_store.replace_validation(
                error_record,
                expected_status=PlanningValidationStatus.SIMULATING,
            )
            log_run_event(
                logger,
                logging.WARNING,
                "ERROR persisted",
                event="planning_validation_error",
                session_id=attempt.session_id,
                attempt_id=attempt.attempt_id,
                error_code=error_code,
            )
        except Exception as exc:
            logger.warning(
                "planning_validation_error_transition_failed attempt_id=%s err=%s",
                attempt.attempt_id,
                type(exc).__name__,
            )

    def _require_aware_now(self) -> datetime:
        now = self._now_provider()
        if now.tzinfo is None or now.utcoffset() is None:
            raise PlanningSimulationIntegrityError(
                "Injected now_provider returned a naive datetime",
            )
        return now
