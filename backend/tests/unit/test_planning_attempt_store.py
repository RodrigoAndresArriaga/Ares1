# PlanningAttemptStore: atomic persistence, containment, and strict parse
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from app.core.errors import (
    InvalidPlanningAttemptIdError,
    PlanningAttemptAlreadyExistsError,
    PlanningAttemptCorruptError,
    PlanningAttemptNotFoundError,
    PlanningAttemptStorageError,
)
from app.services.planning_attempt_store import PlanningAttemptStore
from tests.conftest import (
    PLANNING_ATTEMPT_ID,
    make_planning_attempt_store,
    make_planning_root,
)
from tests.unit.test_planning_schema import _attempt

OTHER_ID = "00000000-0000-4000-8000-000000000002"


def _try_symlink(link: Path, target: Path) -> bool:
    try:
        link.symlink_to(target)
        return True
    except OSError:
        return False


def test_construction_valid_absolute_root(tmp_path: Path) -> None:
    root = make_planning_root(tmp_path)
    store = PlanningAttemptStore(root)
    assert store._planning_root == root.resolve()


def test_construction_rejects_missing_root(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(PlanningAttemptStorageError):
        PlanningAttemptStore(missing)


def test_create_read_round_trip(
    tmp_path: Path,
    baseline_result_data: object,
) -> None:
    store = make_planning_attempt_store(tmp_path)
    attempt = _attempt(baseline_result_data)
    created = store.create_attempt(attempt)
    read = store.read_attempt(PLANNING_ATTEMPT_ID)
    assert created == read == attempt


def test_create_rejects_duplicate(
    tmp_path: Path,
    baseline_result_data: object,
) -> None:
    store = make_planning_attempt_store(tmp_path)
    attempt = _attempt(baseline_result_data)
    store.create_attempt(attempt)
    with pytest.raises(PlanningAttemptAlreadyExistsError):
        store.create_attempt(attempt)


def test_read_missing_attempt(tmp_path: Path) -> None:
    store = make_planning_attempt_store(tmp_path)
    with pytest.raises(PlanningAttemptNotFoundError):
        store.read_attempt(PLANNING_ATTEMPT_ID)


def test_invalid_attempt_id_rejected(tmp_path: Path) -> None:
    store = make_planning_attempt_store(tmp_path)
    with pytest.raises(InvalidPlanningAttemptIdError):
        store.read_attempt("not-a-uuid")


def test_corrupt_json_rejected(
    tmp_path: Path,
    baseline_result_data: object,
) -> None:
    store = make_planning_attempt_store(tmp_path)
    attempt = _attempt(baseline_result_data)
    store.create_attempt(attempt)
    path = make_planning_root(tmp_path) / PLANNING_ATTEMPT_ID / "attempt.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(PlanningAttemptCorruptError):
        store.read_attempt(PLANNING_ATTEMPT_ID)


def test_schema_invalid_json_rejected(
    tmp_path: Path,
    baseline_result_data: object,
) -> None:
    store = make_planning_attempt_store(tmp_path)
    attempt = _attempt(baseline_result_data)
    store.create_attempt(attempt)
    path = make_planning_root(tmp_path) / PLANNING_ATTEMPT_ID / "attempt.json"
    path.write_text(json.dumps({"attempt_id": PLANNING_ATTEMPT_ID}), encoding="utf-8")
    with pytest.raises(PlanningAttemptCorruptError):
        store.read_attempt(PLANNING_ATTEMPT_ID)


def test_stored_attempt_id_mismatch_rejected(
    tmp_path: Path,
    baseline_result_data: object,
) -> None:
    store = make_planning_attempt_store(tmp_path)
    attempt = _attempt(baseline_result_data)
    store.create_attempt(attempt)
    path = make_planning_root(tmp_path) / PLANNING_ATTEMPT_ID / "attempt.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["attempt_id"] = OTHER_ID
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    with pytest.raises(PlanningAttemptCorruptError):
        store.read_attempt(PLANNING_ATTEMPT_ID)


def test_atomic_write_failure_preserves_existing_state(
    tmp_path: Path,
    baseline_result_data: object,
) -> None:
    store = make_planning_attempt_store(tmp_path)
    attempt = _attempt(baseline_result_data)
    store.create_attempt(attempt)
    before = (
        make_planning_root(tmp_path) / PLANNING_ATTEMPT_ID / "attempt.json"
    ).read_bytes()
    other_id = "00000000-0000-4000-8000-000000000099"
    duplicate = attempt.model_copy(
        update={
            "attempt_id": other_id,
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        },
    )
    with patch("app.services.planning_attempt_store.write_json_atomic") as mocked:
        from app.core.errors import ArtifactStorageError

        mocked.side_effect = ArtifactStorageError("boom")
        with pytest.raises(PlanningAttemptStorageError):
            store.create_attempt(duplicate)
    after = (
        make_planning_root(tmp_path) / PLANNING_ATTEMPT_ID / "attempt.json"
    ).read_bytes()
    assert before == after


def test_failed_create_cleans_empty_directory(
    tmp_path: Path,
    baseline_result_data: object,
) -> None:
    store = make_planning_attempt_store(tmp_path)
    attempt = _attempt(baseline_result_data)
    with patch("app.services.planning_attempt_store.write_json_atomic") as mocked:
        mocked.side_effect = OSError("disk full")
        with pytest.raises(PlanningAttemptStorageError):
            store.create_attempt(attempt)
    assert not (make_planning_root(tmp_path) / PLANNING_ATTEMPT_ID).exists()


def test_no_temporary_files_left_after_create(
    tmp_path: Path,
    baseline_result_data: object,
) -> None:
    store = make_planning_attempt_store(tmp_path)
    store.create_attempt(_attempt(baseline_result_data))
    attempt_dir = make_planning_root(tmp_path) / PLANNING_ATTEMPT_ID
    names = {p.name for p in attempt_dir.iterdir()}
    assert names == {"attempt.json"}


def test_attempt_exists(
    tmp_path: Path,
    baseline_result_data: object,
) -> None:
    store = make_planning_attempt_store(tmp_path)
    assert store.attempt_exists(PLANNING_ATTEMPT_ID) is False
    store.create_attempt(_attempt(baseline_result_data))
    assert store.attempt_exists(PLANNING_ATTEMPT_ID) is True


@pytest.mark.skipif(os.name != "posix", reason="symlink escape checks require POSIX")
def test_symlink_escape_rejected(
    tmp_path: Path,
    baseline_result_data: object,
) -> None:
    store = make_planning_attempt_store(tmp_path)
    attempt = _attempt(baseline_result_data)
    store.create_attempt(attempt)
    attempt_dir = make_planning_root(tmp_path) / PLANNING_ATTEMPT_ID
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    link = attempt_dir / "attempt.json"
    if link.exists():
        link.unlink()
    if not _try_symlink(link, outside):
        pytest.skip("symlink not supported")
    with pytest.raises(PlanningAttemptCorruptError):
        store.read_attempt(PLANNING_ATTEMPT_ID)
