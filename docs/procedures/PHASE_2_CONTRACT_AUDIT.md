# ARES-1 Phase 2 Section 1: Simulator Contract Audit and Procedure Knowledge Boundary

Documentation-only inventory. Frozen C++ simulator and Phase 1 backend contracts are not modified by this document. Future emergency manuals and RAG sources may reference only what is allowed here.

Audit date context: Phase 1 complete (RELEASE_GATE). Evidence is repository-current only.

---

## 1. Authority and source precedence

When future documents disagree, apply this order. Lower-priority sources cannot override higher-priority contracts.

1. **Current C++ implementation and serializer** — `Simulator/include/*`, `Simulator/src/ActionExecutor.cpp`, `Simulator/src/Validator.cpp`, `Simulator/src/Simulation.cpp`, `Simulator/src/JsonIO.cpp`
2. **Current release scenario and plan fixtures** — `scenarios/mars_hab_atmosphere_solar_failure.json`, `plans/sample_plan.json`, `plans/invalid_plan.json`
3. **Current captured simulator result fixtures** — `backend/tests/fixtures/results/` (`baseline_result.json`, `valid_plan_result.json`, `invalid_plan_result.json`)
4. **Strict Phase 1 backend schemas** — `backend/app/schemas/` (`actions.py`, `plan.py`, `crew.py`, `telemetry.py`, `result.py`, `common.py`)
5. **Revised C++ development guide or current repository documentation** — `Simulator/docs/ARES-1_Cpp_Simulation_Core_Development_Guide_NASA_Telemetry_Crew_Vitals_v3.md`, `docs/ARES-1_Phase_1_FastAPI_Backend_Implementation_Guide.md`, `backend/RELEASE_GATE.md`, `backend/tests/fixtures/results/README.md`, `backend/README.md`
6. **Original project overview examples** — cited in Phase 1 Appendix B as “ARES-1 Project Overview”; **no overview file is present in this repository**. Treat illustrated JSON from that missing overview as the lowest priority and reject it when it conflicts with items 1–4 (notably `survival_probability`).

Rule: manuals must not invent telemetry, actions, equipment, modules, constraints, or outcomes that do not exist in the higher-priority layers.

---

## 2. Exact allowed action inventory

Expected action families confirmed from `Enums.hpp` / `JsonIO::parseActionType` / `backend/app/schemas/actions.py`:

| Serialized `type` | Enum (`ActionType`) |
|---|---|
| `reduce_power_load` | `ReducePowerLoad` |
| `isolate_module` | `IsolateModule` |
| `oxygen_rationing` | `OxygenRationing` |
| `repair_solar_array` | `RepairSolarArray` |
| `delay_rover_use` | `DelayRoverUse` |
| `send_emergency_packet` | `SendEmergencyPacket` |

**Discrepancy vs expected list:** none for naming. All six families exist. C++ also has `ActionType::Unknown` serialized as `"unknown"` for in-process use; JSON plan load rejects unknown type strings at parse. Python `ActionType` has no `unknown` member.

Shared optional Action fields (C++ `Action.hpp`; Python `ActionBase`): `percent`, `module`, `level`, `duration_min`, `hours`, `crew_id`, `eva_crew_id`, `assigned_crew_ids`, `target_crew_ids`, `load_groups`. Always required in JSON: `type`, `start_min`.

Timeline evidence event types while actions run: `action_started`, `action_complete`, `action_failed`, `action_aborted` (`ActionExecutor.cpp`).

### 2.1 `reduce_power_load`

| Item | Contract |
|---|---|
| Serialized type | `reduce_power_load` |
| Enum | `ActionType::ReducePowerLoad` |
| Required fields | `percent` (double, percent 0–100); `load_groups` (string[], non-empty) |
| Optional fields | other Action fields unused for semantics |
| Units | `percent`: percent; `start_min`: minutes |
| Structural restrictions | Load groups that may shed: `discretionary`; `thermal_control` / `tcs`; `communications` / `comms`; `eva_support` / `eva`. Protected (runtime fail): `essential`, `life_support`, `life-support`, `protected`. Unknown group fails. |
| ActionExecutor | Scales matching loads by `(1 - percent/100)`; scales discretionary equipment heat with discretionary load. Completes immediately. |
| Validator | `reduce_power_percent`, `reduce_power_groups` |
| Outcomes | Complete immediately; Failed if percent/groups invalid or protected/unknown group |
| Telemetry/timeline | `action_started` / `action_complete` (or `action_failed`); power habitat fields on subsequent samples |

### 2.2 `isolate_module`

| Item | Contract |
|---|---|
| Serialized type | `isolate_module` |
| Enum | `ActionType::IsolateModule` |
| Required fields | `module` (string, non-empty) |
| Optional fields | unused for semantics |
| Units | `start_min`: minutes; module is identifier string |
| Structural restrictions | Fails if any crew `location_module` equals target module |
| ActionExecutor | Sets module isolated, volume → `isolated_habitable_volume_m3`, multiplies leak by `isolation_leak_multiplier`. Completes immediately. |
| Validator | `isolate_module_missing` |
| Outcomes | Complete immediately; Failed if module missing or crew trapped |
| Telemetry/timeline | `action_started` / `action_complete` (or `action_failed`); atmosphere/pressure/O2 paths affected |

### 2.3 `oxygen_rationing`

