# typed domain errors for registry, artifact store, and simulator client
# HTTP handlers deferred to Section 15
from __future__ import annotations

from typing import Any

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


class SimulatorUnavailableError(AresBackendError):
    def __init__(
        self,
        message: str = "Simulator executable is unavailable",
        *,
        run_id: str | None = None,
        process_evidence: Any | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.SIMULATOR_UNAVAILABLE,
            run_id=run_id,
        )
        self.process_evidence = process_evidence


class SimulatorTimeoutError(AresBackendError):
    def __init__(
        self,
        message: str = "Simulator execution timed out",
        *,
        run_id: str | None = None,
        process_evidence: Any | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.SIMULATOR_TIMEOUT,
            run_id=run_id,
        )
        self.process_evidence = process_evidence


class SimulatorExecutionError(AresBackendError):
    def __init__(
        self,
        message: str = "Simulator process execution failed",
        *,
        run_id: str | None = None,
        process_evidence: Any | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.SIMULATOR_EXECUTION_FAILED,
            run_id=run_id,
        )
        self.process_evidence = process_evidence


class SimulatorOutputMissingError(AresBackendError):
    def __init__(
        self,
        message: str = "Simulator result output is missing",
        *,
        run_id: str | None = None,
        process_evidence: Any | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.SIMULATOR_OUTPUT_MISSING,
            run_id=run_id,
        )
        self.process_evidence = process_evidence


class SimulatorOutputParseError(AresBackendError):
    def __init__(
        self,
        message: str = "Simulator result output is not valid JSON",
        *,
        run_id: str | None = None,
        process_evidence: Any | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.SIMULATOR_OUTPUT_INVALID_JSON,
            run_id=run_id,
        )
        self.process_evidence = process_evidence


class SimulatorOutputValidationError(AresBackendError):
    def __init__(
        self,
        message: str = "Simulator result failed contract validation",
        *,
        run_id: str | None = None,
        process_evidence: Any | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.SIMULATOR_OUTPUT_CONTRACT_ERROR,
            run_id=run_id,
        )
        self.process_evidence = process_evidence
