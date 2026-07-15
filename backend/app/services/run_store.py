# per-run workspace creation and durable artifact persistence
# UUID isolation, exact scenario copy, atomic JSON writes
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from app.core.errors import (
    ArtifactStorageError,
    InvalidRunIdError,
    RunArtifactStorageError,
    RunMetadataCorruptError,
    RunMetadataNotFoundError,
    RunNotFoundError,
    RunResultCorruptError,
    RunResultNotFoundError,
)
from app.schemas.api import ErrorCode, SimulationRunRequest
from app.schemas.result import SimulationResult
from app.schemas.run import RunArtifactMetadata, validate_canonical_run_id

logger = logging.getLogger("ares.run_store")

_UUID_CREATE_ATTEMPTS = 3
_HASH_CHUNK_SIZE = 1024 * 1024
_JSON_INDENT = 2
_JSON_SEPARATORS = (", ", ": ")
_RESULT_FILENAME = "result.json"
_METADATA_FILENAME = "metadata.json"


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

    # accept only canonical lowercase hyphenated UUID strings
    def _canonical_run_id(self, value: object) -> str:
        try:
            return validate_canonical_run_id(value)
        except ValueError as exc:
            run_id = value if isinstance(value, str) else None
            raise InvalidRunIdError(
                "Run ID is invalid",
                run_id=run_id,
            ) from exc

    # resolve run directory and prove containment under the runs root
    def _resolve_run_directory(self, run_id: str) -> Path:
        canonical = self._canonical_run_id(run_id)
        candidate = self._runs_root / canonical
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self._runs_root):
            logger.warning(
                "run_directory_containment_rejected run_id=%s error_code=%s",
                canonical,
                ErrorCode.RUN_NOT_FOUND.value,
            )
            raise RunNotFoundError("Run not found", run_id=canonical)
        if candidate.is_symlink():
            if not resolved.is_relative_to(self._runs_root):
                logger.warning(
                    "run_directory_symlink_escape run_id=%s error_code=%s",
                    canonical,
                    ErrorCode.RUN_NOT_FOUND.value,
                )
                raise RunNotFoundError("Run not found", run_id=canonical)
        if not resolved.is_dir():
            logger.warning(
                "run_not_found run_id=%s error_code=%s",
                canonical,
                ErrorCode.RUN_NOT_FOUND.value,
            )
            raise RunNotFoundError("Run not found", run_id=canonical)
        return resolved

    # resolve a contained artifact file under the trusted run directory
    def _resolve_artifact_path(
        self,
        run_id: str,
        filename: str,
        *,
        artifact_label: Literal["result", "metadata"],
    ) -> Path:
        canonical = self._canonical_run_id(run_id)
        run_dir = self._resolve_run_directory(canonical)
        not_found_error = (
            RunResultNotFoundError
            if artifact_label == "result"
            else RunMetadataNotFoundError
        )
        corrupt_error = (
            RunResultCorruptError
            if artifact_label == "result"
            else RunMetadataCorruptError
        )
        not_found_message = (
            "Run result artifact not found"
            if artifact_label == "result"
            else "Run metadata artifact not found"
        )
        corrupt_message = (
            "Run result artifact is corrupt"
            if artifact_label == "result"
            else "Run metadata artifact is corrupt"
        )
        corrupt_code = (
            ErrorCode.RUN_RESULT_CORRUPT.value
            if artifact_label == "result"
            else ErrorCode.RUN_METADATA_CORRUPT.value
        )
        not_found_code = (
            ErrorCode.RUN_RESULT_NOT_FOUND.value
            if artifact_label == "result"
            else ErrorCode.RUN_METADATA_NOT_FOUND.value
        )
        candidate = run_dir / filename
        if candidate.is_symlink():
            resolved = candidate.resolve()
            if not resolved.is_relative_to(run_dir):
                logger.warning(
                    "run_artifact_symlink_escape run_id=%s artifact_type=%s error_code=%s",
                    canonical,
                    artifact_label,
                    corrupt_code,
                )
                raise corrupt_error(corrupt_message, run_id=canonical)
            if not resolved.is_file() or resolved.is_symlink():
                logger.warning(
                    "run_artifact_corrupt run_id=%s artifact_type=%s error_code=%s",
                    canonical,
                    artifact_label,
                    corrupt_code,
                )
                raise corrupt_error(corrupt_message, run_id=canonical)
            return resolved
        resolved = candidate.resolve()
        if not resolved.is_relative_to(run_dir):
            logger.warning(
                "run_artifact_containment_rejected run_id=%s artifact_type=%s error_code=%s",
                canonical,
                artifact_label,
                corrupt_code,
            )
            raise corrupt_error(corrupt_message, run_id=canonical)
        if resolved.is_dir():
            logger.warning(
                "run_artifact_is_directory run_id=%s artifact_type=%s error_code=%s",
                canonical,
                artifact_label,
                corrupt_code,
            )
            raise corrupt_error(corrupt_message, run_id=canonical)
        if not resolved.is_file():
            logger.warning(
                "run_artifact_not_found run_id=%s artifact_type=%s error_code=%s",
                canonical,
                artifact_label,
                not_found_code,
            )
            raise not_found_error(not_found_message, run_id=canonical)
        return resolved

    # read and validate persisted result.json without mutating the artifact
    def read_result(self, run_id: str) -> SimulationResult:
        canonical = self._canonical_run_id(run_id)
        path = self._resolve_artifact_path(
            canonical,
            _RESULT_FILENAME,
            artifact_label="result",
        )
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError as exc:
            logger.warning(
                "run_result_corrupt run_id=%s artifact_type=result error_code=%s",
                canonical,
                ErrorCode.RUN_RESULT_CORRUPT.value,
            )
            raise RunResultCorruptError(
                "Run result artifact is corrupt",
                run_id=canonical,
            ) from exc
        except OSError as exc:
            logger.warning(
                "run_artifact_storage_error run_id=%s artifact_type=result error_code=%s",
                canonical,
                ErrorCode.RUN_ARTIFACT_STORAGE_ERROR.value,
            )
            raise RunArtifactStorageError(
                "Run artifact storage failed",
                run_id=canonical,
            ) from exc
        try:
            result = SimulationResult.model_validate_json(text)
        except ValidationError as exc:
            logger.warning(
                "run_result_corrupt run_id=%s artifact_type=result error_code=%s",
                canonical,
                ErrorCode.RUN_RESULT_CORRUPT.value,
            )
            raise RunResultCorruptError(
                "Run result artifact is corrupt",
                run_id=canonical,
            ) from exc
        logger.debug(
            "run_result_retrieved run_id=%s artifact_type=result outcome=%s",
            canonical,
            result.outcome.value,
        )
        return result

    # read and validate persisted metadata.json without mutating the artifact
    def read_metadata(self, run_id: str) -> RunArtifactMetadata:
        canonical = self._canonical_run_id(run_id)
        path = self._resolve_artifact_path(
            canonical,
            _METADATA_FILENAME,
            artifact_label="metadata",
        )
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError as exc:
            logger.warning(
                "run_metadata_corrupt run_id=%s artifact_type=metadata error_code=%s",
                canonical,
                ErrorCode.RUN_METADATA_CORRUPT.value,
            )
            raise RunMetadataCorruptError(
                "Run metadata artifact is corrupt",
                run_id=canonical,
            ) from exc
        except OSError as exc:
            logger.warning(
                "run_artifact_storage_error run_id=%s artifact_type=metadata error_code=%s",
                canonical,
                ErrorCode.RUN_ARTIFACT_STORAGE_ERROR.value,
            )
            raise RunArtifactStorageError(
                "Run artifact storage failed",
                run_id=canonical,
            ) from exc
        try:
            metadata = RunArtifactMetadata.model_validate_json(text)
        except ValidationError as exc:
            logger.warning(
                "run_metadata_corrupt run_id=%s artifact_type=metadata error_code=%s",
                canonical,
                ErrorCode.RUN_METADATA_CORRUPT.value,
            )
            raise RunMetadataCorruptError(
                "Run metadata artifact is corrupt",
                run_id=canonical,
            ) from exc
        if metadata.run_id != canonical:
            logger.warning(
                "run_metadata_run_id_mismatch run_id=%s artifact_type=metadata error_code=%s",
                canonical,
                ErrorCode.RUN_METADATA_CORRUPT.value,
            )
            raise RunMetadataCorruptError(
                "Run metadata artifact is corrupt",
                run_id=canonical,
            )
        logger.debug(
            "run_metadata_retrieved run_id=%s artifact_type=metadata status=%s",
            canonical,
            metadata.status,
        )
        return metadata

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

    # persist exact process stdout bytes
    def write_stdout(self, workspace: RunWorkspace, data: bytes) -> None:
        self._write_process_log(workspace, workspace.stdout_path, data)

    # persist exact process stderr bytes
    def write_stderr(self, workspace: RunWorkspace, data: bytes) -> None:
        self._write_process_log(workspace, workspace.stderr_path, data)

    # uppercase SHA-256 of existing simulator-written result.json
    def hash_result_artifact(self, workspace: RunWorkspace) -> str:
        try:
            return sha256_file(workspace.result_path)
        except ArtifactStorageError as exc:
            raise ArtifactStorageError(
                exc.message,
                run_id=workspace.run_id,
            ) from exc

    # hash result when present; otherwise None
    def try_hash_result_artifact(self, workspace: RunWorkspace) -> str | None:
        if not workspace.result_path.is_file():
            return None
        return self.hash_result_artifact(workspace)

    # replace created metadata with completed infrastructure evidence
    def write_completed_metadata(
        self,
        workspace: RunWorkspace,
        *,
        result_sha256: str,
        process_exit_code: int | None,
        duration_ms: int | None,
        outcome: str,
    ) -> None:
        created = self._load_metadata(workspace)
        completed = RunMetadata(
            run_id=created.run_id,
            created_at=created.created_at,
            mode=created.mode,
            scenario_id=created.scenario_id,
            plan_id=created.plan_id,
            scenario_sha256=created.scenario_sha256,
            plan_sha256=created.plan_sha256,
            result_sha256=result_sha256,
            process_exit_code=process_exit_code,
            duration_ms=duration_ms,
            outcome=outcome,
            status="completed",
            error_code=None,
        )
        self._write_metadata(workspace, completed)

    # replace created metadata with infrastructure failure evidence
    def write_failed_metadata(
        self,
        workspace: RunWorkspace,
        *,
        error_code: str,
        result_sha256: str | None = None,
        process_exit_code: int | None = None,
        duration_ms: int | None = None,
        outcome: str | None = None,
    ) -> None:
        created = self._load_metadata(workspace)
        failed = RunMetadata(
            run_id=created.run_id,
            created_at=created.created_at,
            mode=created.mode,
            scenario_id=created.scenario_id,
            plan_id=created.plan_id,
            scenario_sha256=created.scenario_sha256,
            plan_sha256=created.plan_sha256,
            result_sha256=result_sha256,
            process_exit_code=process_exit_code,
            duration_ms=duration_ms,
            outcome=outcome,
            status="failed",
            error_code=error_code,
        )
        self._write_metadata(workspace, failed)

    def _write_process_log(
        self,
        workspace: RunWorkspace,
        dest: Path,
        data: bytes,
    ) -> None:
        try:
            write_bytes_atomic(dest, data)
        except ArtifactStorageError as exc:
            raise ArtifactStorageError(
                "Failed to write process log",
                run_id=workspace.run_id,
            ) from exc

    def _load_metadata(self, workspace: RunWorkspace) -> RunMetadata:
        try:
            payload = json.loads(
                workspace.metadata_path.read_text(encoding="utf-8"),
            )
        except (OSError, json.JSONDecodeError, UnicodeError) as exc:
            raise ArtifactStorageError(
                "Failed to read run metadata",
                run_id=workspace.run_id,
            ) from exc
        try:
            return RunMetadata(
                run_id=payload["run_id"],
                created_at=payload["created_at"],
                mode=payload["mode"],
                scenario_id=payload["scenario_id"],
                plan_id=payload["plan_id"],
                scenario_sha256=payload["scenario_sha256"],
                plan_sha256=payload["plan_sha256"],
                result_sha256=payload["result_sha256"],
                process_exit_code=payload["process_exit_code"],
                duration_ms=payload["duration_ms"],
                outcome=payload["outcome"],
                status=payload["status"],
                error_code=payload["error_code"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ArtifactStorageError(
                "Run metadata is corrupt",
                run_id=workspace.run_id,
            ) from exc

    def _write_metadata(
        self,
        workspace: RunWorkspace,
        metadata: RunMetadata,
    ) -> None:
        try:
            write_json_atomic(
                workspace.metadata_path,
                metadata.to_json_dict(),
            )
        except ArtifactStorageError as exc:
            raise ArtifactStorageError(
                "Failed to write run metadata",
                run_id=workspace.run_id,
            ) from exc