| Item | Contract |
|---|---|
| Serialized type | `oxygen_rationing` |
| Enum | `ActionType::OxygenRationing` |
| Required fields | Validator + Python: `level` (string). Python also requires `target_crew_ids`. Executor: if `target_crew_ids` empty, applies to all crew. |
| Optional fields | `target_crew_ids` (executor); `level` defaults to Resting activity if omitted at runtime |
| Units | `start_min`: minutes; level is activity alias string |
| Structural restrictions | Level aliases: `sleep`; `rest`/`resting`; `nominal`/`nominal_work`/`nominalwork`; `high`/`high_workload`/`highworkload`; `recovery`; unknown → Resting |
| ActionExecutor | Sets `oxygen_rationing_active`; sets activity when not mid-EVA. Completes immediately. |
| Validator | `rationing_level_missing`, `rationing_crew_unknown` |
| Outcomes | Complete immediately; Failed if target crew unknown |
| Telemetry/timeline | `action_started` / `action_complete`; crew activity / metabolic effects downstream |

### 2.4 `repair_solar_array`

| Item | Contract |
|---|---|
| Serialized type | `repair_solar_array` |
| Enum | `ActionType::RepairSolarArray` |
| Required fields | At least one crew identity: `eva_crew_id` or `assigned_crew_ids[0]` or `crew_id` (executor resolution order) |
| Optional fields | remaining crew identity fields |
| Units | `start_min`: minutes; EVA phase durations from scenario `eva.*` minutes |
| Structural restrictions | Crew must exist, be EVA-qualified, not mid-EVA, health not Impaired/Critical/Incapacitated; if `eva.rover_required`, rover available and battery ≥ reserve |
| ActionExecutor | Starts EVA Preparing; remains Active until EVA Complete + `solar_repair_progress >= 1`; Aborted if EVA Aborted |
| Validator | `repair_crew_missing`, `repair_crew_unknown`, `repair_crew_unqualified`, `eva_unavailable`, `rover_reserved` (when delay conflict and rover required) |
| Outcomes | Active → Complete or Aborted; Failed at start if checks fail |
| Telemetry/timeline | `action_started`; later `action_complete` or `action_aborted`; crew activity EVA_* ; habitat power / `eva_safe_return_margin_min`; metrics `eva_completed` |

### 2.5 `delay_rover_use`

| Item | Contract |
|---|---|
| Serialized type | `delay_rover_use` |
| Enum | `ActionType::DelayRoverUse` |
| Required fields | Validator + Python: positive `hours`. Executor also accepts `duration_min` if `hours` absent. |
| Optional fields | `duration_min` (executor-only acceptance) |
| Units | `hours`: hours; `duration_min`: minutes; reservation stored as minutes |
| Structural restrictions | Duration must resolve to positive minutes |
| ActionExecutor | Sets `rover_available=false`, `rover_reserved_until_min`; Active until time reaches reservation; then Complete |
| Validator | `delay_rover_hours` only (positive `hours` required) |
| Outcomes | Active → Complete; Failed if neither hours nor duration_min / non-positive |
| Telemetry/timeline | `action_started` / `action_complete` |

### 2.6 `send_emergency_packet`

| Item | Contract |
|---|---|
| Serialized type | `send_emergency_packet` |
| Enum | `ActionType::SendEmergencyPacket` |
| Required fields | none beyond `type` + `start_min` |
| Optional fields | none semantic |
| Units | `start_min`: minutes; transmission uses `transmission_duration_min`, `transmission_power_kw` |
| Structural restrictions | Window must be open at start; cannot send twice |
| ActionExecutor | Raises communications load; Active for transmission duration; sets `emergency_packet_sent` |
| Validator | `comms_windows_missing`, `comms_window_closed` |
| Outcomes | Active → Complete; Failed if already sent or window closed |
| Telemetry/timeline | `action_started` / `action_complete`; metrics `communications_sent` when complete |

### 2.7 Known action-contract discrepancies (do not silently resolve)

1. `delay_rover_use`: Validator requires `hours`; Executor accepts `hours` or `duration_min`.
2. `oxygen_rationing`: Validator requires `level`; Executor defaults Resting if omitted. Python requires `target_crew_ids`; Executor defaults to all crew if empty.
3. `repair_solar_array`: Executor failure text says `eva_crew_id or assigned_crew_ids` but also uses `crew_id`; Python text includes `crew_id`.
4. Python schema enforces type-specific required fields at HTTP validate time (422). C++ `parseAction` only requires `type`/`start_min`; type rules run in Validator → REJECTED.
5. Protected load groups and trap-crew / rover-battery checks are runtime Executor, not static Validator (except rover×repair static conflict when applicable).
6. Release `eva.rover_required: false` — rover reservation static check inactive for release fixtures.
7. Frozen valid-plan fixture exercises only `isolate_module`, `reduce_power_load`, `repair_solar_array` (3/6).

---

## 3. Scenario vocabulary

Source: `scenarios/mars_hab_atmosphere_solar_failure.json` only. Do not generalize beyond this release scenario.

