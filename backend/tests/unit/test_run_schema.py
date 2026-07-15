# strict RunArtifactMetadata contract validation
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from app.schemas.run import RunArtifactMetadata
from app.services.run_store import RunStore, sha256_file
from pydantic import ValidationError
from tests.conftest import RELEASE_SCENARIO_PATH, make_baseline_request


def _completed_metadata_payload(tmp_path: Path) -> dict[str, Any]:
    store = RunStore(tmp_path / "runs")
    workspace = store.create_workspace(
        make_baseline_request(),
        RELEASE_SCENARIO_PATH,
    )
    workspace.result_path.write_bytes(b'{"outcome":"FAILURE"}')
    digest = sha256_file(workspace.result_path)
    store.write_completed_metadata(
        workspace,
        result_sha256=digest,
        process_exit_code=0,
        duration_ms=42,
        outcome="FAILURE",
    )
    return json.loads(workspace.metadata_path.read_text(encoding="utf-8"))


def test_real_metadata_fixture_validates(tmp_path: Path) -> None:
    payload = _completed_metadata_payload(tmp_path)
    model = RunArtifactMetadata.model_validate(payload)
    assert model.status == "completed"
    assert model.outcome == "FAILURE"
    assert model.duration_ms == 42


def test_rejects_extra_field(tmp_path: Path) -> None:
    payload = _completed_metadata_payload(tmp_path)
    payload["survival_probability"] = 0.5
    with pytest.raises(ValidationError):
        RunArtifactMetadata.model_validate(payload)


def test_rejects_missing_required_field(tmp_path: Path) -> None:
    payload = _completed_metadata_payload(tmp_path)
    del payload["scenario_sha256"]
    with pytest.raises(ValidationError):
        RunArtifactMetadata.model_validate(payload)


@pytest.mark.parametrize(
    "run_id",
    [
        "UPPERCASE-0000-4000-8000-000000000001",
        "00000000400080000000000000000001",
        "{00000000-0000-4000-8000-000000000001}",
        "",
    ],
)
def test_rejects_invalid_run_id(tmp_path: Path, run_id: str) -> None:
    payload = _completed_metadata_payload(tmp_path)
    payload["run_id"] = run_id
    with pytest.raises(ValidationError):
        RunArtifactMetadata.model_validate(payload)


def test_rejects_naive_created_at(tmp_path: Path) -> None:
    payload = _completed_metadata_payload(tmp_path)
    payload["created_at"] = "2026-01-01T00:00:00"
    with pytest.raises(ValidationError):
        RunArtifactMetadata.model_validate(payload)


def test_rejects_invalid_timestamp(tmp_path: Path) -> None:
    payload = _completed_metadata_payload(tmp_path)
    payload["created_at"] = "not-a-timestamp"
    with pytest.raises(ValidationError):
        RunArtifactMetadata.model_validate(payload)


def test_rejects_lowercase_hash(tmp_path: Path) -> None:
    payload = _completed_metadata_payload(tmp_path)
    payload["scenario_sha256"] = payload["scenario_sha256"].lower()
    with pytest.raises(ValidationError):
        RunArtifactMetadata.model_validate(payload)


def test_rejects_invalid_mode(tmp_path: Path) -> None:
    payload = _completed_metadata_payload(tmp_path)
    payload["mode"] = "custom"
    with pytest.raises(ValidationError):
        RunArtifactMetadata.model_validate(payload)


def test_rejects_invalid_status(tmp_path: Path) -> None:
    payload = _completed_metadata_payload(tmp_path)
    payload["status"] = "pending"
    with pytest.raises(ValidationError):
        RunArtifactMetadata.model_validate(payload)
