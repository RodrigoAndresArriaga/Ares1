# Phase 5 Step 2 transport-neutral mission planning orchestration
# authoritative replay telemetry, deterministic retrieval, evidence-grounded candidates
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from uuid import UUID, uuid4

from app.core.errors import (
    BaselineResultMismatchError,
    InvalidRunIdError,
    MissionSessionConflictError,
    MissionSessionNotFoundError,
    PlannerCandidateUngroundedError,
    PlanningContextMismatchError,
    PlanningInProgressError,
    PlanningNotAvailableError,
    ReplayNotStartedError,
    RunArtifactStorageError,
    RunNotFoundError,
    RunResultCorruptError,
    RunResultNotFoundError,
)
from app.core.logging import log_run_event
from app.schemas.api import ErrorCode
from app.schemas.mission import MissionSessionStatus
from app.schemas.planner import PlannerMissionContext, PlannerPromptInput
from app.schemas.planning import PLANNING_SCHEMA_VERSION, PlanningAttempt, PlanningAttemptStatus
from app.schemas.replay import CurrentTelemetryResponse
from app.schemas.result import OutcomeStatus, SimulationResult
from app.services.mission_lifecycle_service import utc_now
from app.services.mission_retrieval_query import MissionRetrievalQueryBuilder
from app.services.planner_candidate_validator import PlannerCandidateValidator
from app.services.planner_prompt import PlannerPromptBuilder
from app.services.planner_provider import PlannerProvider
from app.services.planning_attempt_store import PlanningAttemptStore
from app.services.procedure_retrieval import ProcedureRetrievalService
from app.services.run_store import RunStore
from app.services.session_store import SessionStore
from app.services.telemetry_replay_service import TelemetryReplayService

logger = logging.getLogger("ares.mission_planning")

_PLANNING_ELIGIBLE_STATUSES = frozenset(
    {
        MissionSessionStatus.REPLAYING,
        MissionSessionStatus.COMPLETED,
    },
)


