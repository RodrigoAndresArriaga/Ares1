# ARES-1 Phase 1 Section 7 — Frozen Result Contract Inventory

Authoritative simulator outputs captured for later Pydantic contracts.
These JSON files are exact byte copies of `sim_core.exe --output` results.
They were not normalized, pretty-printed again, manually edited, or reconstructed.

## 1. Capture metadata

| Item | Value |
|------|-------|
| Capture date (local) | 2026-07-14T20:28:05-05:00 (staging); fixtures installed 2026-07-14T20:28:27-05:00 |
| OS | Microsoft Windows NT 10.0.26200.0 |
| PowerShell | 5.1.26100.8655 |
| CMake | `C:\Program Files\CMake\bin\cmake.exe` |
| CTest | `C:\Program Files\CMake\bin\ctest.exe` |
| Ninja | `C:\msys64\ucrt64\bin\ninja.exe` |
| C++ compiler (from build cache) | `C:/msys64/ucrt64/bin/c++.exe` |
| CMake generator | Ninja |
| Staging directory | `C:\Users\rodri\AppData\Local\Temp\ares1_section7_20260714_202805` |

### Simulator executable

| Item | Value |
|------|-------|
| Path | `C:\Users\rodri\OneDrive\Documents\Dev\Ares1\Simulator\build\sim_core.exe` |
| Size | 2760137 bytes |
| LastWriteTime | 2026-07-14 4:49:25 PM |

Note: the Phase 1 guide diagrams use `sim_core/` as the C++ tree name. On disk the frozen tree is `Simulator/`.

## 2. Release inputs

| Role | Absolute path |
|------|----------------|
| Scenario | `C:\Users\rodri\OneDrive\Documents\Dev\Ares1\scenarios\mars_hab_atmosphere_solar_failure.json` |
| Valid plan | `C:\Users\rodri\OneDrive\Documents\Dev\Ares1\plans\sample_plan.json` |
| Invalid plan | `C:\Users\rodri\OneDrive\Documents\Dev\Ares1\plans\invalid_plan.json` |

| Input ID | Value |
|----------|-------|
| `scenario_id` | `mars_hab_atmosphere_solar_failure` |
| Valid `plan_id` | `sample_plan` |
| Invalid `plan_id` | `invalid_plan` |

Shared repository `results/` was not used as a write destination for this capture.

## 3. Commands executed

Working directory for build/test: `C:\Users\rodri\OneDrive\Documents\Dev\Ares1\Simulator`

```powershell
cmake --build build
ctest --test-dir build --output-on-failure
```

Release runs (absolute paths; `$CaptureRoot` = unique TEMP staging dir):

```powershell
$Root = "C:\Users\rodri\OneDrive\Documents\Dev\Ares1"
$Exe = "$Root\Simulator\build\sim_core.exe"

& $Exe --scenario "$Root\scenarios\mars_hab_atmosphere_solar_failure.json" --output "$CaptureRoot\baseline_result.json"
& $Exe --scenario "$Root\scenarios\mars_hab_atmosphere_solar_failure.json" --plan "$Root\plans\sample_plan.json" --output "$CaptureRoot\valid_plan_result.json"
& $Exe --scenario "$Root\scenarios\mars_hab_atmosphere_solar_failure.json" --plan "$Root\plans\invalid_plan.json" --output "$CaptureRoot\invalid_plan_result.json"
& $Exe --scenario "$Root\scenarios\mars_hab_atmosphere_solar_failure.json" --plan "$Root\plans\sample_plan.json" --output "$CaptureRoot\valid_plan_result_repeat.json"
```

Hashes:

```powershell
Get-FileHash -Algorithm SHA256 <path>
```

Fixture install (exact byte copy):

```powershell
Copy-Item -LiteralPath <staging> -Destination <fixture>
```

## 4. Build and CTest evidence

| Gate | Result |
|------|--------|
| `cmake --build build` | Succeeded (`ninja: no work to do.`) |
| CTest | **114/114 passed** (100%), total time ~1.89 s |

## 5. Process exit codes vs JSON outcomes

CLI contract: `sim_core --scenario <path> [--plan <path>] --output <path>`

| Run | Process exit code | JSON `outcome` |
|-----|-------------------|----------------|
| Baseline (no `--plan`) | 0 | `FAILURE` |
| Valid plan | 0 | `STABILIZED` |
| Invalid plan | 0 | `REJECTED` |
| Valid plan repeat | 0 | `STABILIZED` |

`FAILURE` and `REJECTED` are valid simulator results, not CLI failures. Exit code `0` means the result file was written successfully.

## 6. SHA-256 hashes (authoritative fixtures)

