# async C++ simulator subprocess client
# sole production launcher of the frozen executable
from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import (
    SimulatorExecutionError,
    SimulatorOutputMissingError,
    SimulatorOutputParseError,
    SimulatorOutputValidationError,
    SimulatorTimeoutError,
    SimulatorUnavailableError,
)
from app.schemas.result import SimulationResult
from app.services.run_store import RunWorkspace

SpawnCallable = Callable[..., Awaitable[asyncio.subprocess.Process]]


@dataclass(frozen=True, slots=True)
class ProcessEvidence:
    exit_code: int | None
    stdout_bytes: bytes
    stderr_bytes: bytes
    stdout_text: str
    stderr_text: str
    duration_ms: int
    timed_out: bool


@dataclass(frozen=True, slots=True)
class SimulatorExecutionResult:
    result: SimulationResult
    process: ProcessEvidence


# decode pipe bytes for log text without destroying raw evidence
def _decode_pipe_text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


# truncate monotonic seconds to nonnegative integer milliseconds
def _duration_ms(start: float, end: float) -> int:
    return max(0, int((end - start) * 1000))


# true when candidate resolves inside workspace root
def _is_under_root(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


class SimulatorClient:
    def __init__(
        self,
        settings: Settings,
        *,
        _spawn: SpawnCallable | None = None,
    ) -> None:
        self._binary = settings.sim_binary
        self._timeout_seconds = settings.sim_timeout_seconds
        self._max_concurrent = settings.max_concurrent_runs
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_runs)
        self._spawn: SpawnCallable = (
            _spawn if _spawn is not None else asyncio.create_subprocess_exec
        )

    async def run(self, workspace: RunWorkspace) -> SimulatorExecutionResult:
        self._ensure_binary_available(workspace.run_id)
        self._validate_workspace_preconditions(workspace)
        command = self._build_command(workspace)

        async with self._semaphore:
            start = time.monotonic()
            process: asyncio.subprocess.Process | None = None
            stdout_bytes = b""
            stderr_bytes = b""
            try:
                try:
                    process = await self._spawn(
                        *command,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                except FileNotFoundError as exc:
                    raise SimulatorUnavailableError(
                        run_id=workspace.run_id,
                    ) from exc
                except PermissionError as exc:
                    raise SimulatorUnavailableError(
                        run_id=workspace.run_id,
                    ) from exc
                except OSError as exc:
                    raise SimulatorUnavailableError(
                        run_id=workspace.run_id,
                    ) from exc

                try:
                    stdout_bytes, stderr_bytes = await asyncio.wait_for(
                        process.communicate(),
                        timeout=self._timeout_seconds,
                    )
                except asyncio.TimeoutError as exc:
                    stdout_bytes, stderr_bytes = await self._kill_and_drain(
                        process,
                    )
                    end = time.monotonic()
                    evidence = self._make_evidence(
                        exit_code=process.returncode,
                        stdout_bytes=stdout_bytes,
                        stderr_bytes=stderr_bytes,
                        duration_ms=_duration_ms(start, end),
                        timed_out=True,
                    )
                    raise SimulatorTimeoutError(
                        run_id=workspace.run_id,
                        process_evidence=evidence,
                    ) from exc
            except asyncio.CancelledError:
                if process is not None and process.returncode is None:
                    await self._kill_and_drain(process)
                raise

            assert process is not None
            end = time.monotonic()
            evidence = self._make_evidence(
                exit_code=process.returncode,
                stdout_bytes=stdout_bytes,
                stderr_bytes=stderr_bytes,
                duration_ms=_duration_ms(start, end),
                timed_out=False,
            )

            if process.returncode != 0:
                raise SimulatorExecutionError(
                    run_id=workspace.run_id,
                    process_evidence=evidence,
                )

            result = self._load_and_validate_result(workspace, evidence)
            return SimulatorExecutionResult(result=result, process=evidence)

    # build exact argument vector from trusted workspace paths
    def _build_command(self, workspace: RunWorkspace) -> list[str]:
        mode = self._read_workspace_mode(workspace)
        scenario_path = workspace.scenario_path
        result_path = workspace.result_path
        root = workspace.root

        if not _is_under_root(root, scenario_path):
            raise SimulatorExecutionError(run_id=workspace.run_id)
        if not _is_under_root(root, result_path):
            raise SimulatorExecutionError(run_id=workspace.run_id)

        command = [
            str(self._binary),
            "--scenario",
            str(scenario_path),
        ]
        if mode == "plan":
            if not workspace.plan_path.is_file():
                raise SimulatorExecutionError(run_id=workspace.run_id)
            if not _is_under_root(root, workspace.plan_path):
                raise SimulatorExecutionError(run_id=workspace.run_id)
            command.extend(["--plan", str(workspace.plan_path)])
        command.extend(["--output", str(result_path)])
        return command

    def _read_workspace_mode(self, workspace: RunWorkspace) -> str:
        try:
            raw = workspace.metadata_path.read_text(encoding="utf-8")
            payload: dict[str, Any] = json.loads(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SimulatorExecutionError(run_id=workspace.run_id) from exc
        mode = payload.get("mode")
        if mode not in ("baseline", "plan"):
            raise SimulatorExecutionError(run_id=workspace.run_id)
        return str(mode)

    def _ensure_binary_available(self, run_id: str) -> None:
        binary = self._binary
        if not binary.exists() or not binary.is_file():
            raise SimulatorUnavailableError(run_id=run_id)

    def _validate_workspace_preconditions(self, workspace: RunWorkspace) -> None:
        run_id = workspace.run_id
        if not workspace.root.exists() or not workspace.root.is_dir():
            raise SimulatorExecutionError(run_id=run_id)
        if not workspace.scenario_path.is_file():
            raise SimulatorExecutionError(run_id=run_id)
        if not _is_under_root(workspace.root, workspace.result_path):
            raise SimulatorExecutionError(run_id=run_id)
        if workspace.result_path.exists():
            raise SimulatorExecutionError(run_id=run_id)

    def _make_evidence(
        self,
        *,
        exit_code: int | None,
        stdout_bytes: bytes,
        stderr_bytes: bytes,
        duration_ms: int,
        timed_out: bool,
    ) -> ProcessEvidence:
        return ProcessEvidence(
            exit_code=exit_code,
            stdout_bytes=stdout_bytes,
            stderr_bytes=stderr_bytes,
            stdout_text=_decode_pipe_text(stdout_bytes),
            stderr_text=_decode_pipe_text(stderr_bytes),
            duration_ms=duration_ms,
            timed_out=timed_out,
        )

    async def _kill_and_drain(
        self,
        process: asyncio.subprocess.Process,
    ) -> tuple[bytes, bytes]:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            except OSError:
                pass
        try:
            stdout_bytes, stderr_bytes = await process.communicate()
        except (OSError, ValueError):
            stdout_bytes = b""
            stderr_bytes = b""
            if process.returncode is None:
                try:
                    await process.wait()
                except OSError:
                    pass
        return stdout_bytes, stderr_bytes

    def _load_and_validate_result(
        self,
        workspace: RunWorkspace,
        evidence: ProcessEvidence,
    ) -> SimulationResult:
        run_id = workspace.run_id
        result_path = workspace.result_path

        if not result_path.exists() or not result_path.is_file():
            raise SimulatorOutputMissingError(
                run_id=run_id,
                process_evidence=evidence,
            )
        if not _is_under_root(workspace.root, result_path):
            raise SimulatorOutputMissingError(
                run_id=run_id,
                process_evidence=evidence,
            )
        try:
            raw = result_path.read_bytes()
        except OSError as exc:
            raise SimulatorOutputMissingError(
                run_id=run_id,
                process_evidence=evidence,
            ) from exc
        if len(raw) == 0:
            raise SimulatorOutputMissingError(
                run_id=run_id,
                process_evidence=evidence,
            )

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SimulatorOutputParseError(
                run_id=run_id,
                process_evidence=evidence,
            ) from exc

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SimulatorOutputParseError(
                run_id=run_id,
                process_evidence=evidence,
            ) from exc

        try:
            return SimulationResult.model_validate(payload)
        except ValidationError as exc:
            raise SimulatorOutputValidationError(
                run_id=run_id,
                process_evidence=evidence,
            ) from exc
