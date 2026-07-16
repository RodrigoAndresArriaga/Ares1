# mission lifecycle orchestration (backend states only)
#
# Coordinates session creation, accident trigger, baseline linkage, and replay
# start. The C++ simulator remains authoritative for physics and telemetry.
# SessionStore is the persistent lifecycle authority. Replay position calculation
# is intentionally deferred to ReplayClock (Phase 3 Step 7).
#
# Per-session asyncio locks serialize same-process transitions only; there is
# no distributed locking.
#
# When ERROR persistence fails after a simulator/infrastructure failure, the
# storage error is raised and the original failure is retained as __cause__.
from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.errors import (
    AresBackendError,
    BaselineTelemetryEmptyError,
    MissionSessionConflictError,
    MissionSessionCorruptError,
    MissionSessionNotFoundError,
    MissionSessionStorageError,
    ReplayIntervalInvalidError,
)
from app.schemas.api import ErrorCode, SimulationRunRequest
from app.schemas.mission import (
    AccidentTriggerResponse,
    MissionCreateRequest,
    MissionSession,
    MissionSessionStatus,
)
from app.schemas.replay import ReplayStartRequest
from app.schemas.result import OutcomeStatus
from app.services.scenario_registry import ScenarioRegistry
from app.services.session_store import SessionStore
from app.services.simulation_service import SimulationService

logger = logging.getLogger("ares.mission_lifecycle")


@dataclass(frozen=True, slots=True)
class ReconciliationSummary:
    # startup recovery counts for interrupted TRIGGERING sessions
    sessions_seen: int
    triggering_recovered: int
    unchanged: int
    corrupt: int
    conflicts: int


