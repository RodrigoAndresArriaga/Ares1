# startup reconciliation: list_session_ids and stale TRIGGERING recovery
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from app.core.errors import (
    MissionSessionConflictError,
    MissionSessionStorageError,
)
from app.schemas.api import ErrorCode
from app.schemas.mission import MissionSession, MissionSessionStatus
from app.services.mission_lifecycle_service import ReconciliationSummary
from app.services.session_store import SessionStore
from tests.conftest import RELEASE_SCENARIO_ID
from tests.unit.test_mission_lifecycle_service import (
    OTHER_ID,
    SESSION_ID,
    T0,
    T1,
    T2,
    SequenceClock,
    make_baseline_ready_session,
    make_completed_session,
    make_error_session,
    make_ready_session,
    make_replaying_session,
    make_service,
    make_sessions_root,
    make_triggering_session,
)

OTHER_TRIGGERING_ID = "00000000-0000-4000-8000-000000000099"


def _try_symlink(link: Path, target: Path) -> bool:
    try:
        link.symlink_to(target)
        return True
    except OSError:
        return False


def _write_raw_session(root: Path, session_id: str, payload: dict[str, Any]) -> Path:
    session_dir = root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    path = session_dir / "session.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# --- list_session_ids ---


def test_list_session_ids_accepts_canonical_sorted(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    store = SessionStore(root)
    store.create_session(make_ready_session(session_id=OTHER_ID))
    store.create_session(make_ready_session(session_id=SESSION_ID))
    assert store.list_session_ids() == (SESSION_ID, OTHER_ID)


def test_list_session_ids_ignores_non_canonical_and_files(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    store = SessionStore(root)
    store.create_session(make_ready_session())

    (root / "not-a-uuid").mkdir()
    # uppercase UUID name is non-canonical (str(UUID) is lowercase)
    (root / "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA").mkdir()
    (root / "00000000000040008000000000000001").mkdir()
    (root / "readme.txt").write_text("x", encoding="utf-8")
    nested = root / SESSION_ID / "nested"
    nested.mkdir(exist_ok=True)

    assert store.list_session_ids() == (SESSION_ID,)


def test_list_session_ids_ignores_symlinked_directories(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    store = SessionStore(root)
    store.create_session(make_ready_session())

    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / OTHER_ID
    if not _try_symlink(link, outside):
        pytest.skip("symlinks not supported")

    assert store.list_session_ids() == (SESSION_ID,)
    assert isinstance(store.list_session_ids()[0], str)
    assert "/" not in store.list_session_ids()[0]
    assert "\\" not in store.list_session_ids()[0]


def test_list_session_ids_includes_dirs_without_parsing(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    store = SessionStore(root)
    (root / SESSION_ID).mkdir()
    assert store.list_session_ids() == (SESSION_ID,)


def test_list_session_ids_cwd_independent(tmp_path: Path) -> None:
    import os

    root = make_sessions_root(tmp_path)
    store = SessionStore(root)
    store.create_session(make_ready_session())
    original = Path.cwd()
    try:
        os.chdir(tmp_path / "sessions")
        assert store.list_session_ids() == (SESSION_ID,)
        os.chdir(tmp_path)
        assert store.list_session_ids() == (SESSION_ID,)
    finally:
        os.chdir(original)


def test_list_session_ids_raises_on_iterdir_failure(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    store = SessionStore(root)
    with patch.object(Path, "iterdir", side_effect=OSError("denied")):
        with pytest.raises(MissionSessionStorageError) as exc_info:
            store.list_session_ids()
    assert exc_info.value.code == ErrorCode.MISSION_SESSION_STORAGE_ERROR


# --- reconcile_interrupted_sessions ---


@pytest.mark.asyncio
async def test_reconcile_triggering_to_error(tmp_path: Path) -> None:
    fake_sim = AsyncMock()
    clock = SequenceClock([T2])
    service, store, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        clock=clock,
    )
    triggering = make_triggering_session()
    store.create_session(triggering)

    summary = await service.reconcile_interrupted_sessions()

    assert summary == ReconciliationSummary(
        sessions_seen=1,
        triggering_recovered=1,
        unchanged=0,
        corrupt=0,
        conflicts=0,
    )
    persisted = store.read_session(SESSION_ID)
    assert persisted.status == MissionSessionStatus.ERROR
    assert persisted.error_code == ErrorCode.MISSION_TRIGGER_INTERRUPTED.value
    assert persisted.session_id == SESSION_ID
    assert persisted.scenario_id == RELEASE_SCENARIO_ID
    assert persisted.created_at == T0
    assert persisted.accident_triggered_at == T1
    assert persisted.baseline_run_id is None
    assert persisted.baseline_outcome is None
    assert persisted.telemetry_sample_count is None
    assert persisted.replay_started_at is None
    assert persisted.replay_interval_ms is None
    assert persisted.updated_at == T2
    fake_sim.run_simulation.assert_not_called()


@pytest.mark.asyncio
async def test_reconcile_leaves_non_triggering_unchanged(tmp_path: Path) -> None:
    fake_sim = AsyncMock()
    service, store, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        clock=SequenceClock([T2]),
    )
    sessions = (
        make_ready_session(session_id=SESSION_ID),
        make_baseline_ready_session(session_id=OTHER_ID),
        make_replaying_session(
            session_id="00000000-0000-4000-8000-000000000010",
        ),
        make_completed_session(
            session_id="00000000-0000-4000-8000-000000000011",
        ),
        make_error_session(
            session_id="00000000-0000-4000-8000-000000000012",
        ),
    )
    for session in sessions:
        store.create_session(session)

    before = {
        sid: (store._sessions_root / sid / "session.json").read_bytes()
        for sid in store.list_session_ids()
    }

    summary = await service.reconcile_interrupted_sessions()

    assert summary.triggering_recovered == 0
    assert summary.unchanged == 5
    assert summary.corrupt == 0
    for sid, raw in before.items():
        assert (store._sessions_root / sid / "session.json").read_bytes() == raw
    fake_sim.run_simulation.assert_not_called()


@pytest.mark.asyncio
async def test_reconcile_skips_corrupt_and_continues(tmp_path: Path) -> None:
    fake_sim = AsyncMock()
    service, store, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        clock=SequenceClock([T2]),
    )
    store.create_session(make_triggering_session(session_id=SESSION_ID))
    corrupt_path = _write_raw_session(
        store._sessions_root,
        OTHER_ID,
        {"session_id": OTHER_ID, "status": "READY"},
    )
    before_corrupt = corrupt_path.read_bytes()

    summary = await service.reconcile_interrupted_sessions()

    assert summary.sessions_seen == 2
    assert summary.triggering_recovered == 1
    assert summary.corrupt == 1
    assert corrupt_path.read_bytes() == before_corrupt
    recovered = store.read_session(SESSION_ID)
    assert recovered.status == MissionSessionStatus.ERROR
    assert recovered.error_code == ErrorCode.MISSION_TRIGGER_INTERRUPTED.value
    fake_sim.run_simulation.assert_not_called()


@pytest.mark.asyncio
async def test_reconcile_compare_conflict_skips_safely(tmp_path: Path) -> None:
    fake_sim = AsyncMock()
    service, store, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        clock=SequenceClock([T2]),
    )
    store.create_session(make_triggering_session())
    original_replace = store.replace_session

    def conflict_once(
        session: MissionSession,
        **kwargs: Any,
    ) -> MissionSession:
        store.replace_session = original_replace  # type: ignore[method-assign]
        # simulate concurrent transition to BASELINE_READY before CAS
        path = store._sessions_root / SESSION_ID / "session.json"
        path.write_text(
            make_baseline_ready_session().model_dump_json(),
            encoding="utf-8",
        )
        raise MissionSessionConflictError(
            "Mission session state conflict",
            session_id=SESSION_ID,
        )

    store.replace_session = conflict_once  # type: ignore[method-assign]

    summary = await service.reconcile_interrupted_sessions()

    assert summary.conflicts == 1
    assert summary.triggering_recovered == 0
    current = store.read_session(SESSION_ID)
    assert current.status == MissionSessionStatus.BASELINE_READY
    fake_sim.run_simulation.assert_not_called()


@pytest.mark.asyncio
async def test_reconcile_empty_root(tmp_path: Path) -> None:
    fake_sim = AsyncMock()
    service, _, _ = make_service(tmp_path, simulation_service=fake_sim)
    summary = await service.reconcile_interrupted_sessions()
    assert summary == ReconciliationSummary(
        sessions_seen=0,
        triggering_recovered=0,
        unchanged=0,
        corrupt=0,
        conflicts=0,
    )
    fake_sim.run_simulation.assert_not_called()


@pytest.mark.asyncio
async def test_reconcile_multiple_triggering_sessions(tmp_path: Path) -> None:
    fake_sim = AsyncMock()
    clock = SequenceClock([T2, T2 + timedelta(seconds=1)])
    service, store, _ = make_service(
        tmp_path,
        simulation_service=fake_sim,
        clock=clock,
    )
    store.create_session(make_triggering_session(session_id=SESSION_ID))
    store.create_session(make_triggering_session(session_id=OTHER_TRIGGERING_ID))
    store.create_session(make_ready_session(session_id=OTHER_ID))

    summary = await service.reconcile_interrupted_sessions()

    assert summary.sessions_seen == 3
    assert summary.triggering_recovered == 2
    assert summary.unchanged == 1
    assert (
        store.read_session(SESSION_ID).error_code
        == ErrorCode.MISSION_TRIGGER_INTERRUPTED.value
    )
    assert (
        store.read_session(OTHER_TRIGGERING_ID).error_code
        == ErrorCode.MISSION_TRIGGER_INTERRUPTED.value
    )
    assert store.read_session(OTHER_ID).status == MissionSessionStatus.READY
    fake_sim.run_simulation.assert_not_called()
