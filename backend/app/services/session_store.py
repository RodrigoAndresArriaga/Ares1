# filesystem-backed MissionSession persistence with in-process locks
#
# The filesystem record under sessions_root is authoritative. Writes are atomic
# same-directory temp + replace. Per-session asyncio.Lock instances serialize
# same-process transitions only; there is no distributed locking. Lifecycle
# transition policy belongs to MissionLifecycleService, not this store.
from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Collection
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from app.core.errors import (
    ArtifactStorageError,
    InvalidMissionSessionIdError,
    MissionSessionAlreadyExistsError,
    MissionSessionConflictError,
    MissionSessionCorruptError,
    MissionSessionNotFoundError,
    MissionSessionStorageError,
)
from app.schemas.mission import MissionSession, MissionSessionStatus
from app.services.run_store import write_json_atomic

logger = logging.getLogger("ares.session_store")

_SESSION_FILENAME = "session.json"


class SessionStore:
    # Persist strict MissionSession JSON under an isolated sessions root.
    # Locks are in-process only; callers must acquire lock_session around
    # multi-step transitions. The store never invents lifecycle transitions.
    def __init__(self, sessions_root: Path) -> None:
        root = sessions_root.resolve()
        if not root.exists() or not root.is_dir():
            raise MissionSessionStorageError(
                "Sessions root is missing or not a directory",
            )
        self._sessions_root = root
        self._locks: dict[str, asyncio.Lock] = {}

    # accept only canonical lowercase hyphenated UUID strings
    def _canonical_session_id(self, value: object) -> str:
        if not isinstance(value, str):
            raise InvalidMissionSessionIdError(
                "Mission session ID is invalid",
            )
        if not value or value != value.strip():
            raise InvalidMissionSessionIdError(
                "Mission session ID is invalid",
                session_id=value if isinstance(value, str) else None,
            )
        if any(ch in value for ch in ("/", "\\", "%")):
            raise InvalidMissionSessionIdError(
                "Mission session ID is invalid",
                session_id=value,
            )
        if value in (".", "..") or ".." in value:
            raise InvalidMissionSessionIdError(
                "Mission session ID is invalid",
                session_id=value,
            )
        try:
            parsed = uuid.UUID(value)
        except (ValueError, AttributeError, TypeError) as exc:
            raise InvalidMissionSessionIdError(
                "Mission session ID is invalid",
                session_id=value,
            ) from exc
        canonical = str(parsed)
        if value != canonical:
            raise InvalidMissionSessionIdError(
                "Mission session ID is invalid",
                session_id=value,
            )
        return canonical

    # resolve session directory and prove containment under the sessions root
    def _session_dir(self, session_id: str) -> Path:
        canonical = self._canonical_session_id(session_id)
        candidate = self._sessions_root / canonical
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self._sessions_root):
            raise MissionSessionCorruptError(
                "Mission session path escapes sessions root",
                session_id=canonical,
            )
        return resolved

    # resolve session.json and enforce file containment under the session dir
    def _session_json_path(self, session_id: str) -> Path:
        session_dir = self._session_dir(session_id)
        candidate = session_dir / _SESSION_FILENAME
        if candidate.is_symlink():
            resolved = candidate.resolve()
            if not resolved.is_relative_to(session_dir):
                raise MissionSessionCorruptError(
                    "Mission session artifact escapes session directory",
                    session_id=session_id,
                )
            if not resolved.is_file() or resolved.is_symlink():
                raise MissionSessionCorruptError(
                    "Mission session artifact is corrupt",
                    session_id=session_id,
                )
            return resolved
        resolved = candidate.resolve()
        if not resolved.is_relative_to(session_dir):
            raise MissionSessionCorruptError(
                "Mission session path escapes sessions root",
                session_id=session_id,
            )
        return resolved

    # remove empty session dir created during failed create_session
    def _cleanup_new_session_dir(self, session_dir: Path) -> None:
        try:
            for child in session_dir.iterdir():
                if child.name.endswith(".tmp") and child.is_file():
                    child.unlink(missing_ok=True)
            session_dir.rmdir()
        except OSError as exc:
            logger.warning(
                "session_create_cleanup_failed session_dir_name=%s err=%s",
                session_dir.name,
                type(exc).__name__,
            )

    # create a new session record; never overwrite an existing directory
    def create_session(self, session: MissionSession) -> MissionSession:
        canonical = self._canonical_session_id(session.session_id)
        if session.session_id != canonical:
            raise InvalidMissionSessionIdError(
                "Mission session ID is invalid",
                session_id=session.session_id,
            )

        session_dir = self._sessions_root / canonical
        created_dir = False
        try:
            session_dir.mkdir(exist_ok=False)
            created_dir = True
            payload = session.model_dump(mode="json")
            dest = session_dir / _SESSION_FILENAME
            write_json_atomic(dest, payload)
        except FileExistsError as exc:
            raise MissionSessionAlreadyExistsError(
                "Mission session already exists",
                session_id=canonical,
            ) from exc
        except ArtifactStorageError as exc:
            if created_dir:
                self._cleanup_new_session_dir(session_dir)
            logger.error(
                "session_storage_failure op=create session_id=%s code=%s",
                canonical,
                "MISSION_SESSION_STORAGE_ERROR",
            )
            raise MissionSessionStorageError(
                "Failed to create mission session",
                session_id=canonical,
            ) from exc
        except OSError as exc:
            if created_dir:
                self._cleanup_new_session_dir(session_dir)
            logger.error(
                "session_storage_failure op=create session_id=%s",
                canonical,
            )
            raise MissionSessionStorageError(
                "Failed to create mission session",
                session_id=canonical,
            ) from exc
        except Exception:
            if created_dir:
                self._cleanup_new_session_dir(session_dir)
            raise

        logger.info(
            "session_created session_id=%s status=%s",
            canonical,
            session.status.value,
        )
        return self.read_session(canonical)

    # read and validate the authoritative session.json
    def read_session(self, session_id: str) -> MissionSession:
        canonical = self._canonical_session_id(session_id)
        try:
            session_dir = self._session_dir(canonical)
        except MissionSessionCorruptError:
            raise
        except InvalidMissionSessionIdError:
            raise

        if not session_dir.exists() or not session_dir.is_dir():
            raise MissionSessionNotFoundError(
                "Mission session not found",
                session_id=canonical,
            )

        try:
            json_path = self._session_json_path(canonical)
        except MissionSessionCorruptError as exc:
            logger.error(
                "session_corrupt session_id=%s code=%s",
                canonical,
                exc.code.value,
            )
            raise

        if not json_path.exists():
            raise MissionSessionNotFoundError(
                "Mission session not found",
                session_id=canonical,
            )
        if json_path.is_dir():
            logger.error("session_corrupt session_id=%s reason=json_is_dir", canonical)
            raise MissionSessionCorruptError(
                "Mission session artifact is corrupt",
                session_id=canonical,
            )
        if not json_path.is_file():
            raise MissionSessionNotFoundError(
                "Mission session not found",
                session_id=canonical,
            )

        try:
            raw = json_path.read_bytes()
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            logger.error("session_corrupt session_id=%s reason=utf8", canonical)
            raise MissionSessionCorruptError(
                "Mission session artifact is corrupt",
                session_id=canonical,
            ) from exc
        except OSError as exc:
            logger.error("session_storage_failure op=read session_id=%s", canonical)
            raise MissionSessionStorageError(
                "Failed to read mission session",
                session_id=canonical,
            ) from exc

        try:
            session = MissionSession.model_validate_json(text)
        except ValidationError as exc:
            logger.error("session_corrupt session_id=%s reason=schema", canonical)
            raise MissionSessionCorruptError(
                "Mission session artifact is corrupt",
                session_id=canonical,
            ) from exc
        except ValueError as exc:
            logger.error("session_corrupt session_id=%s reason=json", canonical)
            raise MissionSessionCorruptError(
                "Mission session artifact is corrupt",
                session_id=canonical,
            ) from exc

        if session.session_id != canonical:
            logger.error(
                "session_corrupt session_id=%s reason=id_mismatch",
                canonical,
            )
            raise MissionSessionCorruptError(
                "Mission session artifact is corrupt",
                session_id=canonical,
            )

        logger.debug(
            "session_read session_id=%s status=%s",
            canonical,
            session.status.value,
        )
        return session

    # atomically replace an existing session with optional compare guards
    def replace_session(
        self,
        session: MissionSession,
        *,
        expected_status: (
            MissionSessionStatus | Collection[MissionSessionStatus] | None
        ) = None,
        expected_updated_at: datetime | None = None,
    ) -> MissionSession:
        canonical = self._canonical_session_id(session.session_id)
        if session.session_id != canonical:
            raise InvalidMissionSessionIdError(
                "Mission session ID is invalid",
                session_id=session.session_id,
            )

        current = self.read_session(canonical)
        if session.session_id != current.session_id:
            raise MissionSessionConflictError(
                "Mission session ID mismatch",
                session_id=canonical,
            )

        if expected_status is not None:
            if isinstance(expected_status, MissionSessionStatus):
                allowed: set[MissionSessionStatus] = {expected_status}
            else:
                allowed = set(expected_status)
            if current.status not in allowed:
                logger.info(
                    "session_replace_conflict session_id=%s "
                    "expected_status=%s actual_status=%s code=%s",
                    canonical,
                    sorted(s.value for s in allowed),
                    current.status.value,
                    "MISSION_STATE_CONFLICT",
                )
                raise MissionSessionConflictError(
                    "Mission session state conflict",
                    session_id=canonical,
                )

        if expected_updated_at is not None:
            if current.updated_at != expected_updated_at:
                logger.info(
                    "session_replace_conflict session_id=%s "
                    "reason=stale_updated_at code=%s",
                    canonical,
                    "MISSION_STATE_CONFLICT",
                )
                raise MissionSessionConflictError(
                    "Mission session state conflict",
                    session_id=canonical,
                )

        json_path = self._session_json_path(canonical)
        old_status = current.status
        try:
            payload = session.model_dump(mode="json")
            write_json_atomic(json_path, payload)
        except ArtifactStorageError as exc:
            logger.error(
                "session_storage_failure op=replace session_id=%s",
                canonical,
            )
            raise MissionSessionStorageError(
                "Failed to replace mission session",
                session_id=canonical,
            ) from exc
        except OSError as exc:
            logger.error(
                "session_storage_failure op=replace session_id=%s",
                canonical,
            )
            raise MissionSessionStorageError(
                "Failed to replace mission session",
                session_id=canonical,
            ) from exc

        logger.info(
            "session_replaced session_id=%s old_status=%s new_status=%s",
            canonical,
            old_status.value,
            session.status.value,
        )
        return self.read_session(canonical)

    # true only for a contained session directory with a regular session.json
    def session_exists(self, session_id: str) -> bool:
        canonical = self._canonical_session_id(session_id)
        session_dir = self._sessions_root / canonical
        try:
            resolved_dir = session_dir.resolve()
        except OSError:
            return False
        if not resolved_dir.is_relative_to(self._sessions_root):
            return False
        if not resolved_dir.is_dir():
            return False
        json_path = resolved_dir / _SESSION_FILENAME
        if json_path.is_symlink():
            try:
                target = json_path.resolve()
            except OSError:
                return False
            return target.is_relative_to(resolved_dir) and target.is_file()
        return json_path.is_file()

    # return sorted canonical UUID session directory names only
    def list_session_ids(self) -> tuple[str, ...]:
        try:
            entries = list(self._sessions_root.iterdir())
        except OSError as exc:
            logger.error("session_list_failed")
            raise MissionSessionStorageError(
                "Failed to enumerate mission sessions",
            ) from exc

        accepted: list[str] = []
        for entry in entries:
            name = entry.name
            try:
                parsed = uuid.UUID(name)
            except (ValueError, AttributeError, TypeError):
                continue
            canonical = str(parsed)
            if name != canonical:
                continue
            try:
                if entry.is_symlink():
                    continue
                if not entry.is_dir():
                    continue
            except OSError:
                continue
            accepted.append(canonical)

        return tuple(sorted(accepted))

    # per-session asyncio lock for in-process transition serialization
    @asynccontextmanager
    async def lock_session(self, session_id: str) -> AsyncIterator[None]:
        canonical = self._canonical_session_id(session_id)
        lock = self._locks.setdefault(canonical, asyncio.Lock())
        async with lock:
            yield
