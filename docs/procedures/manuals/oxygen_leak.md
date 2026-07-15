# Habitat Atmosphere Leak and Oxygen-Depletion Response

> **Status and use:** ARES-1 simulated mission emergency procedure. Informed by NASA technical and operational references. It is not an official NASA procedure, is not flight-certified, and must not be used for real mission operations. The planner may recommend actions; the deterministic C++ simulator alone determines feasibility, state evolution, validation, and outcome.

## Procedure metadata

```json
{
  "procedure_id": "ARES-PROC-OXY-001",
  "procedure_version": "1.0.0",
  "title": "Habitat Atmosphere Leak and Oxygen-Depletion Response",
  "filename": "oxygen_leak.md",
  "status": "PARTIAL_EVIDENCE",
  "applicable_faults": [
    "atmosphere_and_solar"
  ],
  "applicable_scenarios": [
    "mars_hab_atmosphere_solar_failure"
  ],
  "primary_actions": [
    "isolate_module"
  ],
  "supporting_actions": [
    "oxygen_rationing",
    "reduce_power_load"
  ],
  "prohibited_actions": [],
  "telemetry_dependencies": [
    {
      "field": "simulation_time_min",
      "json_location": "telemetry_history[].simulation_time_min",
      "unit": "min",
      "condition_roles": [
        "entry",
        "monitoring",
        "abort",
        "success"
      ]
    },
    {
      "field": "cabin_pressure_kpa",
      "json_location": "telemetry_history[].habitat.cabin_pressure_kpa",
      "unit": "kPa",
      "condition_roles": [
        "entry",
        "monitoring",
        "abort",
        "success"
      ]
    },
    {
      "field": "inspired_oxygen_mmhg",
      "json_location": "telemetry_history[].habitat.inspired_oxygen_mmhg",
      "unit": "mmHg",
      "condition_roles": [
        "entry",
        "monitoring",
        "abort",
        "success"
      ]
    },
    {
      "field": "oxygen_hours_remaining",
      "json_location": "telemetry_history[].habitat.oxygen_hours_remaining",
      "unit": "hr",
      "condition_roles": [
        "entry",
        "monitoring",
        "abort",
        "success"
      ]
    },
    {
      "field": "mission_status",
      "json_location": "telemetry_history[].habitat.mission_status",
      "unit": "enum",
      "condition_roles": [
        "entry",
        "monitoring",
        "abort",
        "success"
      ]
    },
    {
      "field": "spo2_percent",
      "json_location": "telemetry_history[].crew[].spo2_percent",
      "unit": "%",
      "condition_roles": [
        "entry",
        "monitoring",
        "abort"
      ]
    },
    {
      "field": "health_status",
      "json_location": "telemetry_history[].crew[].health_status",
      "unit": "enum",
      "condition_roles": [
        "monitoring",
        "abort"
      ]
    },
    {
      "field": "alarms",
      "json_location": "telemetry_history[].crew[].alarms",
      "unit": "list[enum]",
      "condition_roles": [
        "entry",
        "monitoring",
        "abort"
      ]
    },
    {
      "field": "events",
      "json_location": "telemetry_history[].events",
      "unit": "list",
      "condition_roles": [
        "entry",
        "monitoring",
        "success"
      ]
    }
  ],
  "source_classifications": [
    "NASA_STANDARD",
    "NASA_REFERENCE",
    "DERIVED_PHYSICS",
    "ARES_ASSUMPTION",
    "ARES_RELEASE_CONFIGURATION"
  ],
  "evidence_references": [
    {
      "evidence_id": "EVID-NASA_STD-001",
      "classification": "NASA_STANDARD",
      "source_title": "NASA-STD-3001 Volume 2",
      "locator": "V2 6001; V2 6003; V2 6006; V2 6020–6022; V2 6108",
      "url": "https://www.nasa.gov/reference/6-0-natural-and-induced-environments-vol-2/",
      "supports": "Trend atmospheric data; maintain inspired oxygen and pressure; record, display, and alert on atmospheric parameters."
    },
    {
      "evidence_id": "EVID-NASA_STD-002",
      "classification": "NASA_STANDARD",
      "source_title": "NASA-STD-3001 Volume 2",
      "locator": "V2 11100",
      "url": "https://www.nasa.gov/reference/11-0-spacesuits-vol-2/",
      "supports": "Pressure-suit capability is a design control for high-risk loss-of-cabin-pressure operations."
    },
    {
      "evidence_id": "EVID-NASA_REF-001",
      "classification": "NASA_REFERENCE",
      "source_title": "Human Integration Design Handbook",
      "locator": "Internal atmosphere design rationale",
      "url": "https://www.nasa.gov/organizations/ochmo/human-integration-design-handbook/",
      "supports": "Background and rationale for NASA-STD-3001 human-system requirements."
    },
    {
      "evidence_id": "EVID-ARES_REL-001",
      "classification": "ARES_RELEASE_CONFIGURATION",
      "source_title": "ARES-1 release scenario",
      "locator": "scenario_id; failure_type; leak_module=lab; configured leak and atmosphere thresholds",
      "url": "",
      "supports": "Defines the executable release fault and module identifier."
    },
    {
      "evidence_id": "EVID-DER_PHYS-001",
      "classification": "DERIVED_PHYSICS",
      "source_title": "ARES-1 deterministic simulator",
      "locator": "Atmosphere inventory, mixed-gas leak, ideal-gas pressure, inspired-oxygen and reserve calculations",
      "url": "",
      "supports": "Produces the authoritative pressure, oxygen, and reserve trends."
    },
    {
      "evidence_id": "EVID-ARES_ASM-001",
      "classification": "ARES_ASSUMPTION",
      "source_title": "ARES-1 procedure mapping",
      "locator": "Containment sequence and action prioritization",
      "url": "",
      "supports": "Maps NASA-informed monitoring principles to the current simulator action library."
    }
  ],
  "release_configuration_dependencies": [
    "fault.failure_type",
    "fault.leak_module=lab",
    "fault.total_gas_leak_kg_hr",
    "fault.isolation_leak_multiplier",
    "atmosphere pressure and inspired-oxygen warning/failure thresholds",
    "stabilization hold duration"
  ],
  "last_reviewed": "2026-07-15",
  "supersedes": [],
  "superseded_by": [],
  "notes": "The filename uses the project-domain term oxygen_leak; the executable fault is a mixed habitat-atmosphere leak.",
  "domain_aliases": [
    "oxygen leak",
    "cabin depressurization",
    "atmosphere loss",
    "mixed-gas leak"
  ],
  "chunk_boundary_notes": [
    "Keep isolation steps with their post-action monitoring and abort conditions.",
    "Do not separate numerical limits from source classifications."
  ]
}
```

