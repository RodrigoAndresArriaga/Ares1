# transport-neutral telemetry replay sample selection and event envelopes
# uses ReplayClock for position; SessionStore for COMPLETED reconciliation
# does not sleep, format SSE, or mutate simulator result artifacts
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.core.errors import (
    BaselineResultMismatchError,
    BaselineResultUnavailableError,
    InvalidRunIdError,
    MissionSessionConflictError,
    ReplayEventIdInvalidError,
    ReplayNotStartedError,
    RunArtifactStorageError,
    RunNotFoundError,
    RunResultCorruptError,
    RunResultNotFoundError,
)
from app.schemas.api import ErrorCode
from app.schemas.mission import MissionSession, MissionSessionStatus
from app.schemas.replay import (
    CurrentTelemetryResponse,
    ReplayCompleteEvent,
    ReplayTelemetryEvent,
)
from app.schemas.result import SimulationResult
from app.services.mission_lifecycle_service import utc_now
from app.services.replay_clock import ReplayClock, ReplayPosition
from app.services.run_store import RunStore
from app.services.session_store import SessionStore

logger = logging.getLogger("ares.telemetry_replay")

_NOT_STARTED_STATUSES = frozenset(
    {
        MissionSessionStatus.READY,
        MissionSessionStatus.TRIGGERING,
        MissionSessionStatus.BASELINE_READY,
    }
)


@dataclass(frozen=True, slots=True)
class ReplayServiceEvent:
    # one ordered replay envelope with matching nested sequence
    event_type: Literal["telemetry", "complete"]
    sequence: int
    payload: ReplayTelemetryEvent | ReplayCompleteEvent


@dataclass(frozen=True, slots=True)
class ReplayEventBatch:
    # immutable catch-up batch with delay hint and terminal flag
    events: tuple[ReplayServiceEvent, ...]
    milliseconds_until_next_event: int
    terminal: bool


@dataclass(frozen=True, slots=True)
class _ReplayContext:
    # reconciled session, linked result, and clock position for one operation
    session: MissionSession
    result: SimulationResult
    position: ReplayPosition
    sample_count: int
    baseline_run_id: str