| Fixture | SHA-256 |
|---------|---------|
| `baseline_result.json` | `C9EAE8F26A37E6D3587038A49984548C0BFF2DEE8367D91C29CFEB76C13A4A79` |
| `valid_plan_result.json` | `A2662DE223878CCB03723063DF5987D933251547B4D8F3FB96499CB3B2EB112C` |
| `invalid_plan_result.json` | `7D9D09FCAC6A0D504F4EE8A9AF6AC89A837E3345B258940CB83A0C1A0AA05CC1` |

Determinism (valid-plan run A vs repeat):

| Check | Result |
|-------|--------|
| SHA-256 equal | Yes (`A2662DE2…B112C` both) |
| `fc /b` raw bytes | No differences |
| Parsed JSON equality | True |

Backend metadata (run_id, wall-clock duration, absolute paths) is not present in simulator output and was not part of this comparison.

## 7. Top-level fields

Present in **all three** fixtures (required for the frozen contract):

| Field | JSON type | Notes |
|-------|-----------|-------|
| `scenario_id` | string | Always `mars_hab_atmosphere_solar_failure` |
| `plan_id` | string | Empty string `""` for baseline; never omitted |
| `outcome` | string | Exact enum strings below |
| `valid_plan` | boolean | See outcome table |
| `metrics` | object | Always present (zeros for REJECTED) |
| `timeline` | array | Empty `[]` for REJECTED |
| `telemetry_history` | array | Empty `[]` for REJECTED |
| `failure_reasons` | array | Empty `[]` for STABILIZED |

Exact `outcome` strings emitted by JsonIO: `FAILURE`, `STABILIZED`, `REJECTED`.

## 8. Outcome comparison

| Fixture | `outcome` | `valid_plan` | `plan_id` | `#failure_reasons` | `#timeline` | `#telemetry_history` |
|---------|-----------|--------------|-----------|--------------------|-------------|----------------------|
| `baseline_result.json` | `FAILURE` | `true` | `""` | 1 | 1 | 6 |
| `valid_plan_result.json` | `STABILIZED` | `true` | `sample_plan` | 0 | 12 | 43 |
| `invalid_plan_result.json` | `REJECTED` | `false` | `invalid_plan` | 2 | 0 | 0 |

### Failure reasons observed

| Fixture | `failure_reasons` |
|---------|-------------------|
| baseline | `critical_repair_impossible` |
| valid plan | `[]` |
| invalid plan | `action_start_past_end: action start_min exceeds maximum_duration_min`, `comms_window_closed: send_emergency_packet start is outside an open communication window` |

### Frozen baseline semantics

Baseline emits `valid_plan: true` with `plan_id: ""`. This is frozen simulator behavior for no-plan / baseline mode. Do not normalize this away in later schemas.

## 9. Nested field groups

### 9.1 `metrics` (present in all outcomes)

| Field | Type |
|-------|------|
| `minimum_inspired_o2_mmhg` | number |
| `minimum_cabin_pressure_kpa` | number |
| `maximum_co2_one_hour_avg_mmhg` | number |
| `minimum_battery_soc_percent` | number |
| `minimum_power_margin_kw` | number |
| `minimum_temperature_margin_c` | number |
| `minimum_eva_safe_return_margin_min` | number |
| `minimum_crew_spo2_percent` | number |
| `maximum_crew_fatigue_percent` | number |
| `eva_completed` | boolean |
| `communications_sent` | boolean |
| `time_to_stabilization_hr` | number |

REJECTED run uses zeroed numeric metrics and `false` for both booleans. STABILIZED run has `time_to_stabilization_hr: 0.7` and `eva_completed: true`.

### 9.2 `timeline[]` / per-sample `events[]`

| Field | Type |
|-------|------|
| `time_min` | integer |
| `event_type` | string |
| `message` | string |
| `severity` | string |

Observed severities: `INFO`, `WARNING`, `FAILURE`.

### 9.3 `telemetry_history[]` sample

| Field | Type |
|-------|------|
| `simulation_time_min` | integer |
| `habitat` | object |
| `crew` | array |
| `events` | array |
| `active_actions` | array |
| `has_warning` | boolean |
| `has_critical` | boolean |

### 9.4 `habitat`

| Field | Type |
|-------|------|
| `cabin_pressure_kpa` | number |
| `inspired_oxygen_mmhg` | number |
| `co2_one_hour_avg_mmhg` | number |
| `oxygen_hours_remaining` | number |
| `battery_soc_percent` | number |
| `solar_generation_percent` | number |
| `power_margin_kw` | number |
| `cabin_temperature_c` | number |
| `temperature_margin_c` | number |
| `eva_safe_return_margin_min` | number |
| `mission_status` | string |

Observed `mission_status` values in fixtures: `NOMINAL`, `WARNING`, `STABILIZED`, `FAILURE`.

