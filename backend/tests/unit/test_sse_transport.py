# unit tests for SSE framing and ReplayStreamLimiter
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from app.api.sse import (
    HEARTBEAT_FRAME,
    ReplayStreamLimiter,
    format_replay_event,
    generate_replay_stream,
)
from app.core.errors import BaselineResultUnavailableError
from app.schemas.api import ErrorCode
from app.schemas.replay import ReplayCompleteEvent, ReplayTelemetryEvent
from app.schemas.result import OutcomeStatus
from app.services.telemetry_replay_service import (
    ReplayEventBatch,
    ReplayServiceEvent,
)
from tests.conftest import RESULTS_DIR

SESSION_ID = "00000000-0000-4000-8000-000000000001"
RUN_ID = "00000000-0000-4000-8000-000000000003"


def _baseline_sample() -> object:
    payload = json.loads((RESULTS_DIR / "baseline_result.json").read_text(encoding="utf-8"))
    return payload["telemetry_history"][0]


class _ConnectedRequest:
    async def is_disconnected(self) -> bool:
        return False


def _telemetry_batch(*, sequence: int = 0, delay_ms: int = 250) -> ReplayEventBatch:
    from app.schemas.telemetry import TelemetrySample

    sample = TelemetrySample.model_validate(_baseline_sample())
    payload = ReplayTelemetryEvent(
        session_id=SESSION_ID,
        sequence=sequence,
        sample_index=sequence,
        sample_count=6,
        telemetry=sample,
    )
    event = ReplayServiceEvent(
        event_type="telemetry",
        sequence=sequence,
        payload=payload,
    )
    return ReplayEventBatch(
        events=(event,),
        milliseconds_until_next_event=delay_ms,
        terminal=False,
    )


def test_format_telemetry_frame_order_and_compact_json() -> None:
    from app.schemas.telemetry import TelemetrySample

    sample = TelemetrySample.model_validate(_baseline_sample())
    payload = ReplayTelemetryEvent(
        session_id=SESSION_ID,
        sequence=0,
        sample_index=0,
        sample_count=6,
        telemetry=sample,
    )
    event = ReplayServiceEvent(
        event_type="telemetry",
        sequence=0,
        payload=payload,
    )
    frame = format_replay_event(event)
    text = frame.decode("utf-8")
    assert text.endswith("\n\n")
    assert "\r" not in text
    lines = text[:-2].split("\n")
    assert lines[0] == "id: 0"
    assert lines[1] == "event: telemetry"
    assert lines[2].startswith("data: ")
    data = json.loads(lines[2].removeprefix("data: "))
    assert data == json.loads(payload.model_dump_json())
    assert "\n" not in lines[2].removeprefix("data: ")


def test_format_complete_frame() -> None:
    from app.schemas.result import SimulationResult

    result = SimulationResult.model_validate_json(
        (RESULTS_DIR / "baseline_result.json").read_bytes()
    )
    payload = ReplayCompleteEvent(
        session_id=SESSION_ID,
        sequence=6,
        baseline_run_id=RUN_ID,
        outcome=result.outcome,
        valid_plan=result.valid_plan,
        failure_reasons=list(result.failure_reasons),
        metrics=result.metrics,
    )
    event = ReplayServiceEvent(
        event_type="complete",
        sequence=6,
        payload=payload,
    )
    text = format_replay_event(event).decode("utf-8")
    assert text.startswith("id: 6\nevent: complete\ndata: ")
    assert text.endswith("\n\n")
    data = json.loads(text.split("\n")[2].removeprefix("data: "))
    assert data["outcome"] == OutcomeStatus.FAILURE.value
    assert "survival_probability" not in data


def test_heartbeat_frame_is_comment_only() -> None:
    assert HEARTBEAT_FRAME == b": heartbeat\n\n"
    text = HEARTBEAT_FRAME.decode("utf-8")
    assert "id:" not in text
    assert "event:" not in text
    assert "data:" not in text


@pytest.mark.asyncio
async def test_limiter_capacity_and_idempotent_release() -> None:
    limiter = ReplayStreamLimiter(capacity=1)
    first = await limiter.try_acquire()
    assert first is not None
    assert limiter.active_count == 1
    second = await limiter.try_acquire()
    assert second is None
    assert limiter.active_count == 1
    await first.release()
    assert limiter.active_count == 0
    await first.release()
    assert limiter.active_count == 0
    third = await limiter.try_acquire()
    assert third is not None
    await third.release()


