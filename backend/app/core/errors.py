# typed domain errors and FastAPI HTTP exception handlers
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Self

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.schemas.api import ErrorCode, ErrorResponse

logger = logging.getLogger("ares.errors")

ARES_HTTP_STATUS_BY_CODE: Mapping[ErrorCode, int] = {
    ErrorCode.SCENARIO_NOT_FOUND: 404,
    ErrorCode.SIMULATOR_UNAVAILABLE: 503,
    ErrorCode.SIMULATOR_TIMEOUT: 504,
    ErrorCode.SIMULATOR_EXECUTION_FAILED: 502,
    ErrorCode.SIMULATOR_OUTPUT_MISSING: 502,
    ErrorCode.SIMULATOR_OUTPUT_INVALID_JSON: 502,
    ErrorCode.SIMULATOR_OUTPUT_CONTRACT_ERROR: 502,
    ErrorCode.ARTIFACT_STORAGE_ERROR: 500,
    ErrorCode.MISSION_SESSION_NOT_FOUND: 404,
    ErrorCode.MISSION_SESSION_ALREADY_EXISTS: 409,
    ErrorCode.MISSION_SESSION_CORRUPT: 500,
    ErrorCode.MISSION_SESSION_STORAGE_ERROR: 500,
    ErrorCode.MISSION_STATE_CONFLICT: 409,
    ErrorCode.MISSION_SESSION_ID_INVALID: 400,
    ErrorCode.BASELINE_TELEMETRY_EMPTY: 500,
    ErrorCode.REPLAY_INTERVAL_INVALID: 422,
    ErrorCode.REPLAY_NOT_STARTED: 409,
    ErrorCode.REPLAY_EVENT_ID_INVALID: 400,
    ErrorCode.REPLAY_STREAM_LIMIT: 503,
    ErrorCode.BASELINE_RESULT_UNAVAILABLE: 500,
    ErrorCode.BASELINE_RESULT_MISMATCH: 500,
    ErrorCode.MISSION_TRIGGER_FAILED: 500,
    ErrorCode.MISSION_TRIGGER_CANCELLED: 500,
    ErrorCode.MISSION_TRIGGER_INTERRUPTED: 500,
    ErrorCode.RUN_NOT_FOUND: 404,
    ErrorCode.RUN_ID_INVALID: 400,
    ErrorCode.RUN_RESULT_NOT_FOUND: 404,
    ErrorCode.RUN_RESULT_CORRUPT: 500,
    ErrorCode.RUN_METADATA_NOT_FOUND: 404,
    ErrorCode.RUN_METADATA_CORRUPT: 500,
    ErrorCode.RUN_ARTIFACT_STORAGE_ERROR: 500,
    ErrorCode.PROCEDURE_CORPUS_INVALID: 400,
    ErrorCode.PROCEDURE_MANIFEST_INVALID: 400,
    ErrorCode.PROCEDURE_MANUAL_NOT_FOUND: 404,
    ErrorCode.PROCEDURE_MANUAL_SECURITY_ERROR: 400,
    ErrorCode.PROCEDURE_MANUAL_PARSE_ERROR: 400,
    ErrorCode.EMBEDDING_PROVIDER_ERROR: 502,
    ErrorCode.EMBEDDING_VALIDATION_ERROR: 400,
    ErrorCode.EMBEDDING_MODEL_MISMATCH: 400,
    ErrorCode.RETRIEVAL_QUERY_INVALID: 400,
    ErrorCode.RETRIEVAL_INDEX_NOT_FOUND: 503,
    ErrorCode.RETRIEVAL_INDEX_CORRUPT: 500,
    ErrorCode.RETRIEVAL_INDEX_STALE: 503,
    ErrorCode.RETRIEVAL_INDEX_UNAVAILABLE: 503,
    ErrorCode.NVIDIA_NIM_AUTH_ERROR: 500,
    ErrorCode.NVIDIA_NIM_RATE_LIMITED: 503,
    ErrorCode.NVIDIA_NIM_TIMEOUT: 504,
    ErrorCode.NVIDIA_NIM_UNAVAILABLE: 502,
    ErrorCode.NVIDIA_NIM_RESPONSE_INVALID: 502,
    ErrorCode.RERANK_RESPONSE_INVALID: 502,
    ErrorCode.PLANNER_CONTEXT_INVALID: 500,
    ErrorCode.PLANNER_PROMPT_TOO_LARGE: 500,
    ErrorCode.PLANNER_OUTPUT_INVALID: 502,
    ErrorCode.PLANNER_MODEL_MISMATCH: 502,
    ErrorCode.PLANNER_RESPONSE_INCOMPLETE: 502,
    ErrorCode.PLANNING_NOT_AVAILABLE: 409,
    ErrorCode.PLANNING_CONTEXT_MISMATCH: 500,
    ErrorCode.PLANNING_IN_PROGRESS: 409,
    ErrorCode.PLANNER_CANDIDATE_UNGROUNDED: 502,
    ErrorCode.PLANNING_ATTEMPT_NOT_FOUND: 404,
    ErrorCode.PLANNING_ATTEMPT_ALREADY_EXISTS: 409,
    ErrorCode.PLANNING_ATTEMPT_CORRUPT: 500,
    ErrorCode.PLANNING_ATTEMPT_STORAGE_ERROR: 500,
    ErrorCode.PLANNING_ATTEMPT_ID_INVALID: 400,
    ErrorCode.MISSION_RETRIEVAL_QUERY_TOO_LARGE: 500,
    ErrorCode.INTERNAL_SERVER_ERROR: 500,
}


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

    # return same error category with run_id attached
    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        raise TypeError(
            f"{type(self).__name__} must override with_run_id",
        )


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

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            scenario_id=self.scenario_id,
            run_id=run_id,
        )


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

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class MissionSessionNotFoundError(AresBackendError):
    def __init__(
        self,
        message: str = "Mission session not found",
        *,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.MISSION_SESSION_NOT_FOUND,
            run_id=run_id,
        )
        self.session_id = session_id

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            session_id=self.session_id,
            run_id=run_id,
        )