class TelemetryReplayService:
    # Exact sample selection and ordered catch-up for mission telemetry replay.
    # ReplayClock owns position math. SessionStore owns COMPLETED persistence.
    # Does not sleep, format SSE, or store a client cursor.

    def __init__(
        self,
        *,
        session_store: SessionStore,
        run_store: RunStore,
        now_provider: Callable[[], datetime] = utc_now,
    ) -> None:
        self._session_store = session_store
        self._run_store = run_store
        self._now_provider = now_provider

    async def get_current_telemetry(
        self,
        session_id: str,
    ) -> CurrentTelemetryResponse:
        async with self._session_store.lock_session(session_id):
            ctx = self._load_replay_context(session_id)
            sample = ctx.result.telemetry_history[ctx.position.sample_index]
            return CurrentTelemetryResponse(
                session_id=ctx.session.session_id,
                status=ctx.session.status,
                sample_index=ctx.position.sample_index,
                sample_count=ctx.sample_count,
                telemetry=sample,
                baseline_run_id=ctx.baseline_run_id,
            )

    async def get_due_events(
        self,
        session_id: str,
        *,
        last_event_id: str | None,
    ) -> ReplayEventBatch:
        async with self._session_store.lock_session(session_id):
            ctx = self._load_replay_context(session_id)
            last_sequence = _parse_last_event_id(
                last_event_id,
                sample_count=ctx.sample_count,
                session_id=ctx.session.session_id,
            )
            return self._build_event_batch(ctx, last_sequence=last_sequence)

    # load session + result, verify integrity, compute position, maybe COMPLETE
    def _load_replay_context(self, session_id: str) -> _ReplayContext:
        session = self._session_store.read_session(session_id)
        self._require_replay_status(session)

        baseline_run_id = session.baseline_run_id
        sample_count = session.telemetry_sample_count
        replay_started_at = session.replay_started_at
        replay_interval_ms = session.replay_interval_ms
        if (
            baseline_run_id is None
            or sample_count is None
            or replay_started_at is None
            or replay_interval_ms is None
            or session.baseline_outcome is None
        ):
            raise MissionSessionConflictError(
                "Mission session is missing required replay fields",
                session_id=session.session_id,
            )

        result = self._read_linked_result(
            session_id=session.session_id,
            baseline_run_id=baseline_run_id,
        )
        self._verify_linked_result(session, result, baseline_run_id=baseline_run_id)

        now = self._require_aware_now()
        position = ReplayClock.position_at(
            replay_started_at=replay_started_at,
            current_time=now,
            replay_interval_ms=replay_interval_ms,
            telemetry_sample_count=sample_count,
        )

        if session.status == MissionSessionStatus.COMPLETED:
            position = ReplayPosition(
                sample_index=sample_count - 1,
                complete=True,
                milliseconds_until_next_sample=0,
            )
        elif position.complete and session.status == MissionSessionStatus.REPLAYING:
            session = self._persist_completed(session, now=now)

        logger.debug(
            "replay_context_loaded session_id=%s baseline_run_id=%s "
            "status=%s sample_index=%s sample_count=%s complete=%s",
            session.session_id,
            baseline_run_id,
            session.status.value,
            position.sample_index,
            sample_count,
            position.complete,
        )
        return _ReplayContext(
            session=session,
            result=result,
            position=position,
            sample_count=sample_count,
            baseline_run_id=baseline_run_id,
        )

    def _require_replay_status(self, session: MissionSession) -> None:
        if session.status in _NOT_STARTED_STATUSES:
            logger.info(
                "replay_not_started session_id=%s actual_status=%s code=%s",
                session.session_id,
                session.status.value,
                ErrorCode.REPLAY_NOT_STARTED.value,
            )
            raise ReplayNotStartedError(
                "Mission replay has not started",
                session_id=session.session_id,
            )
        if session.status == MissionSessionStatus.ERROR:
            logger.info(
                "mission_state_conflict session_id=%s operation=%s "
                "actual_status=%s code=%s",
                session.session_id,
                "telemetry_replay",
                session.status.value,
                ErrorCode.MISSION_STATE_CONFLICT.value,
            )
            raise MissionSessionConflictError(
                "Mission session state conflict",
                session_id=session.session_id,
            )
        if session.status not in (
            MissionSessionStatus.REPLAYING,
            MissionSessionStatus.COMPLETED,
        ):
            raise MissionSessionConflictError(
                "Mission session state conflict",
                session_id=session.session_id,
            )

    def _read_linked_result(
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
            logger.error(
                "baseline_result_unavailable session_id=%s baseline_run_id=%s "
                "code=%s",
                session_id,
                baseline_run_id,
                ErrorCode.BASELINE_RESULT_UNAVAILABLE.value,
            )
            raise BaselineResultUnavailableError(
                "Baseline simulation result is unavailable",
                session_id=session_id,
                run_id=baseline_run_id,
            ) from exc

    def _verify_linked_result(
        self,
        session: MissionSession,
        result: SimulationResult,
        *,
        baseline_run_id: str,
    ) -> None:
        sample_count = session.telemetry_sample_count
        if (
            result.scenario_id != session.scenario_id
            or result.outcome != session.baseline_outcome
            or sample_count is None
            or len(result.telemetry_history) != sample_count
            or len(result.telemetry_history) == 0
        ):
            logger.error(
                "baseline_result_mismatch session_id=%s baseline_run_id=%s "
                "code=%s",
                session.session_id,
                baseline_run_id,
                ErrorCode.BASELINE_RESULT_MISMATCH.value,
            )
            raise BaselineResultMismatchError(
                "Baseline simulation result does not match mission session",
                session_id=session.session_id,
                run_id=baseline_run_id,
            )

    def _persist_completed(
        self,
        session: MissionSession,
        *,
        now: datetime,
    ) -> MissionSession:
        completed = session.model_copy(
            update={
                "status": MissionSessionStatus.COMPLETED,
                "updated_at": now,
                "error_code": None,
            }
        )
        persisted = self._session_store.replace_session(
            completed,
            expected_status=MissionSessionStatus.REPLAYING,
            expected_updated_at=session.updated_at,
        )
        logger.info(
            "mission_transition session_id=%s old_status=%s new_status=%s",
            session.session_id,
            MissionSessionStatus.REPLAYING.value,
            MissionSessionStatus.COMPLETED.value,
        )
        return persisted

    def _build_event_batch(
        self,
        ctx: _ReplayContext,
        *,
        last_sequence: int,
    ) -> ReplayEventBatch:
        n = ctx.sample_count
        due_index = ctx.position.sample_index
        events: list[ReplayServiceEvent] = []

        if last_sequence >= n:
            batch = ReplayEventBatch(
                events=(),
                milliseconds_until_next_event=0,
                terminal=True,
            )
            self._log_batch_summary(ctx, batch)
            return batch

        start = last_sequence + 1
        end = due_index
        for index in range(max(start, 0), min(end, n - 1) + 1):
            payload = ReplayTelemetryEvent(
                session_id=ctx.session.session_id,
                sequence=index,
                sample_index=index,
                sample_count=n,
                telemetry=ctx.result.telemetry_history[index],
            )
            events.append(
                ReplayServiceEvent(
                    event_type="telemetry",
                    sequence=index,
                    payload=payload,
                )
            )

        if ctx.position.complete and last_sequence < n:
            complete_payload = ReplayCompleteEvent(
                session_id=ctx.session.session_id,
                sequence=n,
                baseline_run_id=ctx.baseline_run_id,
                outcome=ctx.result.outcome,
                valid_plan=ctx.result.valid_plan,
                failure_reasons=list(ctx.result.failure_reasons),
                metrics=ctx.result.metrics,
            )
            events.append(
                ReplayServiceEvent(
                    event_type="complete",
                    sequence=n,
                    payload=complete_payload,
                )
            )

        terminal = ctx.position.complete and (
            last_sequence >= n or any(e.event_type == "complete" for e in events)
        )
        if events:
            delay = 0
        elif ctx.position.complete:
            delay = 0
            terminal = True
        else:
            delay = ctx.position.milliseconds_until_next_sample
            terminal = False

        batch = ReplayEventBatch(
            events=tuple(events),
            milliseconds_until_next_event=delay,
            terminal=terminal,
        )
        self._log_batch_summary(ctx, batch)
        return batch

    def _log_batch_summary(
        self,
        ctx: _ReplayContext,
        batch: ReplayEventBatch,
    ) -> None:
        logger.debug(
            "replay_batch session_id=%s baseline_run_id=%s events_emitted=%s "
            "terminal=%s delay_ms=%s sample_index=%s sample_count=%s",
            ctx.session.session_id,
            ctx.baseline_run_id,
            len(batch.events),
            batch.terminal,
            batch.milliseconds_until_next_event,
            ctx.position.sample_index,
            ctx.sample_count,
        )

    def _require_aware_now(self) -> datetime:
        now = self._now_provider()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now_provider must return a timezone-aware datetime")
        return now


# parse Last-Event-ID as canonical base-10 sequence in 0..N inclusive
def _parse_last_event_id(
    raw: str | None,
    *,
    sample_count: int,
    session_id: str,
) -> int:
    if raw is None:
        return -1
    if not raw.isdigit() or str(int(raw)) != raw:
        logger.info(
            "replay_event_id_invalid session_id=%s code=%s",
            session_id,
            ErrorCode.REPLAY_EVENT_ID_INVALID.value,
        )
        raise ReplayEventIdInvalidError(
            "Replay Last-Event-ID is invalid",
            session_id=session_id,
        )
    value = int(raw)
    if value > sample_count:
        logger.info(
            "replay_event_id_invalid session_id=%s code=%s",
            session_id,
            ErrorCode.REPLAY_EVENT_ID_INVALID.value,
        )
        raise ReplayEventIdInvalidError(
            "Replay Last-Event-ID is invalid",
            session_id=session_id,
        )
    return value
