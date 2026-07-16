# strict schema tests for Phase 4 Step 1 retrieval contracts
from __future__ import annotations

import pytest
from app.schemas.actions import ActionType
from app.schemas.api import ErrorCode
from app.schemas.retrieval import (
    CORPUS_SCHEMA_VERSION,
    CorpusManifest,
    CorpusManifestEntry,
    EvidenceReference,
    ProcedureChunk,
    ProcedureCorpusSnapshot,
    ProcedureDocumentDescriptor,
    ProcedureMetadata,
    ProcedureStatus,
    SourceClassification,
    TelemetryDependency,
)
from pydantic import ValidationError

_SHA = "a" * 64
_SHA_B = "b" * 64


def _evidence() -> EvidenceReference:
    return EvidenceReference(
        evidence_id="EVID-ARES_ASM-001",
        classification=SourceClassification.ARES_ASSUMPTION,
        source_title="Test",
        locator="unit-test",
        supports="Unit test evidence.",
        url="",
    )


def _telemetry() -> TelemetryDependency:
    return TelemetryDependency(
        field="cabin_pressure_kpa",
        json_location="telemetry_history[].habitat.cabin_pressure_kpa",
        unit="kPa",
        condition_roles=("monitoring",),
    )


def _metadata(**overrides: object) -> ProcedureMetadata:
    payload: dict[str, object] = {
        "procedure_id": "ARES-PROC-OXY-001",
        "procedure_version": "1.0.0",
        "title": "Test Procedure",
        "filename": "oxygen_leak.md",
        "status": ProcedureStatus.PARTIAL_EVIDENCE,
        "applicable_faults": ("atmosphere_and_solar",),
        "applicable_scenarios": ("mars_hab_atmosphere_solar_failure",),
        "primary_actions": (ActionType.ISOLATE_MODULE,),
        "supporting_actions": (ActionType.OXYGEN_RATIONING,),
        "prohibited_actions": (),
        "telemetry_dependencies": (_telemetry(),),
        "source_classifications": (SourceClassification.ARES_ASSUMPTION,),
        "evidence_references": (_evidence(),),
        "release_configuration_dependencies": ("fault.failure_type",),
        "last_reviewed": "2026-07-15",
        "supersedes": (),
        "superseded_by": (),
    }
    payload.update(overrides)
    return ProcedureMetadata.model_validate(payload)


def _document(**overrides: object) -> ProcedureDocumentDescriptor:
    payload: dict[str, object] = {
        "procedure_id": "ARES-PROC-OXY-001",
        "title": "Test Procedure",
        "manual_path": "docs/procedures/manuals/oxygen_leak.md",
        "status": ProcedureStatus.PARTIAL_EVIDENCE,
        "index_eligible": True,
        "primary_actions": (ActionType.ISOLATE_MODULE,),
        "supporting_actions": (ActionType.OXYGEN_RATIONING,),
        "prohibited_actions": (),
        "source_classifications": (SourceClassification.ARES_ASSUMPTION,),
        "evidence_references": (_evidence(),),
        "manual_sha256": _SHA,
    }
    payload.update(overrides)
    return ProcedureDocumentDescriptor.model_validate(payload)


def _chunk(**overrides: object) -> ProcedureChunk:
    payload: dict[str, object] = {
        "schema_version": CORPUS_SCHEMA_VERSION,
        "chunk_id": _SHA,
        "procedure_id": "ARES-PROC-OXY-001",
        "procedure_title": "Test Procedure",
        "manual_path": "docs/procedures/manuals/oxygen_leak.md",
        "section_path": ("Purpose",),
        "section_title": "Purpose",
        "chunk_index": 0,
        "content": "Operational content.",
        "embedding_text": "Procedure: Test Procedure\n...",
        "content_sha256": _SHA_B,
        "manual_sha256": _SHA,
        "source_classifications": (SourceClassification.ARES_ASSUMPTION,),
        "evidence_references": (_evidence(),),
        "allowed_actions": (ActionType.ISOLATE_MODULE,),
        "procedure_status": ProcedureStatus.PARTIAL_EVIDENCE,
    }
    payload.update(overrides)
    return ProcedureChunk.model_validate(payload)


def test_error_codes_registered() -> None:
    assert ErrorCode.PROCEDURE_CORPUS_INVALID.value == "PROCEDURE_CORPUS_INVALID"
    assert ErrorCode.PROCEDURE_MANIFEST_INVALID.value == "PROCEDURE_MANIFEST_INVALID"
    assert ErrorCode.PROCEDURE_MANUAL_NOT_FOUND.value == "PROCEDURE_MANUAL_NOT_FOUND"
    assert (
        ErrorCode.PROCEDURE_MANUAL_SECURITY_ERROR.value
        == "PROCEDURE_MANUAL_SECURITY_ERROR"
    )
    assert ErrorCode.PROCEDURE_MANUAL_PARSE_ERROR.value == "PROCEDURE_MANUAL_PARSE_ERROR"


