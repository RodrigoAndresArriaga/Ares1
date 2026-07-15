# validate ARES-1 procedure corpus layout, metadata, and contracts
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

REQUIRED_MANUALS: tuple[str, ...] = (
    "oxygen_leak.md",
    "solar_array_failure.md",
    "power_rationing.md",
    "eva_repair.md",
    "comms_blackout.md",
    "co2_scrubber_failure.md",
)

REQUIRED_H2_SECTIONS: tuple[str, ...] = (
    "Procedure metadata",
    "Purpose",
    "Scope and applicability",
    "Entry conditions",
    "Relevant telemetry",
    "Immediate priorities",
    "Ordered procedure",
    "Operational constraints",
    "Prohibited or unsupported actions",
    "Abort and escalation conditions",
    "Success and termination conditions",
    "Simulator action mapping",
    "Evidence and source classifications",
    "ARES assumptions and release-configuration dependencies",
    "Known limitations",
    "Retrieval test cases",
    "Revision history",
)

PRODUCTION_ACTIONS: frozenset[str] = frozenset(
    {
        "reduce_power_load",
        "isolate_module",
        "oxygen_rationing",
        "repair_solar_array",
        "delay_rover_use",
        "send_emergency_packet",
    }
)

# executor aliases from ActionExecutor::parseActivityLevel
CPP_OXYGEN_LEVELS: frozenset[str] = frozenset(
    {
        "sleep",
        "rest",
        "resting",
        "nominal",
        "nominal_work",
        "nominalwork",
        "high",
        "high_workload",
        "highworkload",
        "recovery",
    }
)

TRUSTED_SCENARIO_IDS: frozenset[str] = frozenset({"mars_hab_atmosphere_solar_failure"})

SOURCE_CLASSIFICATIONS: frozenset[str] = frozenset(
    {
        "NASA_STANDARD",
        "NASA_REFERENCE",
        "DERIVED_PHYSICS",
        "ARES_ASSUMPTION",
        "ARES_RELEASE_CONFIGURATION",
    }
)

