# Mars Habitat Solar-Generation Loss and Array Recovery

> **Status and use:** ARES-1 simulated mission emergency procedure. Informed by NASA technical and operational references. It is not an official NASA procedure, is not flight-certified, and must not be used for real mission operations. The planner may recommend actions; the deterministic C++ simulator alone determines feasibility, state evolution, validation, and outcome.

## Procedure metadata

```json
{
  "procedure_id": "ARES-PROC-SOLAR-001",
  "procedure_version": "1.0.0",
  "title": "Mars Habitat Solar-Generation Loss and Array Recovery",
  "filename": "solar_array_failure.md",
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
    "reduce_power_load",
    "delay_rover_use",
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
      "field": "solar_generation_percent",
      "json_location": "telemetry_history[].habitat.solar_generation_percent",
      "unit": "%",
      "condition_roles": [
        "entry",
        "monitoring",
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
        "abort",
        "success"
      ]
    },
    {
      "field": "power_margin_kw",
      "json_location": "telemetry_history[].habitat.power_margin_kw",
      "unit": "kW",
      "condition_roles": [
        "entry",
        "monitoring",
        "abort",
        "success"
      ]
    },
    {
      "field": "cabin_temperature_c",
      "json_location": "telemetry_history[].habitat.cabin_temperature_c",
      "unit": "°C",
      "condition_roles": [
        "monitoring",
        "abort"
      ]
    },
    {
      "field": "temperature_margin_c",
      "json_location": "telemetry_history[].habitat.temperature_margin_c",
      "unit": "°C",
      "condition_roles": [
        "monitoring",
        "abort"
      ]
    },
    {
      "field": "eva_safe_return_margin_min",
      "json_location": "telemetry_history[].habitat.eva_safe_return_margin_min",
      "unit": "min",
      "condition_roles": [
        "monitoring",
        "abort"
      ]
    },
    {
      "field": "mission_status",
      "json_location": "telemetry_history[].habitat.mission_status",
      "unit": "enum",
      "condition_roles": [
        "monitoring",
        "abort",
        "success"
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
      "evidence_id": "EVID-NASA_REF-101",
      "classification": "NASA_REFERENCE",
      "source_title": "Mars Solar Power",
      "locator": "Landis, 2004; Mars illumination, atmosphere, dust deposition, temperature effects",
      "url": "https://ntrs.nasa.gov/api/citations/20040191326/downloads/20040191326.pdf",
      "supports": "Mars-specific factors that can reduce photovoltaic output."
    },
    {
      "evidence_id": "EVID-NASA_REF-102",
      "classification": "NASA_REFERENCE",
      "source_title": "Mars Surface Power Generation Challenges and Considerations",
      "locator": "Dust storms and surface power risk",
      "url": "https://www.nasa.gov/wp-content/uploads/2024/01/mars-surface-power-generation-challenges-and-considerations.pdf",
      "supports": "Dust and atmospheric attenuation can materially reduce surface solar power."
    },
    {
      "evidence_id": "EVID-NASA_REF-103",
      "classification": "NASA_REFERENCE",
      "source_title": "Spacecraft Electrical Power Systems",
      "locator": "Power distribution, regulation and control",
      "url": "https://ntrs.nasa.gov/api/citations/20180007969/downloads/20180007969.pdf",
      "supports": "Energy balance, battery management, protection, sensing, and load control."
    },
    {
      "evidence_id": "EVID-NASA_STD-101",
      "classification": "NASA_STANDARD",
      "source_title": "NASA-STD-3001 Volume 2",
      "locator": "Section 11; V2 11001, 11023, 11024, 11037–11038, 11101",
      "url": "https://www.nasa.gov/reference/11-0-spacesuits-vol-2/",
      "supports": "EVA preparation, suit information, work capability, metabolic monitoring, and rescue resources."
    },
    {
      "evidence_id": "EVID-ARES_REL-101",
      "classification": "ARES_RELEASE_CONFIGURATION",
      "source_title": "ARES-1 release scenario",
      "locator": "solar fault factor, repaired factor, battery and EVA configuration",
      "url": "",
      "supports": "Defines the executable solar-loss and repair model."
    },
    {
      "evidence_id": "EVID-ARES_ASM-101",
      "classification": "ARES_ASSUMPTION",
      "source_title": "ARES-1 repair model",
      "locator": "EVA phase durations, rover requirements, repair progress",
      "url": "",
      "supports": "Maps the simulated repair to the action library."
    }
  ],
  "release_configuration_dependencies": [
    "fault.solar_fault_factor",
    "fault.repaired_solar_fault_factor",
    "solar array configuration",
    "power battery capacity/reserve and load groups",
    "EVA preparation/egress/work/ingress/reserve durations",
    "rover requirement and reserve"
  ],
  "last_reviewed": "2026-07-15",
  "supersedes": [],
  "superseded_by": [],
  "notes": "The simulator models partial restoration after a completed EVA repair; it does not model detailed electrical troubleshooting or physical component replacement.",
  "domain_aliases": [
    "solar degradation",
    "photovoltaic loss",
    "array failure",
    "Mars surface power loss"
  ],
  "chunk_boundary_notes": [
    "Keep EVA feasibility and repair execution constraints together.",
    "Keep load-shedding support separate from the physical repair step."
  ]
}
```

