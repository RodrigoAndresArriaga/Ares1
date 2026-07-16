# Phase 4 Step 1 procedure corpus contracts
# manifest is the inclusion authority; no embeddings or retrieval scores
from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.actions import ActionType
from app.schemas.common import CONTRACT_CONFIG, StrictBool, StrictInt

CORPUS_SCHEMA_VERSION = "1.0.0"

Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
NonEmptyStr = Annotated[str, Field(min_length=1)]
ProcedureId = Annotated[
    str,
    Field(pattern=r"^ARES-PROC-(OXY|SOLAR|PWR|EVA|COMMS|CO2)-[0-9]{3}$"),
]
ProcedureVersion = Annotated[str, Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")]
IsoDate = Annotated[str, Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")]
EvidenceId = Annotated[
    str,
    Field(pattern=r"^EVID-(NASA_STD|NASA_REF|DER_PHYS|ARES_ASM|ARES_REL)-[0-9]{3}$"),
]


# detect Windows drive paths and POSIX absolute paths without importing pathlib here
def _is_absolute_path_like(value: str) -> bool:
    if value.startswith("/") or value.startswith("\\"):
        return True
    if len(value) >= 3 and value[1] == ":" and value[2] in {"/", "\\"}:
        return True
    return False


class ProcedureStatus(str, Enum):
    DRAFT = "DRAFT"
    READY_FOR_AUTHORING = "READY_FOR_AUTHORING"
    PARTIAL_EVIDENCE = "PARTIAL_EVIDENCE"
    DEFERRED_SOURCE_REQUIRED = "DEFERRED_SOURCE_REQUIRED"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"


class SourceClassification(str, Enum):
    NASA_STANDARD = "NASA_STANDARD"
    NASA_REFERENCE = "NASA_REFERENCE"
    DERIVED_PHYSICS = "DERIVED_PHYSICS"
    ARES_ASSUMPTION = "ARES_ASSUMPTION"
    ARES_RELEASE_CONFIGURATION = "ARES_RELEASE_CONFIGURATION"


class ConditionRole(str, Enum):
    ENTRY = "entry"
    MONITORING = "monitoring"
    ABORT = "abort"
    SUCCESS = "success"


class CorpusManifestEntry(BaseModel):
    model_config = CONTRACT_CONFIG

    procedure_id: ProcedureId
    filename: NonEmptyStr

    @field_validator("filename")
    @classmethod
    def _validate_filename(cls, value: str) -> str:
        if _is_absolute_path_like(value):
            raise ValueError("filename must be a basename, not an absolute path")
        if "/" in value or "\\" in value or value in {".", ".."} or ".." in value:
            raise ValueError("filename must be a basename without path separators")
        if not value.endswith(".md"):
            raise ValueError("filename must end with .md")
        return value


class CorpusManifestExcludedEntry(CorpusManifestEntry):
    reason: NonEmptyStr


class CorpusManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    manifest_version: NonEmptyStr
    procedure_root: NonEmptyStr
    source_register: NonEmptyStr
    metadata_schema: NonEmptyStr = Field(alias="schema")
    active_candidates: tuple[CorpusManifestEntry, ...]
    excluded: tuple[CorpusManifestExcludedEntry, ...]

    @model_validator(mode="after")
    def _reject_duplicates(self) -> CorpusManifest:
        active_ids = [e.procedure_id for e in self.active_candidates]
        active_files = [e.filename for e in self.active_candidates]
        excl_ids = [e.procedure_id for e in self.excluded]
        excl_files = [e.filename for e in self.excluded]
        if len(active_ids) != len(set(active_ids)):
            raise ValueError("duplicate procedure_id in active_candidates")
        if len(active_files) != len(set(active_files)):
            raise ValueError("duplicate filename in active_candidates")
        if len(excl_ids) != len(set(excl_ids)):
            raise ValueError("duplicate procedure_id in excluded")
        if len(excl_files) != len(set(excl_files)):
            raise ValueError("duplicate filename in excluded")
        overlap_ids = set(active_ids) & set(excl_ids)
        if overlap_ids:
            raise ValueError("procedure_id appears in both active_candidates and excluded")
        overlap_files = set(active_files) & set(excl_files)
        if overlap_files:
            raise ValueError("filename appears in both active_candidates and excluded")
        return self


class EvidenceReference(BaseModel):
    model_config = CONTRACT_CONFIG

    evidence_id: EvidenceId
    classification: SourceClassification
    source_title: NonEmptyStr
    locator: NonEmptyStr
    supports: NonEmptyStr
    url: str = ""


class TelemetryDependency(BaseModel):
    model_config = CONTRACT_CONFIG

    field: NonEmptyStr
    json_location: NonEmptyStr
    unit: NonEmptyStr
    condition_roles: tuple[ConditionRole, ...] = Field(min_length=1)
    display_label: NonEmptyStr | None = None


class ProcedureMetadata(BaseModel):
    model_config = CONTRACT_CONFIG

    procedure_id: ProcedureId
    procedure_version: ProcedureVersion
    title: NonEmptyStr
    filename: NonEmptyStr
    status: ProcedureStatus
    applicable_faults: tuple[NonEmptyStr, ...]
    applicable_scenarios: tuple[NonEmptyStr, ...]
    primary_actions: tuple[ActionType, ...]
    supporting_actions: tuple[ActionType, ...]
    prohibited_actions: tuple[ActionType, ...]
    telemetry_dependencies: tuple[TelemetryDependency, ...]
    source_classifications: tuple[SourceClassification, ...]
    evidence_references: tuple[EvidenceReference, ...]
    release_configuration_dependencies: tuple[NonEmptyStr, ...]
    last_reviewed: IsoDate
    supersedes: tuple[ProcedureId, ...]
    superseded_by: tuple[ProcedureId, ...]
    notes: str | None = None
    domain_aliases: tuple[NonEmptyStr, ...] | None = None
    chunk_boundary_notes: tuple[NonEmptyStr, ...] | None = None

    @field_validator("filename")
    @classmethod
    def _validate_filename(cls, value: str) -> str:
        if _is_absolute_path_like(value) or "/" in value or "\\" in value:
            raise ValueError("filename must be a basename")
        if not value.endswith(".md"):
            raise ValueError("filename must end with .md")
        return value


class ProcedureDocumentDescriptor(BaseModel):
    model_config = CONTRACT_CONFIG

    procedure_id: ProcedureId
    title: NonEmptyStr
    manual_path: NonEmptyStr
    status: ProcedureStatus
    index_eligible: StrictBool
    primary_actions: tuple[ActionType, ...]
    supporting_actions: tuple[ActionType, ...]
    prohibited_actions: tuple[ActionType, ...]
    source_classifications: tuple[SourceClassification, ...]
    evidence_references: tuple[EvidenceReference, ...]
    manual_sha256: Sha256Hex

    @field_validator("manual_path")
    @classmethod
    def _relative_posix_path(cls, value: str) -> str:
        if _is_absolute_path_like(value):
            raise ValueError("manual_path must be repository-relative")
        if "\\" in value:
            raise ValueError("manual_path must use POSIX separators")
        if value.startswith("/") or ".." in value.split("/"):
            raise ValueError("manual_path must be a relative POSIX path")
        return value


class ProcedureChunk(BaseModel):
    model_config = CONTRACT_CONFIG

    schema_version: NonEmptyStr
    chunk_id: Sha256Hex
    procedure_id: ProcedureId
    procedure_title: NonEmptyStr
    manual_path: NonEmptyStr
    section_path: tuple[str, ...]
    section_title: NonEmptyStr
    chunk_index: StrictInt = Field(ge=0)
    content: NonEmptyStr
    embedding_text: NonEmptyStr
    content_sha256: Sha256Hex
    manual_sha256: Sha256Hex
    source_classifications: tuple[SourceClassification, ...]
    evidence_references: tuple[EvidenceReference, ...]
    allowed_actions: tuple[ActionType, ...]
    procedure_status: ProcedureStatus

    @field_validator("manual_path")
    @classmethod
    def _relative_posix_path(cls, value: str) -> str:
        if _is_absolute_path_like(value):
            raise ValueError("manual_path must be repository-relative")
        if "\\" in value:
            raise ValueError("manual_path must use POSIX separators")
        if value.startswith("/") or ".." in value.split("/"):
            raise ValueError("manual_path must be a relative POSIX path")
        return value


class ProcedureCorpusSnapshot(BaseModel):
    model_config = CONTRACT_CONFIG

    schema_version: NonEmptyStr
    manifest_sha256: Sha256Hex
    corpus_sha256: Sha256Hex
    included_documents: tuple[ProcedureDocumentDescriptor, ...]
    excluded_documents: tuple[ProcedureDocumentDescriptor, ...]
    chunks: tuple[ProcedureChunk, ...]
