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
    ErrorCode.RUN_NOT_FOUND: 404,
    ErrorCode.RUN_ID_INVALID: 400,
    ErrorCode.RUN_RESULT_NOT_FOUND: 404,
    ErrorCode.RUN_RESULT_CORRUPT: 500,
    ErrorCode.RUN_METADATA_NOT_FOUND: 404,
    ErrorCode.RUN_METADATA_CORRUPT: 500,
    ErrorCode.RUN_ARTIFACT_STORAGE_ERROR: 500,
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
