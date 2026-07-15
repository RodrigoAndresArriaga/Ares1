# Emergency EVA Preparation, External Repair, and Safe Return

> **Status and use:** ARES-1 simulated mission emergency procedure. Informed by NASA technical and operational references. It is not an official NASA procedure, is not flight-certified, and must not be used for real mission operations. The planner may recommend actions; the deterministic C++ simulator alone determines feasibility, state evolution, validation, and outcome.

## Procedure metadata

```json
{
  "procedure_id": "ARES-PROC-EVA-001",
  "procedure_version": "1.0.0",
  "title": "Emergency EVA Preparation, External Repair, and Safe Return",
  "filename": "eva_repair.md",
  "status": "PARTIAL_EVIDENCE",
  "applicable_faults": [
    "atmosphere_and_solar"
  ],
  "applicable_scenarios": [
    "mars_hab_atmosphere_solar_failure"
  ],
  "primary_actions": [
    "repair_solar_array"
  ],
  "supporting_actions": [
    "delay_rover_use",
    "reduce_power_load",
    "send_emergency_packet"
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
      "field": "eva_safe_return_margin_min",
      "json_location": "telemetry_history[].habitat.eva_safe_return_margin_min",
      "unit": "min",
      "condition_roles": [
        "entry",
        "monitoring",
        "abort",
        "success"
      ]
    },
    {
      "field": "battery_soc_percent",
      "json_location": "telemetry_history[].habitat.battery_soc_percent",
      "unit": "%",
      "condition_roles": [
        "entry",
        "monitoring",
        "abort"
      ]
    },
    {
      "field": "power_margin_kw",
      "json_location": "telemetry_history[].habitat.power_margin_kw",
      "unit": "kW",
      "condition_roles": [
        "monitoring",
        "abort"
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
      "field": "heart_rate_bpm",
      "json_location": "telemetry_history[].crew[].heart_rate_bpm",
      "unit": "bpm",
      "condition_roles": [
        "monitoring",
        "abort"
      ]
    },
    {
      "field": "respiratory_rate_bpm",
      "json_location": "telemetry_history[].crew[].respiratory_rate_bpm",
      "unit": "breaths/min",
      "condition_roles": [
        "monitoring",
        "abort"
      ]
    },
    {
      "field": "core_temperature_c",
      "json_location": "telemetry_history[].crew[].core_temperature_c",
      "unit": "°C",
      "condition_roles": [
        "monitoring",
        "abort"
      ]
    },
    {
      "field": "fatigue_percent",
      "json_location": "telemetry_history[].crew[].fatigue_percent",
      "unit": "%",
      "condition_roles": [
        "monitoring",
        "abort"
      ]
    },
    {
      "field": "physical_performance_percent",
      "json_location": "telemetry_history[].crew[].physical_performance_percent",
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
        "entry",
        "monitoring",
        "abort"
      ]
    },
    {
      "field": "alarms",
      "json_location": "telemetry_history[].crew[].alarms",
      "unit": "list[enum]",
      "condition_roles": [
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
    "ARES_ASSUMPTION",
    "ARES_RELEASE_CONFIGURATION"
  ],
  "evidence_references": [
    {
      "evidence_id": "EVID-NASA_STD-301",
      "classification": "NASA_STANDARD",
      "source_title": "NASA-STD-3001 Volume 2",
      "locator": "Section 11; V2 11001, 11023, 11024, 11037, 11038, 11101",
      "url": "https://www.nasa.gov/reference/11-0-spacesuits-vol-2/",
      "supports": "Contingency donning, suit/status data, task capability, metabolic monitoring/display, rescue resources."
    },
    {
      "evidence_id": "EVID-NASA_STD-302",
      "classification": "NASA_STANDARD",
      "source_title": "NASA-STD-3001 Volume 2",
      "locator": "V2 6001 and V2 6008–6009",
      "url": "https://www.nasa.gov/reference/6-0-natural-and-induced-environments-vol-2/",
      "supports": "Trend analysis and decompression-risk/treatment design context."
    },
    {
      "evidence_id": "EVID-NASA_REF-301",
      "classification": "NASA_REFERENCE",
      "source_title": "Human Integration Design Handbook",
      "locator": "EVA and human-system rationale",
      "url": "https://www.nasa.gov/organizations/ochmo/human-integration-design-handbook/",
      "supports": "Background for workload, fatigue, suited performance and operations."
    },
    {
      "evidence_id": "EVID-ARES_REL-301",
      "classification": "ARES_RELEASE_CONFIGURATION",
      "source_title": "ARES-1 release scenario",
      "locator": "EVA availability, phase durations, maximum duration, reserve, rover requirement",
      "url": "",
      "supports": "Defines executable EVA timing and resource limits."
    },
    {
      "evidence_id": "EVID-ARES_ASM-301",
      "classification": "ARES_ASSUMPTION",
      "source_title": "ARES-1 physiology and ActionExecutor",
      "locator": "Performance-scaled work, abort and phase advancement",
      "url": "",
      "supports": "Defines simulated crew and repair behavior."
    }
  ],
  "release_configuration_dependencies": [
    "EVA availability",
    "preparation, egress, work, ingress, reserve and maximum duration",
    "qualified crew roster",
    "rover requirement and minimum reserve",
    "battery and EVA-support loads",
    "crew response coefficients"
  ],
  "last_reviewed": "2026-07-15",
  "supersedes": [],
  "superseded_by": [],
  "notes": "This procedure governs the simulator-supported solar-array repair EVA, not general real-world EVA.",
  "domain_aliases": [
    "EVA repair",
    "external maintenance",
    "safe return",
    "surface repair"
  ],
  "chunk_boundary_notes": [
    "Do not separate EVA phase steps from safe-return and crew-abort conditions.",
    "Keep NASA requirements distinct from ARES phase durations."
  ]
}
```