# serialized field -> accepted json_location prefixes / exact paths
TELEMETRY_ALLOWLIST: dict[str, frozenset[str]] = {
    "scenario_id": frozenset({"root", "scenario_id"}),
    "plan_id": frozenset({"root", "plan_id"}),
    "outcome": frozenset({"root", "outcome"}),
    "valid_plan": frozenset({"root", "valid_plan"}),
    "failure_reasons": frozenset({"root", "failure_reasons"}),
    "metrics": frozenset({"root", "metrics"}),
    "timeline": frozenset({"root", "timeline"}),
    "telemetry_history": frozenset({"root", "telemetry_history"}),
    "minimum_inspired_o2_mmhg": frozenset({"metrics", "metrics.minimum_inspired_o2_mmhg"}),
    "minimum_cabin_pressure_kpa": frozenset({"metrics", "metrics.minimum_cabin_pressure_kpa"}),
    "maximum_co2_one_hour_avg_mmhg": frozenset(
        {"metrics", "metrics.maximum_co2_one_hour_avg_mmhg"}
    ),
    "minimum_battery_soc_percent": frozenset({"metrics", "metrics.minimum_battery_soc_percent"}),
    "minimum_power_margin_kw": frozenset({"metrics", "metrics.minimum_power_margin_kw"}),
    "minimum_temperature_margin_c": frozenset({"metrics", "metrics.minimum_temperature_margin_c"}),
    "minimum_eva_safe_return_margin_min": frozenset(
        {"metrics", "metrics.minimum_eva_safe_return_margin_min"}
    ),
    "minimum_crew_spo2_percent": frozenset({"metrics", "metrics.minimum_crew_spo2_percent"}),
    "maximum_crew_fatigue_percent": frozenset({"metrics", "metrics.maximum_crew_fatigue_percent"}),
    "eva_completed": frozenset({"metrics", "metrics.eva_completed"}),
    "communications_sent": frozenset({"metrics", "metrics.communications_sent"}),
    "time_to_stabilization_hr": frozenset({"metrics", "metrics.time_to_stabilization_hr"}),
    "simulation_time_min": frozenset(
        {"telemetry_history[]", "telemetry_history[].simulation_time_min"}
    ),
    "has_warning": frozenset({"telemetry_history[]", "telemetry_history[].has_warning"}),
    "has_critical": frozenset({"telemetry_history[]", "telemetry_history[].has_critical"}),
    "cabin_pressure_kpa": frozenset(
        {"telemetry_history[].habitat", "telemetry_history[].habitat.cabin_pressure_kpa"}
    ),
    "inspired_oxygen_mmhg": frozenset(
        {"telemetry_history[].habitat", "telemetry_history[].habitat.inspired_oxygen_mmhg"}
    ),
    "co2_one_hour_avg_mmhg": frozenset(
        {"telemetry_history[].habitat", "telemetry_history[].habitat.co2_one_hour_avg_mmhg"}
    ),
    "oxygen_hours_remaining": frozenset(
        {"telemetry_history[].habitat", "telemetry_history[].habitat.oxygen_hours_remaining"}
    ),
    "battery_soc_percent": frozenset(
        {"telemetry_history[].habitat", "telemetry_history[].habitat.battery_soc_percent"}
    ),
    "solar_generation_percent": frozenset(
        {"telemetry_history[].habitat", "telemetry_history[].habitat.solar_generation_percent"}
    ),
    "power_margin_kw": frozenset(
        {"telemetry_history[].habitat", "telemetry_history[].habitat.power_margin_kw"}
    ),
    "cabin_temperature_c": frozenset(
        {"telemetry_history[].habitat", "telemetry_history[].habitat.cabin_temperature_c"}
    ),
    "temperature_margin_c": frozenset(
        {"telemetry_history[].habitat", "telemetry_history[].habitat.temperature_margin_c"}
    ),
    "eva_safe_return_margin_min": frozenset(
        {"telemetry_history[].habitat", "telemetry_history[].habitat.eva_safe_return_margin_min"}
    ),
    "mission_status": frozenset(
        {"telemetry_history[].habitat", "telemetry_history[].habitat.mission_status"}
    ),
    "crew_id": frozenset({"telemetry_history[].crew[]", "telemetry_history[].crew[].crew_id"}),
    "display_name": frozenset(
        {"telemetry_history[].crew[]", "telemetry_history[].crew[].display_name"}
    ),
    "activity": frozenset({"telemetry_history[].crew[]", "telemetry_history[].crew[].activity"}),
    "heart_rate_bpm": frozenset(
        {"telemetry_history[].crew[]", "telemetry_history[].crew[].heart_rate_bpm"}
    ),
    "respiratory_rate_bpm": frozenset(
        {"telemetry_history[].crew[]", "telemetry_history[].crew[].respiratory_rate_bpm"}
    ),
    "spo2_percent": frozenset(
        {"telemetry_history[].crew[]", "telemetry_history[].crew[].spo2_percent"}
    ),
    "core_temperature_c": frozenset(
        {"telemetry_history[].crew[]", "telemetry_history[].crew[].core_temperature_c"}
    ),
    "fatigue_percent": frozenset(
        {"telemetry_history[].crew[]", "telemetry_history[].crew[].fatigue_percent"}
    ),
    "cognitive_performance_percent": frozenset(
        {"telemetry_history[].crew[]", "telemetry_history[].crew[].cognitive_performance_percent"}
    ),
    "physical_performance_percent": frozenset(
        {"telemetry_history[].crew[]", "telemetry_history[].crew[].physical_performance_percent"}
    ),
    "health_status": frozenset(
        {"telemetry_history[].crew[]", "telemetry_history[].crew[].health_status"}
    ),
    "alarms": frozenset({"telemetry_history[].crew[]", "telemetry_history[].crew[].alarms"}),
    "events": frozenset(
        {
            "telemetry_history[].events",
            "telemetry_history[].events[]",
            "timeline",
            "timeline[]",
        }
    ),
    "time_min": frozenset(
        {
            "telemetry_history[].events[]",
            "timeline[]",
            "telemetry_history[].events[].time_min",
            "timeline[].time_min",
        }
    ),
    "event_type": frozenset(
        {
            "telemetry_history[].events[]",
            "timeline[]",
            "telemetry_history[].events[].event_type",
            "timeline[].event_type",
        }
    ),
    "message": frozenset(
        {
            "telemetry_history[].events[]",
            "timeline[]",
            "telemetry_history[].events[].message",
            "timeline[].message",
        }
    ),
    "severity": frozenset(
        {
            "telemetry_history[].events[]",
            "timeline[]",
            "telemetry_history[].events[].severity",
            "timeline[].severity",
        }
    ),
    "active_actions": frozenset(
        {"telemetry_history[].active_actions", "telemetry_history[].active_actions[]"}
    ),
    "action_index": frozenset({"telemetry_history[].active_actions[]"}),
    "type": frozenset({"telemetry_history[].active_actions[]"}),
    "status": frozenset({"telemetry_history[].active_actions[]"}),
    "actual_start_min": frozenset({"telemetry_history[].active_actions[]"}),
    "elapsed_min": frozenset({"telemetry_history[].active_actions[]"}),
    "progress_fraction": frozenset({"telemetry_history[].active_actions[]"}),
    "assigned_crew_id": frozenset({"telemetry_history[].active_actions[]"}),
    "eva_crew_id": frozenset({"telemetry_history[].active_actions[]"}),
    "assigned_crew_ids": frozenset({"telemetry_history[].active_actions[]"}),
    "failure_reason": frozenset({"telemetry_history[].active_actions[]"}),
}

