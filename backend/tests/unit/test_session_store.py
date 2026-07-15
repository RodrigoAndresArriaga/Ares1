# SessionStore: atomic persistence, containment, locks, compare-and-replace
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from app.core.errors import (
    ArtifactStorageError,
    InvalidMissionSessionIdError,
    MissionSessionAlreadyExistsError,
    MissionSessionConflictError,
    MissionSessionCorruptError,
    MissionSessionNotFoundError,
    MissionSessionStorageError,
)
from app.schemas.api import ErrorCode
from app.schemas.mission import MissionSession, MissionSessionStatus
from app.services.session_store import SessionStore

SESSION_ID = "00000000-0000-4000-8000-000000000001"
OTHER_ID = "00000000-0000-4000-8000-000000000002"
SCENARIO_ID = "mars_hab_atmosphere_solar_failure"

T0 = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(seconds=1)
T2 = T0 + timedelta(seconds=2)


# build a valid READY MissionSession
def make_ready_session(
    *,
    session_id: str = SESSION_ID,
    updated_at: datetime | None = None,
) -> MissionSession:
    return MissionSession.model_validate(
        {
            "session_id": session_id,
            "scenario_id": SCENARIO_ID,
            "status": MissionSessionStatus.READY.value,
            "created_at": T0,
            "updated_at": updated_at or T0,
            "accident_triggered_at": None,
            "baseline_run_id": None,
            "baseline_outcome": None,
            "telemetry_sample_count": None,
            "replay_started_at": None,
            "replay_interval_ms": None,
            "error_code": None,
        }
    )


# build a valid TRIGGERING MissionSession
def make_triggering_session(
    *,
    session_id: str = SESSION_ID,
    updated_at: datetime | None = None,
) -> MissionSession:
    return MissionSession.model_validate(
        {
            "session_id": session_id,
            "scenario_id": SCENARIO_ID,
            "status": MissionSessionStatus.TRIGGERING.value,
            "created_at": T0,
            "updated_at": updated_at or T1,
            "accident_triggered_at": T1,
            "baseline_run_id": None,
            "baseline_outcome": None,
            "telemetry_sample_count": None,
            "replay_started_at": None,
            "replay_interval_ms": None,
            "error_code": None,
        }
    )


# create sessions root directory for a store under tmp_path
def make_sessions_root(tmp_path: Path) -> Path:
    root = tmp_path / "sessions"
    root.mkdir()
    return root


def _try_symlink(link: Path, target: Path) -> bool:
    try:
        link.symlink_to(target)
        return True
    except OSError:
        return False


