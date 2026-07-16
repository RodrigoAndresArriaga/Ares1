# RunStore: UUID workspaces, exact copies, atomic writes, hashes, strict retrieval
from __future__ import annotations

import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from app.core.errors import (
    ArtifactStorageError,
    InvalidRunIdError,
    RunMetadataCorruptError,
    RunMetadataNotFoundError,
    RunNotFoundError,
    RunResultCorruptError,
    RunResultNotFoundError,
)
from app.schemas.api import ErrorCode, SimulationRunRequest
from app.schemas.plan import RecoveryPlan
from app.schemas.result import OutcomeStatus, SimulationResult
from app.schemas.run import RunArtifactMetadata
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
    RESULTS_DIR,
    SHARED_SIM_RESULT_PATH,
    make_baseline_request,
    make_plan_request,
    sha256_hex_upper,
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
        exclude_none=True,
    )
    assert loaded == expected
    assert RELEASE_SCENARIO_PATH.exists()


def test_plan_artifact_omits_explicit_null_optional_fields(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    request = SimulationRunRequest.model_validate(
        {
            "scenario_id": RELEASE_SCENARIO_ID,
            "plan": {
                "plan_id": "planner-null-test",
                "summary": "omit null optional fields for simulator wire format",
                "actions": [
                    {
                        "type": "reduce_power_load",
                        "start_min": 5,
                        "percent": 0.3,
                        "load_groups": ["nonessential"],
                        "module": None,
                        "assigned_crew_ids": None,
                    },
                ],
                "rationale": "regression",
                "expected_risk": "HIGH",
                "constraints_checked": ["power_margin"],
            },
        },
    )
    workspace = store.create_workspace(request, RELEASE_SCENARIO_PATH)
    loaded = json.loads(workspace.plan_path.read_text(encoding="utf-8"))
    action = loaded["actions"][0]
    assert "assigned_crew_ids" not in action
    assert "module" not in action


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
        exclude_none=True,
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


def _try_symlink(link: Path, target: Path) -> bool:
    try:
        link.symlink_to(target)
        return True
    except OSError:
        return False


def _seed_completed_run(
    store: RunStore,
    result_fixture: Path,
    *,
    request: SimulationRunRequest | None = None,
) -> RunWorkspace:
    req = request if request is not None else make_baseline_request()
    workspace = store.create_workspace(req, RELEASE_SCENARIO_PATH)
    result_bytes = result_fixture.read_bytes()
    workspace.result_path.write_bytes(result_bytes)
    outcome = json.loads(result_bytes.decode("utf-8"))["outcome"]
    store.write_completed_metadata(
        workspace,
        result_sha256=sha256_file(workspace.result_path),
        process_exit_code=0,
        duration_ms=1,
        outcome=outcome,
    )
    return workspace


def _artifact_snapshot(run_dir: Path) -> dict[str, bytes]:
    return {
        path.name: path.read_bytes()
        for path in sorted(run_dir.iterdir())
        if path.is_file()
    }


def test_construction_relative_root_cwd_independent(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    store = RunStore(runs)
    workspace = _seed_completed_run(store, RESULTS_DIR / "baseline_result.json")
    (tmp_path / "other").mkdir()
    original = Path.cwd()
    try:
        os.chdir(tmp_path / "other")
        result = store.read_result(workspace.run_id)
        metadata = store.read_metadata(workspace.run_id)
    finally:
        os.chdir(original)
    assert result.outcome == OutcomeStatus.FAILURE
    assert metadata.status == "completed"


def test_retrieval_after_cwd_change(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    store = RunStore(runs)
    workspace = _seed_completed_run(store, RESULTS_DIR / "baseline_result.json")
    original = Path.cwd()
    try:
        os.chdir(tmp_path)
        read = store.read_result(workspace.run_id)
    finally:
        os.chdir(original)
    assert read.outcome == OutcomeStatus.FAILURE


@pytest.mark.parametrize(
    "bad_id",
    [
        "not-a-uuid",
        "ABCDEF00-0000-4000-8000-000000000001",
        "00000000400080000000000000000001",
        "{00000000-0000-4000-8000-000000000001}",
        "00000000-0000-4000-8000-000000000001 ",
        "../00000000-0000-4000-8000-000000000001",
        "00000000-0000-4000-8000-000000000001/../x",
        r"00000000-0000-4000-8000-000000000001" + "\\",
        "%2e%2e%2f00000000-0000-4000-8000-000000000001",
        "",
        "run-name",
    ],
)
def test_rejects_invalid_run_ids(tmp_path: Path, bad_id: str) -> None:
    store = RunStore(tmp_path / "runs")
    with pytest.raises(InvalidRunIdError) as exc_info:
        store.read_result(bad_id)
    assert exc_info.value.code == ErrorCode.RUN_ID_INVALID
    assert str(tmp_path) not in exc_info.value.message


def test_read_baseline_failure_result(tmp_path: Path, baseline_result_data: Any) -> None:
    store = RunStore(tmp_path / "runs")
    fixture = RESULTS_DIR / "baseline_result.json"
    workspace = _seed_completed_run(store, fixture)
    before_bytes = workspace.result_path.read_bytes()
    before_hash = sha256_hex_upper(workspace.result_path)
    result = store.read_result(workspace.run_id)
    expected = SimulationResult.model_validate(baseline_result_data)
    assert result == expected
    assert result.outcome == OutcomeStatus.FAILURE
    assert result.plan_id == ""
    assert result.valid_plan is True
    assert workspace.result_path.read_bytes() == before_bytes
    assert sha256_hex_upper(workspace.result_path) == before_hash


def test_read_stabilized_result(
    tmp_path: Path,
    valid_plan_result_data: Any,
    sample_plan_data: Any,
) -> None:
    store = RunStore(tmp_path / "runs")
    fixture = RESULTS_DIR / "valid_plan_result.json"
    workspace = _seed_completed_run(
        store,
        fixture,
        request=make_plan_request(sample_plan_data),
    )
    result = store.read_result(workspace.run_id)
    expected = SimulationResult.model_validate(valid_plan_result_data)
    assert result == expected
    assert result.outcome == OutcomeStatus.STABILIZED


def test_read_rejected_result(
    tmp_path: Path,
    invalid_plan_result_data: Any,
    invalid_plan_data: Any,
) -> None:
    store = RunStore(tmp_path / "runs")
    fixture = RESULTS_DIR / "invalid_plan_result.json"
    workspace = _seed_completed_run(
        store,
        fixture,
        request=make_plan_request(invalid_plan_data),
    )
    result = store.read_result(workspace.run_id)
    expected = SimulationResult.model_validate(invalid_plan_result_data)
    assert result == expected
    assert result.outcome == OutcomeStatus.REJECTED
    assert result.valid_plan is False


def test_read_metadata_from_phase1_path(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = _seed_completed_run(store, RESULTS_DIR / "baseline_result.json")
    before_bytes = workspace.metadata_path.read_bytes()
    before_hash = sha256_hex_upper(workspace.metadata_path)
    metadata = store.read_metadata(workspace.run_id)
    persisted = json.loads(workspace.metadata_path.read_text(encoding="utf-8"))
    assert metadata == RunArtifactMetadata.model_validate(persisted)
    assert metadata.run_id == workspace.run_id
    assert metadata.outcome == "FAILURE"
    assert workspace.metadata_path.read_bytes() == before_bytes
    assert sha256_hex_upper(workspace.metadata_path) == before_hash


def test_unknown_run_not_found(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    missing = "00000000-0000-4000-8000-000000000099"
    with pytest.raises(RunNotFoundError) as exc_info:
        store.read_result(missing)
    assert exc_info.value.code == ErrorCode.RUN_NOT_FOUND
    assert str(tmp_path) not in exc_info.value.message


def test_missing_result_json(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = store.create_workspace(make_baseline_request(), RELEASE_SCENARIO_PATH)
    with pytest.raises(RunResultNotFoundError) as exc_info:
        store.read_result(workspace.run_id)
    assert exc_info.value.code == ErrorCode.RUN_RESULT_NOT_FOUND


def test_missing_metadata_json(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = store.create_workspace(make_baseline_request(), RELEASE_SCENARIO_PATH)
    workspace.metadata_path.unlink()
    with pytest.raises(RunMetadataNotFoundError) as exc_info:
        store.read_metadata(workspace.run_id)
    assert exc_info.value.code == ErrorCode.RUN_METADATA_NOT_FOUND


def test_result_path_is_directory(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = store.create_workspace(make_baseline_request(), RELEASE_SCENARIO_PATH)
    workspace.result_path.mkdir()
    with pytest.raises(RunResultCorruptError) as exc_info:
        store.read_result(workspace.run_id)
    assert exc_info.value.code == ErrorCode.RUN_RESULT_CORRUPT


def test_metadata_path_is_directory(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = store.create_workspace(make_baseline_request(), RELEASE_SCENARIO_PATH)
    workspace.metadata_path.unlink()
    workspace.metadata_path.mkdir()
    with pytest.raises(RunMetadataCorruptError) as exc_info:
        store.read_metadata(workspace.run_id)
    assert exc_info.value.code == ErrorCode.RUN_METADATA_CORRUPT


def test_corrupt_result_invalid_utf8(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = _seed_completed_run(store, RESULTS_DIR / "baseline_result.json")
    workspace.result_path.write_bytes(b"\xff\xfe")
    with pytest.raises(RunResultCorruptError):
        store.read_result(workspace.run_id)


def test_corrupt_result_malformed_json(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = _seed_completed_run(store, RESULTS_DIR / "baseline_result.json")
    workspace.result_path.write_text("{not json", encoding="utf-8")
    with pytest.raises(RunResultCorruptError):
        store.read_result(workspace.run_id)


def test_corrupt_result_extra_field(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = _seed_completed_run(store, RESULTS_DIR / "baseline_result.json")
    payload = json.loads(workspace.result_path.read_text(encoding="utf-8"))
    payload["survival_probability"] = 0.5
    workspace.result_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RunResultCorruptError):
        store.read_result(workspace.run_id)


def test_corrupt_result_missing_telemetry_history(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = _seed_completed_run(store, RESULTS_DIR / "baseline_result.json")
    payload = json.loads(workspace.result_path.read_text(encoding="utf-8"))
    del payload["telemetry_history"]
    workspace.result_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RunResultCorruptError):
        store.read_result(workspace.run_id)


def test_corrupt_result_invalid_outcome(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = _seed_completed_run(store, RESULTS_DIR / "baseline_result.json")
    payload = json.loads(workspace.result_path.read_text(encoding="utf-8"))
    payload["outcome"] = "EXPLODED"
    workspace.result_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RunResultCorruptError):
        store.read_result(workspace.run_id)


def test_corrupt_metadata_invalid_utf8(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = _seed_completed_run(store, RESULTS_DIR / "baseline_result.json")
    workspace.metadata_path.write_bytes(b"\xff\xfe")
    with pytest.raises(RunMetadataCorruptError):
        store.read_metadata(workspace.run_id)


def test_corrupt_metadata_malformed_json(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = _seed_completed_run(store, RESULTS_DIR / "baseline_result.json")
    workspace.metadata_path.write_text("{bad", encoding="utf-8")
    with pytest.raises(RunMetadataCorruptError):
        store.read_metadata(workspace.run_id)


def test_corrupt_metadata_extra_field(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = _seed_completed_run(store, RESULTS_DIR / "baseline_result.json")
    payload = json.loads(workspace.metadata_path.read_text(encoding="utf-8"))
    payload["extra"] = True
    workspace.metadata_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RunMetadataCorruptError):
        store.read_metadata(workspace.run_id)


def test_corrupt_metadata_run_id_mismatch(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = _seed_completed_run(store, RESULTS_DIR / "baseline_result.json")
    payload = json.loads(workspace.metadata_path.read_text(encoding="utf-8"))
    payload["run_id"] = "00000000-0000-4000-8000-000000000001"
    workspace.metadata_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RunMetadataCorruptError):
        store.read_metadata(workspace.run_id)


def test_corrupt_metadata_invalid_hash(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = _seed_completed_run(store, RESULTS_DIR / "baseline_result.json")
    payload = json.loads(workspace.metadata_path.read_text(encoding="utf-8"))
    payload["scenario_sha256"] = "abc"
    workspace.metadata_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RunMetadataCorruptError):
        store.read_metadata(workspace.run_id)


def test_symlink_run_directory_escape_rejected(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = runs / "00000000-0000-4000-8000-000000000001"
    if not _try_symlink(link, outside):
        pytest.skip("symlinks not supported")
    store = RunStore(runs)
    with pytest.raises(RunNotFoundError):
        store.read_result("00000000-0000-4000-8000-000000000001")


def test_symlink_result_escape_rejected(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = store.create_workspace(make_baseline_request(), RELEASE_SCENARIO_PATH)
    outside = tmp_path / "secret.json"
    outside.write_text("{}", encoding="utf-8")
    link = workspace.result_path
    link.unlink(missing_ok=True)
    if not _try_symlink(link, outside):
        pytest.skip("symlinks not supported")
    with pytest.raises(RunResultCorruptError):
        store.read_result(workspace.run_id)


def test_symlink_metadata_escape_rejected(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = store.create_workspace(make_baseline_request(), RELEASE_SCENARIO_PATH)
    outside = tmp_path / "secret.json"
    outside.write_text("{}", encoding="utf-8")
    link = workspace.metadata_path
    link.unlink(missing_ok=True)
    if not _try_symlink(link, outside):
        pytest.skip("symlinks not supported")
    with pytest.raises(RunMetadataCorruptError):
        store.read_metadata(workspace.run_id)


def test_contained_run_accepted(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = _seed_completed_run(store, RESULTS_DIR / "baseline_result.json")
    assert store.read_result(workspace.run_id).outcome == OutcomeStatus.FAILURE


def test_repeated_reads_do_not_mutate_artifacts(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    workspace = _seed_completed_run(store, RESULTS_DIR / "baseline_result.json")
    run_dir = workspace.root
    before_files = _artifact_snapshot(run_dir)
    before_result_hash = sha256_hex_upper(workspace.result_path)
    before_metadata_hash = sha256_hex_upper(workspace.metadata_path)
    for _ in range(3):
        store.read_result(workspace.run_id)
        store.read_metadata(workspace.run_id)
    assert _artifact_snapshot(run_dir) == before_files
    assert sha256_hex_upper(workspace.result_path) == before_result_hash
    assert sha256_hex_upper(workspace.metadata_path) == before_metadata_hash
    assert list(run_dir.glob(".*.tmp")) == []


def test_failure_and_rejected_return_simulation_result(
    tmp_path: Path,
    invalid_plan_data: Any,
) -> None:
    store = RunStore(tmp_path / "runs")
    failure_ws = _seed_completed_run(store, RESULTS_DIR / "baseline_result.json")
    failure = store.read_result(failure_ws.run_id)
    assert isinstance(failure, SimulationResult)
    assert failure.outcome == OutcomeStatus.FAILURE

    rejected_ws = _seed_completed_run(
        store,
        RESULTS_DIR / "invalid_plan_result.json",
        request=make_plan_request(invalid_plan_data),
    )
    rejected = store.read_result(rejected_ws.run_id)
    assert isinstance(rejected, SimulationResult)
    assert rejected.outcome == OutcomeStatus.REJECTED
