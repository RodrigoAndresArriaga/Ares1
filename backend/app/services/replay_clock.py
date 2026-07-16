# pure deterministic time-to-index calculator for telemetry replay
# first sample is due at replay start; does not mutate lifecycle state
# does not sleep or read the system clock; sample selection is TelemetryReplayService
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

_US_PER_DAY = 86_400_000_000
_US_PER_SECOND = 1_000_000
_US_PER_MS = 1000


class ReplayClockError(ValueError):
    # invalid ReplayClock inputs
    pass


@dataclass(frozen=True, slots=True)
class ReplayPosition:
    # immutable replay index, completion, and ceiling delay to next sample
    sample_index: int
    complete: bool
    milliseconds_until_next_sample: int


class ReplayClock:
    # Pure deterministic map from injected timestamps to sample index.
    # Does not mutate lifecycle state, sleep, or access the system clock.
    # Sample selection belongs to TelemetryReplayService.

    @staticmethod
    def position_at(
        *,
        replay_started_at: datetime,
        current_time: datetime,
        replay_interval_ms: int,
        telemetry_sample_count: int,
    ) -> ReplayPosition:
        _require_aware(replay_started_at, field_name="replay_started_at")
        _require_aware(current_time, field_name="current_time")
        _require_positive_strict_int(
            replay_interval_ms,
            field_name="replay_interval_ms",
        )
        _require_positive_strict_int(
            telemetry_sample_count,
            field_name="telemetry_sample_count",
        )

        interval_us = replay_interval_ms * _US_PER_MS
        elapsed_us = _elapsed_us(replay_started_at, current_time)
        raw_index = elapsed_us // interval_us
        sample_index = min(telemetry_sample_count - 1, raw_index)
        final_due_us = interval_us * (telemetry_sample_count - 1)
        complete = elapsed_us >= final_due_us

        if complete:
            delay_ms = 0
        else:
            next_due_us = interval_us * (sample_index + 1)
            remaining_us = max(0, next_due_us - elapsed_us)
            delay_ms = (remaining_us + 999) // 1000

        return ReplayPosition(
            sample_index=sample_index,
            complete=complete,
            milliseconds_until_next_sample=delay_ms,
        )


# reject naive datetimes
def _require_aware(value: datetime, *, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ReplayClockError(f"{field_name} must be timezone-aware")


# reject bool and non-int; require positive integer
def _require_positive_strict_int(value: object, *, field_name: str) -> None:
    if isinstance(value, bool) or type(value) is not int:
        raise ReplayClockError(f"{field_name} must be a positive integer")
    if value <= 0:
        raise ReplayClockError(f"{field_name} must be a positive integer")


# integer microseconds elapsed, clamped at zero for future start
def _elapsed_us(replay_started_at: datetime, current_time: datetime) -> int:
    delta = current_time - replay_started_at
    total_us = (
        delta.days * _US_PER_DAY
        + delta.seconds * _US_PER_SECOND
        + delta.microseconds
    )
    return max(0, total_us)