## Purpose

Provide controlled evidence for planning the ARES-1 solar-array repair EVA, monitoring suited crew and resources, and aborting work before safe return becomes impossible. NASA-STD-3001 establishes human-system design and monitoring principles; ARES defines the simulated phase durations, rover use, consumables, performance scaling and repair completion.

## Scope and applicability

This procedure applies only to the simulator-supported `repair_solar_array` action in `mars_hab_atmosphere_solar_failure`. It does not represent a general NASA EVA checklist and does not include detailed suit checks, prebreathe protocols, decompression schedules, tools, hardware interfaces, rescue techniques or medical treatment.

## Entry conditions

- A critical external repair is required and no internal action resolves the fault.
- EVA is available in scenario configuration.
- A qualified crewmember can be assigned.
- Battery, atmosphere, rover and consumable margins can support preparation through ingress plus reserve.
- Crew health/performance permit complex EVA work.
- `eva_safe_return_margin_min` is nonnegative with adequate configured reserve.

## Relevant telemetry

| Field | JSON location | Unit | Role | Condition | Evidence |
|---|---|---:|---|---|---|
| `eva_safe_return_margin_min` | `telemetry_history[].habitat.eva_safe_return_margin_min` | min | Entry / monitoring / abort | Must remain nonnegative while crew are outside. | EVID-ARES_REL-301 |
| `battery_soc_percent` | `telemetry_history[].habitat.battery_soc_percent` | % | Entry / monitoring / abort | Must support EVA loads and habitat survival through return. | EVID-ARES_REL-301 |
| `power_margin_kw` | `telemetry_history[].habitat.power_margin_kw` | kW | Monitoring / abort | Detect inability to support EVA and essential loads. | EVID-ARES_REL-301 |
| `spo2_percent` | `telemetry_history[].crew[].spo2_percent` | % | Crew monitoring / abort | Use configured ARES thresholds. | EVID-NASA_STD-301; EVID-ARES_ASM-301 |
| `heart_rate_bpm` | `telemetry_history[].crew[].heart_rate_bpm` | bpm | Crew monitoring | Trend workload and stress; simulator owns thresholds. | EVID-NASA_STD-301 |
| `respiratory_rate_bpm` | `telemetry_history[].crew[].respiratory_rate_bpm` | breaths/min | Crew monitoring | Trend workload and atmosphere response. | EVID-NASA_STD-301 |
| `core_temperature_c` | `telemetry_history[].crew[].core_temperature_c` | °C | Crew monitoring / abort | Detect modeled thermal stress. | EVID-NASA_STD-301 |
| `fatigue_percent` | `telemetry_history[].crew[].fatigue_percent` | % | Performance monitoring | Work duration may change through modeled performance. | EVID-ARES_ASM-301 |
| `physical_performance_percent` | `telemetry_history[].crew[].physical_performance_percent` | % | Entry / monitoring | Used by the simulator to scale repair work. | EVID-ARES_ASM-301 |
| `health_status` | `telemetry_history[].crew[].health_status` | enum | Entry / abort | Do not assign critical/incapacitated crew. | EVID-ARES_ASM-301 |
| `alarms` | `telemetry_history[].crew[].alarms` | list | Abort support | Critical EVA vital alarms trigger return logic when modeled. | EVID-ARES_ASM-301 |
| `events` | `telemetry_history[].events` | list | Phase confirmation | Track preparation, egress, work, ingress, completion and abort. | EVID-ARES_ASM-301 |