## Purpose

Provide NASA-informed evidence for diagnosing reduced Mars surface solar generation, preserving battery energy, and proposing the simulator-supported EVA array repair. The procedure does not model detailed electrical fault isolation, dust removal hardware, wiring repair, or photovoltaic component replacement.

## Scope and applicability

Apply when `solar_generation_percent` is degraded in `mars_hab_atmosphere_solar_failure`, particularly when `power_margin_kw` is negative or `battery_soc_percent` is declining. NASA references establish that Mars solar performance is affected by atmospheric attenuation, dust deposition, dust storms, incidence, and temperature. The executable fault magnitude and repair effect are ARES release configuration.

## Entry conditions

1. A fault/event identifies solar degradation.
2. `solar_generation_percent` is below the release nominal state.
3. `power_margin_kw` is negative or deteriorating.
4. `battery_soc_percent` is trending toward the configured reserve.
5. The power shortfall threatens atmosphere, thermal, EVA-support, or communications loads.

## Relevant telemetry

| Field | JSON location | Unit | Role | Condition | Evidence |
|---|---|---:|---|---|---|
| `solar_generation_percent` | `telemetry_history[].habitat.solar_generation_percent` | % | Entry / monitoring / success | Compare with nominal and repaired release behavior. | EVID-NASA_REF-101; EVID-NASA_REF-102; EVID-ARES_REL-101 |
| `power_margin_kw` | `telemetry_history[].habitat.power_margin_kw` | kW | Entry / monitoring / abort | Negative margin indicates loads exceed current generation before battery effects. | EVID-NASA_REF-103 |
| `battery_soc_percent` | `telemetry_history[].habitat.battery_soc_percent` | % | Entry / monitoring / abort | Compare with configured reserve and repair timeline. | EVID-NASA_REF-103; EVID-ARES_REL-101 |
| `cabin_temperature_c` | `telemetry_history[].habitat.cabin_temperature_c` | °C | Supporting safety | Detect thermal consequences of load shedding or inadequate power. | NASA-STD-3001 V2 6012–6013 |
| `temperature_margin_c` | `telemetry_history[].habitat.temperature_margin_c` | °C | Abort | Escalate when thermal safety is being lost. | EVID-ARES_REL-101 |
| `eva_safe_return_margin_min` | `telemetry_history[].habitat.eva_safe_return_margin_min` | min | EVA abort | Must remain non-negative while crew are outside. | EVID-NASA_STD-101; EVID-ARES_ASM-101 |
| `mission_status` | `telemetry_history[].habitat.mission_status` | enum | Monitoring / termination | Use exact serialized status. | EVID-ARES_REL-101 |
| `events` | `telemetry_history[].events` | list | Confirmation | Confirm fault, repair phase, completion, abort, and stabilization. | EVID-ARES_ASM-101 |

## Immediate priorities

1. Confirm the power deficit and estimate whether battery reserve can support essential loads until repair completion.
2. Reduce discretionary demand without disabling protected life-support functions.
3. Preserve EVA and rover capability required for repair.
4. Assign only qualified crew through the current action contract.
5. Start repair only when preparation, consumables, power, rover, crew health, and return margin are feasible.
6. Monitor authoritative telemetry through ingress and stabilization.

## Ordered procedure

### Step 1 — Characterize the generation deficit

