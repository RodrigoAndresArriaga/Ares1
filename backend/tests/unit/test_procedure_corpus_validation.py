# unit tests for procedure corpus validator
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
SCRIPTS = BACKEND_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from validate_procedure_corpus import (  # noqa: E402
    REQUIRED_H2_SECTIONS,
    REQUIRED_MANUALS,
    sha256_file,
    strip_disclaimer_spans,
    validate_corpus,
)

CANONICAL_MANUALS = REPO_ROOT / "docs" / "procedures" / "manuals"


def _minimal_manual(
    *,
    procedure_id: str,
    filename: str,
    status: str,
    primary_actions: list[str],
    title: str = "Test Procedure",
    supporting_actions: list[str] | None = None,
    extras_meta: dict | None = None,
    disclaimer: str | None = None,
    known_limitations: str = "- None.",
    mapping_row: str = (
        "| Step 1 | `INFORMATIONAL_ONLY` | none | none | none | Simulator decides. |"
    ),
) -> str:
    meta: dict = {
        "procedure_id": procedure_id,
        "procedure_version": "1.0.0",
        "title": title,
        "filename": filename,
        "status": status,
        "applicable_faults": ["atmosphere_and_solar"],
        "applicable_scenarios": ["mars_hab_atmosphere_solar_failure"],
        "primary_actions": primary_actions,
        "supporting_actions": supporting_actions or [],
        "prohibited_actions": [],
        "telemetry_dependencies": [
            {
                "field": "cabin_pressure_kpa",
                "json_location": "telemetry_history[].habitat.cabin_pressure_kpa",
                "unit": "kPa",
                "condition_roles": ["monitoring"],
            }
        ],
        "source_classifications": ["ARES_ASSUMPTION"],
        "evidence_references": [
            {
                "evidence_id": "EVID-ARES_ASM-001",
                "classification": "ARES_ASSUMPTION",
                "source_title": "Test",
                "locator": "unit-test",
                "supports": "Test evidence.",
                "url": "",
            }
        ],
        "release_configuration_dependencies": ["fault.failure_type"],
        "last_reviewed": "2026-07-15",
        "supersedes": [],
        "superseded_by": [],
    }
    if extras_meta:
        meta.update(extras_meta)
    body_disclaimer = disclaimer or (
        "> It is not an official NASA procedure, is not flight-certified, "
        "and must not be used for real mission operations."
    )
    sections: list[str] = [f"# {title}", "", body_disclaimer, ""]
    for heading in REQUIRED_H2_SECTIONS:
        sections.append(f"## {heading}")
        sections.append("")
        if heading == "Procedure metadata":
            sections.append("```json")
            sections.append(json.dumps(meta, indent=2))
            sections.append("```")
            sections.append("")
        elif heading == "Simulator action mapping":
            sections.append(
                "| Procedure step | Exact action type | Required fields | "
                "Optional fields | Preconditions | Simulator authority notes |"
            )
            sections.append("|---|---|---|---|---|---|")
            sections.append(mapping_row)
            sections.append("")
        elif heading == "Known limitations":
            sections.append(known_limitations)
            sections.append("")
        else:
            sections.append("Placeholder.")
            sections.append("")
    return "\n".join(sections)