## Immediate priorities

1. Confirm external repair is necessary and executable.
2. Select qualified crew.
3. Preserve habitat and rover resources.
4. Verify safe-return margin before egress.
5. Monitor crew, power and return margin continuously.
6. Abort work and transition to ingress when critical safety conditions occur.
7. Treat repair completion and mission stabilization as separate simulator decisions.

## Ordered procedure

### Step 1 — Confirm repair necessity and deadline

- **Action mapping:** `INFORMATIONAL_ONLY`
- Compare the remaining battery/atmosphere deadline with the earliest feasible repair completion.
- Do not begin EVA when the repair cannot complete with return reserve.
- **Evidence:** EVID-ARES_REL-301.

### Step 2 — Assign qualified crew

- **Action mapping:** represented within `repair_solar_array`
- Use the production crew-assignment field and an `eva_qualified` crewmember.
- Reject assignment when health or performance is incompatible with current validation rules.
- **Evidence:** EVID-NASA_STD-301; EVID-ARES_ASM-301.

### Step 3 — Preserve rover and electrical support

- **Action mapping:** `delay_rover_use` and/or `reduce_power_load`
- Reserve rover energy when the scenario requires it.
- Preserve EVA-support and essential habitat loads.
- **Evidence:** EVID-ARES_REL-301.

### Step 4 — Start repair EVA

- **Action mapping:** `repair_solar_array`
- **Required fields:** exact production `type`, `start_min`, `duration_min`, and crew assignment.
- Simulator advances preparation, egress, work, ingress and completion.
- **Evidence:** EVID-ARES_REL-301; EVID-ARES_ASM-301.

### Step 5 — Monitor during preparation and egress

- **Action mapping:** `INFORMATIONAL_ONLY`
- Monitor crew health/vitals, battery, events and safe-return margin.
- Abort before egress if any critical constraint is already violated.
- **Evidence:** EVID-NASA_STD-301.

### Step 6 — Conduct external work

- **Action mapping:** active `repair_solar_array`
- Monitor physical performance and fatigue because the simulator may scale work progress.
- Do not declare success until completion event/state is emitted.
- **Evidence:** EVID-ARES_ASM-301.

### Step 7 — Abort and return when required

- **Action mapping:** simulator-controlled abort/ingress behavior
- Trigger criteria include critical crew state, negative safe-return margin, unavailable rover, resource loss or action abort.
- The planner does not directly set EVA phase.
- **Evidence:** EVID-NASA_STD-301; EVID-ARES_ASM-301.

### Step 8 — Verify ingress, repair result and mission state

- **Action mapping:** `INFORMATIONAL_ONLY`
- Confirm crew are no longer outside, repair completion is recorded and coupled habitat conditions remain safe.
- **Evidence:** EVID-ARES_REL-301.

## Operational constraints

- NASA-STD-3001 requires effective contingency donning/doffing, suit information management, suited task capability, metabolic monitoring and rescue resources. ARES models only a subset.
- All phase durations and reserves are ARES release configuration.
- Physical performance can extend work duration.
- Critical EVA vitals or negative return margin require abort/ingress when possible.
- The current planner action does not directly command phase transitions.