| Item | Exact current value |
|---|---|
| Scenario ID | `mars_hab_atmosphere_solar_failure` |
| Scenario name | `Mars habitat lab leak with degraded solar array` |
| Fault type (`failure_type`) | `atmosphere_and_solar` |
| Leak module | `lab` |
| Recognized module identifiers in release data | `lab` (fault / sample isolate target); `core` (crew `initial_location_module`) |
| Available assets | **No separate assets array.** Runtime state includes rover fields (`rover_available`, battery/reserve) and EVA availability; scrubber capacity exists as atmosphere params (`scrubber_capacity_g_min`, `initial_scrubber_efficiency`) — not a named asset inventory. |
| Crew identifiers and roles | `crew_01` Avery Chen, role `EVA Specialist`, `eva_qualified: true`; `crew_02` Jordan Blake, role `Systems Engineer`, `eva_qualified: true` |
| EVA availability | `eva.available: true` |
| Rover requirements | `eva.rover_required: false`; `eva.rover_minimum_reserve_percent: 20.0` |
| Communication windows | `windows: [{open_min: 0, close_min: 1000}]`; `transmission_duration_min: 5`; `transmission_power_kw: 0.1` |
| Simulation timestep | `time_step_s: 60` |
| Maximum duration | `maximum_duration_min: 180` |
| Stabilization hold duration | `stabilization_hold_min: 15` |

Related fault numbers (release): `total_gas_leak_kg_hr: 1.0`, `isolation_leak_multiplier: 0.05`, `solar_fault_factor: 0.05`, `repaired_solar_fault_factor: 1.0`, `stabilized_leak_kg_hr: 0.1`.

EVA phases (release): preparation/egress/repair_work/ingress/reserve = 5/5/10/5/5 min; `maximum_duration_min: 360`.

---

## 4. Telemetry vocabulary

### 4.1 Procedure-referenceable fields (serialized JSON contract)

Authority: `JsonIO.cpp` serialize path + Phase 1 schemas + release fixtures. Procedures may use these exact JSON names only. No user-friendly aliases.

Procedure use tags: **E** entry, **M** monitoring, **A** abort, **S** success. Multiple tags allowed.

#### Result root (`SimulationResult`)

| JSON field | Nested location | Type | Unit | Owner/producer | Cadence | Category | Procedure use |
|---|---|---|---|---|---|---|---|
| `scenario_id` | root | string | — | simulator | final result | result | M |
| `plan_id` | root | string | — | plan echo / `""` baseline | final result | result | M |
| `outcome` | root | enum string | — | simulator | final result | result | S / A (`STABILIZED` / `FAILURE` / `REJECTED`) |
| `valid_plan` | root | bool | — | simulator | final result | result | E / A (`false` → rejected) |
| `failure_reasons` | root | string[] | — | simulator | final result | result | A |
| `metrics` | root object | object | — | simulator | final result | result | M / S / A |
| `timeline` | root array | object[] | — | simulator | final result (full run log) | event | M / A / S |
| `telemetry_history` | root array | object[] | — | simulator | per recorded timestep | mixed | E / M / A / S |

#### Metrics (`metrics`)

| JSON field | Nested location | Type | Unit | Owner/producer | Cadence | Category | Procedure use |
|---|---|---|---|---|---|---|---|
| `minimum_inspired_o2_mmhg` | `metrics` | number | mmHg | simulator extrema | final | environmental | M / A / S |
| `minimum_cabin_pressure_kpa` | `metrics` | number | kPa | simulator extrema | final | environmental | M / A / S |
| `maximum_co2_one_hour_avg_mmhg` | `metrics` | number | mmHg | simulator extrema | final | environmental | M / A / S |
| `minimum_battery_soc_percent` | `metrics` | number | percent | simulator extrema | final | operational | M / A / S |
| `minimum_power_margin_kw` | `metrics` | number | kW | simulator extrema | final | operational | M / A / S |
| `minimum_temperature_margin_c` | `metrics` | number | °C | simulator extrema | final | environmental | M / A / S |
| `minimum_eva_safe_return_margin_min` | `metrics` | number | minutes | simulator extrema | final | operational | M / A / S |
| `minimum_crew_spo2_percent` | `metrics` | number | percent | simulator extrema | final | crew | M / A / S |
| `maximum_crew_fatigue_percent` | `metrics` | number | percent | simulator extrema | final | crew | M / A |
| `eva_completed` | `metrics` | bool | — | simulator | final | operational / result | S |
| `communications_sent` | `metrics` | bool | — | simulator | final | operational / result | S |
| `time_to_stabilization_hr` | `metrics` | number | hours | simulator | final | result | S |

#### Per-sample envelope (`telemetry_history[]`)

| JSON field | Nested location | Type | Unit | Owner/producer | Cadence | Category | Procedure use |
|---|---|---|---|---|---|---|---|
| `simulation_time_min` | sample | int | minutes | simulator clock | per sample | operational | E / M |
| `has_warning` | sample | bool | — | simulator | per sample | warning | M / A |
| `has_critical` | sample | bool | — | simulator | per sample | warning | M / A |

#### Habitat (`telemetry_history[].habitat`)