def test_construction_valid_absolute_root(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    store = SessionStore(root)
    assert store._sessions_root == root.resolve()


def test_construction_relative_root_cwd_independent(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    relative = Path(os.path.relpath(root, Path.cwd()))
    store = SessionStore(relative)
    original = Path.cwd()
    try:
        os.chdir(tmp_path)
        created = store.create_session(make_ready_session())
        read = store.read_session(SESSION_ID)
    finally:
        os.chdir(original)
    assert created.session_id == SESSION_ID
    assert read.status == MissionSessionStatus.READY
    assert (root / SESSION_ID / "session.json").is_file()


def test_construction_rejects_missing_root(tmp_path: Path) -> None:
    with pytest.raises(MissionSessionStorageError):
        SessionStore(tmp_path / "missing")


def test_construction_rejects_file_root(tmp_path: Path) -> None:
    as_file = tmp_path / "sessions_file"
    as_file.write_text("x", encoding="utf-8")
    with pytest.raises(MissionSessionStorageError):
        SessionStore(as_file)


@pytest.mark.parametrize(
    "bad_id",
    [
        "not-a-uuid",
        "00000000-0000-4000-8000-00000000000G",
        "AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE",
        "00000000000040008000000000000001",
        "{00000000-0000-4000-8000-000000000001}",
        " 00000000-0000-4000-8000-000000000001",
        "00000000-0000-4000-8000-000000000001 ",
        "../00000000-0000-4000-8000-000000000001",
        "00000000-0000-4000-8000-000000000001/../x",
        r"00000000-0000-4000-8000-000000000001\x",
        "%2e%2e%2f00000000-0000-4000-8000-000000000001",
        "",
        "session-name",
    ],
)
def test_rejects_invalid_session_ids(tmp_path: Path, bad_id: str) -> None:
    store = SessionStore(make_sessions_root(tmp_path))
    with pytest.raises(InvalidMissionSessionIdError) as exc_info:
        store.read_session(bad_id)
    assert exc_info.value.code == ErrorCode.MISSION_SESSION_ID_INVALID
    assert str(tmp_path) not in exc_info.value.message


def test_accepts_canonical_uuid(tmp_path: Path) -> None:
    store = SessionStore(make_sessions_root(tmp_path))
    session = store.create_session(make_ready_session())
    assert session.session_id == SESSION_ID


def test_create_read_round_trip(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    store = SessionStore(root)
    original = make_ready_session()
    created = store.create_session(original)
    assert created.model_dump(mode="json") == original.model_dump(mode="json")

    session_dir = root / SESSION_ID
    session_json = session_dir / "session.json"
    assert session_dir.is_dir()
    assert session_json.is_file()

    raw = session_json.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    parsed = MissionSession.model_validate_json(raw)
    assert parsed.model_dump(mode="json") == original.model_dump(mode="json")

    read = store.read_session(SESSION_ID)
    assert read.model_dump(mode="json") == original.model_dump(mode="json")


def test_duplicate_create_rejected_no_overwrite(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    store = SessionStore(root)
    store.create_session(make_ready_session())
    before = (root / SESSION_ID / "session.json").read_text(encoding="utf-8")
    with pytest.raises(MissionSessionAlreadyExistsError) as exc_info:
        store.create_session(make_ready_session(updated_at=T1))
    assert exc_info.value.code == ErrorCode.MISSION_SESSION_ALREADY_EXISTS
    after = (root / SESSION_ID / "session.json").read_text(encoding="utf-8")
    assert after == before


def test_persisted_json_content_constraints(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    store = SessionStore(root)
    store.create_session(make_ready_session())
    payload = json.loads((root / SESSION_ID / "session.json").read_text(encoding="utf-8"))
    assert "telemetry_history" not in payload
    assert "metrics" not in payload
    assert "result" not in payload
    assert payload["status"] == "READY"
    assert isinstance(payload["status"], str)
    for key, value in payload.items():
        if isinstance(value, str):
            assert not value.startswith(str(tmp_path))
            assert "\\" not in value or key.endswith("_id") or key == "scenario_id"


def test_unknown_session_not_found(tmp_path: Path) -> None:
    store = SessionStore(make_sessions_root(tmp_path))
    with pytest.raises(MissionSessionNotFoundError) as exc_info:
        store.read_session(SESSION_ID)
    assert exc_info.value.code == ErrorCode.MISSION_SESSION_NOT_FOUND
    assert str(tmp_path) not in exc_info.value.message


def test_missing_session_json_not_found(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    store = SessionStore(root)
    (root / SESSION_ID).mkdir()
    with pytest.raises(MissionSessionNotFoundError):
        store.read_session(SESSION_ID)


def test_session_json_directory_is_corrupt(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    store = SessionStore(root)
    session_dir = root / SESSION_ID
    session_dir.mkdir()
    (session_dir / "session.json").mkdir()
    with pytest.raises(MissionSessionCorruptError) as exc_info:
        store.read_session(SESSION_ID)
    assert exc_info.value.code == ErrorCode.MISSION_SESSION_CORRUPT


def test_invalid_utf8_is_corrupt(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    store = SessionStore(root)
    session_dir = root / SESSION_ID
    session_dir.mkdir()
    (session_dir / "session.json").write_bytes(b"\xff\xfe not utf-8")
    with pytest.raises(MissionSessionCorruptError):
        store.read_session(SESSION_ID)


def test_malformed_json_is_corrupt(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    store = SessionStore(root)
    session_dir = root / SESSION_ID
    session_dir.mkdir()
    (session_dir / "session.json").write_text("{not-json", encoding="utf-8")
    with pytest.raises(MissionSessionCorruptError):
        store.read_session(SESSION_ID)


def test_schema_invalid_json_is_corrupt(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    store = SessionStore(root)
    session_dir = root / SESSION_ID
    session_dir.mkdir()
    (session_dir / "session.json").write_text(
        json.dumps({"session_id": SESSION_ID}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(MissionSessionCorruptError):
        store.read_session(SESSION_ID)


def test_session_id_mismatch_is_corrupt(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    store = SessionStore(root)
    session = make_ready_session()
    store.create_session(session)
    payload = json.loads((root / SESSION_ID / "session.json").read_text(encoding="utf-8"))
    payload["session_id"] = OTHER_ID
    (root / SESSION_ID / "session.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(MissionSessionCorruptError):
        store.read_session(SESSION_ID)


def test_unexpected_extra_field_is_corrupt(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    store = SessionStore(root)
    store.create_session(make_ready_session())
    payload = json.loads((root / SESSION_ID / "session.json").read_text(encoding="utf-8"))
    payload["survival_probability"] = 0.5
    (root / SESSION_ID / "session.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(MissionSessionCorruptError):
        store.read_session(SESSION_ID)


def test_invalid_lifecycle_combination_is_corrupt(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    store = SessionStore(root)
    store.create_session(make_ready_session())
    payload = json.loads((root / SESSION_ID / "session.json").read_text(encoding="utf-8"))
    payload["baseline_run_id"] = OTHER_ID
    (root / SESSION_ID / "session.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(MissionSessionCorruptError):
        store.read_session(SESSION_ID)


def test_replace_ready_to_triggering(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    store = SessionStore(root)
    store.create_session(make_ready_session())
    replaced = store.replace_session(
        make_triggering_session(),
        expected_status=MissionSessionStatus.READY,
    )
    assert replaced.status == MissionSessionStatus.TRIGGERING
    assert store.read_session(SESSION_ID).status == MissionSessionStatus.TRIGGERING


def test_replace_expected_status_collection(tmp_path: Path) -> None:
    store = SessionStore(make_sessions_root(tmp_path))
    store.create_session(make_ready_session())
    replaced = store.replace_session(
        make_triggering_session(),
        expected_status={
            MissionSessionStatus.READY,
            MissionSessionStatus.ERROR,
        },
    )
    assert replaced.status == MissionSessionStatus.TRIGGERING


def test_replace_wrong_expected_status_conflicts(tmp_path: Path) -> None:
    store = SessionStore(make_sessions_root(tmp_path))
    store.create_session(make_ready_session())
    with pytest.raises(MissionSessionConflictError) as exc_info:
        store.replace_session(
            make_triggering_session(),
            expected_status=MissionSessionStatus.BASELINE_READY,
        )
    assert exc_info.value.code == ErrorCode.MISSION_STATE_CONFLICT
    assert store.read_session(SESSION_ID).status == MissionSessionStatus.READY


def test_replace_expected_updated_at_succeeds(tmp_path: Path) -> None:
    store = SessionStore(make_sessions_root(tmp_path))
    created = store.create_session(make_ready_session())
    replaced = store.replace_session(
        make_triggering_session(),
        expected_updated_at=created.updated_at,
    )
    assert replaced.status == MissionSessionStatus.TRIGGERING


def test_replace_stale_updated_at_conflicts(tmp_path: Path) -> None:
    store = SessionStore(make_sessions_root(tmp_path))
    store.create_session(make_ready_session())
    with pytest.raises(MissionSessionConflictError):
        store.replace_session(
            make_triggering_session(),
            expected_updated_at=T2,
        )
    assert store.read_session(SESSION_ID).status == MissionSessionStatus.READY


def test_replace_unknown_session_fails(tmp_path: Path) -> None:
    store = SessionStore(make_sessions_root(tmp_path))
    with pytest.raises(MissionSessionNotFoundError):
        store.replace_session(make_triggering_session())


def test_replace_targets_own_session_id_only(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    store = SessionStore(root)
    store.create_session(make_ready_session())
    with pytest.raises(MissionSessionNotFoundError):
        store.replace_session(make_triggering_session(session_id=OTHER_ID))
    assert store.read_session(SESSION_ID).status == MissionSessionStatus.READY
    assert store.session_exists(OTHER_ID) is False


def test_replace_write_failure_leaves_original(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    store = SessionStore(root)
    store.create_session(make_ready_session())
    before = (root / SESSION_ID / "session.json").read_text(encoding="utf-8")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise ArtifactStorageError("simulated write failure")

    with patch("app.services.session_store.write_json_atomic", side_effect=boom):
        with pytest.raises(MissionSessionStorageError):
            store.replace_session(make_triggering_session())

    after = (root / SESSION_ID / "session.json").read_text(encoding="utf-8")
    assert after == before
    assert list((root / SESSION_ID).glob(".*.tmp")) == []


def test_create_write_failure_cleans_empty_directory(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    store = SessionStore(root)

    def boom(*_args: object, **_kwargs: object) -> None:
        raise ArtifactStorageError("simulated write failure")

    with patch("app.services.session_store.write_json_atomic", side_effect=boom):
        with pytest.raises(MissionSessionStorageError):
            store.create_session(make_ready_session())

    assert not (root / SESSION_ID).exists()
    assert list(root.glob("**/.*.tmp")) == []


def test_os_replace_failure_leaves_original(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    store = SessionStore(root)
    store.create_session(make_ready_session())
    before = (root / SESSION_ID / "session.json").read_text(encoding="utf-8")

    real_replace = os.replace

    def fail_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        if Path(dst).name == "session.json":
            raise OSError("simulated replace failure")
        real_replace(src, dst)

    with patch("app.services.run_store.os.replace", side_effect=fail_replace):
        with pytest.raises(MissionSessionStorageError):
            store.replace_session(make_triggering_session())

    after = (root / SESSION_ID / "session.json").read_text(encoding="utf-8")
    assert after == before
    assert list((root / SESSION_ID).glob(".*.tmp")) == []


def test_symlink_session_dir_escape_rejected(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / SESSION_ID
    if not _try_symlink(link, outside):
        pytest.skip("symlinks not supported")
    store = SessionStore(root)
    with pytest.raises((MissionSessionCorruptError, MissionSessionNotFoundError)):
        store.read_session(SESSION_ID)
    assert store.session_exists(SESSION_ID) is False


def test_symlink_session_json_escape_rejected(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    store = SessionStore(root)
    session_dir = root / SESSION_ID
    session_dir.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    link = session_dir / "session.json"
    if not _try_symlink(link, outside):
        pytest.skip("symlinks not supported")
    with pytest.raises(MissionSessionCorruptError) as exc_info:
        store.read_session(SESSION_ID)
    assert str(outside) not in exc_info.value.message
    assert store.session_exists(SESSION_ID) is False


def test_normal_contained_path_accepted(tmp_path: Path) -> None:
    store = SessionStore(make_sessions_root(tmp_path))
    store.create_session(make_ready_session())
    assert store.session_exists(SESSION_ID) is True
    assert store.read_session(SESSION_ID).status == MissionSessionStatus.READY


@pytest.mark.asyncio
async def test_lock_same_session_id_identity(tmp_path: Path) -> None:
    store = SessionStore(make_sessions_root(tmp_path))
    async with store.lock_session(SESSION_ID):
        lock_a = store._locks[SESSION_ID]
    async with store.lock_session(SESSION_ID):
        lock_b = store._locks[SESSION_ID]
    assert lock_a is lock_b


@pytest.mark.asyncio
async def test_lock_different_session_ids_independent(tmp_path: Path) -> None:
    store = SessionStore(make_sessions_root(tmp_path))
    async with store.lock_session(SESSION_ID):
        pass
    async with store.lock_session(OTHER_ID):
        pass
    assert store._locks[SESSION_ID] is not store._locks[OTHER_ID]


@pytest.mark.asyncio
async def test_same_session_lock_serializes(tmp_path: Path) -> None:
    store = SessionStore(make_sessions_root(tmp_path))
    order: list[str] = []

    async def worker(name: str) -> None:
        async with store.lock_session(SESSION_ID):
            order.append(f"{name}-enter")
            await asyncio.sleep(0.05)
            order.append(f"{name}-exit")

    await asyncio.gather(worker("a"), worker("b"))
    assert order in (
        ["a-enter", "a-exit", "b-enter", "b-exit"],
        ["b-enter", "b-exit", "a-enter", "a-exit"],
    )


@pytest.mark.asyncio
async def test_different_session_locks_concurrent(tmp_path: Path) -> None:
    store = SessionStore(make_sessions_root(tmp_path))
    concurrent = 0
    max_concurrent = 0
    gate = asyncio.Event()

    async def worker(session_id: str) -> None:
        nonlocal concurrent, max_concurrent
        async with store.lock_session(session_id):
            concurrent += 1
            max_concurrent = max(max_concurrent, concurrent)
            if concurrent == 2:
                gate.set()
            await asyncio.wait_for(gate.wait(), timeout=1.0)
            concurrent -= 1

    await asyncio.gather(worker(SESSION_ID), worker(OTHER_ID))
    assert max_concurrent == 2


@pytest.mark.asyncio
async def test_lock_does_not_create_session_files(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    store = SessionStore(root)
    async with store.lock_session(SESSION_ID):
        pass
    assert list(root.iterdir()) == []


@pytest.mark.asyncio
async def test_lock_rejects_invalid_id(tmp_path: Path) -> None:
    store = SessionStore(make_sessions_root(tmp_path))
    with pytest.raises(InvalidMissionSessionIdError):
        async with store.lock_session("not-a-uuid"):
            pass


@pytest.mark.asyncio
async def test_concurrent_compare_and_replace_with_lock(tmp_path: Path) -> None:
    store = SessionStore(make_sessions_root(tmp_path))
    store.create_session(make_ready_session())
    results: list[str] = []

    async def first() -> None:
        async with store.lock_session(SESSION_ID):
            current = store.read_session(SESSION_ID)
            await asyncio.sleep(0.05)
            store.replace_session(
                make_triggering_session(updated_at=T2),
                expected_status=MissionSessionStatus.READY,
                expected_updated_at=current.updated_at,
            )
            results.append("first-ok")

    async def second() -> None:
        await asyncio.sleep(0.01)
        async with store.lock_session(SESSION_ID):
            current = store.read_session(SESSION_ID)
            if current.status != MissionSessionStatus.READY:
                results.append("second-saw-update")
                return
            try:
                store.replace_session(
                    make_triggering_session(updated_at=T2),
                    expected_status=MissionSessionStatus.READY,
                    expected_updated_at=T0,
                )
                results.append("second-ok")
            except MissionSessionConflictError:
                results.append("second-conflict")

    await asyncio.gather(first(), second())
    assert "first-ok" in results
    assert "second-saw-update" in results or "second-conflict" in results
    final = store.read_session(SESSION_ID)
    assert final.status == MissionSessionStatus.TRIGGERING
    MissionSession.model_validate_json(
        (tmp_path / "sessions" / SESSION_ID / "session.json").read_text(encoding="utf-8")
    )


def test_restart_safe_across_store_instances(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    first = SessionStore(root)
    first.create_session(make_ready_session())
    second = SessionStore(root)
    read = second.read_session(SESSION_ID)
    assert read.status == MissionSessionStatus.READY


def test_session_exists_false_for_unknown(tmp_path: Path) -> None:
    store = SessionStore(make_sessions_root(tmp_path))
    assert store.session_exists(SESSION_ID) is False


def test_cwd_independence_after_construction(tmp_path: Path) -> None:
    root = make_sessions_root(tmp_path)
    store = SessionStore(root)
    other = tmp_path / "other"
    other.mkdir()
    original = Path.cwd()
    try:
        os.chdir(other)
        store.create_session(make_ready_session())
        store.replace_session(
            make_triggering_session(),
            expected_status=MissionSessionStatus.READY,
        )
        session = store.read_session(SESSION_ID)
    finally:
        os.chdir(original)
    assert session.status == MissionSessionStatus.TRIGGERING
    assert (root / SESSION_ID / "session.json").is_file()