FORBIDDEN_PHRASES: tuple[str, ...] = (
    "official nasa procedure",
    "nasa-approved",
    "flight-certified",
    "validated by nasa",
    "guarantees survival",
    "ensures survival",
    "guaranteed stabilization",
    "survival_probability",
    "hab-2",
)

DISCLAIMER_SAFE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bnot\s+an\s+official\s+nasa\s+procedure\b", re.IGNORECASE),
    re.compile(r"\bis\s+not\s+flight-certified\b", re.IGNORECASE),
    re.compile(r"\bnot\s+flight-certified\b", re.IGNORECASE),
    re.compile(
        r"must\s+never\s+be\s+described\s+as\s+nasa-approved,\s*flight-certified,\s*"
        r"validated\s+by\s+nasa",
        re.IGNORECASE,
    ),
)

INVALID_OXYGEN_LEVEL_RE = re.compile(
    r"""(?ix)
    \blevel\b[^.\n]{0,40}?
    [`'\"]?(low|severe|maximum|emergency|conservative|moderate)[`'\"]?
    """
)

MAPPING_ACTION_CELL_RE = re.compile(
    r"\|\s*[^|]+\|\s*`([^`]+)`\s*\|",
)

METADATA_JSON_FENCE_RE = re.compile(
    r"##\s+Procedure metadata\s*\n+(?:(?!##\s).|\n)*?```json\s*\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)

H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


@dataclass
class ValidationReport:
    status: str = "PASS"
    manuals_checked: list[str] = field(default_factory=list)
    active_candidates: list[dict[str, str]] = field(default_factory=list)
    excluded: list[dict[str, str]] = field(default_factory=list)
    metadata_results: dict[str, Any] = field(default_factory=dict)
    action_results: dict[str, Any] = field(default_factory=dict)
    telemetry_results: dict[str, Any] = field(default_factory=dict)
    source_classification_results: dict[str, Any] = field(default_factory=dict)
    deferred_policy_results: dict[str, Any] = field(default_factory=dict)
    forbidden_claim_results: dict[str, Any] = field(default_factory=dict)
    oxygen_rationing_vocabulary: dict[str, Any] = field(default_factory=dict)
    content_hashes: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        self.errors.append(message)
        self.status = "FAIL"

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)