class MissionSessionAlreadyExistsError(AresBackendError):
    def __init__(
        self,
        message: str = "Mission session already exists",
        *,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.MISSION_SESSION_ALREADY_EXISTS,
            run_id=run_id,
        )
        self.session_id = session_id

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            session_id=self.session_id,
            run_id=run_id,
        )


class MissionSessionCorruptError(AresBackendError):
    def __init__(
        self,
        message: str = "Mission session artifact is corrupt",
        *,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.MISSION_SESSION_CORRUPT,
            run_id=run_id,
        )
        self.session_id = session_id

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            session_id=self.session_id,
            run_id=run_id,
        )


class MissionSessionStorageError(AresBackendError):
    def __init__(
        self,
        message: str = "Mission session storage failed",
        *,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.MISSION_SESSION_STORAGE_ERROR,
            run_id=run_id,
        )
        self.session_id = session_id

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            session_id=self.session_id,
            run_id=run_id,
        )


class MissionSessionConflictError(AresBackendError):
    def __init__(
        self,
        message: str = "Mission session state conflict",
        *,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.MISSION_STATE_CONFLICT,
            run_id=run_id,
        )
        self.session_id = session_id

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            session_id=self.session_id,
            run_id=run_id,
        )


class BaselineTelemetryEmptyError(AresBackendError):
    def __init__(
        self,
        message: str = "Baseline simulation returned empty telemetry history",
        *,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.BASELINE_TELEMETRY_EMPTY,
            run_id=run_id,
        )
        self.session_id = session_id

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            session_id=self.session_id,
            run_id=run_id,
        )


class ReplayIntervalInvalidError(AresBackendError):
    def __init__(
        self,
        message: str = "Replay interval is outside configured bounds",
        *,
        provided_interval_ms: int | None = None,
        min_interval_ms: int | None = None,
        max_interval_ms: int | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.REPLAY_INTERVAL_INVALID,
            run_id=run_id,
        )
        self.provided_interval_ms = provided_interval_ms
        self.min_interval_ms = min_interval_ms
        self.max_interval_ms = max_interval_ms
        self.session_id = session_id

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            provided_interval_ms=self.provided_interval_ms,
            min_interval_ms=self.min_interval_ms,
            max_interval_ms=self.max_interval_ms,
            session_id=self.session_id,
            run_id=run_id,
        )


class ReplayNotStartedError(AresBackendError):
    def __init__(
        self,
        message: str = "Mission replay has not started",
        *,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.REPLAY_NOT_STARTED,
            run_id=run_id,
        )
        self.session_id = session_id

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            session_id=self.session_id,
            run_id=run_id,
        )


