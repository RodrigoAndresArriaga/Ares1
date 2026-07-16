# filesystem-backed immutable PlanningAttempt persistence
# exclusive create only; simulator validation artifacts belong in Step 3
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from pydantic import ValidationError

from app.core.errors import (
    ArtifactStorageError,
    InvalidPlanningAttemptIdError,
    PlanningAttemptAlreadyExistsError,
    PlanningAttemptCorruptError,
    PlanningAttemptNotFoundError,
    PlanningAttemptStorageError,
)
from app.schemas.planning import PlanningAttempt
from app.services.run_store import write_json_atomic

logger = logging.getLogger("ares.planning_attempt_store")

_ATTEMPT_FILENAME = "attempt.json"


class PlanningAttemptStore:
    # Persist strict PlanningAttempt JSON under an isolated planning root.

    def __init__(self, planning_root: Path) -> None:
        root = planning_root.resolve()
        if not root.exists() or not root.is_dir():
            raise PlanningAttemptStorageError(
                "Planning attempts root is missing or not a directory",
            )
        self._planning_root = root

    # accept only canonical lowercase hyphenated UUID strings
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

    # resolve attempt directory and prove containment under planning root
    def _attempt_dir(self, attempt_id: str) -> Path:
        canonical = self._canonical_attempt_id(attempt_id)
        candidate = self._planning_root / canonical
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self._planning_root):
            raise PlanningAttemptCorruptError(
                "Planning attempt path escapes planning root",
                attempt_id=canonical,
            )
        return resolved

    # resolve attempt.json and enforce file containment under attempt dir
    def _attempt_json_path(self, attempt_id: str) -> Path:
        attempt_dir = self._attempt_dir(attempt_id)
        candidate = attempt_dir / _ATTEMPT_FILENAME
        if candidate.is_symlink():
            resolved = candidate.resolve()
            if not resolved.is_relative_to(attempt_dir):
                raise PlanningAttemptCorruptError(
                    "Planning attempt artifact escapes attempt directory",
                    attempt_id=attempt_id,
                )
            if not resolved.is_file() or resolved.is_symlink():
                raise PlanningAttemptCorruptError(
                    "Planning attempt artifact is corrupt",
                    attempt_id=attempt_id,
                )
            return resolved
        resolved = candidate.resolve()
        if not resolved.is_relative_to(attempt_dir):
            raise PlanningAttemptCorruptError(
                "Planning attempt path escapes planning root",
                attempt_id=attempt_id,
            )
        return resolved

    # remove empty attempt dir created during failed create_attempt
    def _cleanup_new_attempt_dir(self, attempt_dir: Path) -> None:
        try:
            for child in attempt_dir.iterdir():
                if child.name.endswith(".tmp") and child.is_file():
                    child.unlink(missing_ok=True)
            attempt_dir.rmdir()
        except OSError as exc:
            logger.warning(
                "planning_attempt_create_cleanup_failed attempt_dir_name=%s err=%s",
                attempt_dir.name,
                type(exc).__name__,
            )

    def create_attempt(self, attempt: PlanningAttempt) -> PlanningAttempt:
        canonical = self._canonical_attempt_id(attempt.attempt_id)
        if attempt.attempt_id != canonical:
            raise InvalidPlanningAttemptIdError(
                "Planning attempt ID is invalid",
                attempt_id=attempt.attempt_id,
            )

        attempt_dir = self._planning_root / canonical
        created_dir = False
        try:
            attempt_dir.mkdir(exist_ok=False)
            created_dir = True
            payload = attempt.model_dump(mode="json")
            dest = attempt_dir / _ATTEMPT_FILENAME
            write_json_atomic(dest, payload)
        except FileExistsError as exc:
            raise PlanningAttemptAlreadyExistsError(
                "Planning attempt already exists",
                attempt_id=canonical,
            ) from exc
        except ArtifactStorageError as exc:
            if created_dir:
                self._cleanup_new_attempt_dir(attempt_dir)
            logger.error(
                "planning_attempt_storage_failure op=create attempt_id=%s code=%s",
                canonical,
                "PLANNING_ATTEMPT_STORAGE_ERROR",
            )
            raise PlanningAttemptStorageError(
                "Failed to create planning attempt",
                attempt_id=canonical,
            ) from exc
        except OSError as exc:
            if created_dir:
                self._cleanup_new_attempt_dir(attempt_dir)
            logger.error(
                "planning_attempt_storage_failure op=create attempt_id=%s",
                canonical,
            )
            raise PlanningAttemptStorageError(
                "Failed to create planning attempt",
                attempt_id=canonical,
            ) from exc
        except Exception:
            if created_dir:
                self._cleanup_new_attempt_dir(attempt_dir)
            raise

        logger.info(
            "planning_attempt_created attempt_id=%s session_id=%s status=%s",
            canonical,
            attempt.session_id,
            attempt.status.value,
        )
        return self.read_attempt(canonical)

    def read_attempt(self, attempt_id: str) -> PlanningAttempt:
        canonical = self._canonical_attempt_id(attempt_id)
        try:
            attempt_dir = self._attempt_dir(canonical)
        except PlanningAttemptCorruptError:
            raise
        except InvalidPlanningAttemptIdError:
            raise

        if not attempt_dir.exists() or not attempt_dir.is_dir():
            raise PlanningAttemptNotFoundError(
                "Planning attempt not found",
                attempt_id=canonical,
            )

        try:
            json_path = self._attempt_json_path(canonical)
        except PlanningAttemptCorruptError as exc:
            logger.error(
                "planning_attempt_corrupt attempt_id=%s code=%s",
                canonical,
                exc.code.value,
            )
            raise

        if not json_path.exists():
            raise PlanningAttemptNotFoundError(
                "Planning attempt not found",
                attempt_id=canonical,
            )
        if json_path.is_dir():
            logger.error(
                "planning_attempt_corrupt attempt_id=%s reason=json_is_dir",
                canonical,
            )
            raise PlanningAttemptCorruptError(
                "Planning attempt artifact is corrupt",
                attempt_id=canonical,
            )
        if not json_path.is_file():
            raise PlanningAttemptNotFoundError(
                "Planning attempt not found",
                attempt_id=canonical,
            )

        try:
            raw = json_path.read_bytes()
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            logger.error(
                "planning_attempt_corrupt attempt_id=%s reason=utf8",
                canonical,
            )
            raise PlanningAttemptCorruptError(
                "Planning attempt artifact is corrupt",
                attempt_id=canonical,
            ) from exc
        except OSError as exc:
            logger.error(
                "planning_attempt_storage_failure op=read attempt_id=%s",
                canonical,
            )
            raise PlanningAttemptStorageError(
                "Failed to read planning attempt",
                attempt_id=canonical,
            ) from exc

        try:
            attempt = PlanningAttempt.model_validate_json(text)
        except ValidationError as exc:
            logger.error(
                "planning_attempt_corrupt attempt_id=%s reason=schema",
                canonical,
            )
            raise PlanningAttemptCorruptError(
                "Planning attempt artifact is corrupt",
                attempt_id=canonical,
            ) from exc
        except ValueError as exc:
            logger.error(
                "planning_attempt_corrupt attempt_id=%s reason=json",
                canonical,
            )
            raise PlanningAttemptCorruptError(
                "Planning attempt artifact is corrupt",
                attempt_id=canonical,
            ) from exc

        if attempt.attempt_id != canonical:
            logger.error(
                "planning_attempt_corrupt attempt_id=%s reason=id_mismatch",
                canonical,
            )
            raise PlanningAttemptCorruptError(
                "Planning attempt artifact is corrupt",
                attempt_id=canonical,
            )

        logger.debug(
            "planning_attempt_read attempt_id=%s session_id=%s status=%s",
            canonical,
            attempt.session_id,
            attempt.status.value,
        )
        return attempt

    def attempt_exists(self, attempt_id: str) -> bool:
        canonical = self._canonical_attempt_id(attempt_id)
        attempt_dir = self._planning_root / canonical
        try:
            resolved_dir = attempt_dir.resolve()
        except OSError:
            return False
        if not resolved_dir.is_relative_to(self._planning_root):
            return False
        if not resolved_dir.is_dir():
            return False
        json_path = resolved_dir / _ATTEMPT_FILENAME
        if json_path.is_symlink():
            try:
                target = json_path.resolve()
            except OSError:
                return False
            return target.is_relative_to(resolved_dir) and target.is_file()
        return json_path.is_file()