## Purpose

Provide controlled evidence for recognizing and responding to the ARES-1 mixed habitat-atmosphere leak. The procedure prioritizes crew accountability, containment of the affected `lab` module, preservation of breathable atmosphere, and trend-based monitoring. The project filename is `oxygen_leak.md`; the release simulator models loss of mixed cabin gas rather than a pure oxygen-line or oxygen-tank rupture.

## Scope and applicability

Apply this procedure to the release scenario `mars_hab_atmosphere_solar_failure` when the `atmosphere_and_solar` fault is active or serialized telemetry shows a pressure or inspired-oxygen decline consistent with atmosphere loss.

The procedure is limited to the current action library. It does not authorize manual repressurization, oxygen-tank transfer, hatch repair, suit donning, leak patching, or rescue actions because those commands do not exist in the frozen simulator contract.

## Entry conditions

Enter when one or more of the following is present:

1. A fault or event identifies atmosphere loss in module `lab`.
2. `cabin_pressure_kpa` shows a sustained downward trend.
3. `inspired_oxygen_mmhg` approaches or crosses the configured warning boundary.
4. `oxygen_hours_remaining` is decreasing materially relative to the mission timeline.
5. One or more crew records show declining `spo2_percent`, a degraded `health_status`, or atmosphere-related entries in `alarms`.
6. `mission_status` changes from nominal operation toward warning or critical operation while atmosphere telemetry is degrading.

A single crew-vital change does not independently prove a habitat leak. Correlate crew data with habitat pressure, inspired oxygen, reserve-time trends, and events.

## Relevant telemetry