class ReplayEventIdInvalidError(AresBackendError):
    def __init__(
        self,
        message: str = "Replay Last-Event-ID is invalid",
        *,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.REPLAY_EVENT_ID_INVALID,
            run_id=run_id,
        )
        self.session_id = session_id

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            session_id=self.session_id,
            run_id=run_id,
        )


class ReplayStreamLimitError(AresBackendError):
    def __init__(
        self,
        message: str = "Maximum concurrent replay streams reached",
        *,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.REPLAY_STREAM_LIMIT,
            run_id=run_id,
        )
        self.session_id = session_id

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            session_id=self.session_id,
            run_id=run_id,
        )


class BaselineResultUnavailableError(AresBackendError):
    def __init__(
        self,
        message: str = "Baseline simulation result is unavailable",
        *,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.BASELINE_RESULT_UNAVAILABLE,
            run_id=run_id,
        )
        self.session_id = session_id

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            session_id=self.session_id,
            run_id=run_id,
        )


class BaselineResultMismatchError(AresBackendError):
    def __init__(
        self,
        message: str = "Baseline simulation result does not match mission session",
        *,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.BASELINE_RESULT_MISMATCH,
            run_id=run_id,
        )
        self.session_id = session_id

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            session_id=self.session_id,
            run_id=run_id,
        )


class InvalidMissionSessionIdError(AresBackendError):
    def __init__(
        self,
        message: str = "Mission session ID is invalid",
        *,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.MISSION_SESSION_ID_INVALID,
            run_id=run_id,
        )
        self.session_id = session_id

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            session_id=self.session_id,
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

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            run_id=run_id,
            process_evidence=self.process_evidence,
        )


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

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            run_id=run_id,
            process_evidence=self.process_evidence,
        )


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

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            run_id=run_id,
            process_evidence=self.process_evidence,
        )


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

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            run_id=run_id,
            process_evidence=self.process_evidence,
        )


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

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            run_id=run_id,
            process_evidence=self.process_evidence,
        )