def test_manifest_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        CorpusManifest.model_validate(
            {
                "manifest_version": "1.0.0",
                "procedure_root": "docs/procedures/manuals",
                "source_register": "docs/procedures/sources/NASA_SOURCE_REGISTER.md",
                "schema": "docs/procedures/procedure_metadata.schema.json",
                "active_candidates": [],
                "excluded": [],
                "extra": True,
            }
        )


def test_manifest_rejects_missing_required_fields() -> None:
    with pytest.raises(ValidationError):
        CorpusManifest.model_validate(
            {
                "manifest_version": "1.0.0",
                "procedure_root": "docs/procedures/manuals",
                "source_register": "docs/procedures/sources/NASA_SOURCE_REGISTER.md",
                "schema": "docs/procedures/procedure_metadata.schema.json",
                "active_candidates": [],
            }
        )


def test_manifest_rejects_duplicate_procedure_ids() -> None:
    with pytest.raises(ValidationError):
        CorpusManifest.model_validate(
            {
                "manifest_version": "1.0.0",
                "procedure_root": "docs/procedures/manuals",
                "source_register": "docs/procedures/sources/NASA_SOURCE_REGISTER.md",
                "schema": "docs/procedures/procedure_metadata.schema.json",
                "active_candidates": [
                    {
                        "procedure_id": "ARES-PROC-OXY-001",
                        "filename": "oxygen_leak.md",
                    },
                    {
                        "procedure_id": "ARES-PROC-OXY-001",
                        "filename": "solar_array_failure.md",
                    },
                ],
                "excluded": [],
            }
        )


def test_manifest_rejects_duplicate_manual_paths() -> None:
    with pytest.raises(ValidationError):
        CorpusManifest.model_validate(
            {
                "manifest_version": "1.0.0",
                "procedure_root": "docs/procedures/manuals",
                "source_register": "docs/procedures/sources/NASA_SOURCE_REGISTER.md",
                "schema": "docs/procedures/procedure_metadata.schema.json",
                "active_candidates": [
                    {
                        "procedure_id": "ARES-PROC-OXY-001",
                        "filename": "oxygen_leak.md",
                    },
                    {
                        "procedure_id": "ARES-PROC-SOLAR-001",
                        "filename": "oxygen_leak.md",
                    },
                ],
                "excluded": [],
            }
        )


def test_manifest_rejects_absolute_and_traversal_filenames() -> None:
    with pytest.raises(ValidationError):
        CorpusManifestEntry.model_validate(
            {
                "procedure_id": "ARES-PROC-OXY-001",
                "filename": "/etc/passwd.md",
            }
        )
    with pytest.raises(ValidationError):
        CorpusManifestEntry.model_validate(
            {
                "procedure_id": "ARES-PROC-OXY-001",
                "filename": "../secret.md",
            }
        )
    with pytest.raises(ValidationError):
        CorpusManifestEntry.model_validate(
            {
                "procedure_id": "ARES-PROC-OXY-001",
                "filename": "notes.txt",
            }
        )


def test_metadata_rejects_unknown_status_and_actions() -> None:
    with pytest.raises(ValidationError):
        _metadata(status="NOT_A_STATUS")
    with pytest.raises(ValidationError):
        _metadata(primary_actions=["invent_action"])
    with pytest.raises(ValidationError):
        _metadata(source_classifications=["NOT_A_CLASS"])


def test_chunk_rejects_extra_fields_and_bad_hashes() -> None:
    with pytest.raises(ValidationError):
        _chunk(**{"retrieval_score": 0.9})
    with pytest.raises(ValidationError):
        _chunk(chunk_id="not-a-hash")
    with pytest.raises(ValidationError):
        _chunk(content_sha256="ABC" + "d" * 61)
    with pytest.raises(ValidationError):
        _chunk(content="")
    with pytest.raises(ValidationError):
        _chunk(procedure_id="")
    with pytest.raises(ValidationError):
        _chunk(chunk_index=-1)
    with pytest.raises(ValidationError):
        _chunk(manual_path="C:/Windows/oxygen_leak.md")
    with pytest.raises(ValidationError):
        _chunk(allowed_actions=["not_an_action"])


def test_document_rejects_absolute_manual_path() -> None:
    with pytest.raises(ValidationError):
        _document(manual_path="/abs/oxygen_leak.md")
    with pytest.raises(ValidationError):
        _document(manual_path="docs\\procedures\\manuals\\oxygen_leak.md")


def test_snapshot_round_trip() -> None:
    snapshot = ProcedureCorpusSnapshot(
        schema_version=CORPUS_SCHEMA_VERSION,
        manifest_sha256=_SHA,
        corpus_sha256=_SHA_B,
        included_documents=(_document(),),
        excluded_documents=(),
        chunks=(_chunk(),),
    )
    restored = ProcedureCorpusSnapshot.model_validate(snapshot.model_dump(mode="json"))
    assert restored == snapshot