| Field | JSON location | Unit | Role | Condition | Evidence |
|---|---|---:|---|---|---|
| `simulation_time_min` | `telemetry_history[].simulation_time_min` | min | Context | Establish trend windows and action timing. | EVID-NASA_STD-001 |
| `cabin_pressure_kpa` | `telemetry_history[].habitat.cabin_pressure_kpa` | kPa | Entry / monitoring / abort | Compare with configured warning and failure limits and prior samples. | EVID-NASA_STD-001; EVID-DER_PHYS-001 |
| `inspired_oxygen_mmhg` | `telemetry_history[].habitat.inspired_oxygen_mmhg` | mmHg | Entry / monitoring / abort | Compare with configured warning and failure limits and trend direction. | EVID-NASA_STD-001; EVID-DER_PHYS-001 |
| `oxygen_hours_remaining` | `telemetry_history[].habitat.oxygen_hours_remaining` | hr | Monitoring / prioritization | Determine whether atmosphere reserve is degrading faster than recovery actions can complete. | EVID-DER_PHYS-001 |
| `mission_status` | `telemetry_history[].habitat.mission_status` | enum | Monitoring / termination | Use the exact serialized status; do not infer a separate status. | EVID-DER_PHYS-001 |
| `spo2_percent` | `telemetry_history[].crew[].spo2_percent` | % | Crew monitoring / abort | Track each crewmember against configured ARES response thresholds. | EVID-ARES_ASM-001 |
| `health_status` | `telemetry_history[].crew[].health_status` | enum | Crew monitoring / abort | Escalate when required crew become critical or incapacitated. | EVID-ARES_ASM-001 |
| `alarms` | `telemetry_history[].crew[].alarms` | list | Crew monitoring | Treat new or worsening atmosphere-related alarms as corroborating evidence. | EVID-ARES_ASM-001 |
| `events` | `telemetry_history[].events` | list | Confirmation | Confirm fault, action start, action completion, abort, and stabilization events when emitted. | EVID-DER_PHYS-001 |

NASA-STD-3001 requires continuous recording, real-time display, alerting, and trend-compatible formats for atmospheric parameters. The ARES telemetry fields are simulated representations of those operational principles, not authentic NASA telemetry.

## Immediate priorities

1. Account for every crewmember and identify anyone located in `lab`.
2. Prevent additional crew exposure to the affected volume.
3. Submit containment through the exact `isolate_module` action.
4. Preserve life-support capability while monitoring pressure, inspired oxygen, and reserve trends.
5. Reduce metabolic demand only through a structurally valid `oxygen_rationing` action.
6. Preserve electrical margin when the compound solar fault threatens life-support continuity.
7. Allow the simulator—not the manual or planner—to determine whether containment is adequate.

## Ordered procedure

### Step 1 — Confirm an atmosphere-loss pattern

- **Objective:** Correlate fault/event data with pressure, inspired oxygen, reserve time, and crew response.
- **Action mapping:** `INFORMATIONAL_ONLY`
- **Prerequisites:** At least two authoritative telemetry samples unless a direct fault event is present.
- **Monitor:** `cabin_pressure_kpa`, `inspired_oxygen_mmhg`, `oxygen_hours_remaining`, crew `spo2_percent`, `alarms`.
- **Abort/escalate:** Immediately escalate when a configured hard limit is crossed or a required crewmember becomes critical.
- **Completion evidence:** A supported atmosphere-loss diagnosis or a direct simulator fault event.
- **Evidence:** EVID-NASA_STD-001; EVID-DER_PHYS-001.

### Step 2 — Account for crew in the affected module

- **Objective:** Prevent isolation while a crewmember remains in `lab`.
- **Action mapping:** `INFORMATIONAL_ONLY`
- **Prerequisites:** Serialized crew location or simulator state evidence available to the orchestration layer.
- **Monitor:** Crew identity, location context when exposed, activity, and health state.
- **Abort/escalate:** Do not recommend isolation if crew accountability is unresolved.
- **Completion evidence:** The simulator accepts the isolation action; acceptance is not proof of mission stabilization.
- **Evidence:** EVID-ARES_ASM-001.

### Step 3 — Isolate the leaking module

- **Objective:** Reduce the remaining mixed-gas leak by isolating `lab`.
- **Action mapping:** `isolate_module`
- **Required fields:** `type="isolate_module"`, `module="lab"`, `start_min`.
- **Prerequisites:** Exact module identifier; crew accountability; structurally valid timing.
- **Monitor:** Action events/status plus pressure, inspired oxygen, and reserve trends.
- **Abort/escalate:** Simulator rejection, trapped-crew condition, or continued degradation to a hard limit.
- **Completion evidence:** Simulator-emitted action completion or timeline evidence.
- **Evidence:** EVID-ARES_REL-001; EVID-DER_PHYS-001; EVID-ARES_ASM-001.

### Step 4 — Evaluate containment effectiveness

- **Objective:** Determine whether the authoritative trend improves after isolation.
- **Action mapping:** `INFORMATIONAL_ONLY`
- **Prerequisites:** Post-action telemetry samples.
- **Monitor:** Rate and direction of change in `cabin_pressure_kpa`, `inspired_oxygen_mmhg`, and `oxygen_hours_remaining`.
- **Abort/escalate:** Worsening trend, hard-limit crossing, or critical crew response.
- **Completion evidence:** The simulator maintains all required stabilization conditions for its configured hold time.
- **Evidence:** EVID-NASA_STD-001; EVID-DER_PHYS-001.

