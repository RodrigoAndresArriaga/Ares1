# load and validate Phase 1/3/4 settings
# resolve paths against backend package root, not CWD
from __future__ import annotations

import math
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

_SUPPORTED_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})

DEFAULT_NVIDIA_EMBED_MODEL_ID = "nvidia/llama-nemotron-embed-1b-v2"
DEFAULT_NVIDIA_RERANK_MODEL_ID = "nvidia/llama-nemotron-rerank-1b-v2"
DEFAULT_NVIDIA_PLANNER_MODEL_ID = "nvidia/llama-3.3-nemotron-super-49b-v1"
DEFAULT_NVIDIA_EMBED_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_NVIDIA_RERANK_BASE_URL = "https://ai.api.nvidia.com/v1"
DEFAULT_EMBED_DIMENSIONS = 2048


# resolve a configured path against backend_root when relative
def resolve_against_backend(raw: Path | str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path.resolve()
    return (BACKEND_ROOT / path).resolve()


# create dir if needed and verify writability with a temp probe
def ensure_writable_dir(path: Path, *, env_name: str) -> None:
    if path.exists() and path.is_file():
        raise ValueError(f"{env_name} exists as a file: {path}")
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise ValueError(f"{env_name} is not a directory: {path}")

    probe = path / f".ares_write_probe_{uuid.uuid4().hex}"
    try:
        probe.write_text("ok", encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"{env_name} is not writable: {path}") from exc
    finally:
        probe.unlink(missing_ok=True)


# create runs dir if needed and verify writability with a temp probe
def ensure_writable_runs_dir(runs_dir: Path) -> None:
    ensure_writable_dir(runs_dir, env_name="ARES_RUNS_DIR")


# path is under project_root (resolved containment)
def _is_under_project_root(candidate: Path, project_root: Path) -> bool:
    try:
        candidate.relative_to(project_root)
        return True
    except ValueError:
        return False


# strict positive integer from env/kwargs
def _positive_strict_int(value: Any, *, env_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{env_name} must be a strict integer > 0")
    if isinstance(value, str):
        text = value.strip()
        if not text or any(ch in text for ch in ".eE"):
            raise ValueError(f"{env_name} must be a strict integer > 0")
        try:
            value = int(text, 10)
        except ValueError as exc:
            raise ValueError(f"{env_name} must be a strict integer > 0") from exc
    if type(value) is not int:
        raise ValueError(f"{env_name} must be a strict integer > 0")
    if value <= 0:
        raise ValueError(f"{env_name} must be a strict integer > 0")
    return value


# non-negative strict integer from env/kwargs
def _non_negative_strict_int(value: Any, *, env_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{env_name} must be a strict integer >= 0")
    if isinstance(value, str):
        text = value.strip()
        if not text or any(ch in text for ch in ".eE"):
            raise ValueError(f"{env_name} must be a strict integer >= 0")
        try:
            value = int(text, 10)
        except ValueError as exc:
            raise ValueError(f"{env_name} must be a strict integer >= 0") from exc
    if type(value) is not int:
        raise ValueError(f"{env_name} must be a strict integer >= 0")
    if value < 0:
        raise ValueError(f"{env_name} must be a strict integer >= 0")
    return value


# finite float > 0 from env/kwargs
def _positive_finite_float(value: Any, *, env_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{env_name} must be a finite number > 0")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{env_name} must be a finite number > 0") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{env_name} must be a finite number > 0")
    return number


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
    sessions_dir: Path = Field(default=Path("data/sessions"))
    sim_timeout_seconds: float = Field(default=30.0)
    max_concurrent_runs: int = Field(default=2)
    replay_default_interval_ms: int = Field(default=250)
    replay_min_interval_ms: int = Field(default=25)
    replay_max_interval_ms: int = Field(default=60000)
    max_replay_streams: int = Field(default=20)
    sse_heartbeat_seconds: float = Field(default=15.0)
    log_level: str = Field(default="INFO")

    nvidia_api_key: SecretStr | None = Field(default=None)
    nvidia_embed_base_url: str = Field(default=DEFAULT_NVIDIA_EMBED_BASE_URL)
    nvidia_rerank_base_url: str = Field(default=DEFAULT_NVIDIA_RERANK_BASE_URL)
    nvidia_embed_model_id: str = Field(default=DEFAULT_NVIDIA_EMBED_MODEL_ID)
    nvidia_embed_model_revision: str | None = Field(default=None)
    nvidia_rerank_model_id: str = Field(default=DEFAULT_NVIDIA_RERANK_MODEL_ID)
    nvidia_rerank_model_revision: str | None = Field(default=None)
    nvidia_embed_dimensions: int = Field(default=DEFAULT_EMBED_DIMENSIONS)
    nvidia_request_timeout_seconds: float = Field(default=60.0)
    nvidia_max_retries: int = Field(default=2)
    nvidia_retry_backoff_seconds: float = Field(default=0.5)
    nvidia_embed_batch_size: int = Field(default=32)

    nvidia_planner_model_id: str = Field(default=DEFAULT_NVIDIA_PLANNER_MODEL_ID)
    nvidia_planner_model_revision: str | None = Field(default="1.0")
    nvidia_planner_max_tokens: int = Field(default=4096)
    nvidia_planner_temperature: float = Field(default=0.0)
    planner_max_prompt_characters: int = Field(default=120000)

    procedure_embedding_index_path: Path = Field(
        default=Path("data/retrieval/procedure_embedding_index.json"),
    )
    procedure_manifest_path: Path = Field(
        default=Path("../docs/procedures/corpus_manifest.json"),
    )
    procedure_manuals_root: Path = Field(
        default=Path("../docs/procedures/manuals"),
    )

    retrieval_default_top_k: int = Field(default=5)
    retrieval_max_top_k: int = Field(default=10)
    # 40 keeps multi-topic compound queries inside the rerank pool
    retrieval_rerank_candidate_count: int = Field(default=40)

    @field_validator("sim_timeout_seconds", mode="before")
    @classmethod
    def _validate_timeout(cls, value: Any) -> float:
        return _positive_finite_float(value, env_name="ARES_SIM_TIMEOUT_SECONDS")

    @field_validator("sse_heartbeat_seconds", mode="before")
    @classmethod
    def _validate_heartbeat(cls, value: Any) -> float:
        return _positive_finite_float(value, env_name="ARES_SSE_HEARTBEAT_SECONDS")

    @field_validator("nvidia_request_timeout_seconds", mode="before")
    @classmethod
    def _validate_nim_timeout(cls, value: Any) -> float:
        return _positive_finite_float(
            value,
            env_name="ARES_NVIDIA_REQUEST_TIMEOUT_SECONDS",
        )

    @field_validator("nvidia_retry_backoff_seconds", mode="before")
    @classmethod
    def _validate_nim_backoff(cls, value: Any) -> float:
        return _positive_finite_float(
            value,
            env_name="ARES_NVIDIA_RETRY_BACKOFF_SECONDS",
        )

    @field_validator("max_concurrent_runs", mode="before")
    @classmethod
    def _validate_concurrency(cls, value: Any) -> int:
        return _positive_strict_int(value, env_name="ARES_MAX_CONCURRENT_RUNS")

    @field_validator("max_replay_streams", mode="before")
    @classmethod
    def _validate_max_replay_streams(cls, value: Any) -> int:
        return _positive_strict_int(value, env_name="ARES_MAX_REPLAY_STREAMS")

    @field_validator("replay_default_interval_ms", mode="before")
    @classmethod
    def _validate_replay_default(cls, value: Any) -> int:
        return _positive_strict_int(value, env_name="ARES_REPLAY_DEFAULT_INTERVAL_MS")

    @field_validator("replay_min_interval_ms", mode="before")
    @classmethod
    def _validate_replay_min(cls, value: Any) -> int:
        return _positive_strict_int(value, env_name="ARES_REPLAY_MIN_INTERVAL_MS")

    @field_validator("replay_max_interval_ms", mode="before")
    @classmethod
    def _validate_replay_max(cls, value: Any) -> int:
        return _positive_strict_int(value, env_name="ARES_REPLAY_MAX_INTERVAL_MS")

    @field_validator("nvidia_max_retries", mode="before")
    @classmethod
    def _validate_nim_retries(cls, value: Any) -> int:
        return _non_negative_strict_int(value, env_name="ARES_NVIDIA_MAX_RETRIES")

    @field_validator("nvidia_embed_batch_size", mode="before")
    @classmethod
    def _validate_embed_batch(cls, value: Any) -> int:
        return _positive_strict_int(value, env_name="ARES_NVIDIA_EMBED_BATCH_SIZE")

    @field_validator("nvidia_planner_max_tokens", mode="before")
    @classmethod
    def _validate_planner_max_tokens(cls, value: Any) -> int:
        parsed = _positive_strict_int(value, env_name="ARES_NVIDIA_PLANNER_MAX_TOKENS")
        if parsed > 16384:
            raise ValueError("ARES_NVIDIA_PLANNER_MAX_TOKENS must be <= 16384")
        return parsed

    @field_validator("planner_max_prompt_characters", mode="before")
    @classmethod
    def _validate_planner_prompt_limit(cls, value: Any) -> int:
        return _positive_strict_int(value, env_name="ARES_PLANNER_MAX_PROMPT_CHARACTERS")

    @field_validator("nvidia_planner_temperature", mode="before")
    @classmethod
    def _validate_planner_temperature(cls, value: Any) -> float:
        if isinstance(value, bool):
            raise ValueError("ARES_NVIDIA_PLANNER_TEMPERATURE must be between 0 and 1")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "ARES_NVIDIA_PLANNER_TEMPERATURE must be between 0 and 1",
            ) from exc
        if not math.isfinite(number) or number < 0 or number > 1:
            raise ValueError("ARES_NVIDIA_PLANNER_TEMPERATURE must be between 0 and 1")
        return number

    @field_validator("nvidia_embed_dimensions", mode="before")
    @classmethod
    def _validate_embed_dims(cls, value: Any) -> int:
        return _positive_strict_int(value, env_name="ARES_NVIDIA_EMBED_DIMENSIONS")

    @field_validator("retrieval_default_top_k", mode="before")
    @classmethod
    def _validate_default_top_k(cls, value: Any) -> int:
        return _positive_strict_int(value, env_name="ARES_RETRIEVAL_DEFAULT_TOP_K")

    @field_validator("retrieval_max_top_k", mode="before")
    @classmethod
    def _validate_max_top_k(cls, value: Any) -> int:
        return _positive_strict_int(value, env_name="ARES_RETRIEVAL_MAX_TOP_K")

    @field_validator("retrieval_rerank_candidate_count", mode="before")
    @classmethod
    def _validate_rerank_candidates(cls, value: Any) -> int:
        return _positive_strict_int(
            value,
            env_name="ARES_RETRIEVAL_RERANK_CANDIDATE_COUNT",
        )

    @field_validator("log_level", mode="before")
    @classmethod
    def _validate_log_level(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("ARES_LOG_LEVEL must be a supported logging level")
        normalized = value.strip().upper()
        if normalized not in _SUPPORTED_LOG_LEVELS:
            raise ValueError("ARES_LOG_LEVEL must be a supported logging level")
        return normalized

    @field_validator(
        "nvidia_embed_base_url",
        "nvidia_rerank_base_url",
        "nvidia_embed_model_id",
        "nvidia_rerank_model_id",
        "nvidia_planner_model_id",
        mode="before",
    )
    @classmethod
    def _nonempty_str(cls, value: Any) -> str:
        if not isinstance(value, str) or value.strip() == "":
            raise ValueError("NVIDIA URL and model ID settings must be non-empty")
        return value.strip().rstrip("/")

    @model_validator(mode="after")
    def _resolve_and_validate_paths(self) -> Self:
        project_root = resolve_against_backend(self.project_root)
        sim_binary = resolve_against_backend(self.sim_binary)
        scenario_dir = resolve_against_backend(self.scenario_dir)
        runs_dir = resolve_against_backend(self.runs_dir)
        sessions_dir = resolve_against_backend(self.sessions_dir)
        index_path = resolve_against_backend(self.procedure_embedding_index_path)
        manifest_path = resolve_against_backend(self.procedure_manifest_path)
        manuals_root = resolve_against_backend(self.procedure_manuals_root)

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
        ensure_writable_dir(sessions_dir, env_name="ARES_SESSIONS_DIR")
        ensure_writable_dir(index_path.parent, env_name="ARES_PROCEDURE_EMBEDDING_INDEX_PATH")

        if self.replay_min_interval_ms <= 0:
            raise ValueError("ARES_REPLAY_MIN_INTERVAL_MS must be a strict integer > 0")
        if self.replay_max_interval_ms < self.replay_min_interval_ms:
            raise ValueError(
                "ARES_REPLAY_MAX_INTERVAL_MS must be >= ARES_REPLAY_MIN_INTERVAL_MS"
            )
        if not (
            self.replay_min_interval_ms
            <= self.replay_default_interval_ms
            <= self.replay_max_interval_ms
        ):
            raise ValueError(
                "ARES_REPLAY_DEFAULT_INTERVAL_MS must lie within "
                "ARES_REPLAY_MIN_INTERVAL_MS and ARES_REPLAY_MAX_INTERVAL_MS"
            )

        if self.retrieval_default_top_k > self.retrieval_max_top_k:
            raise ValueError(
                "ARES_RETRIEVAL_DEFAULT_TOP_K must be <= ARES_RETRIEVAL_MAX_TOP_K"
            )
        if self.retrieval_rerank_candidate_count < self.retrieval_max_top_k:
            raise ValueError(
                "ARES_RETRIEVAL_RERANK_CANDIDATE_COUNT must be >= "
                "ARES_RETRIEVAL_MAX_TOP_K"
            )
        if self.nvidia_embed_dimensions != DEFAULT_EMBED_DIMENSIONS:
            raise ValueError(
                "ARES_NVIDIA_EMBED_DIMENSIONS must be 2048 for "
                "nvidia/llama-nemotron-embed-1b-v2"
            )

        object.__setattr__(self, "project_root", project_root)
        object.__setattr__(self, "sim_binary", sim_binary)
        object.__setattr__(self, "scenario_dir", scenario_dir)
        object.__setattr__(self, "runs_dir", runs_dir)
        object.__setattr__(self, "sessions_dir", sessions_dir)
        object.__setattr__(self, "procedure_embedding_index_path", index_path)
        object.__setattr__(self, "procedure_manifest_path", manifest_path)
        object.__setattr__(self, "procedure_manuals_root", manuals_root)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