@pytest.mark.asyncio
async def test_limiter_rejects_nonpositive_capacity() -> None:
    with pytest.raises(ValueError):
        ReplayStreamLimiter(capacity=0)


@pytest.mark.asyncio
async def test_limiter_concurrent_acquire_respects_capacity() -> None:
    limiter = ReplayStreamLimiter(capacity=2)

    async def acquire_one() -> object:
        return await limiter.try_acquire()

    leases = await asyncio.gather(*[acquire_one() for _ in range(5)])
    acquired = [lease for lease in leases if lease is not None]
    assert len(acquired) == 2
    assert limiter.active_count == 2
    await asyncio.gather(*[lease.release() for lease in acquired])
    assert limiter.active_count == 0


@pytest.mark.asyncio
async def test_post_header_service_error_releases_lease() -> None:
    limiter = ReplayStreamLimiter(capacity=1)
    lease = await limiter.try_acquire()
    assert lease is not None
    assert limiter.active_count == 1

    service = AsyncMock()
    service.get_due_events = AsyncMock(
        side_effect=BaselineResultUnavailableError(
            "Baseline result unavailable",
            session_id=SESSION_ID,
            run_id=RUN_ID,
        )
    )
    initial = _telemetry_batch(delay_ms=10)

    async def sleeper(_delay: float) -> None:
        return None

    chunks: list[bytes] = []
    async for chunk in generate_replay_stream(
        request=_ConnectedRequest(),  # type: ignore[arg-type]
        service=service,
        lease=lease,
        session_id=SESSION_ID,
        initial_batch=initial,
        initial_last_event_id=None,
        heartbeat_seconds=15.0,
        sleep=sleeper,
    ):
        chunks.append(chunk)

    assert any(b"event: telemetry" in chunk for chunk in chunks)
    joined = b"".join(chunks)
    assert b"Traceback" not in joined
    assert b"Baseline result unavailable" not in joined
    assert ErrorCode.BASELINE_RESULT_UNAVAILABLE.value.encode() not in joined
    assert limiter.active_count == 0

    reacquired = await limiter.try_acquire()
    assert reacquired is not None
    await reacquired.release()


@pytest.mark.asyncio
async def test_post_header_unexpected_error_releases_lease() -> None:
    limiter = ReplayStreamLimiter(capacity=1)
    lease = await limiter.try_acquire()
    assert lease is not None

    service = AsyncMock()
    service.get_due_events = AsyncMock(side_effect=RuntimeError("boom-secret"))
    initial = _telemetry_batch(delay_ms=10)

    async def sleeper(_delay: float) -> None:
        return None

    chunks: list[bytes] = []
    async for chunk in generate_replay_stream(
        request=_ConnectedRequest(),  # type: ignore[arg-type]
        service=service,
        lease=lease,
        session_id=SESSION_ID,
        initial_batch=initial,
        initial_last_event_id=None,
        heartbeat_seconds=15.0,
        sleep=sleeper,
    ):
        chunks.append(chunk)

    joined = b"".join(chunks)
    assert b"boom-secret" not in joined
    assert b"Traceback" not in joined
    assert limiter.active_count == 0


@pytest.mark.asyncio
async def test_stream_cancellation_releases_lease_and_reraises() -> None:
    limiter = ReplayStreamLimiter(capacity=1)
    lease = await limiter.try_acquire()
    assert lease is not None

    service = AsyncMock()
    service.get_due_events = AsyncMock(
        return_value=ReplayEventBatch(
            events=(),
            milliseconds_until_next_event=60_000,
            terminal=False,
        )
    )
    initial = _telemetry_batch(delay_ms=60_000)

    async def sleeper(_delay: float) -> None:
        raise asyncio.CancelledError()

    gen = generate_replay_stream(
        request=_ConnectedRequest(),  # type: ignore[arg-type]
        service=service,
        lease=lease,
        session_id=SESSION_ID,
        initial_batch=initial,
        initial_last_event_id=None,
        heartbeat_seconds=15.0,
        sleep=sleeper,
    )
    with pytest.raises(asyncio.CancelledError):
        async for _chunk in gen:
            pass

    assert limiter.active_count == 0
    reacquired = await limiter.try_acquire()
    assert reacquired is not None
    await reacquired.release()
