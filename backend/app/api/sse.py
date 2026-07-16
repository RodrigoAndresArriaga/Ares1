# SSE transport helpers for telemetry replay streams
# owns framing, heartbeats, sleep polling, and stream-slot leases
# does not select samples or parse Last-Event-ID
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

from starlette.requests import Request

from app.core.errors import AresBackendError
from app.services.telemetry_replay_service import (
    ReplayEventBatch,
    ReplayServiceEvent,
    TelemetryReplayService,
)

logger = logging.getLogger("ares.sse")

HEARTBEAT_FRAME = b": heartbeat\n\n"

SleepFn = Callable[[float], Coroutine[Any, Any, None]]


@dataclass(slots=True)
class StreamLease:
    # idempotent release token for one acquired stream slot
    _limiter: ReplayStreamLimiter
    _released: bool = field(default=False, init=False, repr=False)

    @property
    def active_count(self) -> int:
        return self._limiter.active_count

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        await self._limiter._release_slot()


class ReplayStreamLimiter:
    # in-process nonblocking capacity gate for concurrent SSE streams
    def __init__(self, *, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be greater than 0")
        self._capacity = capacity
        self._active = 0
        self._lock = asyncio.Lock()

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def active_count(self) -> int:
        return self._active

    async def try_acquire(self) -> StreamLease | None:
        async with self._lock:
            if self._active >= self._capacity:
                return None
            self._active += 1
            return StreamLease(_limiter=self)

    async def _release_slot(self) -> None:
        async with self._lock:
            if self._active <= 0:
                return
            self._active -= 1


# format one service event as a compact SSE frame
def format_replay_event(event: ReplayServiceEvent) -> bytes:
    data = event.payload.model_dump_json()
    frame = (
        f"id: {event.sequence}\n"
        f"event: {event.event_type}\n"
        f"data: {data}\n"
        f"\n"
    )
    return frame.encode("utf-8")


# poll TelemetryReplayService and yield SSE frames until terminal or disconnect
async def generate_replay_stream(
    *,
    request: Request,
    service: TelemetryReplayService,
    lease: StreamLease,
    session_id: str,
    initial_batch: ReplayEventBatch,
    initial_last_event_id: str | None,
    heartbeat_seconds: float,
    sleep: SleepFn | None = None,
) -> AsyncIterator[bytes]:
    sleeper: SleepFn = sleep if sleep is not None else asyncio.sleep
    last_event_id = initial_last_event_id
    batch = initial_batch
    emitted = 0
    terminal = False
    disconnected = False
    cancelled = False

    try:
        logger.info(
            "replay_stream_connected session_id=%s last_event_id=%s",
            session_id,
            initial_last_event_id,
        )
        while True:
            if await request.is_disconnected():
                disconnected = True
                return

            for event in batch.events:
                if await request.is_disconnected():
                    disconnected = True
                    return
                yield format_replay_event(event)
                last_event_id = str(event.sequence)
                emitted += 1

            if batch.terminal:
                terminal = True
                return

            delay_ms = batch.milliseconds_until_next_event
            delay_seconds = delay_ms / 1000.0
            heartbeat_due = delay_seconds > heartbeat_seconds

            if delay_seconds > 0:
                if await request.is_disconnected():
                    disconnected = True
                    return
                await sleeper(min(delay_seconds, heartbeat_seconds))
                if await request.is_disconnected():
                    disconnected = True
                    return
                if heartbeat_due:
                    yield HEARTBEAT_FRAME

            try:
                batch = await service.get_due_events(
                    session_id,
                    last_event_id=last_event_id,
                )
            except AresBackendError as exc:
                logger.warning(
                    "replay_stream_post_header_error session_id=%s code=%s",
                    session_id,
                    exc.code.value,
                )
                return
            except Exception:
                logger.exception(
                    "replay_stream_post_header_unexpected session_id=%s",
                    session_id,
                )
                return
    except asyncio.CancelledError:
        cancelled = True
        raise
    finally:
        await lease.release()
        if cancelled:
            logger.info(
                "replay_stream_cancelled session_id=%s emitted=%s",
                session_id,
                emitted,
            )
        elif disconnected:
            logger.info(
                "replay_stream_disconnected session_id=%s emitted=%s",
                session_id,
                emitted,
            )
        elif terminal:
            logger.info(
                "replay_stream_completed session_id=%s emitted=%s terminal=%s",
                session_id,
                emitted,
                terminal,
            )
        else:
            logger.info(
                "replay_stream_terminated session_id=%s emitted=%s",
                session_id,
                emitted,
            )
        logger.info(
            "replay_stream_slot_released session_id=%s active=%s",
            session_id,
            lease.active_count,
        )