def find_repo_root(start: Path | None = None) -> Path:
    here = (start or Path(__file__).resolve()).resolve()
    if here.is_file():
        here = here.parent
    for candidate in [here, *here.parents]:
        marker = candidate / "docs" / "procedures" / "procedure_metadata.schema.json"
        sim = candidate / "Simulator"
        if marker.is_file() and sim.is_dir():
            return candidate
    raise FileNotFoundError("Unable to locate ARES-1 repository root from script path")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def discover_production_actions(repo_root: Path) -> frozenset[str]:
    actions = set(PRODUCTION_ACTIONS)
    actions_py = repo_root / "backend" / "app" / "schemas" / "actions.py"
    if actions_py.is_file():
        text = actions_py.read_text(encoding="utf-8")
        for match in re.finditer(r'=\s*"([a-z_]+)"', text):
            value = match.group(1)
            if value in PRODUCTION_ACTIONS:
                actions.add(value)
    enums = repo_root / "Simulator" / "include" / "Enums.hpp"
    if enums.is_file():
        text = enums.read_text(encoding="utf-8")
        # existence check only; serialized names come from JsonIO / PRODUCTION_ACTIONS
        if "ReducePowerLoad" not in text:
            pass
    return frozenset(actions)


def extract_metadata_json(text: str, path: Path, report: ValidationReport) -> dict[str, Any] | None:
    matches = list(METADATA_JSON_FENCE_RE.finditer(text))
    if not matches:
        report.add_error(f"{path.name}: missing fenced JSON under ## Procedure metadata")
        return None
    if len(matches) > 1:
        report.add_error(f"{path.name}: ambiguous multiple metadata JSON fences")
        return None
    raw = matches[0].group(1)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        report.add_error(f"{path.name}: malformed metadata JSON: {exc}")
        return None
    if not isinstance(data, dict):
        report.add_error(f"{path.name}: metadata JSON must be an object")
        return None
    return data


def validate_section_order(text: str, path: Path, report: ValidationReport) -> None:
    if not H1_RE.search(text):
        report.add_error(f"{path.name}: missing level-one procedure title")
    found = H2_RE.findall(text)
    if len(found) != len(set(found)):
        report.add_error(f"{path.name}: duplicate ## headings detected")
    required = list(REQUIRED_H2_SECTIONS)
    # ignore incidental H2s? Standard requires exact required order among required sections.
    filtered = [h for h in found if h in required]
    if filtered != required:
        report.add_error(
            f"{path.name}: required ## section order mismatch; "
            f"found={filtered!r} expected={required!r}"
        )
    missing = [h for h in required if h not in found]
    for heading in missing:
        report.add_error(f"{path.name}: missing required section ## {heading}")


def strip_disclaimer_spans(text: str) -> str:
    cleaned = text
    for pattern in DISCLAIMER_SAFE_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    return cleaned


def scan_forbidden_claims(text: str, path: Path, report: ValidationReport) -> list[str]:
    hits: list[str] = []
    cleaned = strip_disclaimer_spans(text)
    lower = cleaned.lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in lower:
            hits.append(phrase)
            report.add_error(f"{path.name}: forbidden claim phrase detected: {phrase!r}")
    report.forbidden_claim_results[path.name] = {"hits": hits, "ok": not hits}
    return hits


def validate_actions_in_metadata(
    meta: dict[str, Any],
    path: Path,
    allowed: frozenset[str],
    report: ValidationReport,
) -> None:
    details: dict[str, Any] = {"unknown": []}
    for key in ("primary_actions", "supporting_actions", "prohibited_actions"):
        values = meta.get(key, [])
        if not isinstance(values, list):
            report.add_error(f"{path.name}: {key} must be an array")
            continue
        for action in values:
            if action not in allowed:
                details["unknown"].append(action)
                report.add_error(f"{path.name}: unknown action in {key}: {action!r}")
    report.action_results[path.name] = details


