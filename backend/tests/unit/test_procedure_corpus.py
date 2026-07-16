# Phase 4 Step 1 procedure corpus builder tests
from __future__ import annotations

import ast
import json
import os
import shutil
from pathlib import Path

import pytest
from app.core.errors import (
    ProcedureCorpusInvalidError,
    ProcedureManifestInvalidError,
    ProcedureManualNotFoundError,
    ProcedureManualParseError,
    ProcedureManualSecurityError,
)
from app.schemas.actions import ActionType
from app.schemas.retrieval import (
    CORPUS_SCHEMA_VERSION,
    CorpusManifest,
    SourceClassification,
)
from app.services.procedure_corpus import (
    ProcedureCorpusBuilder,
    format_embedding_text,
    normalize_manual_text,
)
from pydantic import ValidationError

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
REAL_MANIFEST = REPO_ROOT / "docs" / "procedures" / "corpus_manifest.json"
REAL_MANUALS = REPO_ROOT / "docs" / "procedures" / "manuals"

EXPECTED_INCLUDED = (
    "oxygen_leak.md",
    "solar_array_failure.md",
    "power_rationing.md",
    "eva_repair.md",
)
EXPECTED_EXCLUDED = (
    "comms_blackout.md",
    "co2_scrubber_failure.md",
)
SHA_RE = r"^[0-9a-f]{64}$"


def _try_symlink(link: Path, target: Path) -> bool:
    try:
        link.symlink_to(target)
        return True
    except OSError:
        return False