| JSON field | Nested location | Type | Unit | Owner/producer | Cadence | Category | Procedure use |
|---|---|---|---|---|---|---|---|
| `cabin_pressure_kpa` | `habitat` | number | kPa | ResourceModel / DerivedTelemetry | per sample | environmental | E / M / A / S |
| `inspired_oxygen_mmhg` | `habitat` | number | mmHg | DerivedTelemetry | per sample | environmental | E / M / A / S |
| `co2_one_hour_avg_mmhg` | `habitat` | number | mmHg | DerivedTelemetry | per sample | environmental | E / M / A / S |
| `oxygen_hours_remaining` | `habitat` | number | hours | DerivedTelemetry | per sample | environmental | M / A |
| `battery_soc_percent` | `habitat` | number | percent | DerivedTelemetry | per sample | operational | E / M / A / S |
| `solar_generation_percent` | `habitat` | number | percent | DerivedTelemetry | per sample | operational | E / M / S |
| `power_margin_kw` | `habitat` | number | kW | DerivedTelemetry | per sample | operational | E / M / A / S |
| `cabin_temperature_c` | `habitat` | number | °C | DerivedTelemetry | per sample | environmental | E / M / A / S |
| `temperature_margin_c` | `habitat` | number | °C | DerivedTelemetry | per sample | environmental | M / A / S |
| `eva_safe_return_margin_min` | `habitat` | number | minutes | DerivedTelemetry | per sample | operational | M / A / S |
| `mission_status` | `habitat` | enum string | — | Simulation mission logic | per sample | result / operational | M / A / S |

`mission_status` values: `NOMINAL`, `WARNING`, `CRITICAL`, `STABILIZED`, `FAILURE`, `REJECTED`.

#### Crew (`telemetry_history[].crew[]`)

| JSON field | Nested location | Type | Unit | Owner/producer | Cadence | Category | Procedure use |
|---|---|---|---|---|---|---|---|
| `crew_id` | `crew[]` | string | — | CrewPhysiology | per sample | crew | E / M |
| `display_name` | `crew[]` | string | — | config echo | per sample | crew | M |
| `activity` | `crew[]` | enum string | — | CrewPhysiology / actions | per sample | crew / operational | M |
| `heart_rate_bpm` | `crew[]` | number | bpm | CrewPhysiology | per sample | crew | M / A |
| `respiratory_rate_bpm` | `crew[]` | number | bpm | CrewPhysiology | per sample | crew | M / A |
| `spo2_percent` | `crew[]` | number | percent | CrewPhysiology | per sample | crew | M / A / S |
| `core_temperature_c` | `crew[]` | number | °C | CrewPhysiology | per sample | crew | M / A |
| `fatigue_percent` | `crew[]` | number | percent | CrewPhysiology | per sample | crew | M / A |
| `cognitive_performance_percent` | `crew[]` | number | percent | CrewPhysiology | per sample | crew | M / A |
| `physical_performance_percent` | `crew[]` | number | percent | CrewPhysiology | per sample | crew | M / A |
| `health_status` | `crew[]` | enum string | — | CrewPhysiology | per sample | crew | M / A / S |
| `alarms` | `crew[]` | enum string[] | — | CrewPhysiology | per sample | warning / crew | M / A |

Crew activity values: `SLEEP`, `RESTING`, `NOMINAL_WORK`, `HIGH_WORKLOAD`, `EVA_PREP`, `EVA_TRANSIT`, `EVA_WORK`, `RECOVERY`, `INCAPACITATED`.

Health: `NOMINAL`, `ELEVATED_STRESS`, `IMPAIRED`, `CRITICAL`, `INCAPACITATED`.

Alarms: `HYPOXIA`, `HYPERCAPNIA`, `PRESSURE`, `TACHYCARDIA`, `RESPIRATORY`, `THERMAL`, `FATIGUE`, `PERFORMANCE`, `EVA_RETURN`.

#### Events (`telemetry_history[].events[]` and root `timeline[]`)

| JSON field | Nested location | Type | Unit | Owner/producer | Cadence | Category | Procedure use |
|---|---|---|---|---|---|---|---|
| `time_min` | event | int | minutes | simulator | per event | event | M |
| `event_type` | event | string | — | ActionExecutor / Simulation | per event | event | M / A / S |
| `message` | event | string | — | ActionExecutor / Simulation | per event | event | M / A / S |
| `severity` | event | enum | — | emitter | per event | warning / event | M / A |

Known event types from executable: `action_started`, `action_complete`, `action_failed`, `action_aborted`, `mission_failure`, `mission_stabilized`. Severity: `INFO`, `WARNING`, `CRITICAL`, `FAILURE`.

#### Active actions (`telemetry_history[].active_actions[]`)

| JSON field | Nested location | Type | Unit | Owner/producer | Cadence | Category | Procedure use |
|---|---|---|---|---|---|---|---|
| `action_index` | active_actions[] | int | — | ActionExecutor | per sample | operational | M |
| `type` | active_actions[] | ActionType string | — | ActionExecutor | per sample | operational | M |
| `status` | active_actions[] | enum | — | ActionExecutor | per sample | operational | M / A / S |
| `actual_start_min` | active_actions[] | int \| null | minutes | ActionExecutor | per sample | operational | M |
| `elapsed_min` | active_actions[] | int | minutes | ActionExecutor | per sample | operational | M |
| `progress_fraction` | active_actions[] | number | fraction 0–1 | ActionExecutor | per sample | operational | M / S |
| `assigned_crew_id` | active_actions[] | string \| null | — | ActionExecutor | per sample | operational | M |
| `eva_crew_id` | active_actions[] | string \| null | — | ActionExecutor | per sample | operational | M |
| `assigned_crew_ids` | active_actions[] | string[] | — | ActionExecutor | per sample | operational | M |
| `failure_reason` | active_actions[] | string | — | ActionExecutor | per sample | result / operational | A |

`status`: `PENDING`, `ACTIVE`, `COMPLETE`, `FAILED`, `ABORTED`.

### 4.2 In-memory only — not allowed for manuals until serialized

