# filesystem-backed PlanningValidationRecord persistence
# lives beside immutable attempt.json under the same planning root
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from pydantic import ValidationError

from app.core.errors import (
    ArtifactStorageError,
    InvalidPlanningAttemptIdError,
    PlanningValidationAlreadyExistsError,
    PlanningValidationConflictError,
    PlanningValidationCorruptError,
    PlanningValidationNotFoundError,
    PlanningValidationStorageError,
)
from app.schemas.planning_validation import (
    PlanningValidationRecord,
    PlanningValidationStatus,
)
from app.services.run_store import write_json_atomic

logger = logging.getLogger("ares.planning_validation_store")

_VALIDATION_FILENAME = "validation.json"
_ATTEMPT_FILENAME = "attempt.json"
_TERMINAL_STATUSES = frozenset(
    {
        PlanningValidationStatus.SIMULATION_COMPLETE,
        PlanningValidationStatus.ERROR,
    },
)


class PlanningValidationStore:
    # Persist strict PlanningValidationRecord JSON under an existing attempt dir.

    def __init__(self, planning_root: Path) -> None:
        root = planning_root.resolve()
        if not root.exists() or not root.is_dir():
            raise PlanningValidationStorageError(
                "Planning validation root is missing or not a directory",
            )
        self._planning_root = root

    def _canonical_attempt_id(self, value: object) -> str:
        if not isinstance(value, str):
            raise InvalidPlanningAttemptIdError(
                "Planning attempt ID is invalid",
            )
        if not value or value != value.strip():
            raise InvalidPlanningAttemptIdError(
                "Planning attempt ID is invalid",
                attempt_id=value if isinstance(value, str) else None,
            )
        if any(ch in value for ch in ("/", "\\", "%")):
            raise InvalidPlanningAttemptIdError(
                "Planning attempt ID is invalid",
                attempt_id=value,
            )
        if value in (".", "..") or ".." in value:
            raise InvalidPlanningAttemptIdError(
                "Planning attempt ID is invalid",
                attempt_id=value,
            )
        try:
            parsed = uuid.UUID(value)
        except (ValueError, AttributeError, TypeError) as exc:
            raise InvalidPlanningAttemptIdError(
                "Planning attempt ID is invalid",
                attempt_id=value,
            ) from exc
        canonical = str(parsed)
        if value != canonical:
            raise InvalidPlanningAttemptIdError(
                "Planning attempt ID is invalid",
                attempt_id=value,
            )
        return canonical

    def _attempt_dir(self, attempt_id: str) -> Path:
        canonical = self._canonical_attempt_id(attempt_id)
        candidate = self._planning_root / canonical
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self._planning_root):
            raise PlanningValidationCorruptError(
                "Planning validation path escapes planning root",
                attempt_id=canonical,
            )
        return resolved

    def _validation_json_path(self, attempt_id: str) -> Path:
        attempt_dir = self._attempt_dir(attempt_id)
        candidate = attempt_dir / _VALIDATION_FILENAME
        if candidate.is_symlink():
            resolved = candidate.resolve()
            if not resolved.is_relative_to(attempt_dir):
                raise PlanningValidationCorruptError(
                    "Planning validation artifact escapes attempt directory",
                    attempt_id=attempt_id,
                )
            if not resolved.is_file() or resolved.is_symlink():
                raise PlanningValidationCorruptError(
                    "Planning validation artifact is corrupt",
                    attempt_id=attempt_id,
                )
            return resolved
        resolved = candidate.resolve()
        if not resolved.is_relative_to(attempt_dir):
            raise PlanningValidationCorruptError(
                "Planning validation path escapes planning root",
                attempt_id=attempt_id,
            )
        return resolved

    def _require_attempt_dir_exists(self, attempt_id: str) -> Path:
        canonical = self._canonical_attempt_id(attempt_id)
        attempt_dir = self._attempt_dir(canonical)
        if not attempt_dir.exists() or not attempt_dir.is_dir():
            raise PlanningValidationNotFoundError(
                "Planning attempt directory not found for validation",
                attempt_id=canonical,
            )
        attempt_json = attempt_dir / _ATTEMPT_FILENAME
        if not attempt_json.is_file():
            raise PlanningValidationNotFoundError(
                "Planning attempt directory not found for validation",
                attempt_id=canonical,
            )
        return attempt_dir

    def create_validation(self, record: PlanningValidationRecord) -> PlanningValidationRecord:
        canonical = self._canonical_attempt_id(record.attempt_id)
        if record.attempt_id != canonical:
            raise InvalidPlanningAttemptIdError(
                "Planning attempt ID is invalid",
                attempt_id=record.attempt_id,
            )

        self._require_attempt_dir_exists(canonical)
        attempt_dir = self._attempt_dir(canonical)
        dest = attempt_dir / _VALIDATION_FILENAME
        if dest.exists():
            raise PlanningValidationAlreadyExistsError(
                "Planning validation already exists",
                attempt_id=canonical,
            )

        try:
            payload = record.model_dump(mode="json")
            write_json_atomic(dest, payload)
        except ArtifactStorageError as exc:
            logger.error(
                "planning_validation_storage_failure op=create attempt_id=%s code=%s",
                canonical,
                "PLANNING_VALIDATION_STORAGE_ERROR",
            )
            raise PlanningValidationStorageError(
                "Failed to create planning validation",
                attempt_id=canonical,
            ) from exc
        except OSError as exc:
            logger.error(
                "planning_validation_storage_failure op=create attempt_id=%s",
                canonical,
            )
            raise PlanningValidationStorageError(
                "Failed to create planning validation",
                attempt_id=canonical,
            ) from exc

        logger.info(
            "planning_validation_created attempt_id=%s session_id=%s status=%s",
            canonical,
            record.session_id,
            record.status.value,
        )
        return self.read_validation(canonical)

    def read_validation(self, attempt_id: str) -> PlanningValidationRecord:
        canonical = self._canonical_attempt_id(attempt_id)
        attempt_dir = self._attempt_dir(canonical)
        if not attempt_dir.exists() or not attempt_dir.is_dir():
            raise PlanningValidationNotFoundError(
                "Planning validation not found",
                attempt_id=canonical,
            )

        try:
            json_path = self._validation_json_path(canonical)
        except PlanningValidationCorruptError as exc:
            logger.error(
                "planning_validation_corrupt attempt_id=%s code=%s",
                canonical,
                exc.code.value,
            )
            raise

        if not json_path.exists():
            raise PlanningValidationNotFoundError(
                "Planning validation not found",
                attempt_id=canonical,
            )
        if json_path.is_dir():
            logger.error(
                "planning_validation_corrupt attempt_id=%s reason=json_is_dir",
                canonical,
            )
            raise PlanningValidationCorruptError(
                "Planning validation artifact is corrupt",
                attempt_id=canonical,
            )
        if not json_path.is_file():
            raise PlanningValidationNotFoundError(
                "Planning validation not found",
                attempt_id=canonical,
            )

        try:
            raw = json_path.read_bytes()
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            logger.error(
                "planning_validation_corrupt attempt_id=%s reason=utf8",
                canonical,
            )
            raise PlanningValidationCorruptError(
                "Planning validation artifact is corrupt",
                attempt_id=canonical,
            ) from exc
        except OSError as exc:
            logger.error(
                "planning_validation_storage_failure op=read attempt_id=%s",
                canonical,
            )
            raise PlanningValidationStorageError(
                "Failed to read planning validation",
                attempt_id=canonical,
            ) from exc

        try:
            record = PlanningValidationRecord.model_validate_json(text)
        except ValidationError as exc:
            logger.error(
                "planning_validation_corrupt attempt_id=%s reason=schema",
                canonical,
            )
            raise PlanningValidationCorruptError(
                "Planning validation artifact is corrupt",
                attempt_id=canonical,
            ) from exc
        except ValueError as exc:
            logger.error(
                "planning_validation_corrupt attempt_id=%s reason=json",
                canonical,
            )
            raise PlanningValidationCorruptError(
                "Planning validation artifact is corrupt",
                attempt_id=canonical,
            ) from exc

        if record.attempt_id != canonical:
            logger.error(
                "planning_validation_corrupt attempt_id=%s reason=id_mismatch",
                canonical,
            )
            raise PlanningValidationCorruptError(
                "Planning validation artifact is corrupt",
                attempt_id=canonical,
            )

        logger.debug(
            "planning_validation_read attempt_id=%s session_id=%s status=%s",
            canonical,
            record.session_id,
            record.status.value,
        )
        return record

    def replace_validation(
        self,
        record: PlanningValidationRecord,
        *,
        expected_status: PlanningValidationStatus | None = None,
    ) -> PlanningValidationRecord:
        canonical = self._canonical_attempt_id(record.attempt_id)
        if record.attempt_id != canonical:
            raise InvalidPlanningAttemptIdError(
                "Planning attempt ID is invalid",
                attempt_id=record.attempt_id,
            )

        current = self.read_validation(canonical)
        if current.status in _TERMINAL_STATUSES:
            logger.info(
                "planning_validation_replace_conflict attempt_id=%s "
                "reason=terminal_status actual_status=%s code=%s",
                canonical,
                current.status.value,
                "PLANNING_VALIDATION_CONFLICT",
            )
            raise PlanningValidationConflictError(
                "Planning validation is in a terminal state",
                attempt_id=canonical,
            )

        if expected_status is not None and current.status != expected_status:
            logger.info(
                "planning_validation_replace_conflict attempt_id=%s "
                "expected_status=%s actual_status=%s code=%s",
                canonical,
                expected_status.value,
                current.status.value,
                "PLANNING_VALIDATION_CONFLICT",
            )
            raise PlanningValidationConflictError(
                "Planning validation status conflict",
                attempt_id=canonical,
            )

        dest = self._validation_json_path(canonical)
        try:
            payload = record.model_dump(mode="json")
            write_json_atomic(dest, payload)
        except ArtifactStorageError as exc:
            logger.error(
                "planning_validation_storage_failure op=replace attempt_id=%s code=%s",
                canonical,
                "PLANNING_VALIDATION_STORAGE_ERROR",
            )
            raise PlanningValidationStorageError(
                "Failed to replace planning validation",
                attempt_id=canonical,
            ) from exc
        except OSError as exc:
            logger.error(
                "planning_validation_storage_failure op=replace attempt_id=%s",
                canonical,
            )
            raise PlanningValidationStorageError(
                "Failed to replace planning validation",
                attempt_id=canonical,
            ) from exc

        logger.info(
            "planning_validation_replaced attempt_id=%s session_id=%s status=%s",
            canonical,
            record.session_id,
            record.status.value,
        )
        return self.read_validation(canonical)
