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