### Step 5 — Reduce crew metabolic demand when supported

- **Objective:** Reduce future oxygen use and CO2 generation without claiming oxygen creation.
- **Action mapping:** `oxygen_rationing`
- **Required fields:** `type="oxygen_rationing"`, `level`, `start_min`; crew targeting fields only when accepted by the production contract.
- **Prerequisites:** Use only a `level` value accepted by the current production parser and executor.
- **Monitor:** `oxygen_hours_remaining`, crew performance/vitals, `health_status`, and alarms.
- **Abort/escalate:** Invalid vocabulary, simulator rejection, unacceptable performance degradation, or critical crew state.
- **Completion evidence:** Simulator action state and subsequent telemetry.
- **Evidence:** EVID-DER_PHYS-001; EVID-ARES_ASM-001.

### Step 6 — Preserve life-support power in the compound failure

- **Objective:** Extend electrical support for atmosphere control when solar generation is degraded.
- **Action mapping:** `reduce_power_load`
- **Required fields:** `type="reduce_power_load"`, `percent`, `start_min`; `load_groups` only if accepted by the active contract.
- **Prerequisites:** Do not shed protected life-support loads.
- **Monitor:** `battery_soc_percent`, `power_margin_kw`, `cabin_temperature_c`, `temperature_margin_c`.
- **Abort/escalate:** Thermal safety degradation or loss of essential life-support capability.
- **Completion evidence:** Simulator action completion and sustained resource trends.
- **Evidence:** EVID-ARES_ASM-001. Detailed logic belongs to `power_rationing.md`.

### Step 7 — Continue crew and habitat monitoring

- **Objective:** Detect delayed hypoxia, worsening atmosphere loss, or failure of the recovery sequence.
- **Action mapping:** `INFORMATIONAL_ONLY`
- **Monitor:** Every authoritative sample until final outcome.
- **Abort/escalate:** Any hard failure, critical crew condition, action abort, or `REJECTED` result.
- **Completion evidence:** Final simulator result and preserved telemetry history.
- **Evidence:** EVID-NASA_STD-001; EVID-DER_PHYS-001.

## Operational constraints

- The release module identifier is exactly `lab`.
- Isolation reduces the connected volume and applies the configured isolation leak multiplier; it does not automatically stop the leak.
- `oxygen_rationing` changes modeled metabolic demand, heat, fatigue, performance, and future action availability; it does not add oxygen.
- `reduce_power_load` is a supporting action for the compound solar failure and is not a leak-containment action.
- Numerical limits are read from the active scenario configuration. Untagged release values are `ARES_RELEASE_CONFIGURATION`, not NASA standards.
- NASA-STD-3001 values describe human-system requirements and design limits. The simulator's configured thresholds remain the executable authority for this scenario.

## Prohibited or unsupported actions

Do not invent or recommend:

- manual oxygen injection
- external oxygen-tank transfer
- leak patching
- repressurization
- pressure-suit donning
- module evacuation commands
- emergency return vehicles
- medical treatment actions

These may be valid concepts in a real mission architecture, but they are not current simulator actions. `repair_solar_array`, `delay_rover_use`, and `send_emergency_packet` may be relevant to the broader compound response but do not directly contain the atmosphere leak.

## Abort and escalation conditions

Escalate the procedure when any of the following occurs:

1. `cabin_pressure_kpa` reaches the configured hard-failure boundary.
2. `inspired_oxygen_mmhg` reaches the configured hard-failure boundary.
3. Oxygen reserve is insufficient to reach the next required recovery milestone.
4. A required crewmember reaches a critical or incapacitated `health_status`.
5. The isolation or rationing action is rejected, aborted, or fails.
6. The simulator determines that critical repair is impossible before the remaining resource deadline.
7. Final outcome is `FAILURE` or `REJECTED`.

## Success and termination conditions

- **Step completion:** The simulator records the mapped action as complete.
- **Containment evidence:** Pressure, inspired oxygen, and reserve trends cease worsening according to authoritative telemetry.
- **Mission stabilization:** Only the exact simulator `STABILIZED` outcome or stabilized mission status after the configured hold duration establishes stabilization.
- **Failure termination:** The simulator returns `FAILURE`.
- **Rejection termination:** The simulator returns `REJECTED`.

No procedure text, planner rationale, or isolated telemetry sample may override the simulator result.

## Simulator action mapping