def _write_corpus(
    root: Path,
    manuals: dict[str, str],
    *,
    active: list[dict[str, str]] | None = None,
    excluded: list[dict[str, str]] | None = None,
    schema_from_repo: bool = True,
) -> None:
    procedures = root / "docs" / "procedures"
    manuals_dir = procedures / "manuals"
    sources = procedures / "sources"
    manuals_dir.mkdir(parents=True)
    sources.mkdir(parents=True)
    (root / "Simulator").mkdir(parents=True)
    for name, text in manuals.items():
        (manuals_dir / name).write_text(text, encoding="utf-8")
    (sources / "NASA_SOURCE_REGISTER.md").write_text(
        "# Source Register\n\nSources do not make ARES-1 an official NASA system.\n",
        encoding="utf-8",
    )
    if schema_from_repo:
        shutil.copy(
            REPO_ROOT / "docs" / "procedures" / "procedure_metadata.schema.json",
            procedures / "procedure_metadata.schema.json",
        )
    (procedures / "PROCEDURE_STANDARD.md").write_text("# Standard\n", encoding="utf-8")
    (procedures / "PROCEDURE_INDEX.md").write_text("# Index\n", encoding="utf-8")
    default_active = active or [
        {"procedure_id": "ARES-PROC-OXY-001", "filename": "oxygen_leak.md"},
        {"procedure_id": "ARES-PROC-SOLAR-001", "filename": "solar_array_failure.md"},
        {"procedure_id": "ARES-PROC-PWR-001", "filename": "power_rationing.md"},
        {"procedure_id": "ARES-PROC-EVA-001", "filename": "eva_repair.md"},
    ]
    default_excluded = excluded or [
        {
            "procedure_id": "ARES-PROC-COMMS-001",
            "filename": "comms_blackout.md",
            "reason": "No standalone blackout fault and no serialized communication-window state.",
        },
        {
            "procedure_id": "ARES-PROC-CO2-001",
            "filename": "co2_scrubber_failure.md",
            "reason": "No standalone scrubber-failure fault and no direct scrubber-repair action.",
        },
    ]
    manifest = {
        "manifest_version": "1.0.0",
        "procedure_root": "docs/procedures/manuals",
        "source_register": "docs/procedures/sources/NASA_SOURCE_REGISTER.md",
        "schema": "docs/procedures/procedure_metadata.schema.json",
        "active_candidates": default_active,
        "excluded": default_excluded,
    }
    (procedures / "corpus_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )


def _six_valid_manuals() -> dict[str, str]:
    return {
        "oxygen_leak.md": _minimal_manual(
            procedure_id="ARES-PROC-OXY-001",
            filename="oxygen_leak.md",
            status="PARTIAL_EVIDENCE",
            primary_actions=["isolate_module"],
        ),
        "solar_array_failure.md": _minimal_manual(
            procedure_id="ARES-PROC-SOLAR-001",
            filename="solar_array_failure.md",
            status="PARTIAL_EVIDENCE",
            primary_actions=["repair_solar_array"],
        ),
        "power_rationing.md": _minimal_manual(
            procedure_id="ARES-PROC-PWR-001",
            filename="power_rationing.md",
            status="PARTIAL_EVIDENCE",
            primary_actions=["reduce_power_load"],
        ),
        "eva_repair.md": _minimal_manual(
            procedure_id="ARES-PROC-EVA-001",
            filename="eva_repair.md",
            status="PARTIAL_EVIDENCE",
            primary_actions=["repair_solar_array"],
        ),
        "comms_blackout.md": _minimal_manual(
            procedure_id="ARES-PROC-COMMS-001",
            filename="comms_blackout.md",
            status="DEFERRED_SOURCE_REQUIRED",
            primary_actions=["send_emergency_packet"],
            known_limitations="- No serialized window state.\n- No standalone blackout fault.",
        ),
        "co2_scrubber_failure.md": _minimal_manual(
            procedure_id="ARES-PROC-CO2-001",
            filename="co2_scrubber_failure.md",
            status="DEFERRED_SOURCE_REQUIRED",
            primary_actions=[],
            known_limitations="- No direct recovery action.\n- No scrubber-repair action.",
        ),
    }


def test_real_corpus_validates() -> None:
    report = validate_corpus(REPO_ROOT)
    assert report.status == "PASS", report.errors
    assert len(report.manuals_checked) == 6
    assert len(report.active_candidates) == 4
    assert len(report.excluded) == 2
    for name in REQUIRED_MANUALS:
        assert name in report.content_hashes


def test_missing_required_section(tmp_path: Path) -> None:
    manuals = _six_valid_manuals()
    text = manuals["oxygen_leak.md"]
    manuals["oxygen_leak.md"] = text.replace("## Purpose\n", "## Purposex\n")
    _write_corpus(tmp_path, manuals)
    report = validate_corpus(tmp_path)
    assert report.status == "FAIL"
    assert any("missing required section ## Purpose" in e for e in report.errors)


def test_reordered_required_section(tmp_path: Path) -> None:
    manuals = _six_valid_manuals()
    text = manuals["oxygen_leak.md"]
    text = text.replace("## Purpose\n", "## __PURP__\n").replace(
        "## Scope and applicability\n", "## Purpose\n"
    ).replace("## __PURP__\n", "## Scope and applicability\n")
    manuals["oxygen_leak.md"] = text
    _write_corpus(tmp_path, manuals)
    report = validate_corpus(tmp_path)
    assert report.status == "FAIL"
    assert any("section order mismatch" in e for e in report.errors)


def test_malformed_metadata_json(tmp_path: Path) -> None:
    manuals = _six_valid_manuals()
    manuals["oxygen_leak.md"] = manuals["oxygen_leak.md"].replace(
        '"procedure_version": "1.0.0",',
        '"procedure_version": "1.0.0",,',
    )
    _write_corpus(tmp_path, manuals)
    report = validate_corpus(tmp_path)
    assert report.status == "FAIL"
    assert any("malformed metadata JSON" in e for e in report.errors)


def test_schema_invalid_metadata(tmp_path: Path) -> None:
    manuals = _six_valid_manuals()
    manuals["oxygen_leak.md"] = _minimal_manual(
        procedure_id="ARES-PROC-BAD-001",
        filename="oxygen_leak.md",
        status="PARTIAL_EVIDENCE",
        primary_actions=["isolate_module"],
    )
    _write_corpus(tmp_path, manuals)
    report = validate_corpus(tmp_path)
    assert report.status == "FAIL"
    assert any("schema validation failed" in e for e in report.errors)


def test_unknown_action(tmp_path: Path) -> None:
    manuals = _six_valid_manuals()
    manuals["oxygen_leak.md"] = _minimal_manual(
        procedure_id="ARES-PROC-OXY-001",
        filename="oxygen_leak.md",
        status="PARTIAL_EVIDENCE",
        primary_actions=["vent_atmosphere"],
    )
    _write_corpus(tmp_path, manuals)
    report = validate_corpus(tmp_path)
    assert report.status == "FAIL"
    assert any("unknown action" in e for e in report.errors)


def test_unknown_telemetry_field(tmp_path: Path) -> None:
    manuals = _six_valid_manuals()
    manuals["oxygen_leak.md"] = _minimal_manual(
        procedure_id="ARES-PROC-OXY-001",
        filename="oxygen_leak.md",
        status="PARTIAL_EVIDENCE",
        primary_actions=["isolate_module"],
        extras_meta={
            "telemetry_dependencies": [
                {
                    "field": "oxygen_fraction",
                    "json_location": "telemetry_history[].habitat.oxygen_fraction",
                    "unit": "fraction",
                    "condition_roles": ["monitoring"],
                }
            ]
        },
    )
    _write_corpus(tmp_path, manuals)
    report = validate_corpus(tmp_path)
    assert report.status == "FAIL"
    assert any("oxygen_fraction" in e for e in report.errors)


def test_duplicate_procedure_id(tmp_path: Path) -> None:
    manuals = _six_valid_manuals()
    manuals["solar_array_failure.md"] = _minimal_manual(
        procedure_id="ARES-PROC-OXY-001",
        filename="solar_array_failure.md",
        status="PARTIAL_EVIDENCE",
        primary_actions=["repair_solar_array"],
    )
    _write_corpus(tmp_path, manuals)
    report = validate_corpus(tmp_path)
    assert report.status == "FAIL"
    assert any("duplicate procedure_id" in e for e in report.errors)


def test_active_excluded_manifest_conflict(tmp_path: Path) -> None:
    manuals = _six_valid_manuals()
    _write_corpus(
        tmp_path,
        manuals,
        active=[
            {"procedure_id": "ARES-PROC-OXY-001", "filename": "oxygen_leak.md"},
            {"procedure_id": "ARES-PROC-SOLAR-001", "filename": "solar_array_failure.md"},
            {"procedure_id": "ARES-PROC-PWR-001", "filename": "power_rationing.md"},
            {"procedure_id": "ARES-PROC-EVA-001", "filename": "eva_repair.md"},
            {"procedure_id": "ARES-PROC-COMMS-001", "filename": "comms_blackout.md"},
        ],
        excluded=[
            {
                "procedure_id": "ARES-PROC-COMMS-001",
                "filename": "comms_blackout.md",
                "reason": "conflict",
            },
            {
                "procedure_id": "ARES-PROC-CO2-001",
                "filename": "co2_scrubber_failure.md",
                "reason": "deferred",
            },
        ],
    )
    report = validate_corpus(tmp_path)
    assert report.status == "FAIL"
    assert any("both lists" in e for e in report.errors)


def test_deferred_incorrectly_active(tmp_path: Path) -> None:
    manuals = _six_valid_manuals()
    manuals["comms_blackout.md"] = _minimal_manual(
        procedure_id="ARES-PROC-COMMS-001",
        filename="comms_blackout.md",
        status="PARTIAL_EVIDENCE",
        primary_actions=["send_emergency_packet"],
        known_limitations="- No serialized window state.",
    )
    _write_corpus(
        tmp_path,
        manuals,
        active=[
            {"procedure_id": "ARES-PROC-OXY-001", "filename": "oxygen_leak.md"},
            {"procedure_id": "ARES-PROC-SOLAR-001", "filename": "solar_array_failure.md"},
            {"procedure_id": "ARES-PROC-PWR-001", "filename": "power_rationing.md"},
            {"procedure_id": "ARES-PROC-COMMS-001", "filename": "comms_blackout.md"},
        ],
        excluded=[
            {
                "procedure_id": "ARES-PROC-EVA-001",
                "filename": "eva_repair.md",
                "reason": "wrong",
            },
            {
                "procedure_id": "ARES-PROC-CO2-001",
                "filename": "co2_scrubber_failure.md",
                "reason": "deferred",
            },
        ],
    )
    report = validate_corpus(tmp_path)
    assert report.status == "FAIL"
    assert any("DEFERRED_SOURCE_REQUIRED" in e or "active_candidates" in e for e in report.errors)


def test_forbidden_nasa_claim(tmp_path: Path) -> None:
    manuals = _six_valid_manuals()
    manuals["oxygen_leak.md"] = _minimal_manual(
        procedure_id="ARES-PROC-OXY-001",
        filename="oxygen_leak.md",
        status="PARTIAL_EVIDENCE",
        primary_actions=["isolate_module"],
        disclaimer="> This is a NASA-approved emergency response.",
    )
    _write_corpus(tmp_path, manuals)
    report = validate_corpus(tmp_path)
    assert report.status == "FAIL"
    assert any("nasa-approved" in e for e in report.errors)


def test_approved_disclaimer_not_rejected() -> None:
    text = (
        "It is not an official NASA procedure, is not flight-certified, "
        "and must not be used for real mission operations."
    )
    cleaned = strip_disclaimer_spans(text).lower()
    assert "official nasa procedure" not in cleaned
    assert "flight-certified" not in cleaned


def test_unsupported_oxygen_rationing_level(tmp_path: Path) -> None:
    manuals = _six_valid_manuals()
    manuals["oxygen_leak.md"] = _minimal_manual(
        procedure_id="ARES-PROC-OXY-001",
        filename="oxygen_leak.md",
        status="PARTIAL_EVIDENCE",
        primary_actions=["oxygen_rationing"],
    )
    manuals["oxygen_leak.md"] += (
        "\nUse oxygen_rationing with level `emergency` only.\n"
    )
    _write_corpus(tmp_path, manuals)
    report = validate_corpus(tmp_path)
    assert report.status == "FAIL"
    assert any("unsupported oxygen_rationing level" in e for e in report.errors)


def test_content_hash_preservation_logic(tmp_path: Path) -> None:
    src = CANONICAL_MANUALS / "oxygen_leak.md"
    assert src.is_file()
    before = sha256_file(src)
    dest = tmp_path / "oxygen_leak.md"
    shutil.copyfile(src, dest)
    after = sha256_file(dest)
    assert before == after
    dest.write_text(dest.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert sha256_file(dest) != before