### 9.5 `crew[]` (JSON name for C++ `crew_vitals`)

Path: `telemetry_history[i].crew[j]`

| Field | Type |
|-------|------|
| `crew_id` | string |
| `display_name` | string |
| `activity` | string |
| `heart_rate_bpm` | number |
| `respiratory_rate_bpm` | number |
| `spo2_percent` | number |
| `core_temperature_c` | number |
| `fatigue_percent` | number |
| `cognitive_performance_percent` | number |
| `physical_performance_percent` | number |
| `health_status` | string |
| `alarms` | array of string |

Crew count in every nonempty sample: **2** (`crew_01`, `crew_02`).

Observed activities: `NOMINAL_WORK`, `EVA_PREP`, `EVA_TRANSIT`, `EVA_WORK`, `RECOVERY`. Observed `health_status` in these fixtures: `NOMINAL`. `alarms` was `[]` throughout these three captures.

C++ `CrewVitalsTelemetry` members **not** serialized into JSON (do not invent into the contract): `assigned_role`, `location_module`, `eva_status`, metabolism fields, and exposure indices.

### 9.6 `active_actions[]`

| Field | Type | Null / empty behavior |
|-------|------|------------------------|
| `action_index` | integer | always present |
| `type` | string | snake_case action enum |
| `status` | string | e.g. `ACTIVE`, `COMPLETE` |
| `actual_start_min` | integer | observed set when action started |
| `elapsed_min` | integer | |
| `progress_fraction` | number | |
| `assigned_crew_id` | string or **null** | null when unassigned |
| `eva_crew_id` | string or **null** | null when not EVA / unset |
| `assigned_crew_ids` | array | may be `[]` |
| `failure_reason` | string | may be `""` |

Observed action types in valid-plan telemetry: `isolate_module`, `reduce_power_load`, `repair_solar_array`.

## 10. Fields common to all outcomes

All eight top-level keys listed in §7 are always present.
All twelve metrics keys are always present.
`failure_reasons`, `timeline`, and `telemetry_history` are always present as arrays (possibly empty).
`plan_id` is always a string (possibly empty), never JSON null and never omitted.

## 11. Outcome-dependent differences

| Behavior | FAILURE | STABILIZED | REJECTED |
|----------|---------|------------|----------|
| `valid_plan` | `true` | `true` | `false` |
| `plan_id` | `""` | `sample_plan` | `invalid_plan` |
| `failure_reasons` | nonempty | empty array | nonempty |
| `timeline` | nonempty | nonempty | empty array |
| `telemetry_history` | nonempty (6) | nonempty (43) | empty array |
| metrics content | populated extrema | populated; `time_to_stabilization_hr > 0` | zeroed defaults |
| `active_actions` in samples | empty in baseline samples | populated | N/A (no samples) |

Empty array vs omitted key: these captures always emit the key with `[]` when empty. JSON `null` appears only for optional active-action identity fields (`assigned_crew_id`, `eva_crew_id`).

## 12. telemetry_history and crew vitals

| Fixture | `telemetry_history` present | Sample count | Crew per sample |
|---------|----------------------------|--------------|-----------------|
| baseline | yes | 6 | 2 |
| valid plan | yes | 43 | 2 |
| invalid plan | yes (empty) | 0 | N/A |

Crew vitals are under each sample's `crew` array (not a top-level `crew_vitals` key).

## 13. Absent fields

- `survival_probability` is **absent** from all three fixtures and from the frozen JsonIO serializer / `SimulationResult`.
- Older ARES-1 overview examples that include `survival_probability` are superseded and must not define the contract.

## 14. Documentation deltas vs frozen implementation

| Source | Finding | Authority |
|--------|---------|-----------|
| Phase 1 guide path `sim_core/` | Real tree is `Simulator/` | On-disk layout |
| Shared `results/sim_result.json` / `rejected_result.json` naming | Fixtures use guide names `valid_plan_result.json` / `invalid_plan_result.json` | Section 7 naming |
| C++ field `crew_vitals` | JSON key is `crew` | JsonIO `serializeSample` |
| Full `CrewVitalsTelemetry` struct | Only the twelve JSON crew fields above are emitted | Captured output |
| Overview `survival_probability` | Not in frozen output | Captured output + serializer |
| Baseline `valid_plan` | `true` with empty `plan_id` | Captured baseline fixture |

## 15. Source-of-truth note for later sections

When implementing Pydantic models:

1. Prefer these three fixture files.
2. Cross-check `Simulator/src/JsonIO.cpp` and `Simulator/include/SimulationResult.hpp`.
3. Do not use older project-overview JSON examples as the schema.
4. Do not mark fields optional unless these fixtures or the active serializer prove absence/omission.