| Procedure step | Exact action type | Required fields | Optional fields | Preconditions | Simulator authority notes |
|---|---|---|---|---|---|
| Isolate `lab` | `isolate_module` | `type`, `module`, `start_min` | Contract-dependent fields only | Crew accountability; exact module ID | Applies the configured isolation behavior; completion is not stabilization. |
| Reduce metabolic demand | `oxygen_rationing` | `type`, `level`, `start_min` | `crew_id` only if accepted | Production-valid level vocabulary | Changes modeled demand/performance; does not add O2. |
| Preserve electrical margin | `reduce_power_load` | `type`, `percent`, `start_min` | `load_groups` if accepted | Protected loads remain available | May affect equipment heat and thermal safety. |

## Evidence and source classifications

| Evidence ID | Classification | Source | Supported use |
|---|---|---|---|
| EVID-NASA_STD-001 | NASA_STANDARD | NASA-STD-3001 Vol. 2, V2 6001, 6003, 6006, 6020–6022, 6108 | Atmosphere trending, inspired-O2 and pressure control, data availability, alerting. |
| EVID-NASA_STD-002 | NASA_STANDARD | NASA-STD-3001 Vol. 2, V2 11100 | Design rationale for pressure-suit protection during high-risk depressurization operations; no suit action exists in ARES-1. |
| EVID-NASA_REF-001 | NASA_REFERENCE | Human Integration Design Handbook | Background and rationale, not executable behavior. |
| EVID-DER_PHYS-001 | DERIVED_PHYSICS | Frozen C++ simulator | Gas inventories, pressure, inspired oxygen, reserve time, outcomes. |
| EVID-ARES_REL-001 | ARES_RELEASE_CONFIGURATION | Release scenario | Fault type, `lab` module, thresholds, leak and stabilization parameters. |
| EVID-ARES_ASM-001 | ARES_ASSUMPTION | This procedure | Prioritization and mappings not directly specified by NASA. |

## ARES assumptions and release-configuration dependencies

- A one-minute deterministic timestep is used by the release simulator.
- The atmosphere leak is mixed-gas loss from `lab`.
- Isolation leaves a configured residual leak.
- Crew-vital response is an ARES deterministic model.
- The procedure uses simulator-configured warning, failure, and stabilization thresholds.
- The exact oxygen-rationing `level` vocabulary must be taken from the production parser/backend schema at integration time.

## Known limitations

- The current serializer does not expose every in-memory atmosphere or crew variable.
- Crew relocation is operationally important but is not an explicit planner action.
- The current valid-plan fixture exercises only a subset of the six actions.
- Pressure-suit response is NASA-supported as a design concept but is not implemented as an ARES action.
- This procedure is repository-grounded and NASA-informed; it is not a real Mars-habitat emergency checklist.

## Retrieval test cases

| Query | Expected section | Relevant actions | Expected behavior |
|---|---|---|---|
| habitat pressure dropping after leak in lab | Entry conditions; Ordered procedure Step 3 | `isolate_module` | Retrieve this procedure highly. |
| inspired oxygen decreasing and oxygen reserve falling | Relevant telemetry; Steps 4–5 | `isolate_module`, `oxygen_rationing` | Retrieve monitoring and demand-reduction sections. |
| crew SpO2 worsening during atmosphere leak | Relevant telemetry; Step 7 | conditional `oxygen_rationing` | Retrieve crew-monitoring constraints, not medical treatment. |
| isolate leaking habitat module | Step 3; action mapping | `isolate_module` | Return exact module/action mapping. |
| reduce oxygen demand after habitat leak | Step 5 | `oxygen_rationing` | Require production-valid level vocabulary. |
| atmosphere leak with solar degradation and declining battery reserve | Steps 3–6 | `isolate_module`, `oxygen_rationing`, `reduce_power_load` | Retrieve this and related power procedure. |
| repair solar array during EVA | Known limitations / cross-domain | `repair_solar_array` | Prefer `solar_array_failure.md` and `eva_repair.md`. |
| communications blackout recovery | Exclusion | none here | Prefer `comms_blackout.md`. |
| standalone CO2 scrubber hardware failure | Exclusion | none direct | Prefer `co2_scrubber_failure.md`. |
| rover battery delay decision | Exclusion | `delay_rover_use` | Prefer `eva_repair.md` or power procedure. |

## Revision history

| Version | Date | Phase | Summary | Evidence basis | Activation status |
|---|---|---|---|---|---|
| 1.0.0 | 2026-07-15 | Phase 2 manual authoring | Initial mixed-atmosphere leak procedure for the frozen release contract. | NASA-STD-3001, HIDH, simulator contract, release scenario. | `PARTIAL_EVIDENCE`; pending repository schema validation and approval. |
