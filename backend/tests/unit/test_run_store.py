# RunStore: UUID workspaces, exact copies, atomic writes, hashes
from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from app.core.errors import ArtifactStorageError
from app.schemas.api import ErrorCode, SimulationRunRequest
from app.schemas.plan import RecoveryPlan
from app.services.run_store import (
    RunStore,
    RunWorkspace,
    sha256_file,
    write_bytes_atomic,
    write_json_atomic,
)
from tests.conftest import (
    RELEASE_SCENARIO_ID,
    RELEASE_SCENARIO_PATH,
    SHARED_SIM_RESULT_PATH,
    make_baseline_request,
    make_plan_request,
)


def _assert_paths_contained(workspace: RunWorkspace) -> None:
    root = workspace.root.resolve()
    for path in (
        workspace.request_path,
        workspace.scenario_path,
        workspace.plan_path,
        workspace.result_path,
        workspace.stdout_path,
        workspace.stderr_path,
        workspace.metadata_path,
    ):
        assert path.resolve().is_relative_to(root)
        assert path.parent == workspace.root


def test_workspace_uuid_format_and_lowercase(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    parsed = uuid.UUID(workspace.run_id)
    assert parsed.version == 4
    assert workspace.run_id == workspace.run_id.lower()
    assert workspace.run_id == str(parsed)


def test_exclusive_directory_creation(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    store = RunStore(runs)
    first = store.create_workspace(make_baseline_request(), RELEASE_SCENARIO_PATH)
    second = store.create_workspace(make_baseline_request(), RELEASE_SCENARIO_PATH)
    assert first.run_id != second.run_id
    assert first.root != second.root
    assert first.root.is_dir()
    assert second.root.is_dir()


def test_uuid_collision_retries_then_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = RunStore(tmp_path / "runs")
    collision = uuid.UUID("11111111-1111-4111-8111-111111111111")
    success = uuid.UUID("22222222-2222-4222-8222-222222222222")
    mkdir_ids = [collision, collision, success]
    call_count = 0
    real_uuid4 = uuid.uuid4

    def fake_uuid4() -> uuid.UUID:
        nonlocal call_count
        call_count += 1
        if call_count <= len(mkdir_ids):
            return mkdir_ids[call_count - 1]
        return real_uuid4()

    monkeypatch.setattr("app.services.run_store.uuid.uuid4", fake_uuid4)
    (tmp_path / "runs" / str(collision)).mkdir(parents=True)
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    assert workspace.run_id == str(success)


def test_uuid_collision_exhaustion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = RunStore(tmp_path / "runs")
    fixed = uuid.UUID("33333333-3333-4333-8333-333333333333")
    monkeypatch.setattr(
        "app.services.run_store.uuid.uuid4",
        lambda: fixed,
    )
    (tmp_path / "runs" / str(fixed)).mkdir(parents=True)
    with pytest.raises(ArtifactStorageError) as exc_info:
        store.create_workspace(make_baseline_request(), RELEASE_SCENARIO_PATH)
    assert exc_info.value.code == ErrorCode.ARTIFACT_STORAGE_ERROR


def test_path_contract_and_shared_result_protection(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    _assert_paths_contained(workspace)
    assert workspace.request_path.name == "request.json"
    assert workspace.scenario_path.name == "scenario.json"
    assert workspace.plan_path.name == "plan.json"
    assert workspace.result_path.name == "result.json"
    assert workspace.stdout_path.name == "stdout.log"
    assert workspace.stderr_path.name == "stderr.log"
    assert workspace.metadata_path.name == "metadata.json"
    assert workspace.result_path.resolve() != SHARED_SIM_RESULT_PATH.resolve()
    assert not workspace.result_path.exists()
    assert not workspace.stdout_path.exists()
    assert not workspace.stderr_path.exists()
    assert not workspace.plan_path.exists()


def test_workspace_immutable(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    with pytest.raises(Exception):
        workspace.run_id = "mutated"  # type: ignore[misc]


def test_exact_scenario_copy(tmp_path: Path) -> None:
    source_before = RELEASE_SCENARIO_PATH.read_bytes()
    store = RunStore(tmp_path / "runs")
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    assert workspace.scenario_path.read_bytes() == source_before
    assert RELEASE_SCENARIO_PATH.read_bytes() == source_before


def test_request_json_baseline_omits_plan(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    request = make_baseline_request()
    workspace = store.create_workspace(request, RELEASE_SCENARIO_PATH)
    loaded = json.loads(workspace.request_path.read_text(encoding="utf-8"))
    assert loaded == {"scenario_id": RELEASE_SCENARIO_ID}
    assert "plan" not in loaded
    SimulationRunRequest.model_validate(loaded)


def test_request_json_deterministic(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    request = make_baseline_request()
    a = store.create_workspace(request, RELEASE_SCENARIO_PATH)
    b = store.create_workspace(request, RELEASE_SCENARIO_PATH)
    assert a.request_path.read_bytes() == b.request_path.read_bytes()


def test_sample_plan_artifact(
    tmp_path: Path, sample_plan_data: Any
) -> None:
    store = RunStore(tmp_path / "runs")
    request = make_plan_request(sample_plan_data)
    workspace = store.create_workspace(request, RELEASE_SCENARIO_PATH)
    assert workspace.plan_path.is_file()
    loaded = json.loads(workspace.plan_path.read_text(encoding="utf-8"))
    expected = RecoveryPlan.model_validate(sample_plan_data).model_dump(
        mode="json",
        exclude_unset=True,
    )
    assert loaded == expected
    assert RELEASE_SCENARIO_PATH.exists()


def test_invalid_plan_artifact(
    tmp_path: Path, invalid_plan_data: Any
) -> None:
    source_plan = (
        Path(__file__).resolve().parents[3] / "plans" / "invalid_plan.json"
    )
    before = source_plan.read_bytes()
    store = RunStore(tmp_path / "runs")
    request = make_plan_request(invalid_plan_data)
    workspace = store.create_workspace(request, RELEASE_SCENARIO_PATH)
    loaded = json.loads(workspace.plan_path.read_text(encoding="utf-8"))
    expected = RecoveryPlan.model_validate(invalid_plan_data).model_dump(
        mode="json",
        exclude_unset=True,
    )
    assert loaded == expected
    assert source_plan.read_bytes() == before


def test_baseline_creates_no_plan_json(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    assert not workspace.plan_path.exists()


def test_atomic_write_success_and_no_temps(tmp_path: Path) -> None:
    dest = tmp_path / "artifact.json"
    write_json_atomic(dest, {"a": 1})
    assert dest.is_file()
    leftovers = list(tmp_path.glob(".*.tmp"))
    assert leftovers == []
    assert json.loads(dest.read_text(encoding="utf-8")) == {"a": 1}


def test_atomic_write_preserves_previous_on_failure(tmp_path: Path) -> None:
    dest = tmp_path / "artifact.json"
    write_json_atomic(dest, {"keep": True})
    previous = dest.read_bytes()

    with patch("app.services.run_store.os.replace", side_effect=OSError("boom")):
        with pytest.raises(ArtifactStorageError):
            write_json_atomic(dest, {"new": True})

    assert dest.read_bytes() == previous
    assert list(tmp_path.glob(".*.tmp")) == []


def test_atomic_write_failed_open_leaves_no_partial(tmp_path: Path) -> None:
    dest = tmp_path / "artifact.json"

    real_open = Path.open

    def boom(
        self: Path,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        if self.name.startswith(".artifact.json.") and self.suffix == ".tmp":
            raise OSError("cannot create temp")
        return real_open(self, *args, **kwargs)

    with patch.object(Path, "open", boom):
        with pytest.raises(ArtifactStorageError):
            write_bytes_atomic(dest, b"partial")

    assert not dest.exists()
    assert list(tmp_path.glob(".*.tmp")) == []


def test_sha256_known_bytes(tmp_path: Path) -> None:
    path = tmp_path / "known.bin"
    path.write_bytes(b"abc")
    assert sha256_file(path) == (
        "BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD"
    )


def test_scenario_and_plan_hashes(
    tmp_path: Path, sample_plan_data: Any
) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = store.create_workspace(
        make_plan_request(sample_plan_data),
        RELEASE_SCENARIO_PATH,
    )
    assert sha256_file(workspace.scenario_path) == sha256_file(
        RELEASE_SCENARIO_PATH
    )
    metadata = json.loads(workspace.metadata_path.read_text(encoding="utf-8"))
    assert metadata["scenario_sha256"] == sha256_file(workspace.scenario_path)
    assert metadata["plan_sha256"] == sha256_file(workspace.plan_path)
    assert metadata["result_sha256"] is None
    assert all(ch in "0123456789ABCDEF" for ch in metadata["scenario_sha256"])


def test_hash_changes_with_bytes(tmp_path: Path) -> None:
    path = tmp_path / "f.bin"
    path.write_bytes(b"one")
    first = sha256_file(path)
    path.write_bytes(b"two")
    assert sha256_file(path) != first


def test_absent_plan_has_null_hash(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    metadata = json.loads(workspace.metadata_path.read_text(encoding="utf-8"))
    assert metadata["plan_sha256"] is None
    assert metadata["mode"] == "baseline"
    assert metadata["status"] == "created"
    assert metadata["plan_id"] is None


def test_sha256_rejects_directory(tmp_path: Path) -> None:
    with pytest.raises(ArtifactStorageError):
        sha256_file(tmp_path)


def test_partial_evidence_preserved(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    request = make_baseline_request()

    def fail_after_request(src: str | Path, dst: str | Path) -> Any:
        raise OSError("copy failed")

    with patch("app.services.run_store.shutil.copyfile", side_effect=fail_after_request):
        with pytest.raises(ArtifactStorageError) as exc_info:
            store.create_workspace(request, RELEASE_SCENARIO_PATH)

    err = exc_info.value
    assert err.run_id is not None
    assert err.code == ErrorCode.ARTIFACT_STORAGE_ERROR
    assert str(tmp_path) not in err.message

    run_dir = tmp_path / "runs" / err.run_id
    assert run_dir.is_dir()
    assert (run_dir / "request.json").is_file()
    assert not (run_dir / "scenario.json").exists()
    assert list(run_dir.glob(".*.tmp")) == []


def test_concurrent_isolation(
    tmp_path: Path, sample_plan_data: Any, invalid_plan_data: Any
) -> None:
    runs = tmp_path / "runs"
    store = RunStore(runs)
    shared_before = (
        SHARED_SIM_RESULT_PATH.stat()
        if SHARED_SIM_RESULT_PATH.exists()
        else None
    )

    requests = [
        make_baseline_request(),
        make_plan_request(sample_plan_data),
        make_plan_request(invalid_plan_data),
        make_baseline_request(),
        make_plan_request(sample_plan_data),
        make_baseline_request(),
        make_plan_request(invalid_plan_data),
        make_plan_request(sample_plan_data),
    ]

    def create_one(req: SimulationRunRequest) -> RunWorkspace:
        return store.create_workspace(req, RELEASE_SCENARIO_PATH)

    with ThreadPoolExecutor(max_workers=8) as pool:
        workspaces = list(pool.map(create_one, requests))

    run_ids = [w.run_id for w in workspaces]
    assert len(run_ids) == len(set(run_ids))
    roots = [w.root.resolve() for w in workspaces]
    assert len(roots) == len(set(roots))

    for workspace, req in zip(workspaces, requests, strict=True):
        assert workspace.scenario_path.read_bytes() == (
            RELEASE_SCENARIO_PATH.read_bytes()
        )
        loaded_req = json.loads(
            workspace.request_path.read_text(encoding="utf-8")
        )
        assert loaded_req["scenario_id"] == req.scenario_id
        if req.plan is None:
            assert not workspace.plan_path.exists()
            assert "plan" not in loaded_req
        else:
            assert workspace.plan_path.is_file()
            assert loaded_req["plan"]["plan_id"] == req.plan.plan_id

    if shared_before is not None:
        after = SHARED_SIM_RESULT_PATH.stat()
        assert after.st_mtime_ns == shared_before.st_mtime_ns
        assert after.st_size == shared_before.st_size


def test_metadata_created_state(
    tmp_path: Path, sample_plan_data: Any
) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = store.create_workspace(
        make_plan_request(sample_plan_data),
        RELEASE_SCENARIO_PATH,
    )
    metadata = json.loads(workspace.metadata_path.read_text(encoding="utf-8"))
    assert metadata["run_id"] == workspace.run_id
    assert metadata["mode"] == "plan"
    assert metadata["scenario_id"] == RELEASE_SCENARIO_ID
    assert metadata["plan_id"] == "sample_plan"
    assert metadata["process_exit_code"] is None
    assert metadata["duration_ms"] is None
    assert metadata["outcome"] is None
    assert metadata["error_code"] is None
    assert "created_at" in metadata


def test_write_stdout_stderr_exact_bytes(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    assert not workspace.stdout_path.exists()
    assert not workspace.stderr_path.exists()
    store.write_stdout(workspace, b"out\x00bytes")
    store.write_stderr(workspace, b"")
    assert workspace.stdout_path.read_bytes() == b"out\x00bytes"
    assert workspace.stderr_path.read_bytes() == b""


def test_hash_result_without_rewrite(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    payload = b'{"outcome":"FAILURE"}'
    workspace.result_path.write_bytes(payload)
    digest = store.hash_result_artifact(workspace)
    assert digest == sha256_file(workspace.result_path)
    assert workspace.result_path.read_bytes() == payload
    assert store.try_hash_result_artifact(workspace) == digest


def test_try_hash_missing_result(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    assert store.try_hash_result_artifact(workspace) is None


def test_write_completed_and_failed_metadata(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    created = json.loads(workspace.metadata_path.read_text(encoding="utf-8"))
    workspace.result_path.write_bytes(b'{"ok":true}')
    digest = store.hash_result_artifact(workspace)
    store.write_completed_metadata(
        workspace,
        result_sha256=digest,
        process_exit_code=0,
        duration_ms=42,
        outcome="FAILURE",
    )
    completed = json.loads(workspace.metadata_path.read_text(encoding="utf-8"))
    assert completed["status"] == "completed"
    assert completed["created_at"] == created["created_at"]
    assert completed["scenario_sha256"] == created["scenario_sha256"]
    assert completed["result_sha256"] == digest
    assert completed["process_exit_code"] == 0
    assert completed["duration_ms"] == 42
    assert completed["outcome"] == "FAILURE"
    assert completed["error_code"] is None

    store.write_failed_metadata(
        workspace,
        error_code=ErrorCode.SIMULATOR_TIMEOUT.value,
        result_sha256=digest,
        process_exit_code=None,
        duration_ms=99,
        outcome=None,
    )
    failed = json.loads(workspace.metadata_path.read_text(encoding="utf-8"))
    assert failed["status"] == "failed"
    assert failed["error_code"] == "SIMULATOR_TIMEOUT"
    assert failed["created_at"] == created["created_at"]
    assert failed["outcome"] is None