Present in `DerivedTelemetry.hpp` / `CrewVitalsTelemetry` but **absent** from `serializeHabitat` / `serializeCrew` / result JSON. Procedures must not cite these as observable telemetry:

**Atmosphere not emitted:** `oxygen_fraction`, `co2_partial_pressure_mmhg`, `time_to_pressure_limit_hr`, `time_to_co2_limit_hr`

**Power not emitted:** `solar_generation_kw`, `healthy_solar_generation_kw`, `total_habitat_load_kw`, `battery_hours_to_reserve`

**Thermal not emitted:** `crew_heat_w`, `tcs_commanded_rejection_w`, `net_thermal_power_w`, `thermal_margin_w`

**EVA not emitted:** `eva_consumables_remaining_min`, `repair_progress_percent`, `active_crew_id` (as dedicated EVA block; repair progress appears only via action `progress_fraction`)

**Communications not emitted as habitat fields:** `comms_window_open`, `next_comms_window_min`, `transmission_in_progress`, `emergency_packet_sent` (completion reflected via metrics `communications_sent` / action state)

**Mission not emitted as nested fields:** `stabilization_elapsed_min`, `violated_constraints`, `warnings` arrays (warnings feed `has_warning` / status indirectly; violation strings appear as `failure_reasons` on FAILURE)

**Crew vitals not emitted:** `assigned_role`, `location_module`, `eva_status`, `oxygen_consumption_g_min`, `co2_production_g_min`, `heat_output_w`, `hypoxia_exposure`, `co2_exposure`, `thermal_exposure`

**Forbidden invented field:** `survival_probability` — absent from JsonIO, schemas, and fixtures; must remain absent.

---

## 5. Validation and outcome inventory

### 5.1 Static plan validation rules (`Validator.cpp`)

| code | message |
|---|---|
| `plan_id_missing` | `plan_id is required` |
| `unknown_action` | `unknown action type: ` + type_raw |
| `action_start_negative` | `action start_min must be non-negative` |
| `action_start_past_end` | `action start_min exceeds maximum_duration_min` |
| `reduce_power_percent` | `reduce_power_load requires percent in [0, 100]` |
| `reduce_power_groups` | `reduce_power_load requires load_groups` |
| `isolate_module_missing` | `isolate_module requires module` |
| `rationing_level_missing` | `oxygen_rationing requires level` |
| `rationing_crew_unknown` | `oxygen_rationing target crew not found: ` + id |
| `repair_crew_missing` | `repair_solar_array requires eva_crew_id or assigned_crew_ids` |
| `repair_crew_unknown` | `repair_solar_array crew not found: ` + id |
| `repair_crew_unqualified` | `crew is not EVA qualified: ` + id |
| `eva_unavailable` | `EVA is not available in this scenario` |
| `delay_rover_hours` | `delay_rover_use requires positive hours` |
| `comms_windows_missing` | `send_emergency_packet requires communication windows` |
| `comms_window_closed` | `send_emergency_packet start is outside an open communication window` |
| `rover_reserved` | `repair_solar_array starts while rover is reserved by delay_rover_use` |

Release `invalid_plan` fixture `failure_reasons` (REJECTED):

1. `action_start_past_end: action start_min exceeds maximum_duration_min`
2. `comms_window_closed: send_emergency_packet start is outside an open communication window`

### 5.2 Scenario validation codes (subset; full list in `Validator.cpp`)

Includes: `scenario_id_missing`, `time_step_invalid`, `duration_invalid`, `hold_invalid`, volume/gas/pressure/O2/CO2/battery/solar/thermal/EVA/comms/fault/vital/crew codes (`crew_roster_empty`, `crew_id_duplicate`, `crew_id_empty`, etc.).

### 5.3 Dynamic action constraints / abort (ActionExecutor)

Runtime failures include: protected load groups; unknown load groups; crew trapped on isolate; unknown rationing crew; EVA qualification/health/busy; rover unavailable/low battery when required; packet already sent; window closed at runtime; unknown action type.

`repair_solar_array` abort: `EVA aborted before repair completion` → `action_aborted`, status `ABORTED`.

### 5.4 Hard mission failure conditions (`Simulation.cpp`)

Bare strings pushed to `failure_reasons` / `violated_constraints`:

| code | Meaning source |
|---|---|
| `inspired_o2_hard_limit` | inspired O2 ≤ `inspired_o2_failure_mmhg` |
| `pressure_hard_limit` | cabin pressure ≤ `pressure_failure_low_kpa` |
| `co2_hard_limit` | CO2 1-hr avg ≥ `co2_one_hour_limit_mmhg` |
| `battery_failure_reserve` | battery energy ≤ 0 or SOC ≤ `battery_reserve_percent` |
| `cabin_temperature_critical` | temp ≤ `critical_low_c` or ≥ `critical_high_c` |
| `eva_crew_incapacitated:<crew_id>` | incapacitated crew while outside EVA |
| `eva_safe_return_negative` | EVA prep/egress/work with negative safe-return margin |
| `all_crew_incapacitated` | every crew incapacitated |
| `critical_repair_impossible` | solar still faulted, repair incomplete, remaining repair time exceeds resource deadline |
| `maximum_duration_exceeded` | run ends without stabilization |

Timeline: `event_type: mission_failure`, `message` = first failure reason.

### 5.5 Stabilization conditions (`Simulation::stabilizationConditionsMet`)

All must hold, then hold for `stabilization_hold_min` continuous minutes:

- Effective leak ≤ `stabilized_leak_kg_hr`
- Inspired O2 > failure limit
- Cabin pressure > failure low
- CO2 1-hr avg < CO2 limit
- Battery SOC > reserve percent
- Cabin temp within critical low/high
- Power OK: `power_margin_kw >= 0` OR solar repaired to `repaired_solar_fault_factor`
- No EVA safe-return violation while outside (Ingress exempt)
- No crew Critical or Incapacitated

On hold complete: `mission_status` Stabilized; event `mission_stabilized` / `stabilization hold complete`; outcome `STABILIZED`.

### 5.6 Outcome and mission status values

| Layer | Exact values |
|---|---|
| Result `outcome` | `STABILIZED`, `FAILURE`, `REJECTED` |
| Habitat `mission_status` | `NOMINAL`, `WARNING`, `CRITICAL`, `STABILIZED`, `FAILURE`, `REJECTED` |
| Baseline no-plan fixture | `outcome: FAILURE`, `valid_plan: true`, `plan_id: ""` (frozen quirk) |
| Sample plan fixture | `outcome: STABILIZED`, `valid_plan: true` |
| Invalid plan fixture | `outcome: REJECTED`, `valid_plan: false`, empty timeline/history |

### 5.7 Validation message structure

Internal C++ `ValidationMessage`: `code`, `message`, `severity`, optional `action_index`, optional `simulation_time_min`.

Rejected runs do **not** serialize ValidationMessage objects. `makeRejectedResult` flattens to `failure_reasons` strings: `"code: message"`.

FAILURE runs use bare constraint codes in `failure_reasons` (no `code: ` prefix).

### 5.8 FAILURE / REJECTED are not backend errors

HTTP SUCCESS (200) carries mission `FAILURE` or `REJECTED` inside `SimulationResult`. Backend transport errors use separate `ErrorResponse` / FastAPI 422 for schema failures. Manuals and RAG must not reinterpret simulator FAILUREs as API outages.

---

## 6. Procedure coverage matrix

Coverage plan only. No procedural instructions.

| Planned document | Applicable fault / condition | Relevant telemetry (serialized) | Actions may recommend | Actions must not recommend beyond inventory | Related validation constraints | Success indicators | Abort indicators | Release scenario exercises? | Source-evidence availability | Known documentation gaps |
|---|---|---|---|---|---|---|---|---|---|---|
| `oxygen_leak.md` | `atmosphere_and_solar` leak from `lab`; isolation / rationing responses | pressure, inspired O2, O2 hours, CO2 avg, mission_status, crew SpO2/alarms | `isolate_module`, `oxygen_rationing`, optionally `reduce_power_load` | any type outside the six; invented modules/assets | isolate module occupied; rationing level/crew; leak stabilization thresholds | leak controlled + hold → `STABILIZED`; pressure/O2 away from hard limits | hard limits; `critical_repair_impossible` if dual fault unrepaired | **Yes (primary)** — dual fault + sample isolate | Strong for fault + isolate path; sparse NASA tagging beyond CO2 | No dedicated oxygen-only fault scenario; scrubber efficiency not an action |
| `solar_array_failure.md` | `solar_fault_factor` degradation under dual fault | solar_generation_percent, power_margin_kw, battery_soc_percent, eva margins | `repair_solar_array`, `reduce_power_load`, optionally `delay_rover_use` when rover_required | inventing non-existent repair tools/assets | EVA/repair crew checks; rover_reserved; eva_unavailable | `eva_completed`, improved solar %, `STABILIZED` | `critical_repair_impossible`, battery_failure_reserve, EVA abort codes | **Yes (primary)** with sample repair | Strong in fixtures (STABILIZED / baseline FAILURE) | Rover-required path not exercised (`rover_required: false`) |
| `power_rationing.md` | Discretionary/TCS/comms/EVA support shed under low power | power_margin_kw, battery_soc_percent, load-shed timeline events | `reduce_power_load` only among power actions | shedding `essential` / life_support (executor fails); inventing load groups | reduce_power_percent/groups | restored margin / SOC away from reserve; contrib to stabilize | battery_failure_reserve; protected-group fail | **Partial** — sample uses `discretionary` 50% | Executor load-group vocabulary clear | Title vs action name mismatch (`power_rationing` vs `reduce_power_load`); no standalone power-only fault |
| `eva_repair.md` | Solar repair EVA lifecycle | crew activity EVA_*, eva_safe_return_margin_min, active_actions progress, metrics eva_completed | `repair_solar_array`; supporting `reduce_power_load` / `delay_rover_use` when needed | inventing EVA tools; non-qualified crew | repair_crew_*, eva_unavailable, rover_* | action COMPLETE + `eva_completed` + stabilize | EVA abort, eva_safe_return_negative, eva_crew_incapacitated | **Yes** via sample_plan | Strong phase durations in scenario | Separating “EVA procedure” from “solar repair” needs naming approval |
| `comms_blackout.md` | Closed / missing windows; emergency packet | metrics `communications_sent`; events; (window state **not** in habitat JSON) | `send_emergency_packet` when window open; avoid scheduling outside window | inventing alternate comms modalities | comms_windows_missing, comms_window_closed | `communications_sent: true` / packet COMPLETE | REJECTED for bad schedule; runtime fail if window closed | **Weak** — release window `[0,1000]` stays open; invalid_plan only demos REJECTED schedule | Action + validator strong; no blackout fault type in release | Filename `comms_blackout.md` vs alternate `communications.md`; no true blackout scenario |
| `co2_scrubber_failure.md` | Elevated CO2 / scrubber degradation | `co2_one_hour_avg_mmhg`, metrics max CO2, crew HYPERCAPNIA | No dedicated scrubber-repair action exists — may only recommend inventory actions with side effects (e.g. `oxygen_rationing`, power/thermal sheds) | inventing `repair_scrubber` or scrubber efficiency actions | `co2_hard_limit`; scenario scrubber capacity is config only | CO2 below limit + stabilize | `co2_hard_limit` | **No** — release fault is leak+solar, not scrubber failure; scrubber starts efficient | Atmosphere fields + NASA_STANDARD CO2 limit tagged | Procedure cannot yet be written as executable scrubber recovery without new actions/scenario evidence |