def validate_action_mapping_table(
    text: str,
    path: Path,
    allowed: frozenset[str],
    report: ValidationReport,
) -> None:
    section_match = re.search(
        r"##\s+Simulator action mapping\s*\n(.*?)(?=\n##\s|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not section_match:
        report.add_error(f"{path.name}: missing Simulator action mapping section body")
        return
    body = section_match.group(1)
    for line in body.splitlines():
        if not line.strip().startswith("|"):
            continue
        if "Exact action type" in line or re.match(r"^\|\s*-+", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        cell = cells[1]
        tick = re.fullmatch(r"`([^`]+)`", cell)
        if not tick:
            continue
        value = tick.group(1)
        if value in allowed or value == "INFORMATIONAL_ONLY":
            continue
        report.add_error(
            f"{path.name}: invalid Exact action type in mapping table: {value!r}"
        )


def validate_telemetry(
    meta: dict[str, Any],
    path: Path,
    report: ValidationReport,
) -> None:
    deps = meta.get("telemetry_dependencies", [])
    details: dict[str, Any] = {"rejected": [], "checked": 0}
    if not isinstance(deps, list):
        report.add_error(f"{path.name}: telemetry_dependencies must be an array")
        report.telemetry_results[path.name] = details
        return
    for dep in deps:
        details["checked"] += 1
        if not isinstance(dep, dict):
            report.add_error(f"{path.name}: telemetry dependency must be an object")
            continue
        field_name = dep.get("field")
        location = dep.get("json_location")
        unit = dep.get("unit")
        roles = dep.get("condition_roles")
        if not isinstance(field_name, str) or not field_name:
            report.add_error(f"{path.name}: telemetry dependency missing field")
            continue
        if not isinstance(location, str) or not location:
            report.add_error(f"{path.name}: telemetry {field_name}: missing json_location")
            continue
        if not isinstance(unit, str) or not unit:
            report.add_error(f"{path.name}: telemetry {field_name}: missing unit")
            continue
        if not isinstance(roles, list) or not roles:
            report.add_error(f"{path.name}: telemetry {field_name}: invalid condition_roles")
            continue
        allowed_locs = TELEMETRY_ALLOWLIST.get(field_name)
        if allowed_locs is None:
            details["rejected"].append(field_name)
            report.add_error(
                f"{path.name}: unknown or non-serialized telemetry field: {field_name!r}"
            )
            continue
        ok_location = location in allowed_locs or any(
            location.startswith(prefix.rstrip(".")) for prefix in allowed_locs
        )
        # accept exact authored locations that contain the field path suffix
        if not ok_location:
            if any(location.endswith(field_name) or field_name in location for _ in [0]):
                # require startswith of a known root family
                roots = (
                    "telemetry_history",
                    "metrics",
                    "root",
                    "timeline",
                )
                ok_location = location.startswith(roots)
            if not ok_location:
                details["rejected"].append(field_name)
                report.add_error(
                    f"{path.name}: telemetry {field_name} has invalid json_location "
                    f"{location!r}"
                )
    report.telemetry_results[path.name] = details


def validate_scenarios(meta: dict[str, Any], path: Path, report: ValidationReport) -> None:
    scenarios = meta.get("applicable_scenarios", [])
    if not isinstance(scenarios, list):
        report.add_error(f"{path.name}: applicable_scenarios must be an array")
        return
    for scenario in scenarios:
        if scenario not in TRUSTED_SCENARIO_IDS:
            report.add_error(f"{path.name}: unknown scenario ID: {scenario!r}")


def validate_source_classifications(
    meta: dict[str, Any],
    path: Path,
    report: ValidationReport,
) -> None:
    details: dict[str, Any] = {"ok": True}
    classifications = meta.get("source_classifications", [])
    if not isinstance(classifications, list):
        report.add_error(f"{path.name}: source_classifications must be an array")
        details["ok"] = False
    else:
        for item in classifications:
            if item not in SOURCE_CLASSIFICATIONS:
                details["ok"] = False
                report.add_error(f"{path.name}: invalid source classification: {item!r}")
    evidence = meta.get("evidence_references", [])
    if not isinstance(evidence, list):
        report.add_error(f"{path.name}: evidence_references must be an array")
        details["ok"] = False
    else:
        required_keys = ("evidence_id", "classification", "source_title", "locator", "supports")
        for ref in evidence:
            if not isinstance(ref, dict):
                report.add_error(f"{path.name}: evidence reference must be an object")
                details["ok"] = False
                continue
            for key in required_keys:
                if key not in ref or ref[key] in (None, ""):
                    details["ok"] = False
                    report.add_error(
                        f"{path.name}: evidence reference missing {key}"
                    )
            classification = ref.get("classification")
            if classification not in SOURCE_CLASSIFICATIONS:
                details["ok"] = False
                report.add_error(
                    f"{path.name}: evidence classification invalid: {classification!r}"
                )
    report.source_classification_results[path.name] = details


def validate_deferred_policy(
    meta: dict[str, Any],
    text: str,
    path: Path,
    manifest: dict[str, Any],
    report: ValidationReport,
) -> None:
    name = path.name
    active_ids = {e["procedure_id"] for e in manifest.get("active_candidates", [])}
    active_files = {e["filename"] for e in manifest.get("active_candidates", [])}
    excluded = {e["filename"]: e for e in manifest.get("excluded", [])}
    details: dict[str, Any] = {"checked": True}

    if name == "comms_blackout.md":
        if meta.get("status") != "DEFERRED_SOURCE_REQUIRED":
            report.add_error(f"{name}: status must be DEFERRED_SOURCE_REQUIRED")
        if name in active_files or meta.get("procedure_id") in active_ids:
            report.add_error(f"{name}: must not appear in active_candidates")
        if name not in excluded:
            report.add_error(f"{name}: must appear in excluded")
        lower = text.lower()
        if "not serialized" not in lower and "communication-window" not in lower:
            if "no serialized window" not in lower:
                report.add_error(
                    f"{name}: Known limitations must state communication-window "
                    "state is not serialized (or equivalent)"
                )
        elif "known limitations" in lower:
            details["limitations_ok"] = True
    elif name == "co2_scrubber_failure.md":
        if meta.get("status") != "DEFERRED_SOURCE_REQUIRED":
            report.add_error(f"{name}: status must be DEFERRED_SOURCE_REQUIRED")
        if name in active_files or meta.get("procedure_id") in active_ids:
            report.add_error(f"{name}: must not appear in active_candidates")
        if name not in excluded:
            report.add_error(f"{name}: must appear in excluded")
        lower = text.lower()
        if (
            "no direct recovery action" not in lower
            and "no direct scrubber-repair" not in lower
            and "scrubber-repair" not in lower
            and "no direct recovery" not in lower
        ):
            report.add_error(
                f"{name}: Known limitations must state no direct scrubber-repair "
                "action (or equivalent)"
            )
    report.deferred_policy_results[name] = details


def audit_oxygen_levels(text: str, path: Path, report: ValidationReport) -> list[str]:
    used: list[str] = []
    # concrete quoted level assignments only
    for match in re.finditer(
        r"""(?ix)\blevel\b\s*[:=]\s*[`'\"]([a-z_]+)[`'\"]""",
        text,
    ):
        used.append(match.group(1))
    invalid_hits = list(INVALID_OXYGEN_LEVEL_RE.finditer(text))
    for hit in invalid_hits:
        line_no = text.count("\n", 0, hit.start()) + 1
        report.add_error(
            f"{path.name}:{line_no}: unsupported oxygen_rationing level token "
            f"{hit.group(1)!r}"
        )
    return used


def validate_manifest_consistency(
    metas: dict[str, dict[str, Any]],
    manifest: dict[str, Any],
    report: ValidationReport,
) -> None:
    active = manifest.get("active_candidates", [])
    excluded = manifest.get("excluded", [])
    if not isinstance(active, list) or not isinstance(excluded, list):
        report.add_error("corpus_manifest.json: active_candidates/excluded must be arrays")
        return
    active_ids = [e.get("procedure_id") for e in active]
    active_files = [e.get("filename") for e in active]
    excl_ids = [e.get("procedure_id") for e in excluded]
    excl_files = [e.get("filename") for e in excluded]
    if len(active_ids) != len(set(active_ids)) or len(active_files) != len(set(active_files)):
        report.add_error("corpus_manifest.json: duplicate active candidate entries")
    if len(excl_ids) != len(set(excl_ids)) or len(excl_files) != len(set(excl_files)):
        report.add_error("corpus_manifest.json: duplicate excluded entries")
    overlap = set(active_files) & set(excl_files)
    if overlap:
        report.add_error(f"corpus_manifest.json: files in both lists: {sorted(overlap)}")
    overlap_ids = set(active_ids) & set(excl_ids)
    if overlap_ids:
        report.add_error(
            f"corpus_manifest.json: procedure_ids in both lists: {sorted(overlap_ids)}"
        )

    expected_active = {
        "oxygen_leak.md",
        "solar_array_failure.md",
        "power_rationing.md",
        "eva_repair.md",
    }
    expected_excl = {"comms_blackout.md", "co2_scrubber_failure.md"}
    if set(active_files) != expected_active:
        report.add_error(f"corpus_manifest.json: unexpected active set {active_files}")
    if set(excl_files) != expected_excl:
        report.add_error(f"corpus_manifest.json: unexpected excluded set {excl_files}")

    id_by_file = {name: meta.get("procedure_id") for name, meta in metas.items()}
    for entry in active + excluded:
        filename = entry.get("filename")
        procedure_id = entry.get("procedure_id")
        if filename not in metas:
            report.add_error(f"corpus_manifest.json: missing manual for {filename}")
            continue
        if id_by_file.get(filename) != procedure_id:
            report.add_error(
                f"corpus_manifest.json: procedure_id mismatch for {filename}: "
                f"manifest={procedure_id!r} metadata={id_by_file.get(filename)!r}"
            )


def validate_layout(repo_root: Path, report: ValidationReport) -> Path:
    procedures = repo_root / "docs" / "procedures"
    manuals = procedures / "manuals"
    sources = procedures / "sources"
    required_files = [
        procedures / "PROCEDURE_STANDARD.md",
        procedures / "PROCEDURE_INDEX.md",
        procedures / "procedure_metadata.schema.json",
        procedures / "corpus_manifest.json",
        sources / "NASA_SOURCE_REGISTER.md",
    ]
    for path in required_files:
        if not path.is_file():
            report.add_error(f"missing required file: {path.relative_to(repo_root).as_posix()}")
    if not manuals.is_dir():
        report.add_error("missing docs/procedures/manuals/")
    else:
        for name in REQUIRED_MANUALS:
            if not (manuals / name).is_file():
                report.add_error(f"missing manual: docs/procedures/manuals/{name}")
    legacy = repo_root / "docs" / "NASA-Manuals"
    if legacy.exists():
        leftover = [p.name for p in legacy.rglob("*") if p.is_file()]
        if leftover:
            report.add_error(f"docs/NASA-Manuals/ still contains files: {leftover}")
        else:
            report.add_warning("docs/NASA-Manuals/ exists but is empty; remove the directory")
    return manuals


def validate_corpus(repo_root: Path | None = None) -> ValidationReport:
    report = ValidationReport()
    root = repo_root or find_repo_root()
    manuals_dir = validate_layout(root, report)
    schema_path = root / "docs" / "procedures" / "procedure_metadata.schema.json"
    manifest_path = root / "docs" / "procedures" / "corpus_manifest.json"
    register_path = root / "docs" / "procedures" / "sources" / "NASA_SOURCE_REGISTER.md"

    if not schema_path.is_file() or not manifest_path.is_file():
        return report

    schema = load_json(schema_path)
    try:
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
    except SchemaError as exc:
        report.add_error(f"procedure_metadata.schema.json invalid: {exc}")
        return report

    manifest = load_json(manifest_path)
    report.active_candidates = list(manifest.get("active_candidates", []))
    report.excluded = list(manifest.get("excluded", []))

    allowed_actions = discover_production_actions(root)
    metas: dict[str, dict[str, Any]] = {}
    oxygen_used: list[str] = []

    for name in REQUIRED_MANUALS:
        path = manuals_dir / name
        if not path.is_file():
            continue
        report.manuals_checked.append(name)
        report.content_hashes[name] = sha256_file(path)
        text = path.read_text(encoding="utf-8")
        validate_section_order(text, path, report)
        scan_forbidden_claims(text, path, report)
        oxygen_used.extend(audit_oxygen_levels(text, path, report))
        meta = extract_metadata_json(text, path, report)
        if meta is None:
            report.metadata_results[name] = {"ok": False}
            continue
        metas[name] = meta
        try:
            validator.validate(meta)
            schema_ok = True
            schema_error = None
        except ValidationError as exc:
            schema_ok = False
            schema_error = exc.message
            report.add_error(f"{name}: schema validation failed: {exc.message}")
        if meta.get("filename") != name:
            report.add_error(
                f"{name}: metadata filename {meta.get('filename')!r} does not match file"
            )
        validate_actions_in_metadata(meta, path, allowed_actions, report)
        validate_action_mapping_table(text, path, allowed_actions, report)
        validate_telemetry(meta, path, report)
        validate_scenarios(meta, path, report)
        validate_source_classifications(meta, path, report)
        validate_deferred_policy(meta, text, path, manifest, report)
        report.metadata_results[name] = {
            "ok": schema_ok,
            "procedure_id": meta.get("procedure_id"),
            "status": meta.get("status"),
            "schema_error": schema_error,
        }

    if register_path.is_file():
        report.content_hashes["NASA_SOURCE_REGISTER.md"] = sha256_file(register_path)
        scan_forbidden_claims(
            register_path.read_text(encoding="utf-8"),
            register_path,
            report,
        )

    ids = [m.get("procedure_id") for m in metas.values()]
    if len(ids) != len(set(ids)):
        report.add_error(f"duplicate procedure_id values: {ids}")

    validate_manifest_consistency(metas, manifest, report)

    report.oxygen_rationing_vocabulary = {
        "backend_schema_structurally_accepts": "any string (OxygenRationingAction.level: str)",
        "cpp_executor_aliases": sorted(CPP_OXYGEN_LEVELS),
        "mismatch": (
            "Backend accepts arbitrary level strings; C++ maps unknown levels to Resting. "
            "Manuals must use executor aliases for interpreter-stable behavior."
        ),
        "manual_concrete_level_tokens": sorted(set(oxygen_used)),
        "manuals_prescribe_invalid_concrete_levels": False,
        "note": (
            "Manuals currently defer to production-valid level vocabulary without "
            "enumerating concrete invalid aliases."
        ),
    }
    if any("unsupported oxygen_rationing level" in e for e in report.errors):
        report.oxygen_rationing_vocabulary["manuals_prescribe_invalid_concrete_levels"] = True

    if report.errors:
        report.status = "FAIL"
    else:
        report.status = "PASS"
    return report


def format_human_report(report: ValidationReport) -> str:
    lines = [
        f"Procedure corpus validation: {report.status}",
        f"Manuals checked: {len(report.manuals_checked)}",
        f"Active candidates: {len(report.active_candidates)}",
        f"Excluded: {len(report.excluded)}",
        f"Errors: {len(report.errors)}",
        f"Warnings: {len(report.warnings)}",
        "",
        "Content hashes:",
    ]
    for name, digest in sorted(report.content_hashes.items()):
        lines.append(f"  {name}: {digest}")
    lines.append("")
    lines.append("Oxygen rationing vocabulary:")
    for key, value in report.oxygen_rationing_vocabulary.items():
        lines.append(f"  {key}: {value}")
    if report.warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"  - {w}" for w in report.warnings)
    if report.errors:
        lines.append("")
        lines.append("Errors:")
        lines.extend(f"  - {e}" for e in report.errors)
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate ARES-1 procedure corpus")
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Optional repository root override",
    )
    args = parser.parse_args(argv)
    report = validate_corpus(args.root)
    payload = asdict(report)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(format_human_report(report))
    return 0 if report.status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
