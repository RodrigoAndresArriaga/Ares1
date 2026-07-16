# ReplayClock unit tests (Phase 3 Step 7)
from __future__ import annotations

import ast
import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from app.services.replay_clock import ReplayClock, ReplayClockError, ReplayPosition

START = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
INTERVAL_250 = 250
SIX = 6


# build current_time as start + exact microsecond offset
def at_us(offset_us: int) -> datetime:
    return START + timedelta(microseconds=offset_us)


# build current_time as start + millisecond offset
def at_ms(offset_ms: int) -> datetime:
    return at_us(offset_ms * 1000)


def position(
    current: datetime,
    *,
    interval_ms: int = INTERVAL_250,
    sample_count: int = SIX,
    started: datetime = START,
) -> ReplayPosition:
    return ReplayClock.position_at(
        replay_started_at=started,
        current_time=current,
        replay_interval_ms=interval_ms,
        telemetry_sample_count=sample_count,
    )


# --- A. Input validation ---


def test_naive_replay_started_at_rejected() -> None:
    naive = datetime(2026, 7, 15, 12, 0, 0)
    with pytest.raises(ReplayClockError, match="replay_started_at"):
        position(at_ms(0), started=naive)


def test_naive_current_time_rejected() -> None:
    naive = datetime(2026, 7, 15, 12, 0, 0)
    with pytest.raises(ReplayClockError, match="current_time"):
        ReplayClock.position_at(
            replay_started_at=START,
            current_time=naive,
            replay_interval_ms=INTERVAL_250,
            telemetry_sample_count=SIX,
        )


@pytest.mark.parametrize("interval", [0, -1, -250])
def test_non_positive_interval_rejected(interval: int) -> None:
    with pytest.raises(ReplayClockError, match="replay_interval_ms"):
        position(at_ms(0), interval_ms=interval)


@pytest.mark.parametrize("count", [0, -1, -6])
def test_non_positive_sample_count_rejected(count: int) -> None:
    with pytest.raises(ReplayClockError, match="telemetry_sample_count"):
        position(at_ms(0), sample_count=count)


@pytest.mark.parametrize("interval", [True, False])
def test_bool_interval_rejected(interval: bool) -> None:
    with pytest.raises(ReplayClockError, match="replay_interval_ms"):
        ReplayClock.position_at(
            replay_started_at=START,
            current_time=at_ms(0),
            replay_interval_ms=interval,  # type: ignore[arg-type]
            telemetry_sample_count=SIX,
        )