class MissionPlanningService:
    # Orchestrate one evidence-grounded planner candidate per session.
    # Current telemetry from TelemetryReplayService is authoritative.
    # Phase 4 retrieval evidence is mandatory. Persisted candidates are not
    # simulator-approved; the frozen simulator validates feasibility in Step 3.

    def __init__(
        self,
        *,
        session_store: SessionStore,
        run_store: RunStore,
        telemetry_replay_service: TelemetryReplayService,
        procedure_retrieval_service: ProcedureRetrievalService,
        planner_prompt_builder: PlannerPromptBuilder,
        planner_provider: PlannerProvider,
        candidate_validator: PlannerCandidateValidator,
        attempt_store: PlanningAttemptStore,
        retrieval_query_builder: MissionRetrievalQueryBuilder,
        retrieval_top_k: int,
        now_provider: Callable[[], datetime] = utc_now,
        attempt_id_provider: Callable[[], UUID] = uuid4,
    ) -> None:
        if retrieval_top_k <= 0:
            raise ValueError("retrieval_top_k must be positive")
        self._session_store = session_store
        self._run_store = run_store
        self._telemetry_replay_service = telemetry_replay_service
        self._procedure_retrieval_service = procedure_retrieval_service
        self._planner_prompt_builder = planner_prompt_builder
        self._planner_provider = planner_provider
        self._candidate_validator = candidate_validator
        self._attempt_store = attempt_store
        self._retrieval_query_builder = retrieval_query_builder
        self._retrieval_top_k = retrieval_top_k
        self._now_provider = now_provider
        self._attempt_id_provider = attempt_id_provider
        self._guard_lock = asyncio.Lock()
        self._active_sessions: set[str] = set()

    async def generate_candidate(self, session_id: str) -> PlanningAttempt:
        acquired = False
        try:
            await self._acquire_planning_guard(session_id)
            acquired = True
            log_run_event(
                logger,
                logging.INFO,
                "planning operation started",
                event="planning_operation_started",
                session_id=session_id,
            )
            return await self._generate_candidate_unlocked(session_id)
        except asyncio.CancelledError:
            log_run_event(
                logger,
                logging.INFO,
                "planning operation cancelled",
                event="planning_operation_cancelled",
                session_id=session_id,
            )
            raise
        except Exception as exc:
            code_value: str | None = None
            error_code = getattr(exc, "code", None)
            if isinstance(error_code, ErrorCode):
                code_value = error_code.value
            log_run_event(
                logger,
                logging.WARNING,
                "planning operation failed",
                event="planning_operation_failed",
                session_id=session_id,
                error_code=code_value,
            )
            raise
        finally:
            if acquired:
                await self._release_planning_guard(session_id)

    async def _acquire_planning_guard(self, session_id: str) -> None:
        async with self._guard_lock:
            if session_id in self._active_sessions:
                log_run_event(
                    logger,
                    logging.INFO,
                    "planning in progress",
                    event="planning_in_progress",
                    session_id=session_id,
                    error_code=ErrorCode.PLANNING_IN_PROGRESS.value,
                )
                raise PlanningInProgressError(
                    "Planning operation already in progress for this session",
                    session_id=session_id,
                )
            self._active_sessions.add(session_id)

    async def _release_planning_guard(self, session_id: str) -> None:
        async with self._guard_lock:
            self._active_sessions.discard(session_id)

    async def _generate_candidate_unlocked(self, session_id: str) -> PlanningAttempt:
        current = await self._load_current_telemetry(session_id)
        session = self._session_store.read_session(session_id)
        self._require_planning_eligible(session_id=session_id, status=session.status)

        baseline_run_id = session.baseline_run_id
        baseline_outcome = session.baseline_outcome
        sample_count = session.telemetry_sample_count
        if (
            baseline_run_id is None
            or baseline_outcome is None
            or sample_count is None
        ):
            raise PlanningContextMismatchError(
                "Mission session is missing required planning fields",
                session_id=session_id,
            )

        result = self._read_baseline_result(
            session_id=session_id,
            baseline_run_id=baseline_run_id,
        )
        mission_context = self._build_mission_context(
            session_id=session_id,
            current=current,
            session_scenario_id=session.scenario_id,
            baseline_run_id=baseline_run_id,
            baseline_outcome=baseline_outcome,
            sample_count=sample_count,
            result=result,
        )
        log_run_event(
            logger,
            logging.INFO,
            "mission context loaded",
            event="mission_context_loaded",
            session_id=session_id,
            scenario_id=mission_context.scenario_id,
            baseline_run_id=mission_context.baseline_run_id,
            sample_index=mission_context.current_sample_index,
        )

        query = self._retrieval_query_builder.build(mission_context)
        retrieval_result = await asyncio.to_thread(
            self._procedure_retrieval_service.retrieve,
            query=query,
            top_k=self._retrieval_top_k,
        )
        log_run_event(
            logger,
            logging.INFO,
            "retrieval completed",
            event="retrieval_completed",
            session_id=session_id,
            retrieval_match_count=retrieval_result.returned_count,
            corpus_sha256=retrieval_result.corpus_sha256,
            index_sha256=retrieval_result.index_sha256,
        )

        prompt_input = PlannerPromptInput(
            mission_context=mission_context,
            retrieval_result=retrieval_result,
        )
        prompt_package = self._planner_prompt_builder.build(prompt_input)
        generation_result = await self._planner_provider.generate_plan(prompt_package)

        if generation_result.prompt_sha256 != prompt_package.prompt_sha256:
            raise PlanningContextMismatchError(
                "Planner generation prompt hash does not match prompt package",
                session_id=session_id,
            )
        if generation_result.evidence_chunk_ids != prompt_package.evidence_chunk_ids:
            raise PlanningContextMismatchError(
                "Planner generation evidence chunk IDs do not match prompt package",
                session_id=session_id,
            )
        if generation_result.evidence_procedure_ids != prompt_package.evidence_procedure_ids:
            raise PlanningContextMismatchError(
                "Planner generation evidence procedure IDs do not match prompt package",
                session_id=session_id,
            )
        if generation_result.model_metadata != prompt_package.model_metadata:
            raise PlanningContextMismatchError(
                "Planner generation model metadata does not match prompt package",
                session_id=session_id,
            )

        log_run_event(
            logger,
            logging.INFO,
            "planner candidate generated",
            event="planner_candidate_generated",
            session_id=session_id,
            prompt_hash=generation_result.prompt_sha256,
            response_hash=generation_result.response_sha256,
            action_count=len(generation_result.plan.actions),
            model_id=generation_result.model_metadata.model_id,
        )

        try:
            preflight = self._candidate_validator.validate(
                retrieval_result=retrieval_result,
                generation_result=generation_result,
            )
        except PlannerCandidateUngroundedError:
            log_run_event(
                logger,
                logging.WARNING,
                "candidate rejected as ungrounded",
                event="planner_candidate_ungrounded",
                session_id=session_id,
                error_code=ErrorCode.PLANNER_CANDIDATE_UNGROUNDED.value,
            )
            raise

        log_run_event(
            logger,
            logging.INFO,
            "candidate preflight passed",
            event="planner_candidate_preflight_passed",
            session_id=session_id,
            action_count=preflight.action_count,
            evidence_procedure_count=len(preflight.evidence_procedure_ids),
        )

        attempt_id = str(self._attempt_id_provider())
        created_at = self._require_aware_now()
        attempt = PlanningAttempt(
            schema_version=PLANNING_SCHEMA_VERSION,
            attempt_id=attempt_id,
            session_id=session_id,
            scenario_id=mission_context.scenario_id,
            baseline_run_id=mission_context.baseline_run_id,
            created_at=created_at,
            status=PlanningAttemptStatus.CANDIDATE_READY,
            mission_context=mission_context,
            retrieval_result=retrieval_result,
            generation_result=generation_result,
            preflight=preflight,
        )
        persisted = self._attempt_store.create_attempt(attempt)
        log_run_event(
            logger,
            logging.INFO,
            "attempt persisted",
            event="planning_attempt_persisted",
            session_id=session_id,
            attempt_id=persisted.attempt_id,
            status=persisted.status.value,
        )
        return persisted

    async def _load_current_telemetry(self, session_id: str) -> CurrentTelemetryResponse:
        try:
            return await self._telemetry_replay_service.get_current_telemetry(session_id)
        except ReplayNotStartedError as exc:
            raise PlanningNotAvailableError(
                "Mission planning is not available before replay starts",
                session_id=session_id,
            ) from exc
        except BaselineResultMismatchError as exc:
            raise PlanningContextMismatchError(
                "Planning context sources disagree",
                session_id=session_id,
                run_id=exc.run_id,
            ) from exc
        except MissionSessionConflictError as exc:
            raise PlanningNotAvailableError(
                "Mission planning is not available for this session state",
                session_id=session_id,
            ) from exc
        except MissionSessionNotFoundError:
            raise

    def _require_planning_eligible(
        self,
        *,
        session_id: str,
        status: MissionSessionStatus,
    ) -> None:
        if status not in _PLANNING_ELIGIBLE_STATUSES:
            log_run_event(
                logger,
                logging.INFO,
                "planning not available",
                event="planning_not_available",
                session_id=session_id,
                error_code=ErrorCode.PLANNING_NOT_AVAILABLE.value,
            )
            raise PlanningNotAvailableError(
                "Mission planning is not available for this session state",
                session_id=session_id,
            )

    def _read_baseline_result(
        self,
        *,
        session_id: str,
        baseline_run_id: str,
    ) -> SimulationResult:
        try:
            return self._run_store.read_result(baseline_run_id)
        except (
            RunNotFoundError,
            RunResultNotFoundError,
            RunResultCorruptError,
            RunArtifactStorageError,
            InvalidRunIdError,
        ) as exc:
            raise PlanningContextMismatchError(
                "Baseline simulation result is unavailable for planning",
                session_id=session_id,
                run_id=baseline_run_id,
            ) from exc

    def _build_mission_context(
        self,
        *,
        session_id: str,
        current: CurrentTelemetryResponse,
        session_scenario_id: str,
        baseline_run_id: str,
        baseline_outcome: OutcomeStatus,
        sample_count: int,
        result: SimulationResult,
    ) -> PlannerMissionContext:
        if current.session_id != session_id:
            raise PlanningContextMismatchError(
                "Current telemetry session_id does not match request",
                session_id=session_id,
            )
        if current.baseline_run_id != baseline_run_id:
            raise PlanningContextMismatchError(
                "Current telemetry baseline_run_id does not match session",
                session_id=session_id,
            )
        if current.sample_count != sample_count:
            raise PlanningContextMismatchError(
                "Current telemetry sample_count does not match session",
                session_id=session_id,
            )
        if result.scenario_id != session_scenario_id:
            raise PlanningContextMismatchError(
                "Baseline result scenario_id does not match session",
                session_id=session_id,
            )
        if result.outcome != baseline_outcome:
            raise PlanningContextMismatchError(
                "Baseline result outcome does not match session",
                session_id=session_id,
            )
        if len(result.telemetry_history) != sample_count:
            raise PlanningContextMismatchError(
                "Baseline result telemetry history length does not match session",
                session_id=session_id,
            )

        expected_sample = result.telemetry_history[current.sample_index]
        if current.telemetry != expected_sample:
            raise PlanningContextMismatchError(
                "Current telemetry sample does not match baseline result history",
                session_id=session_id,
            )

        return PlannerMissionContext(
            session_id=session_id,
            scenario_id=session_scenario_id,
            baseline_run_id=baseline_run_id,
            baseline_outcome=result.outcome,
            baseline_failure_reasons=list(result.failure_reasons),
            baseline_metrics=result.metrics,
            current_sample_index=current.sample_index,
            telemetry_sample_count=sample_count,
            current_telemetry=current.telemetry,
        )

    def _require_aware_now(self) -> datetime:
        now = self._now_provider()
        if now.tzinfo is None or now.utcoffset() is None:
            raise PlanningContextMismatchError(
                "Injected now_provider returned a naive datetime",
            )
        return now
