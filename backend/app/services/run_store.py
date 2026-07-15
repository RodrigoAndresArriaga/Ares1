# per-run workspace creation and durable artifact persistence
# UUID isolation, exact scenario copy, atomic JSON writes
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.core.errors import ArtifactStorageError
from app.schemas.api import SimulationRunRequest

_UUID_CREATE_ATTEMPTS = 3
_HASH_CHUNK_SIZE = 1024 * 1024
_JSON_INDENT = 2
_JSON_SEPARATORS = (", ", ": ")


# uppercase hex SHA-256 of on-disk file bytes (Section 7 convention)
def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise ArtifactStorageError("Cannot hash missing or non-file artifact")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(_HASH_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest().upper()


# same-directory atomic write of raw bytes
def write_bytes_atomic(dest: Path, data: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / f".{dest.name}.{uuid.uuid4().hex}.tmp"
    replaced = False
    try:
        with tmp.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, dest)
        replaced = True
    except OSError as exc:
        raise ArtifactStorageError(
            "Failed to write artifact",
        ) from exc
    finally:
        if not replaced:
            tmp.unlink(missing_ok=True)


# canonicalize then atomically write JSON text
def write_json_atomic(dest: Path, obj: object) -> None:
    text = json.dumps(
        obj,
        ensure_ascii=False,
        indent=_JSON_INDENT,
        separators=_JSON_SEPARATORS,
    ) + "\n"
    write_bytes_atomic(dest, text.encode("utf-8"))


@dataclass(frozen=True, slots=True)
class RunWorkspace:
    run_id: str
    root: Path
    request_path: Path
    scenario_path: Path
    plan_path: Path
    result_path: Path
    stdout_path: Path
    stderr_path: Path
    metadata_path: Path


@dataclass(frozen=True, slots=True)
class RunMetadata:
    run_id: str
    created_at: str
    mode: Literal["baseline", "plan"]
    scenario_id: str
    plan_id: str | None
    scenario_sha256: str
    plan_sha256: str | None
    result_sha256: str | None
    process_exit_code: int | None
    duration_ms: int | None
    outcome: str | None
    status: Literal["created", "completed", "failed"]
    error_code: str | None

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


class RunStore:
    def __init__(self, runs_root: Path) -> None:
        self._runs_root = runs_root.resolve()

    def create_workspace(
        self,
        request: SimulationRunRequest,
        scenario_source: Path,
    ) -> RunWorkspace:
        self._runs_root.mkdir(parents=True, exist_ok=True)
        if not self._runs_root.is_dir():
            raise ArtifactStorageError("Runs root is not a directory")

        run_id, root = self._create_run_directory()
        workspace = self._build_workspace(run_id, root)

        try:
            self._write_request(workspace.request_path, request)
            self._copy_scenario(scenario_source, workspace.scenario_path)
            scenario_sha256 = sha256_file(workspace.scenario_path)

            plan_sha256: str | None = None
            plan_id: str | None = None
            if request.plan is not None:
                plan_id = request.plan.plan_id
                plan_payload = request.plan.model_dump(
                    mode="json",
                    exclude_unset=True,
                )
                write_json_atomic(workspace.plan_path, plan_payload)
                plan_sha256 = sha256_file(workspace.plan_path)

            mode: Literal["baseline", "plan"] = (
                "plan" if request.plan is not None else "baseline"
            )
            metadata = RunMetadata(
                run_id=run_id,
                created_at=datetime.now(timezone.utc).isoformat(),
                mode=mode,
                scenario_id=request.scenario_id,
                plan_id=plan_id,
                scenario_sha256=scenario_sha256,
                plan_sha256=plan_sha256,
                result_sha256=None,
                process_exit_code=None,
                duration_ms=None,
                outcome=None,
                status="created",
                error_code=None,
            )
            write_json_atomic(workspace.metadata_path, metadata.to_json_dict())
        except ArtifactStorageError as exc:
            if exc.run_id is None:
                raise ArtifactStorageError(exc.message, run_id=run_id) from exc
            raise
        except OSError as exc:
            raise ArtifactStorageError(
                "Failed to persist run artifacts",
                run_id=run_id,
            ) from exc

        return workspace

    def _create_run_directory(self) -> tuple[str, Path]:
        last_error: OSError | None = None
        for _ in range(_UUID_CREATE_ATTEMPTS):
            run_id = str(uuid.uuid4())
            root = self._runs_root / run_id
            try:
                root.mkdir(parents=False, exist_ok=False)
                return run_id, root
            except FileExistsError as exc:
                last_error = exc
                continue
            except OSError as exc:
                raise ArtifactStorageError(
                    "Failed to create run directory",
                ) from exc
        raise ArtifactStorageError(
            "Failed to allocate unique run directory",
        ) from last_error

    def _build_workspace(self, run_id: str, root: Path) -> RunWorkspace:
        return RunWorkspace(
            run_id=run_id,
            root=root,
            request_path=root / "request.json",
            scenario_path=root / "scenario.json",
            plan_path=root / "plan.json",
            result_path=root / "result.json",
            stdout_path=root / "stdout.log",
            stderr_path=root / "stderr.log",
            metadata_path=root / "metadata.json",
        )

    def _write_request(
        self,
        dest: Path,
        request: SimulationRunRequest,
    ) -> None:
        payload: dict[str, Any] = {"scenario_id": request.scenario_id}
        if request.plan is not None:
            payload["plan"] = request.plan.model_dump(
                mode="json",
                exclude_unset=True,
            )
        try:
            write_json_atomic(dest, payload)
        except ArtifactStorageError as exc:
            raise ArtifactStorageError(
                "Failed to write request artifact",
                run_id=dest.parent.name,
            ) from exc

    def _copy_scenario(self, source: Path, dest: Path) -> None:
        try:
            shutil.copyfile(source, dest)
        except OSError as exc:
            raise ArtifactStorageError(
                "Failed to copy scenario artifact",
                run_id=dest.parent.name,
            ) from exc