@pytest.mark.parametrize("count", [True, False])
def test_bool_sample_count_rejected(count: bool) -> None:
    with pytest.raises(ReplayClockError, match="telemetry_sample_count"):
        ReplayClock.position_at(
            replay_started_at=START,
            current_time=at_ms(0),
            replay_interval_ms=INTERVAL_250,
            telemetry_sample_count=count,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("interval", [250.0, "250", 250.5])
def test_non_integer_interval_rejected(interval: object) -> None:
    with pytest.raises(ReplayClockError, match="replay_interval_ms"):
        ReplayClock.position_at(
            replay_started_at=START,
            current_time=at_ms(0),
            replay_interval_ms=interval,  # type: ignore[arg-type]
            telemetry_sample_count=SIX,
        )


@pytest.mark.parametrize("count", [6.0, "6", 6.5])
def test_non_integer_sample_count_rejected(count: object) -> None:
    with pytest.raises(ReplayClockError, match="telemetry_sample_count"):
        ReplayClock.position_at(
            replay_started_at=START,
            current_time=at_ms(0),
            replay_interval_ms=INTERVAL_250,
            telemetry_sample_count=count,  # type: ignore[arg-type]
        )


# --- B. First sample ---


def test_first_sample_at_exact_start() -> None:
    pos = position(at_ms(0))
    assert pos.sample_index == 0
    assert pos.complete is False
    assert pos.milliseconds_until_next_sample == INTERVAL_250


# --- C. Exact boundaries (six samples, 250 ms) ---


@pytest.mark.parametrize(
    ("elapsed_ms", "index", "complete", "delay"),
    [
        (0, 0, False, 250),
        (249, 0, False, 1),
        (250, 1, False, 250),
        (499, 1, False, 1),
        (500, 2, False, 250),
        (1000, 4, False, 250),
        (1249, 4, False, 1),
        (1250, 5, True, 0),
        (1500, 5, True, 0),
    ],
)
def test_exact_ms_boundaries(
    elapsed_ms: int,
    index: int,
    complete: bool,
    delay: int,
) -> None:
    pos = position(at_ms(elapsed_ms))
    assert pos.sample_index == index
    assert pos.complete is complete
    assert pos.milliseconds_until_next_sample == delay


# --- D. Microsecond boundaries ---


@pytest.mark.parametrize(
    ("elapsed_us", "index", "complete", "delay"),
    [
        (249_999, 0, False, 1),
        (250_000, 1, False, 250),
        (250_001, 1, False, 250),
        (1_249_999, 4, False, 1),
        (1_250_000, 5, True, 0),
        (1_250_001, 5, True, 0),
    ],
)
def test_microsecond_boundaries(
    elapsed_us: int,
    index: int,
    complete: bool,
    delay: int,
) -> None:
    pos = position(at_us(elapsed_us))
    assert pos.sample_index == index
    assert pos.complete is complete
    assert pos.milliseconds_until_next_sample == delay


# --- E. One-sample replay ---


@pytest.mark.parametrize(
    "current",
    [
        START - timedelta(seconds=5),
        START,
        START + timedelta(seconds=5),
        START + timedelta(hours=1),
    ],
)
def test_one_sample_always_complete(current: datetime) -> None:
    pos = position(current, sample_count=1)
    assert pos.sample_index == 0
    assert pos.complete is True
    assert pos.milliseconds_until_next_sample == 0


# --- F. Future start ---


def test_future_start_clamps_elapsed_to_zero() -> None:
    pos = position(START - timedelta(milliseconds=100))
    assert pos.sample_index == 0
    assert pos.complete is False
    assert pos.milliseconds_until_next_sample == INTERVAL_250


# --- G. Different timezones ---


def test_equivalent_utc_offsets_yield_same_position() -> None:
    start_utc = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
    start_east = datetime(
        2026, 7, 15, 14, 0, 0, tzinfo=timezone(timedelta(hours=2))
    )
    current_utc = start_utc + timedelta(milliseconds=500)
    current_west = datetime(
        2026, 7, 15, 7, 0, 0, 500_000, tzinfo=timezone(timedelta(hours=-5))
    )
    a = position(current_utc, started=start_utc)
    b = position(current_west, started=start_east)
    assert a == b
    assert a.sample_index == 2
    assert a.complete is False
    assert a.milliseconds_until_next_sample == 250


# --- H. Long elapsed time ---


def test_long_elapsed_clamps_to_final() -> None:
    pos = position(START + timedelta(days=30))
    assert pos.sample_index == 5
    assert pos.complete is True
    assert pos.milliseconds_until_next_sample == 0


# --- I. Large valid values ---


def test_large_sample_count_and_interval_boundary() -> None:
    count = 100_000
    interval_ms = 60_000
    # near high-index boundary: index 99998 due just before final
    elapsed_ms = interval_ms * 99_998
    pos = position(
        at_ms(elapsed_ms),
        interval_ms=interval_ms,
        sample_count=count,
    )
    assert pos.sample_index == 99_998
    assert pos.complete is False
    assert pos.milliseconds_until_next_sample == interval_ms

    final = position(
        at_ms(interval_ms * (count - 1)),
        interval_ms=interval_ms,
        sample_count=count,
    )
    assert final.sample_index == count - 1
    assert final.complete is True
    assert final.milliseconds_until_next_sample == 0


# --- J. Determinism ---


def test_determinism_identical_inputs() -> None:
    current = at_ms(750)
    first = position(current)
    second = position(current)
    third = position(current)
    assert first == second == third


# --- K. No input mutation ---


def test_datetime_inputs_unchanged() -> None:
    started = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
    current = datetime(2026, 7, 15, 12, 0, 0, 500_000, tzinfo=timezone.utc)
    started_copy = started.replace()
    current_copy = current.replace()
    position(current, started=started)
    assert started == started_copy
    assert current == current_copy


# --- L. Frozen output ---


def test_replay_position_is_frozen() -> None:
    pos = position(at_ms(0))
    with pytest.raises(Exception):
        pos.sample_index = 1  # type: ignore[misc]


# --- M. No external side effects / forbidden imports ---


def test_replay_clock_has_no_forbidden_imports() -> None:
    module_name = "app.services.replay_clock"
    mod = sys.modules.get(module_name) or importlib.import_module(module_name)
    source_path = Path(mod.__file__ or "")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                imported.add(node.module.split(".")[0])
                if node.module.startswith("app."):
                    imported.add(node.module)
    assert "fastapi" not in imported
    assert "app.services.session_store" not in imported
    assert "app.services.run_store" not in imported
    assert "app.services.simulation_service" not in imported
    assert "app.services.mission_lifecycle_service" not in imported
    assert "app.schemas.telemetry" not in imported
    for name in ("SessionStore", "RunStore", "SimulationService", "MissionLifecycleService"):
        assert name not in mod.__dict__


# --- N. Formula consistency ---


@pytest.mark.parametrize(
    ("sample_count", "interval", "elapsed_ms", "index", "complete"),
    [
        (1, 250, 0, 0, True),
        (2, 250, 0, 0, False),
        (2, 250, 249, 0, False),
        (2, 250, 250, 1, True),
        (6, 250, 750, 3, False),
        (6, 250, 1250, 5, True),
        (6, 1000, 4999, 4, False),
        (6, 1000, 5000, 5, True),
    ],
)
def test_formula_reference_table(
    sample_count: int,
    interval: int,
    elapsed_ms: int,
    index: int,
    complete: bool,
) -> None:
    pos = position(
        at_ms(elapsed_ms),
        interval_ms=interval,
        sample_count=sample_count,
    )
    assert pos.sample_index == index
    assert pos.complete is complete
    if complete:
        assert pos.milliseconds_until_next_sample == 0
    else:
        remaining_us = interval * 1000 * (index + 1) - elapsed_ms * 1000
        expected_delay = (remaining_us + 999) // 1000
        assert pos.milliseconds_until_next_sample == expected_delay


# --- O. No lifecycle work ---


def test_replay_clock_exposes_no_lifecycle_methods() -> None:
    forbidden = (
        "get_current_telemetry",
        "get_current_sample",
        "start_replay",
        "trigger_accident",
        "create_session",
        "persist",
        "transition",
    )
    for name in forbidden:
        assert not hasattr(ReplayClock, name)
    assert list(ReplayClock.__dict__.keys())  # ensure class exists
    public = {k for k in dir(ReplayClock) if not k.startswith("_")}
    assert public == {"position_at"}