- **Action mapping:** `INFORMATIONAL_ONLY`
- **Objective:** Correlate solar generation, power margin, battery trend, and fault events.
- **Monitor:** `solar_generation_percent`, `power_margin_kw`, `battery_soc_percent`.
- **Escalate:** Battery reserve cannot cover essential loads to the earliest feasible repair completion.
- **Evidence:** EVID-NASA_REF-101 through 103; EVID-ARES_REL-101.

### Step 2 — Shed discretionary electrical demand

- **Action mapping:** `reduce_power_load`
- **Objective:** Preserve battery energy and essential life-support capability.
- **Required fields:** `type`, `percent`, `start_min`; `load_groups` only if accepted.
- **Monitor:** Power margin, battery SOC, cabin temperature, temperature margin.
- **Abort:** Thermal control or another protected function becomes unsafe.
- **Evidence:** EVID-NASA_REF-103; EVID-ARES_ASM-101.

### Step 3 — Preserve rover availability when required

- **Action mapping:** `delay_rover_use`
- **Objective:** Prevent nonessential rover use before the repair EVA.
- **Required fields:** Use the production contract's `hours` field and `start_min`; do not substitute `duration_min` unless the active schema accepts it.
- **Monitor:** Repair timing and configured rover reserve.
- **Abort:** Delaying the rover makes the critical repair unreachable before the resource deadline.
- **Evidence:** EVID-ARES_REL-101; EVID-ARES_ASM-101.

### Step 4 — Validate EVA readiness

- **Action mapping:** `INFORMATIONAL_ONLY`
- **Objective:** Verify qualified crew, EVA availability, power, consumables, rover reserve, work duration, and safe return.
- **Monitor:** Crew health/vitals, battery SOC, `eva_safe_return_margin_min`, mission events.
- **Abort:** Crew is unqualified, critical/impaired beyond limits, or safe-return margin would become negative.
- **Evidence:** EVID-NASA_STD-101; EVID-ARES_ASM-101.

### Step 5 — Execute solar-array repair

- **Action mapping:** `repair_solar_array`
- **Required fields:** `type`, `start_min`, `duration_min`, and current contract crew assignment field such as `crew_id`.
- **Objective:** Advance the simulator through EVA preparation, egress, work, ingress, and completion.
- **Monitor:** Repair events/status, EVA return margin, crew health, battery SOC, power margin.
- **Abort:** Critical vital/health state, negative safe-return margin, unavailable rover, inadequate power, or simulator abort.
- **Completion evidence:** Simulator-emitted repair completion; the repaired solar factor applies only on completion.
- **Evidence:** EVID-NASA_STD-101; EVID-ARES_REL-101; EVID-ARES_ASM-101.

### Step 6 — Confirm restored power behavior

- **Action mapping:** `INFORMATIONAL_ONLY`
- **Objective:** Verify that solar generation and power margin reflect the completed repair and that battery trend becomes sustainable.
- **Monitor:** `solar_generation_percent`, `power_margin_kw`, `battery_soc_percent`, thermal state.
- **Terminate:** Only the simulator's stabilization logic establishes `STABILIZED`.
- **Evidence:** EVID-ARES_REL-101.

### Step 7 — Transmit mission status when a window is valid

- **Action mapping:** `send_emergency_packet`
- **Objective:** Send a concise status packet without treating communications as a survival resource.
- **Required fields:** `type`, `start_min`.
- **Prerequisite:** Open configured communication window.
- **Evidence:** EVID-ARES_ASM-101; detailed procedure in `comms_blackout.md`.

## Operational constraints

- Mars environmental references explain plausible output degradation but do not define the release fault magnitude.
- The repair action restores only the configured fraction and only after completion.
- Battery, thermal, atmosphere, crew, EVA, rover, and communications constraints remain coupled.
- A repair start that is structurally valid may still fail dynamically.
- `delay_rover_use` has a known contract discrepancy; planner output must follow the strict backend schema and current parser.

## Prohibited or unsupported actions

Do not invent dust-brush deployment, array tilting, panel replacement, cable repair, bypass switching, spare-array deployment, robotic servicing, or manual battery charging. These are not current ARES actions.

## Abort and escalation conditions

Abort or escalate when:

- battery reserve becomes insufficient to support return/ingress and essential loads;
- `eva_safe_return_margin_min` becomes negative or is projected to do so;
- assigned crew become critical or incapacitated;
- repair is rejected, aborted, or cannot finish before the resource deadline;
- thermal or atmosphere safety is lost;
- final outcome becomes `FAILURE` or `REJECTED`.

## Success and termination conditions

- **Repair completion:** Simulator records completed `repair_solar_array`.
- **Power recovery evidence:** Solar generation reflects the configured repaired factor and power/battery trends become sustainable.
- **Mission stabilization:** Exact simulator `STABILIZED` result after all coupled conditions hold for the configured duration.
- **Failure/rejection:** Exact simulator result controls.

## Simulator action mapping

| Procedure step | Exact action type | Required fields | Optional fields | Preconditions | Simulator authority notes |
|---|---|---|---|---|---|
| Load preservation | `reduce_power_load` | `type`, `percent`, `start_min` | `load_groups` | Protected loads retained | Can worsen thermal safety. |
| Rover preservation | `delay_rover_use` | `type`, `hours`, `start_min` | Contract-proven fields only | Rover required and delay does not block repair | Known validator/executor field discrepancy must follow production schema. |
| EVA repair | `repair_solar_array` | `type`, `duration_min`, `start_min`, crew assignment | Contract-proven fields only | Qualified crew, EVA/rover/power/resources | Restoration occurs only on completion. |
| Status transmission | `send_emergency_packet` | `type`, `start_min` | None unless proven | Open communication window | Does not directly improve physical survival. |

## Evidence and source classifications

| Evidence ID | Classification | Source | Supported use |
|---|---|---|---|
| EVID-NASA_REF-101 | NASA_REFERENCE | Landis, *Mars Solar Power* (2004) | Mars illumination, atmosphere, dust and temperature effects. |
| EVID-NASA_REF-102 | NASA_REFERENCE | *Mars Surface Power Generation Challenges and Considerations* | Dust-storm and surface-power risk. |
| EVID-NASA_REF-103 | NASA_REFERENCE | *Spacecraft Electrical Power Systems* | Energy balance, distribution, battery and load control. |
| EVID-NASA_STD-101 | NASA_STANDARD | NASA-STD-3001 Vol. 2, Section 11 | EVA operations, monitoring, work and rescue design requirements. |
| EVID-ARES_REL-101 | ARES_RELEASE_CONFIGURATION | Release scenario | Fault/repaired factors, battery, EVA and rover parameters. |
| EVID-ARES_ASM-101 | ARES_ASSUMPTION | ARES repair model and this procedure | Repair sequencing and simulator mappings. |

## ARES assumptions and release-configuration dependencies

The release simulator uses configured solar area/efficiency, Mars-Sun distance, incidence, atmospheric transmission, dust factor, fault factor and repaired factor. It does not perform electrical circuit diagnosis. EVA durations and performance scaling are ARES assumptions.

## Known limitations

- No detailed solar-array failure mode is identified.
- No robotic repair or dust-removal action exists.
- The current release fixture validates only one tuned repair sequence.
- NASA references support Mars power risks and EVA design principles, not the exact ARES repair duration or restoration percentage.

## Retrieval test cases

| Query | Expected section | Relevant actions | Expected behavior |
|---|---|---|---|
| Mars habitat solar output fell to half nominal | Entry conditions | `reduce_power_load`, `repair_solar_array` | Retrieve this procedure. |
| battery falling before solar repair can finish | Steps 2–5 | load reduction, rover preservation, repair | Return coupled power/EVA constraints. |
| dust storm reduced array output | Scope; evidence | conditional repair | Use NASA Mars-power rationale without claiming release fault cause. |
| send crew to repair solar array | Steps 4–5 | `repair_solar_array` | Require readiness and abort constraints. |
| leaking lab module | Exclusion/cross-domain | `isolate_module` | Prefer `oxygen_leak.md`. |
| CO2 scrubber hardware failed | Exclusion | none direct | Prefer `co2_scrubber_failure.md`. |

## Revision history

| Version | Date | Phase | Summary | Evidence basis | Activation status |
|---|---|---|---|---|---|
| 1.0.0 | 2026-07-15 | Phase 2 manual authoring | Initial solar-generation loss and EVA repair procedure. | NASA Mars power references, NASA-STD-3001, simulator contract. | `PARTIAL_EVIDENCE`; pending repository schema validation and approval. |