# return current UTC as timezone-aware datetime
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MissionLifecycleService:
    # Transport-neutral mission lifecycle orchestration.
    def __init__(
        self,
        *,
        scenario_registry: ScenarioRegistry,
        session_store: SessionStore,
        simulation_service: SimulationService,
        replay_default_interval_ms: int,
        replay_min_interval_ms: int,
        replay_max_interval_ms: int,
        now_provider: Callable[[], datetime] = utc_now,
    ) -> None:
        if replay_min_interval_ms <= 0:
            raise ValueError("replay_min_interval_ms must be a strict integer > 0")
        if replay_max_interval_ms < replay_min_interval_ms:
            raise ValueError(
                "replay_max_interval_ms must be >= replay_min_interval_ms"
            )
        if not (
            replay_min_interval_ms
            <= replay_default_interval_ms
            <= replay_max_interval_ms
        ):
            raise ValueError(
                "replay_default_interval_ms must lie within "
                "replay_min_interval_ms and replay_max_interval_ms"
            )

        self._scenario_registry = scenario_registry
        self._session_store = session_store
        self._simulation_service = simulation_service
        self._replay_default_interval_ms = replay_default_interval_ms
        self._replay_min_interval_ms = replay_min_interval_ms
        self._replay_max_interval_ms = replay_max_interval_ms
        self._now_provider = now_provider

    # validate scenario, persist READY session, return strict model
    def create_session(self, request: MissionCreateRequest) -> MissionSession:
        self._scenario_registry.resolve_scenario(request.scenario_id)

        session_id = str(uuid.uuid4())
        now = self._require_aware_now()
        session = MissionSession(
            session_id=session_id,
            scenario_id=request.scenario_id,
            status=MissionSessionStatus.READY,
            created_at=now,
            updated_at=now,
            accident_triggered_at=None,
            baseline_run_id=None,
            baseline_outcome=None,
            telemetry_sample_count=None,
            replay_started_at=None,
            replay_interval_ms=None,
            error_code=None,
        )
        persisted = self._session_store.create_session(session)
        logger.info(
            "mission_session_created session_id=%s scenario_id=%s status=%s",
            persisted.session_id,
            persisted.scenario_id,
            persisted.status.value,
        )
        return persisted

    # return exact persisted session without mutation or replay reconciliation
    def get_session(self, session_id: str) -> MissionSession:
        return self._session_store.read_session(session_id)

    # recover stale TRIGGERING sessions left by an interrupted process
    async def reconcile_interrupted_sessions(self) -> ReconciliationSummary:
        session_ids = self._session_store.list_session_ids()
        sessions_seen = 0
        triggering_recovered = 0
        unchanged = 0
        corrupt = 0
        conflicts = 0

        for session_id in session_ids:
            sessions_seen += 1
            async with self._session_store.lock_session(session_id):
                try:
                    session = self._session_store.read_session(session_id)
                except (
                    MissionSessionCorruptError,
                    MissionSessionNotFoundError,
                    MissionSessionStorageError,
                ):
                    logger.error(
                        "mission_reconcile_corrupt session_id=%s code=%s",
                        session_id,
                        ErrorCode.MISSION_SESSION_CORRUPT.value,
                    )
                    corrupt += 1
                    continue

                if session.status != MissionSessionStatus.TRIGGERING:
                    unchanged += 1
                    continue

                now = self._require_aware_now()
                recovered = session.model_copy(
                    update={
                        "status": MissionSessionStatus.ERROR,
                        "updated_at": now,
                        "error_code": ErrorCode.MISSION_TRIGGER_INTERRUPTED.value,
                    }
                )
                try:
                    self._session_store.replace_session(
                        recovered,
                        expected_status=MissionSessionStatus.TRIGGERING,
                        expected_updated_at=session.updated_at,
                    )
                except MissionSessionConflictError:
                    try:
                        current = self._session_store.read_session(session_id)
                    except (
                        MissionSessionCorruptError,
                        MissionSessionNotFoundError,
                        MissionSessionStorageError,
                    ):
                        logger.error(
                            "mission_reconcile_corrupt session_id=%s code=%s",
                            session_id,
                            ErrorCode.MISSION_SESSION_CORRUPT.value,
                        )
                        corrupt += 1
                        continue
                    conflicts += 1
                    logger.info(
                        "mission_reconcile_conflict session_id=%s "
                        "actual_status=%s",
                        session_id,
                        current.status.value,
                    )
                    continue

                triggering_recovered += 1
                logger.info(
                    "mission_transition session_id=%s scenario_id=%s "
                    "old_status=%s new_status=%s error_code=%s",
                    session.session_id,
                    session.scenario_id,
                    MissionSessionStatus.TRIGGERING.value,
                    MissionSessionStatus.ERROR.value,
                    ErrorCode.MISSION_TRIGGER_INTERRUPTED.value,
                )

        summary = ReconciliationSummary(
            sessions_seen=sessions_seen,
            triggering_recovered=triggering_recovered,
            unchanged=unchanged,
            corrupt=corrupt,
            conflicts=conflicts,
        )
        logger.info(
            "mission_reconcile_summary sessions_seen=%s "
            "triggering_recovered=%s unchanged=%s corrupt=%s conflicts=%s",
            summary.sessions_seen,
            summary.triggering_recovered,
            summary.unchanged,
            summary.corrupt,
            summary.conflicts,
        )
        return summary

    # transition READY -> TRIGGERING -> BASELINE_READY under per-session lock
    async def trigger_accident(self, session_id: str) -> AccidentTriggerResponse:
        async with self._session_store.lock_session(session_id):
            session = self._session_store.read_session(session_id)
            if session.status != MissionSessionStatus.READY:
                self._raise_state_conflict(
                    session_id=session.session_id,
                    actual_status=session.status,
                    operation="trigger_accident",
                )

            trigger_at = self._require_aware_now()
            triggering = session.model_copy(
                update={
                    "status": MissionSessionStatus.TRIGGERING,
                    "accident_triggered_at": trigger_at,
                    "updated_at": trigger_at,
                    "error_code": None,
                }
            )
            triggering = self._session_store.replace_session(
                triggering,
                expected_status=MissionSessionStatus.READY,
                expected_updated_at=session.updated_at,
            )
            logger.info(
                "mission_transition session_id=%s scenario_id=%s "
                "old_status=%s new_status=%s",
                triggering.session_id,
                triggering.scenario_id,
                MissionSessionStatus.READY.value,
                MissionSessionStatus.TRIGGERING.value,
            )

            sim_request = SimulationRunRequest(
                scenario_id=triggering.scenario_id,
                plan=None,
            )
            logger.info(
                "baseline_simulation_started session_id=%s scenario_id=%s",
                triggering.session_id,
                triggering.scenario_id,
            )

            try:
                response = await self._simulation_service.run_simulation(
                    sim_request,
                )
            except asyncio.CancelledError as exc:
                self._persist_trigger_error(
                    triggering,
                    error_code=ErrorCode.MISSION_TRIGGER_CANCELLED.value,
                    original=exc,
                )
                raise
            except AresBackendError as exc:
                error_code = exc.code.value
                self._persist_trigger_error(
                    triggering,
                    error_code=error_code,
                    original=exc,
                )
                raise

            result = response.result
            if not result.telemetry_history:
                empty_error = BaselineTelemetryEmptyError(
                    session_id=triggering.session_id,
                    run_id=response.run_id,
                )
                self._persist_empty_telemetry_error(
                    triggering,
                    response_run_id=response.run_id,
                    baseline_outcome=result.outcome,
                    original=empty_error,
                )
                raise empty_error

            completion_at = self._require_aware_now()
            sample_count = len(result.telemetry_history)
            baseline_ready = triggering.model_copy(
                update={
                    "status": MissionSessionStatus.BASELINE_READY,
                    "updated_at": completion_at,
                    "baseline_run_id": response.run_id,
                    "baseline_outcome": result.outcome,
                    "telemetry_sample_count": sample_count,
                    "error_code": None,
                }
            )
            baseline_ready = self._session_store.replace_session(
                baseline_ready,
                expected_status=MissionSessionStatus.TRIGGERING,
                expected_updated_at=triggering.updated_at,
            )
            logger.info(
                "baseline_run_linked session_id=%s baseline_run_id=%s "
                "baseline_outcome=%s telemetry_sample_count=%s",
                baseline_ready.session_id,
                baseline_ready.baseline_run_id,
                baseline_ready.baseline_outcome.value
                if baseline_ready.baseline_outcome is not None
                else None,
                baseline_ready.telemetry_sample_count,
            )
            logger.info(
                "mission_transition session_id=%s old_status=%s new_status=%s",
                baseline_ready.session_id,
                MissionSessionStatus.TRIGGERING.value,
                MissionSessionStatus.BASELINE_READY.value,
            )

            return AccidentTriggerResponse(
                session=baseline_ready,
                baseline_run_id=baseline_ready.baseline_run_id,
                baseline_outcome=baseline_ready.baseline_outcome,
                telemetry_sample_count=baseline_ready.telemetry_sample_count,
            )

    # persist REPLAYING with resolved interval; no simulator or replay math
    async def start_replay(
        self,
        session_id: str,
        request: ReplayStartRequest,
    ) -> MissionSession:
        async with self._session_store.lock_session(session_id):
            session = self._session_store.read_session(session_id)

            interval = (
                request.interval_ms
                if request.interval_ms is not None
                else self._replay_default_interval_ms
            )
            if not (
                self._replay_min_interval_ms
                <= interval
                <= self._replay_max_interval_ms
            ):
                raise ReplayIntervalInvalidError(
                    provided_interval_ms=interval,
                    min_interval_ms=self._replay_min_interval_ms,
                    max_interval_ms=self._replay_max_interval_ms,
                    session_id=session.session_id,
                )

            prior_status = session.status
            if prior_status == MissionSessionStatus.BASELINE_READY:
                pass
            elif prior_status == MissionSessionStatus.COMPLETED:
                if not request.restart:
                    self._raise_state_conflict(
                        session_id=session.session_id,
                        actual_status=prior_status,
                        operation="start_replay",
                    )
            else:
                self._raise_state_conflict(
                    session_id=session.session_id,
                    actual_status=prior_status,
                    operation="start_replay",
                )

            now = self._require_aware_now()
            replaying = session.model_copy(
                update={
                    "status": MissionSessionStatus.REPLAYING,
                    "replay_started_at": now,
                    "replay_interval_ms": interval,
                    "updated_at": now,
                    "error_code": None,
                }
            )
            replaying = self._session_store.replace_session(
                replaying,
                expected_status=prior_status,
                expected_updated_at=session.updated_at,
            )

            if prior_status == MissionSessionStatus.COMPLETED:
                logger.info(
                    "replay_restarted session_id=%s replay_interval_ms=%s",
                    replaying.session_id,
                    replaying.replay_interval_ms,
                )
            else:
                logger.info(
                    "replay_started session_id=%s replay_interval_ms=%s",
                    replaying.session_id,
                    replaying.replay_interval_ms,
                )

            return replaying

    # reject naive datetimes from injected clock before persistence
    def _require_aware_now(self) -> datetime:
        now = self._now_provider()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now_provider must return a timezone-aware datetime")
        return now

    # persist ERROR after infrastructure failure; storage failure takes precedence
    def _persist_trigger_error(
        self,
        triggering: MissionSession,
        *,
        error_code: str,
        original: BaseException | None = None,
    ) -> None:
        now = self._require_aware_now()
        error_session = triggering.model_copy(
            update={
                "status": MissionSessionStatus.ERROR,
                "updated_at": now,
                "error_code": error_code,
            }
        )
        try:
            self._session_store.replace_session(
                error_session,
                expected_status=MissionSessionStatus.TRIGGERING,
                expected_updated_at=triggering.updated_at,
            )
        except MissionSessionStorageError as storage_exc:
            logger.error(
                "mission_error_persist_failed session_id=%s error_code=%s",
                triggering.session_id,
                error_code,
            )
            if original is not None:
                raise storage_exc from original
            raise
        except Exception as storage_exc:
            logger.error(
                "mission_error_persist_failed session_id=%s error_code=%s",
                triggering.session_id,
                error_code,
            )
            wrapped = MissionSessionStorageError(
                "Failed to persist mission session error state",
                session_id=triggering.session_id,
            )
            if original is not None:
                raise wrapped from original
            raise wrapped from storage_exc

        logger.info(
            "mission_transition session_id=%s old_status=%s new_status=%s "
            "error_code=%s",
            triggering.session_id,
            MissionSessionStatus.TRIGGERING.value,
            MissionSessionStatus.ERROR.value,
            error_code,
        )

    # persist ERROR for empty baseline telemetry; raise BaselineTelemetryEmptyError
    def _persist_empty_telemetry_error(
        self,
        triggering: MissionSession,
        *,
        response_run_id: str,
        baseline_outcome: OutcomeStatus,
        original: BaseException | None = None,
    ) -> None:
        now = self._require_aware_now()
        error_session = triggering.model_copy(
            update={
                "status": MissionSessionStatus.ERROR,
                "updated_at": now,
                "baseline_run_id": response_run_id,
                "baseline_outcome": baseline_outcome,
                "telemetry_sample_count": None,
                "error_code": ErrorCode.BASELINE_TELEMETRY_EMPTY.value,
            }
        )
        try:
            self._session_store.replace_session(
                error_session,
                expected_status=MissionSessionStatus.TRIGGERING,
                expected_updated_at=triggering.updated_at,
            )
        except MissionSessionStorageError as storage_exc:
            logger.error(
                "mission_error_persist_failed session_id=%s error_code=%s",
                triggering.session_id,
                ErrorCode.BASELINE_TELEMETRY_EMPTY.value,
            )
            if original is not None:
                raise storage_exc from original
            raise
        except Exception as storage_exc:
            logger.error(
                "mission_error_persist_failed session_id=%s error_code=%s",
                triggering.session_id,
                ErrorCode.BASELINE_TELEMETRY_EMPTY.value,
            )
            wrapped = MissionSessionStorageError(
                "Failed to persist mission session error state",
                session_id=triggering.session_id,
            )
            if original is not None:
                raise wrapped from original
            raise wrapped from storage_exc

        logger.info(
            "mission_transition session_id=%s old_status=%s new_status=%s "
            "error_code=%s",
            triggering.session_id,
            MissionSessionStatus.TRIGGERING.value,
            MissionSessionStatus.ERROR.value,
            ErrorCode.BASELINE_TELEMETRY_EMPTY.value,
        )

    # log and raise lifecycle state conflict
    def _raise_state_conflict(
        self,
        *,
        session_id: str,
        actual_status: MissionSessionStatus,
        operation: str,
    ) -> None:
        logger.info(
            "mission_state_conflict session_id=%s operation=%s "
            "actual_status=%s code=%s",
            session_id,
            operation,
            actual_status.value,
            ErrorCode.MISSION_STATE_CONFLICT.value,
        )
        raise MissionSessionConflictError(
            "Mission session state conflict",
            session_id=session_id,
        )