---

## 7. Source-classification inventory

Definitions (C++ guide §7 / `SourceClassification` enum):

| Classification | Meaning |
|---|---|
| `NASA_STANDARD` | Published exposure requirement or limit |
| `NASA_REFERENCE` | Published design or metabolic reference |
| `DERIVED_PHYSICS` | Conservation laws or unit conversions |
| `ARES_ASSUMPTION` | Fictional habitat, scenario tuning, response coefficients |

Do not convert an ARES assumption into a NASA-derived claim.

### 7.1 NASA_STANDARD

| parameter_name | source_label | note | evidence location |
|---|---|---|---|
| `co2_one_hour_limit_mmhg` | NASA exposure limit | one-hour average CO2 hard limit | `scenarios/mars_hab_atmosphere_solar_failure.json` `parameter_sources` |
| `inspired_o2_warning_mmhg` | NASA inspired-O2 warning limit | hypoxia severity safe threshold | `Simulator/tests/test_crew_physiology.cpp` `buildPhysiologyParameterSources()` (**test helper only; not in release scenario JSON**) |
| `inspired_o2_failure_mmhg` | NASA inspired-O2 failure limit | hypoxia severity critical threshold | test helper only |
| `pressure_warning_low_kpa` | NASA cabin pressure warning | pressure severity safe threshold | test helper only |
| `pressure_failure_low_kpa` | NASA cabin pressure failure | pressure severity critical threshold | test helper only |

Release scenario atmosphere still **contains numeric values** for inspired-O2 and pressure thresholds, but those parameters lack `parameter_sources` rows in the release file (except CO2).

### 7.2 NASA_REFERENCE

| parameter_name | source_label | note | evidence location |
|---|---|---|---|
| `activity_metabolic_profiles` | NASA metabolic design reference | Sleep/Nominal/HighWorkload/EVA O2 CO2 heat rates | test helper only |

**Release scenario:** zero `NASA_REFERENCE` entries.

### 7.3 DERIVED_PHYSICS

| parameter_name | source_label | note | evidence location |
|---|---|---|---|
| *(none inventoried)* | — | Classification defined in enum/parser/docs; **no instances** in release scenario or physiology test helper | `Enums.hpp`, `JsonIO.cpp`, C++ guide §7 examples only |

Unresolved: DERIVED_PHYSICS remains a defined classification without attached release parameters.

### 7.4 ARES_ASSUMPTION

#### Release scenario attached

| parameter_name | source_label | note | evidence location |
|---|---|---|---|
| `fault.total_gas_leak_kg_hr` | ARES demo fault case | lab module mixed-gas leak rate for atmosphere+solar dual fault | release scenario `parameter_sources` |
| `fault.isolation_leak_multiplier` | ARES demo fault case | isolating lab reduces effective leak below stabilized_leak_kg_hr | release scenario |
| `fault.solar_fault_factor` | ARES demo fault case | array degradation leaving habitat generation below continuous load | release scenario |

#### Test-helper physiology (not release-attached)

Exposure/fatigue/vital/performance/rationing coefficients named in `buildPhysiologyParameterSources()` (e.g. `hypoxia_accumulation_rate`, `fatigue_work_rate`, `hr_*_gain`, `rr_*_gain`, `spo2_*_gain`, `core_temp_*`, `cognitive_*_weight`, `physical_*_weight`, `oxygen_rationing_factor` note “hardcoded 0.75 metabolic scale under rationing”) — all `ARES_ASSUMPTION`. See `Simulator/tests/test_crew_physiology.cpp`.

Many release scenario numeric knobs (leak stabilize rate, battery reserve, EVA times, scrubber rates, solar geometry, etc.) have **no** `parameter_sources` row — treat as **unresolved / untagged** for manuals until tagged.

---

## 8. Planner boundary

### 8.1 What a future planner may provide

From `Plan.hpp` / `backend/app/schemas/plan.py` / `actions.py`:

| Field | Notes |
|---|---|
| `plan_id` | string |
| `summary` | string |
| `actions` | list of RecoveryAction discriminated by `type` |
| `rationale` | string |
| `expected_risk` | string |
| `constraints_checked` | list of free strings (declarative; not enforced by schema) |

Action fields the planner may set (within type rules): `type`, `start_min`, `percent`, `module`, `level`, `duration_min`, `hours`, `crew_id`, `eva_crew_id`, `assigned_crew_ids`, `target_crew_ids`, `load_groups`.

### 8.2 What the planner may not provide or control

Owned exclusively by the simulator (result path):