## Prohibited or unsupported actions

Do not invent suit-pressure settings, prebreathe durations, tool procedures, rescue hardware, decompression treatment, dust decontamination, airlock controls, manual phase skipping, or medical interventions.

## Abort and escalation conditions

- `eva_safe_return_margin_min < 0` while crew are outside.
- Critical or incapacitated assigned crew.
- Battery/power cannot support return and essential habitat loads.
- Rover is unavailable when required.
- Repair becomes impossible before resource deadline.
- Simulator abort or final `FAILURE`/`REJECTED`.

## Success and termination conditions

- **EVA completion:** crew complete ingress and the action reaches complete state.
- **Repair completion:** simulator applies the configured repaired solar factor.
- **Mission stabilization:** simulator returns `STABILIZED`.
- **Abort:** work transitions toward ingress or action abort is recorded.
- **Failure/rejection:** exact simulator result.

## Simulator action mapping

| Procedure step | Exact action type | Required fields | Optional fields | Preconditions | Simulator authority notes |
|---|---|---|---|---|---|
| Preserve rover | `delay_rover_use` | `type`, `hours`, `start_min` | Contract-proven only | Rover required; delay does not block repair | Reserves availability/energy. |
| Preserve power | `reduce_power_load` | `type`, `percent`, `start_min` | `load_groups` if accepted | Essential/EVA loads protected | Thermal coupling remains active. |
| Execute EVA repair | `repair_solar_array` | `type`, `duration_min`, `start_min`, crew assignment | Contract-proven only | Qualified crew and all dynamic resources | Executor controls phases and repair progress. |
| Send status | `send_emergency_packet` | `type`, `start_min` | None unless proven | Open comm window | Coordination only. |

## Evidence and source classifications

| Evidence ID | Classification | Source | Supported use |
|---|---|---|---|
| EVID-NASA_STD-301 | NASA_STANDARD | NASA-STD-3001 Vol. 2, Section 11 | Suit operations, monitoring, work capability and rescue design requirements. |
| EVID-NASA_STD-302 | NASA_STANDARD | NASA-STD-3001 Vol. 2, atmosphere/DCS sections | Trend and pressure-transition context. |
| EVID-NASA_REF-301 | NASA_REFERENCE | HIDH | Human-system background and rationale. |
| EVID-ARES_REL-301 | ARES_RELEASE_CONFIGURATION | Release scenario | EVA phases, limits, rover and power requirements. |
| EVID-ARES_ASM-301 | ARES_ASSUMPTION | ARES physiology and ActionExecutor | Performance scaling, phase progression and abort logic. |

## ARES assumptions and release-configuration dependencies

The simulator uses deterministic physiology, fixed phase durations, configured EVA maximum/reserve, and a simplified rover energy constraint. These are not NASA standards.

## Known limitations

- No complete suit or airlock model.
- No explicit rescue action despite NASA rescue-resource requirements.
- No consumable-by-consumable suit telemetry in the serialized contract.
- EVA medical thresholds are ARES configuration/model behavior.

## Retrieval test cases

| Query | Expected section | Relevant actions | Expected behavior |
|---|---|---|---|
| can crew safely start solar repair EVA | Entry; Steps 1–4 | `repair_solar_array` | Retrieve readiness constraints. |
| EVA safe return margin is falling | Steps 5–7 | simulator abort/ingress | Retrieve abort conditions. |
| rover battery must be reserved for repair | Step 3 | `delay_rover_use` | Retrieve this and power procedure. |
| crew fatigue is slowing repair | Step 6 | active repair | Explain performance scaling without inventing treatment. |
| habitat pressure leak | Exclusion/cross-domain | `isolate_module` | Prefer oxygen procedure. |

## Revision history

| Version | Date | Phase | Summary | Evidence basis | Activation status |
|---|---|---|---|---|---|
| 1.0.0 | 2026-07-15 | Phase 2 manual authoring | Initial emergency EVA and safe-return procedure. | NASA-STD-3001, HIDH, simulator EVA contract. | `PARTIAL_EVIDENCE`; pending repository schema validation and approval. |