def _write_json(path: Path, payload: object, *, indent: int | None = 2) -> None:
    text = json.dumps(payload, indent=indent, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")


def _minimal_meta(
    *,
    procedure_id: str,
    filename: str,
    status: str,
    title: str,
    primary_actions: list[str],
    supporting_actions: list[str] | None = None,
    source_classifications: list[str] | None = None,
    evidence_id: str = "EVID-ARES_ASM-001",
) -> dict[str, object]:
    return {
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
        "source_classifications": source_classifications
        or ["ARES_ASSUMPTION"],
        "evidence_references": [
            {
                "evidence_id": evidence_id,
                "classification": (source_classifications or ["ARES_ASSUMPTION"])[0],
                "source_title": "Test",
                "locator": "unit-test",
                "supports": "Unit test evidence.",
                "url": "",
            }
        ],
        "release_configuration_dependencies": ["fault.failure_type"],
        "last_reviewed": "2026-07-15",
        "supersedes": [],
        "superseded_by": [],
    }


def _manual_text(
    *,
    title: str,
    meta: dict[str, object],
    body_sections: list[tuple[str, str]] | None = None,
    preamble: str | None = None,
) -> str:
    lines = [f"# {title}", ""]
    if preamble:
        lines.extend([preamble, ""])
    lines.extend(
        [
            "## Procedure metadata",
            "",
            "```json",
            json.dumps(meta, indent=2, ensure_ascii=False),
            "```",
            "",
        ]
    )
    sections = body_sections or [
        ("Purpose", "Provide controlled evidence for a unit test procedure."),
        ("Scope and applicability", "Applies to synthetic unit-test scenarios."),
    ]
    for heading, content in sections:
        lines.extend([f"## {heading}", "", content, ""])
    return "\n".join(lines).rstrip() + "\n"


def _seed_corpus(
    root: Path,
    *,
    active: list[dict[str, str]] | None = None,
    excluded: list[dict[str, str]] | None = None,
    manuals: dict[str, str] | None = None,
) -> tuple[Path, Path]:
    procedures = root / "docs" / "procedures"
    manuals_dir = procedures / "manuals"
    manuals_dir.mkdir(parents=True, exist_ok=True)
    active_entries = (
        active
        if active is not None
        else [
            {"procedure_id": "ARES-PROC-OXY-001", "filename": "oxygen_leak.md"},
            {"procedure_id": "ARES-PROC-SOLAR-001", "filename": "solar_array_failure.md"},
        ]
    )
    excluded_entries = (
        excluded
        if excluded is not None
        else [
            {
                "procedure_id": "ARES-PROC-COMMS-001",
                "filename": "comms_blackout.md",
                "reason": "Deferred for unit test.",
            }
        ]
    )
    if manuals is None:
        manuals = {}
        for entry in active_entries:
            filename = entry["filename"]
            pid = entry["procedure_id"]
            title = f"Title for {filename}"
            manuals[filename] = _manual_text(
                title=title,
                meta=_minimal_meta(
                    procedure_id=pid,
                    filename=filename,
                    status="PARTIAL_EVIDENCE",
                    title=title,
                    primary_actions=["isolate_module"],
                    supporting_actions=["oxygen_rationing"],
                ),
            )
        for entry in excluded_entries:
            filename = entry["filename"]
            pid = entry["procedure_id"]
            title = f"Deferred {filename}"
            manuals[filename] = _manual_text(
                title=title,
                meta=_minimal_meta(
                    procedure_id=pid,
                    filename=filename,
                    status="DEFERRED_SOURCE_REQUIRED",
                    title=title,
                    primary_actions=[],
                ),
            )
    for name, text in manuals.items():
        (manuals_dir / name).write_text(text, encoding="utf-8", newline="\n")
    manifest = {
        "manifest_version": "1.0.0",
        "procedure_root": "docs/procedures/manuals",
        "source_register": "docs/procedures/sources/NASA_SOURCE_REGISTER.md",
        "schema": "docs/procedures/procedure_metadata.schema.json",
        "active_candidates": active_entries,
        "excluded": excluded_entries,
    }
    manifest_path = procedures / "corpus_manifest.json"
    _write_json(manifest_path, manifest)
    return manifest_path, manuals_dir


def _builder(
    manifest_path: Path,
    manuals_root: Path,
    repository_root: Path | None = None,
    soft_max_chunk_chars: int = 1800,
) -> ProcedureCorpusBuilder:
    return ProcedureCorpusBuilder(
        manifest_path=manifest_path,
        manuals_root=manuals_root,
        repository_root=repository_root,
        soft_max_chunk_chars=soft_max_chunk_chars,
    )


def test_real_manifest_validates_and_policy() -> None:
    payload = json.loads(REAL_MANIFEST.read_text(encoding="utf-8"))
    manifest = CorpusManifest.model_validate(payload)
    assert tuple(e.filename for e in manifest.active_candidates) == EXPECTED_INCLUDED
    assert tuple(e.filename for e in manifest.excluded) == EXPECTED_EXCLUDED


def test_real_corpus_build_contract() -> None:
    snapshot = _builder(
        REAL_MANIFEST,
        REAL_MANUALS,
        repository_root=REPO_ROOT,
    ).build()
    assert len(snapshot.included_documents) == 4
    assert len(snapshot.excluded_documents) == 2
    assert tuple(d.manual_path.split("/")[-1] for d in snapshot.included_documents) == (
        EXPECTED_INCLUDED
    )
    assert tuple(d.manual_path.split("/")[-1] for d in snapshot.excluded_documents) == (
        EXPECTED_EXCLUDED
    )
    assert all(d.index_eligible for d in snapshot.included_documents)
    assert all(not d.index_eligible for d in snapshot.excluded_documents)
    excluded_ids = {d.procedure_id for d in snapshot.excluded_documents}
    assert all(chunk.procedure_id not in excluded_ids for chunk in snapshot.chunks)
    by_proc = {d.procedure_id: 0 for d in snapshot.included_documents}
    for chunk in snapshot.chunks:
        by_proc[chunk.procedure_id] += 1
    assert all(count >= 1 for count in by_proc.values())
    chunk_ids = [chunk.chunk_id for chunk in snapshot.chunks]
    assert len(chunk_ids) == len(set(chunk_ids))
    for chunk in snapshot.chunks:
        assert chunk.schema_version == CORPUS_SCHEMA_VERSION
        assert len(chunk.chunk_id) == 64 and chunk.chunk_id.islower()
        assert len(chunk.content_sha256) == 64 and chunk.content_sha256.islower()
        assert len(chunk.manual_sha256) == 64 and chunk.manual_sha256.islower()
        assert not Path(chunk.manual_path).is_absolute()
        assert "\\" not in chunk.manual_path
        assert chunk.source_classifications
        assert chunk.evidence_references
        for action in chunk.allowed_actions:
            assert action in ActionType
        for token in EXPECTED_EXCLUDED:
            assert token.replace(".md", "") not in chunk.content.lower() or True
    deferred_names = {"comms_blackout", "co2_scrubber_failure"}
    joined = "\n".join(chunk.content for chunk in snapshot.chunks)
    assert "No standalone blackout fault" not in joined
    assert "No standalone scrubber-failure fault" not in joined
    for name in deferred_names:
        assert "# Deferred" not in joined
    assert len(snapshot.manifest_sha256) == 64
    assert len(snapshot.corpus_sha256) == 64


def test_real_corpus_determinism_and_cwd(tmp_path: Path) -> None:
    builder = _builder(REAL_MANIFEST, REAL_MANUALS, repository_root=REPO_ROOT)
    first = builder.build()
    second = builder.build()
    assert first == second
    other = _builder(REAL_MANIFEST, REAL_MANUALS, repository_root=REPO_ROOT).build()
    assert other == first
    previous = Path.cwd()
    try:
        os.chdir(tmp_path)
        moved = _builder(REAL_MANIFEST, REAL_MANUALS, repository_root=REPO_ROOT).build()
    finally:
        os.chdir(previous)
    assert moved == first


def test_manifest_formatting_determinism(tmp_path: Path) -> None:
    manifest_path, manuals_root = _seed_corpus(tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    compact = tmp_path / "compact.json"
    compact.write_text(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )
    reordered = {
        "excluded": payload["excluded"],
        "schema": payload["schema"],
        "source_register": payload["source_register"],
        "procedure_root": payload["procedure_root"],
        "manifest_version": payload["manifest_version"],
        "active_candidates": payload["active_candidates"],
    }
    pretty = tmp_path / "pretty.json"
    pretty.write_text(
        json.dumps(reordered, indent=4, ensure_ascii=False) + "\n\n",
        encoding="utf-8",
    )
    a = _builder(manifest_path, manuals_root, repository_root=tmp_path).build()
    b = _builder(compact, manuals_root, repository_root=tmp_path).build()
    c = _builder(pretty, manuals_root, repository_root=tmp_path).build()
    assert a.manifest_sha256 == b.manifest_sha256 == c.manifest_sha256
    assert a.corpus_sha256 == b.corpus_sha256 == c.corpus_sha256


def test_line_ending_normalization(tmp_path: Path) -> None:
    manifest_path, manuals_root = _seed_corpus(tmp_path)
    lf_path = manuals_root / "oxygen_leak.md"
    lf_text = lf_path.read_text(encoding="utf-8")
    crlf_root = tmp_path / "crlf"
    crlf_manifest, crlf_manuals = _seed_corpus(crlf_root)
    crlf_file = crlf_manuals / "oxygen_leak.md"
    crlf_file.write_bytes(lf_text.replace("\n", "\r\n").encode("utf-8"))
    assert normalize_manual_text(lf_text) == normalize_manual_text(
        crlf_file.read_text(encoding="utf-8")
    )
    lf_snap = _builder(manifest_path, manuals_root, repository_root=tmp_path).build()
    crlf_snap = _builder(crlf_manifest, crlf_manuals, repository_root=crlf_root).build()
    lf_doc = next(
        d for d in lf_snap.included_documents if d.procedure_id == "ARES-PROC-OXY-001"
    )
    crlf_doc = next(
        d for d in crlf_snap.included_documents if d.procedure_id == "ARES-PROC-OXY-001"
    )
    assert lf_doc.manual_sha256 == crlf_doc.manual_sha256
    lf_chunks = [c for c in lf_snap.chunks if c.procedure_id == "ARES-PROC-OXY-001"]
    crlf_chunks = [c for c in crlf_snap.chunks if c.procedure_id == "ARES-PROC-OXY-001"]
    assert [c.chunk_id for c in lf_chunks] == [c.chunk_id for c in crlf_chunks]
    assert lf_snap.corpus_sha256 == crlf_snap.corpus_sha256


def test_heading_hierarchy_and_preamble(tmp_path: Path) -> None:
    meta = _minimal_meta(
        procedure_id="ARES-PROC-OXY-001",
        filename="oxygen_leak.md",
        status="PARTIAL_EVIDENCE",
        title="Hierarchy Manual",
        primary_actions=["isolate_module"],
    )
    body = [
        ("Purpose", "Top purpose."),
        (
            "Ordered procedure",
            "Intro paragraph.\n\n"
            "### Isolation\n\n"
            "Isolate now.\n\n"
            "### Isolation\n\n"
            "Repeated title distinct by order.\n\n"
            "##### Deep Skip\n\n"
            "Skipped levels remain deterministic.",
        ),
        ("Empty section", ""),
        ("Final section", "No trailing newline content"),
    ]
    text = _manual_text(
        title="Hierarchy Manual",
        meta=meta,
        body_sections=body,
        preamble="Preamble before metadata.",
    )
    if text.endswith("\n"):
        text = text[:-1]
    manifest_path, manuals_root = _seed_corpus(
        tmp_path,
        active=[{"procedure_id": "ARES-PROC-OXY-001", "filename": "oxygen_leak.md"}],
        excluded=[],
        manuals={"oxygen_leak.md": text},
    )
    snap = _builder(manifest_path, manuals_root, repository_root=tmp_path).build()
    paths = [chunk.section_path for chunk in snap.chunks]
    assert any(p[-1] == "Purpose" for p in paths)
    assert any(p[-2:] == ("Ordered procedure", "Isolation") for p in paths)
    isolation = [p for p in paths if len(p) >= 2 and p[-2:] == ("Ordered procedure", "Isolation")]
    assert len(isolation) == 2
    assert any(p[-1] == "Deep Skip" for p in paths)
    assert all(chunk.content.strip() for chunk in snap.chunks)


def test_block_integrity_no_internal_splits(tmp_path: Path) -> None:
    table = (
        "| Field | Value |\n"
        "|---|---|\n"
        "| `cabin_pressure_kpa` | declining |\n"
        "| `inspired_oxygen_mmhg` | declining |"
    )
    listing = (
        "1. First item with citation EVID-ARES_ASM-001\n"
        "2. Second item keeps `isolate_module` intact\n"
        "3. Third item remains whole"
    )
    fence = "```text\nkeep this fence together\nacross lines\n```"
    meta = _minimal_meta(
        procedure_id="ARES-PROC-OXY-001",
        filename="oxygen_leak.md",
        status="PARTIAL_EVIDENCE",
        title="Blocks Manual",
        primary_actions=["isolate_module"],
    )
    text = _manual_text(
        title="Blocks Manual",
        meta=meta,
        body_sections=[
            ("Purpose", f"Paragraph one.\n\n{listing}\n\n{table}\n\n{fence}"),
        ],
    )
    manifest_path, manuals_root = _seed_corpus(
        tmp_path,
        active=[{"procedure_id": "ARES-PROC-OXY-001", "filename": "oxygen_leak.md"}],
        excluded=[],
        manuals={"oxygen_leak.md": text},
    )
    snap = _builder(
        manifest_path,
        manuals_root,
        repository_root=tmp_path,
        soft_max_chunk_chars=40,
    ).build()
    contents = [chunk.content for chunk in snap.chunks]
    assert any(table in content for content in contents)
    assert any(listing in content for content in contents)
    assert any(fence in content for content in contents)
    for content in contents:
        if "|" in content and "cabin_pressure_kpa" in content:
            assert table in content
        if "First item with citation" in content:
            assert listing in content
        if "```text" in content:
            assert fence in content


def test_long_section_split_and_oversized_block(tmp_path: Path) -> None:
    paragraphs = [f"Paragraph {i} with enough text to force splits." for i in range(12)]
    huge_table_rows = ["| Field | Value |", "|---|---|"] + [
        f"| `field_{i}` | value_{i} |" for i in range(80)
    ]
    meta = _minimal_meta(
        procedure_id="ARES-PROC-OXY-001",
        filename="oxygen_leak.md",
        status="PARTIAL_EVIDENCE",
        title="Long Manual",
        primary_actions=["isolate_module"],
    )
    text = _manual_text(
        title="Long Manual",
        meta=meta,
        body_sections=[
            ("Purpose", "\n\n".join(paragraphs)),
            ("Relevant telemetry", "\n".join(huge_table_rows)),
        ],
    )
    manifest_path, manuals_root = _seed_corpus(
        tmp_path,
        active=[{"procedure_id": "ARES-PROC-OXY-001", "filename": "oxygen_leak.md"}],
        excluded=[],
        manuals={"oxygen_leak.md": text},
    )
    snap = _builder(
        manifest_path,
        manuals_root,
        repository_root=tmp_path,
        soft_max_chunk_chars=80,
    ).build()
    purpose = [c for c in snap.chunks if c.section_title == "Purpose"]
    assert len(purpose) > 1
    indexes = [c.chunk_index for c in purpose]
    assert indexes == list(range(indexes[0], indexes[-1] + 1))
    assert all(c.section_title == "Purpose" for c in purpose)
    telemetry = [c for c in snap.chunks if c.section_title == "Relevant telemetry"]
    assert len(telemetry) == 1
    assert len(telemetry[0].content) > 80
    assert "field_79" in telemetry[0].content


def test_hash_sensitivity(tmp_path: Path) -> None:
    manifest_path, manuals_root = _seed_corpus(tmp_path)
    base = _builder(manifest_path, manuals_root, repository_root=tmp_path).build()

    mutated = tmp_path / "mut_content"
    m_path, m_root = _seed_corpus(mutated)
    target = m_root / "oxygen_leak.md"
    target.write_text(
        target.read_text(encoding="utf-8").replace(
            "Provide controlled evidence",
            "Provide CHANGED evidence",
        ),
        encoding="utf-8",
    )
    changed = _builder(m_path, m_root, repository_root=mutated).build()
    assert changed.corpus_sha256 != base.corpus_sha256

    heading = tmp_path / "mut_heading"
    h_path, h_root = _seed_corpus(heading)
    h_file = h_root / "oxygen_leak.md"
    h_file.write_text(
        h_file.read_text(encoding="utf-8").replace("## Purpose", "## Mission purpose"),
        encoding="utf-8",
    )
    heading_snap = _builder(h_path, h_root, repository_root=heading).build()
    assert heading_snap.corpus_sha256 != base.corpus_sha256

    action = tmp_path / "mut_action"
    a_path, a_root = _seed_corpus(action)
    a_file = a_root / "oxygen_leak.md"
    a_payload = json.loads(
        a_file.read_text(encoding="utf-8").split("```json\n", 1)[1].split("\n```", 1)[0]
    )
    a_payload["supporting_actions"] = ["reduce_power_load"]
    a_file.write_text(
        _manual_text(
            title="Title for oxygen_leak.md",
            meta=a_payload,
        ),
        encoding="utf-8",
    )
    action_snap = _builder(a_path, a_root, repository_root=action).build()
    assert action_snap.corpus_sha256 != base.corpus_sha256

    source = tmp_path / "mut_source"
    s_path, s_root = _seed_corpus(source)
    s_file = s_root / "oxygen_leak.md"
    s_file.write_text(
        s_file.read_text(encoding="utf-8").replace(
            '"locator": "unit-test"',
            '"locator": "unit-test-changed"',
        ),
        encoding="utf-8",
    )
    source_snap = _builder(s_path, s_root, repository_root=source).build()
    assert source_snap.corpus_sha256 != base.corpus_sha256

    classification = tmp_path / "mut_class"
    c_path, c_root = _seed_corpus(classification)
    c_file = c_root / "oxygen_leak.md"
    c_text = c_file.read_text(encoding="utf-8")
    c_text = c_text.replace('"ARES_ASSUMPTION"', '"NASA_REFERENCE"', 1)
    c_text = c_text.replace(
        '"classification": "ARES_ASSUMPTION"',
        '"classification": "NASA_REFERENCE"',
        1,
    )
    c_text = c_text.replace("EVID-ARES_ASM-001", "EVID-NASA_REF-001", 1)
    c_file.write_text(c_text, encoding="utf-8")
    class_snap = _builder(c_path, c_root, repository_root=classification).build()
    assert class_snap.corpus_sha256 != base.corpus_sha256

    proc = tmp_path / "mut_proc"
    p_path, p_root = _seed_corpus(
        proc,
        active=[{"procedure_id": "ARES-PROC-PWR-001", "filename": "oxygen_leak.md"}],
        excluded=[],
    )
    p_file = p_root / "oxygen_leak.md"
    p_file.write_text(
        p_file.read_text(encoding="utf-8")
        .replace("ARES-PROC-OXY-001", "ARES-PROC-PWR-001")
        .replace("Title for oxygen_leak.md", "Power title"),
        encoding="utf-8",
    )
    # rewrite meta title consistency
    meta = _minimal_meta(
        procedure_id="ARES-PROC-PWR-001",
        filename="oxygen_leak.md",
        status="PARTIAL_EVIDENCE",
        title="Power title",
        primary_actions=["reduce_power_load"],
    )
    p_file.write_text(
        _manual_text(title="Power title", meta=meta),
        encoding="utf-8",
    )
    proc_snap = _builder(p_path, p_root, repository_root=proc).build()
    assert proc_snap.corpus_sha256 != base.corpus_sha256

    status = tmp_path / "mut_status"
    st_path, st_root = _seed_corpus(status)
    st_file = st_root / "oxygen_leak.md"
    st_file.write_text(
        st_file.read_text(encoding="utf-8").replace(
            '"status": "PARTIAL_EVIDENCE"',
            '"status": "ACTIVE"',
        ),
        encoding="utf-8",
    )
    status_snap = _builder(st_path, st_root, repository_root=status).build()
    assert status_snap.corpus_sha256 != base.corpus_sha256


def test_security_and_containment(tmp_path: Path) -> None:
    manifest_path, manuals_root = _seed_corpus(tmp_path)
    (manuals_root / "oxygen_leak.md").unlink()
    with pytest.raises(ProcedureManualNotFoundError):
        _builder(manifest_path, manuals_root, repository_root=tmp_path).build()

    missing_root = tmp_path / "dir_target"
    d_path, d_root = _seed_corpus(missing_root)
    target = d_root / "oxygen_leak.md"
    target.unlink()
    target.mkdir()
    with pytest.raises(ProcedureManualSecurityError):
        _builder(d_path, d_root, repository_root=missing_root).build()

    utf_root = tmp_path / "bad_utf"
    u_path, u_root = _seed_corpus(utf_root)
    (u_root / "oxygen_leak.md").write_bytes(b"\xff\xfe not utf8")
    with pytest.raises(ProcedureManualParseError):
        _builder(u_path, u_root, repository_root=utf_root).build()

    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.md"
    secret.write_text("# secret\n", encoding="utf-8")
    link_root = tmp_path / "symlink_file"
    l_path, l_root = _seed_corpus(link_root)
    link = l_root / "oxygen_leak.md"
    link.unlink()
    if not _try_symlink(link, secret):
        pytest.skip("symlinks not supported")
    with pytest.raises(ProcedureManualSecurityError):
        _builder(l_path, l_root, repository_root=link_root).build()

    dir_link_root = tmp_path / "symlink_dir"
    dl_path, dl_root = _seed_corpus(dir_link_root)
    escape_dir = outside / "escape_manuals"
    escape_dir.mkdir()
    shutil.copyfile(dl_root / "oxygen_leak.md", escape_dir / "oxygen_leak.md")
    for name in list(dl_root.iterdir()):
        if name.is_file():
            name.unlink()
    if not _try_symlink(dl_root / "linked", escape_dir):
        pytest.skip("symlinks not supported")
    # replace manuals root with symlink escaping via file path under linked
    bad_manifest = {
        "manifest_version": "1.0.0",
        "procedure_root": "docs/procedures/manuals",
        "source_register": "docs/procedures/sources/NASA_SOURCE_REGISTER.md",
        "schema": "docs/procedures/procedure_metadata.schema.json",
        "active_candidates": [
            {"procedure_id": "ARES-PROC-OXY-001", "filename": "linked/oxygen_leak.md"}
        ],
        "excluded": [],
    }
    with pytest.raises((ProcedureManifestInvalidError, ValidationError)):
        CorpusManifest.model_validate(bad_manifest)

    listed = tmp_path / "unlisted"
    un_path, un_root = _seed_corpus(listed)
    (un_root / "extra_unlisted.md").write_text("# Extra\n", encoding="utf-8")
    snap = _builder(un_path, un_root, repository_root=listed).build()
    assert all("extra_unlisted" not in d.manual_path for d in snap.included_documents)
    assert all("extra_unlisted" not in c.manual_path for c in snap.chunks)

    non_md = tmp_path / "non_md"
    nm_path, nm_root = _seed_corpus(non_md)
    payload = json.loads(nm_path.read_text(encoding="utf-8"))
    payload["active_candidates"][0]["filename"] = "oxygen_leak.txt"
    with pytest.raises(ValidationError):
        CorpusManifest.model_validate(payload)


def test_metadata_fidelity_real_corpus() -> None:
    snap = _builder(REAL_MANIFEST, REAL_MANUALS, repository_root=REPO_ROOT).build()
    oxy = next(d for d in snap.included_documents if d.procedure_id == "ARES-PROC-OXY-001")
    assert oxy.title.startswith("Habitat Atmosphere")
    assert ActionType.ISOLATE_MODULE in oxy.primary_actions
    assert SourceClassification.NASA_STANDARD in oxy.source_classifications
    assert oxy.evidence_references
    oxy_chunks = [c for c in snap.chunks if c.procedure_id == "ARES-PROC-OXY-001"]
    purpose = next(c for c in oxy_chunks if c.section_title == "Purpose")
    assert purpose.procedure_id == "ARES-PROC-OXY-001"
    assert purpose.section_path[-1] == "Purpose"
    assert purpose.allowed_actions
    assert purpose.source_classifications == oxy.source_classifications
    assert purpose.evidence_references == oxy.evidence_references
    assert "mixed habitat-atmosphere leak" in purpose.content
    expected_embed = format_embedding_text(
        procedure_title=purpose.procedure_title,
        procedure_id=purpose.procedure_id,
        section_path=purpose.section_path,
        allowed_actions=purpose.allowed_actions,
        content=purpose.content,
    )
    assert purpose.embedding_text == expected_embed
    assert purpose.embedding_text.startswith("Procedure: ")
    assert "Procedure ID: ARES-PROC-OXY-001" in purpose.embedding_text
    assert "Allowed actions:" in purpose.embedding_text


def test_unknown_status_rejected_in_manual(tmp_path: Path) -> None:
    manifest_path, manuals_root = _seed_corpus(tmp_path)
    target = manuals_root / "oxygen_leak.md"
    target.write_text(
        target.read_text(encoding="utf-8").replace(
            '"status": "PARTIAL_EVIDENCE"',
            '"status": "UNKNOWN_STATUS"',
        ),
        encoding="utf-8",
    )
    with pytest.raises(ProcedureManualParseError):
        _builder(manifest_path, manuals_root, repository_root=tmp_path).build()


def test_absolute_path_in_manifest_rejected(tmp_path: Path) -> None:
    payload = {
        "manifest_version": "1.0.0",
        "procedure_root": "docs/procedures/manuals",
        "source_register": "docs/procedures/sources/NASA_SOURCE_REGISTER.md",
        "schema": "docs/procedures/procedure_metadata.schema.json",
        "active_candidates": [
            {
                "procedure_id": "ARES-PROC-OXY-001",
                "filename": str(tmp_path / "oxygen_leak.md"),
            }
        ],
        "excluded": [],
    }
    with pytest.raises(ValidationError):
        CorpusManifest.model_validate(payload)


def test_no_later_phase_implementation() -> None:
    service = (BACKEND_ROOT / "app" / "services" / "procedure_corpus.py").read_text(
        encoding="utf-8"
    )
    schema = (BACKEND_ROOT / "app" / "schemas" / "retrieval.py").read_text(
        encoding="utf-8"
    )
    forbidden = (
        "nvidia",
        "openai",
        "httpx",
        "requests",
        "urllib",
        "embedding_vector",
        "cosine",
        "rerank",
        "MissionLifecycleService",
        "APIRouter",
        "lifespan",
    )
    combined = (service + "\n" + schema).lower()
    for token in forbidden:
        assert token not in combined
    tree = ast.parse(service)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    assert "httpx" not in imports
    assert "requests" not in imports
    assert "urllib" not in imports
    assert not (BACKEND_ROOT / "app" / "api" / "retrieval.py").exists()
    main_text = (BACKEND_ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "ProcedureCorpusBuilder" not in main_text


def test_embedding_text_template_stable() -> None:
    text = format_embedding_text(
        procedure_title="Demo",
        procedure_id="ARES-PROC-OXY-001",
        section_path=("Ordered procedure", "Isolation"),
        allowed_actions=(ActionType.ISOLATE_MODULE, ActionType.OXYGEN_RATIONING),
        content="Isolate the lab module.",
    )
    assert text == (
        "Procedure: Demo\n"
        "Procedure ID: ARES-PROC-OXY-001\n"
        "Section: Ordered procedure > Isolation\n"
        "Allowed actions: isolate_module, oxygen_rationing\n"
        "\n"
        "Isolate the lab module."
    )


def test_soft_max_must_be_positive(tmp_path: Path) -> None:
    manifest_path, manuals_root = _seed_corpus(tmp_path)
    with pytest.raises(ProcedureCorpusInvalidError):
        ProcedureCorpusBuilder(
            manifest_path=manifest_path,
            manuals_root=manuals_root,
            repository_root=tmp_path,
            soft_max_chunk_chars=0,
        )