- Physical habitat/atmosphere/power/thermal/EVA state evolution
- Crew vitals and health transitions
- Action success / ActiveActionState runtime progress
- `valid_plan`
- `mission_status`
- `metrics`
- `timeline`
- `failure_reasons`
- `outcome`
- `survival_probability` (must not be introduced)
- Telemetry history contents except as consequences of executing a plan

The planner proposes; the simulator decides feasibility, validation, and outcome.

---

## 9. Discrepancies and unresolved questions

### 9.1 Outdated overview fields

- `survival_probability` in overview-era examples vs absent from JsonIO / schemas / fixtures.
- Guides diagram tree name `sim_core/` vs on-disk `Simulator/` (binary often still `sim_core.exe`).
- C++ guide `crew_vitals` naming vs serialized JSON key `crew`.
- Overview simplified metrics vs full `telemetry_history` + metrics contract.
- Overview file itself **missing from repository** — conflicts known via Phase 1 / fixtures README citations only.

### 9.2 Filename inconsistencies

- Planned manuals use `comms_blackout.md`. Alternate name `communications.md` appears in Section 1 instructions as a discrepancy cue. **Neither file exists.** Requires user approval of the canonical filename before authoring.
- Manual titles (`power_rationing`, `eva_repair`, `solar_array_failure`) do not match action types (`reduce_power_load`, `repair_solar_array`, etc.). Terminology alignment needs approval.

### 9.3 Documentation vs executable gaps

- Many DerivedTelemetry / CrewVitals fields documented in headers are not emitted.
- Soft mission warning strings (`inspired_o2_warning`, `pressure_warning`, `co2_elevated`, `battery_low`, `thermal_comfort`, `crew_alarm:*`, `crew_impaired:*`) exist in Simulation logic but are not serialized as arrays; only flags/`mission_status` surface.
- Python unit tests use oxygen rationing levels `moderate` / `low` that are schema-valid but not in executor aliases (silent Resting).
- `duration_min` on ActionBase unused by typed Python delay action (hours required).

### 9.4 Source metadata insufficient for simulator behavior

- Release `parameter_sources` has only four entries.
- Most thresholds, EVA timings, scrubber params, and vital_response coefficients in the release scenario are **untagged**.
- `DERIVED_PHYSICS` unused.
- `NASA_REFERENCE` unused in release (test helper only).

### 9.5 Procedures that cannot yet be written credibly from repository evidence alone

- `co2_scrubber_failure.md` — no scrubber-failure fault, no scrubber-repair action, release does not exercise scrubber degradation.
- `comms_blackout.md` as a true blackout manual — release keeps a long-open window; only invalid-plan REJECTED path demonstrates closed-window scheduling.
- Any manual claiming equipment, modules, or telemetry beyond Sections 2–4 of this audit.

### 9.6 Terminology requiring user approval before manual authoring

1. Canonical communications procedure filename: `comms_blackout.md` vs `communications.md`.
2. Mapping of manual titles to action families (especially power_rationing ↔ `reduce_power_load`; eva_repair ↔ `repair_solar_array`).
3. Whether manuals may cite **scenario config thresholds** (e.g. `inspired_o2_failure_mmhg`) as authoritative limits when those values lack release `parameter_sources` classification.
4. Whether test-helper physiology classifications may be reused in manuals without being copied into the release scenario.
5. Oxygen `level` vocabulary for manuals (executor aliases only vs free strings).

---

## 10. Phase 2 Section 1 exit checklist

- [x] No frozen code or fixture was modified (`Simulator/`, `backend/app/`, `backend/tests/`, `scenarios/`, `plans/`, `results/` untouched by this section)
- [x] All allowed actions were captured (six families + Unknown parse note)
- [x] All usable telemetry fields were captured (serialized contract + explicit non-emitted list)
- [x] Validation and outcome boundaries were captured
- [x] All six procedure topics were mapped (coverage only)
- [x] Source classifications were preserved (NASA_STANDARD / NASA_REFERENCE / DERIVED_PHYSICS / ARES_ASSUMPTION; no invented upgrades)
- [x] Unsupported assumptions were listed (Section 9)
- [x] No manual content was authored
- [x] No RAG or NVIDIA code was introduced

---

## Sources inspected (this audit)

- `Simulator/include/Enums.hpp`, `Action.hpp`, `Plan.hpp`, `ScenarioConfig.hpp`, `DerivedTelemetry.hpp`, `TelemetrySample.hpp`, `SimulationMetrics.hpp`, `SimulationResult.hpp`, `ValidationResult.hpp`, `CrewMember.hpp`
- `Simulator/src/ActionExecutor.cpp`, `Validator.cpp`, `Simulation.cpp`, `JsonIO.cpp`
- `scenarios/mars_hab_atmosphere_solar_failure.json`
- `plans/sample_plan.json`, `plans/invalid_plan.json`
- `backend/app/schemas/actions.py`, `plan.py`, `crew.py`, `telemetry.py`, `result.py`
- `backend/tests/fixtures/results/` (+ `README.md`)
- `backend/RELEASE_GATE.md`, `backend/README.md`
- `docs/ARES-1_Phase_1_FastAPI_Backend_Implementation_Guide.md`
- `Simulator/docs/ARES-1_Cpp_Simulation_Core_Development_Guide_NASA_Telemetry_Crew_Vitals_v3.md`
- `Simulator/tests/test_crew_physiology.cpp` (`buildPhysiologyParameterSources`)

**Created by this section:** `docs/procedures/PHASE_2_CONTRACT_AUDIT.md` only.
