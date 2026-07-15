# load and validate Phase 1 settings
# resolve paths against backend package root, not CWD
from __future__ import annotations

import math
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

_SUPPORTED_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


# resolve a configured path against backend_root when relative
def resolve_against_backend(raw: Path | str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path.resolve()
    return (BACKEND_ROOT / path).resolve()


# create runs dir if needed and verify writability with a temp probe
def ensure_writable_runs_dir(runs_dir: Path) -> None:
    if runs_dir.exists() and runs_dir.is_file():
        raise ValueError(f"ARES_RUNS_DIR exists as a file: {runs_dir}")
    runs_dir.mkdir(parents=True, exist_ok=True)
    if not runs_dir.is_dir():
        raise ValueError(f"ARES_RUNS_DIR is not a directory: {runs_dir}")

    probe = runs_dir / f".ares_write_probe_{uuid.uuid4().hex}"
    try:
        probe.write_text("ok", encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"ARES_RUNS_DIR is not writable: {runs_dir}") from exc
    finally:
        probe.unlink(missing_ok=True)


# path is under project_root (resolved containment)
def _is_under_project_root(candidate: Path, project_root: Path) -> bool:
    try:
        candidate.relative_to(project_root)
        return True
    except ValueError:
        return False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ARES_",
        env_file=".env",
        env_file_encoding="utf-8",
        frozen=True,
        extra="ignore",
    )

    project_root: Path
    sim_binary: Path
    scenario_dir: Path
    runs_dir: Path
    sim_timeout_seconds: float = Field(default=30.0)
    max_concurrent_runs: int = Field(default=2)
    log_level: str = Field(default="INFO")

    @field_validator("sim_timeout_seconds", mode="before")
    @classmethod
    def _validate_timeout(cls, value: Any) -> float:
        if isinstance(value, bool):
            raise ValueError("ARES_SIM_TIMEOUT_SECONDS must be a finite number > 0")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("ARES_SIM_TIMEOUT_SECONDS must be a finite number > 0") from exc
        if not math.isfinite(number) or number <= 0:
            raise ValueError("ARES_SIM_TIMEOUT_SECONDS must be a finite number > 0")
        return number

    @field_validator("max_concurrent_runs", mode="before")
    @classmethod
    def _validate_concurrency(cls, value: Any) -> int:
        if isinstance(value, bool):
            raise ValueError("ARES_MAX_CONCURRENT_RUNS must be a strict integer > 0")
        if isinstance(value, str):
            text = value.strip()
            if not text or any(ch in text for ch in ".eE"):
                raise ValueError("ARES_MAX_CONCURRENT_RUNS must be a strict integer > 0")
            try:
                value = int(text, 10)
            except ValueError as exc:
                raise ValueError(
                    "ARES_MAX_CONCURRENT_RUNS must be a strict integer > 0"
                ) from exc
        if type(value) is not int:
            raise ValueError("ARES_MAX_CONCURRENT_RUNS must be a strict integer > 0")
        if value <= 0:
            raise ValueError("ARES_MAX_CONCURRENT_RUNS must be a strict integer > 0")
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _validate_log_level(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("ARES_LOG_LEVEL must be a supported logging level")
        normalized = value.strip().upper()
        if normalized not in _SUPPORTED_LOG_LEVELS:
            raise ValueError("ARES_LOG_LEVEL must be a supported logging level")
        return normalized

    @model_validator(mode="after")
    def _resolve_and_validate_paths(self) -> Self:
        project_root = resolve_against_backend(self.project_root)
        sim_binary = resolve_against_backend(self.sim_binary)
        scenario_dir = resolve_against_backend(self.scenario_dir)
        runs_dir = resolve_against_backend(self.runs_dir)

        if not project_root.exists() or not project_root.is_dir():
            raise ValueError(f"ARES_PROJECT_ROOT must be an existing directory: {project_root}")

        if not sim_binary.exists() or not sim_binary.is_file():
            raise ValueError(f"ARES_SIM_BINARY must be an existing regular file: {sim_binary}")

        if not scenario_dir.exists() or not scenario_dir.is_dir():
            raise ValueError(f"ARES_SCENARIO_DIR must be an existing directory: {scenario_dir}")

        if not _is_under_project_root(scenario_dir, project_root):
            raise ValueError(
                "ARES_SCENARIO_DIR must be contained in ARES_PROJECT_ROOT: "
                f"{scenario_dir} not under {project_root}"
            )

        ensure_writable_runs_dir(runs_dir)

        object.__setattr__(self, "project_root", project_root)
        object.__setattr__(self, "sim_binary", sim_binary)
        object.__setattr__(self, "scenario_dir", scenario_dir)
        object.__setattr__(self, "runs_dir", runs_dir)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