class InvalidRunIdError(AresBackendError):
    def __init__(
        self,
        message: str = "Run ID is invalid",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.RUN_ID_INVALID,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class RunNotFoundError(AresBackendError):
    def __init__(
        self,
        message: str = "Run not found",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.RUN_NOT_FOUND,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class RunResultNotFoundError(AresBackendError):
    def __init__(
        self,
        message: str = "Run result artifact not found",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.RUN_RESULT_NOT_FOUND,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class RunResultCorruptError(AresBackendError):
    def __init__(
        self,
        message: str = "Run result artifact is corrupt",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.RUN_RESULT_CORRUPT,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class RunMetadataNotFoundError(AresBackendError):
    def __init__(
        self,
        message: str = "Run metadata artifact not found",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.RUN_METADATA_NOT_FOUND,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class RunMetadataCorruptError(AresBackendError):
    def __init__(
        self,
        message: str = "Run metadata artifact is corrupt",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.RUN_METADATA_CORRUPT,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class RunArtifactStorageError(AresBackendError):
    def __init__(
        self,
        message: str = "Run artifact storage failed",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.RUN_ARTIFACT_STORAGE_ERROR,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


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

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            run_id=run_id,
            process_evidence=self.process_evidence,
        )


class ProcedureCorpusInvalidError(AresBackendError):
    def __init__(
        self,
        message: str = "Procedure corpus is invalid",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.PROCEDURE_CORPUS_INVALID,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class ProcedureManifestInvalidError(AresBackendError):
    def __init__(
        self,
        message: str = "Procedure corpus manifest is invalid",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.PROCEDURE_MANIFEST_INVALID,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class ProcedureManualNotFoundError(AresBackendError):
    def __init__(
        self,
        message: str = "Procedure manual not found",
        *,
        filename: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.PROCEDURE_MANUAL_NOT_FOUND,
            run_id=run_id,
        )
        self.filename = filename

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            filename=self.filename,
            run_id=run_id,
        )


class ProcedureManualSecurityError(AresBackendError):
    def __init__(
        self,
        message: str = "Procedure manual path failed security checks",
        *,
        filename: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.PROCEDURE_MANUAL_SECURITY_ERROR,
            run_id=run_id,
        )
        self.filename = filename

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            filename=self.filename,
            run_id=run_id,
        )


class ProcedureManualParseError(AresBackendError):
    def __init__(
        self,
        message: str = "Procedure manual could not be parsed",
        *,
        filename: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.PROCEDURE_MANUAL_PARSE_ERROR,
            run_id=run_id,
        )
        self.filename = filename

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            filename=self.filename,
            run_id=run_id,
        )


class EmbeddingProviderError(AresBackendError):
    def __init__(
        self,
        message: str = "Embedding provider failed",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.EMBEDDING_PROVIDER_ERROR,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class EmbeddingValidationError(AresBackendError):
    def __init__(
        self,
        message: str = "Embedding validation failed",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.EMBEDDING_VALIDATION_ERROR,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class EmbeddingModelMismatchError(AresBackendError):
    def __init__(
        self,
        message: str = "Embedding model does not match index",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.EMBEDDING_MODEL_MISMATCH,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class RetrievalQueryInvalidError(AresBackendError):
    def __init__(
        self,
        message: str = "Retrieval query is invalid",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.RETRIEVAL_QUERY_INVALID,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class RetrievalIndexNotFoundError(AresBackendError):
    def __init__(
        self,
        message: str = "Procedure embedding index not found",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.RETRIEVAL_INDEX_NOT_FOUND,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class RetrievalIndexCorruptError(AresBackendError):
    def __init__(
        self,
        message: str = "Procedure embedding index is corrupt",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.RETRIEVAL_INDEX_CORRUPT,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class RetrievalIndexStaleError(AresBackendError):
    def __init__(
        self,
        message: str = "Procedure embedding index is stale",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.RETRIEVAL_INDEX_STALE,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class RetrievalIndexUnavailableError(AresBackendError):
    def __init__(
        self,
        message: str = "Procedure retrieval index is unavailable",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.RETRIEVAL_INDEX_UNAVAILABLE,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class NvidiaNimAuthError(AresBackendError):
    def __init__(
        self,
        message: str = "NVIDIA NIM authentication failed",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.NVIDIA_NIM_AUTH_ERROR,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class NvidiaNimRateLimitedError(AresBackendError):
    def __init__(
        self,
        message: str = "NVIDIA NIM rate limited",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.NVIDIA_NIM_RATE_LIMITED,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class NvidiaNimTimeoutError(AresBackendError):
    def __init__(
        self,
        message: str = "NVIDIA NIM request timed out",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.NVIDIA_NIM_TIMEOUT,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class NvidiaNimUnavailableError(AresBackendError):
    def __init__(
        self,
        message: str = "NVIDIA NIM service unavailable",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.NVIDIA_NIM_UNAVAILABLE,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class NvidiaNimResponseInvalidError(AresBackendError):
    def __init__(
        self,
        message: str = "NVIDIA NIM response is invalid",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.NVIDIA_NIM_RESPONSE_INVALID,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class RerankResponseInvalidError(AresBackendError):
    def __init__(
        self,
        message: str = "Rerank response is invalid",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.RERANK_RESPONSE_INVALID,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class PlannerContextInvalidError(AresBackendError):
    def __init__(
        self,
        message: str = "Planner mission context is invalid",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.PLANNER_CONTEXT_INVALID,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class PlannerPromptTooLargeError(AresBackendError):
    def __init__(
        self,
        message: str = "Planner prompt exceeds configured maximum size",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.PLANNER_PROMPT_TOO_LARGE,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class PlannerOutputInvalidError(AresBackendError):
    def __init__(
        self,
        message: str = "Planner model output is invalid",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.PLANNER_OUTPUT_INVALID,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class PlannerModelMismatchError(AresBackendError):
    def __init__(
        self,
        message: str = "Planner response model does not match configured model",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.PLANNER_MODEL_MISMATCH,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class PlannerResponseIncompleteError(AresBackendError):
    def __init__(
        self,
        message: str = "Planner response is incomplete",
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.PLANNER_RESPONSE_INCOMPLETE,
            run_id=run_id,
        )

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(self.message, run_id=run_id)


class PlanningNotAvailableError(AresBackendError):
    def __init__(
        self,
        message: str = "Mission planning is not available for this session state",
        *,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.PLANNING_NOT_AVAILABLE,
            run_id=run_id,
        )
        self.session_id = session_id

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            session_id=self.session_id,
            run_id=run_id,
        )


class PlanningContextMismatchError(AresBackendError):
    def __init__(
        self,
        message: str = "Planning context sources disagree",
        *,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.PLANNING_CONTEXT_MISMATCH,
            run_id=run_id,
        )
        self.session_id = session_id

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            session_id=self.session_id,
            run_id=run_id,
        )


class PlanningInProgressError(AresBackendError):
    def __init__(
        self,
        message: str = "Planning operation already in progress for this session",
        *,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.PLANNING_IN_PROGRESS,
            run_id=run_id,
        )
        self.session_id = session_id

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            session_id=self.session_id,
            run_id=run_id,
        )


class PlannerCandidateUngroundedError(AresBackendError):
    def __init__(
        self,
        message: str = "Planner candidate action lacks retrieved evidence support",
        *,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.PLANNER_CANDIDATE_UNGROUNDED,
            run_id=run_id,
        )
        self.session_id = session_id

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            session_id=self.session_id,
            run_id=run_id,
        )


class PlanningAttemptNotFoundError(AresBackendError):
    def __init__(
        self,
        message: str = "Planning attempt not found",
        *,
        attempt_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.PLANNING_ATTEMPT_NOT_FOUND,
            run_id=run_id,
        )
        self.attempt_id = attempt_id

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            attempt_id=self.attempt_id,
            run_id=run_id,
        )


class PlanningAttemptAlreadyExistsError(AresBackendError):
    def __init__(
        self,
        message: str = "Planning attempt already exists",
        *,
        attempt_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.PLANNING_ATTEMPT_ALREADY_EXISTS,
            run_id=run_id,
        )
        self.attempt_id = attempt_id

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            attempt_id=self.attempt_id,
            run_id=run_id,
        )


class PlanningAttemptCorruptError(AresBackendError):
    def __init__(
        self,
        message: str = "Planning attempt artifact is corrupt",
        *,
        attempt_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.PLANNING_ATTEMPT_CORRUPT,
            run_id=run_id,
        )
        self.attempt_id = attempt_id

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            attempt_id=self.attempt_id,
            run_id=run_id,
        )


class PlanningAttemptStorageError(AresBackendError):
    def __init__(
        self,
        message: str = "Planning attempt storage failed",
        *,
        attempt_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.PLANNING_ATTEMPT_STORAGE_ERROR,
            run_id=run_id,
        )
        self.attempt_id = attempt_id

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            attempt_id=self.attempt_id,
            run_id=run_id,
        )


class InvalidPlanningAttemptIdError(AresBackendError):
    def __init__(
        self,
        message: str = "Planning attempt ID is invalid",
        *,
        attempt_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.PLANNING_ATTEMPT_ID_INVALID,
            run_id=run_id,
        )
        self.attempt_id = attempt_id

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            attempt_id=self.attempt_id,
            run_id=run_id,
        )


class MissionRetrievalQueryTooLargeError(AresBackendError):
    def __init__(
        self,
        message: str = "Mission retrieval query exceeds configured maximum size",
        *,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.MISSION_RETRIEVAL_QUERY_TOO_LARGE,
            run_id=run_id,
        )
        self.session_id = session_id

    def with_run_id(self, run_id: str) -> Self:
        if self.run_id == run_id:
            return self
        return type(self)(
            self.message,
            session_id=self.session_id,
            run_id=run_id,
        )


# register centralized typed and unexpected exception handlers
def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AresBackendError)
    async def ares_backend_error_handler(
        request: Request,
        exc: AresBackendError,
    ) -> JSONResponse:
        status = ARES_HTTP_STATUS_BY_CODE.get(exc.code, 500)
        logger.warning(
            "ares_backend_error code=%s run_id=%s path=%s",
            exc.code.value,
            exc.run_id,
            request.url.path,
        )
        body = ErrorResponse(
            code=exc.code,
            message=exc.message,
            run_id=exc.run_id,
        )
        return JSONResponse(
            status_code=status,
            content=body.model_dump(mode="json"),
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.exception(
            "unexpected_error path=%s",
            request.url.path,
        )
        body = ErrorResponse(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="An unexpected server error occurred",
            run_id=None,
        )
        return JSONResponse(
            status_code=500,
            content=body.model_dump(mode="json"),
        )
