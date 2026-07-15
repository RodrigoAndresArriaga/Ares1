# typed domain errors for registry and artifact store
# HTTP handlers deferred to Section 15
from __future__ import annotations

from app.schemas.api import ErrorCode


class AresBackendError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode,
        run_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.run_id = run_id


class ScenarioNotFoundError(AresBackendError):
    def __init__(
        self,
        message: str = "Scenario not found",
        *,
        scenario_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.SCENARIO_NOT_FOUND,
            run_id=run_id,
        )
        self.scenario_id = scenario_id


class ArtifactStorageError(AresBackendError):
    def __init__(
        self,
        message: str = "Artifact storage failed",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.ARTIFACT_STORAGE_ERROR,
            run_id=run_id,
        )
