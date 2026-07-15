# Habitat Electrical Load Reduction and Battery Preservation

> **Status and use:** ARES-1 simulated mission emergency procedure. Informed by NASA technical and operational references. It is not an official NASA procedure, is not flight-certified, and must not be used for real mission operations. The planner may recommend actions; the deterministic C++ simulator alone determines feasibility, state evolution, validation, and outcome.

## Procedure metadata

```json
{
  "procedure_id": "ARES-PROC-PWR-001",
  "procedure_version": "1.0.0",
  "title": "Habitat Electrical Load Reduction and Battery Preservation",
  "filename": "power_rationing.md",
  "status": "PARTIAL_EVIDENCE",
  "applicable_faults": [
    "atmosphere_and_solar"
  ],
  "applicable_scenarios": [
    "mars_hab_atmosphere_solar_failure"
  ],
  "primary_actions": [
    "reduce_power_load"
  ],
  "supporting_actions": [
    "delay_rover_use",
    "send_emergency_packet"
  ],
  "prohibited_actions": [],
  "telemetry_dependencies": [
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
      "field": "solar_generation_percent",
      "json_location": "telemetry_history[].habitat.solar_generation_percent",
      "unit": "%",
      "condition_roles": [
        "entry",
        "monitoring"
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
      "field": "oxygen_hours_remaining",
      "json_location": "telemetry_history[].habitat.oxygen_hours_remaining",
      "unit": "hr",
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
      "evidence_id": "EVID-NASA_REF-201",
      "classification": "NASA_REFERENCE",
      "source_title": "Space Vehicle Powerdown Philosophies Derived from the Space Shuttle Program",
      "locator": "Real-time management of electrical equipment and vehicle power level",
      "url": "https://ntrs.nasa.gov/api/citations/20110000783/downloads/20110000783.pdf",
      "supports": "Powerdown and load-prioritization philosophy."
    },
    {
      "evidence_id": "EVID-NASA_REF-202",
      "classification": "NASA_REFERENCE",
      "source_title": "Spacecraft Electrical Power Systems",
      "locator": "Power distribution, regulation and control",
      "url": "https://ntrs.nasa.gov/api/citations/20180007969/downloads/20180007969.pdf",
      "supports": "Energy balance, battery management, protection and load control."
    },
    {
      "evidence_id": "EVID-NASA_STD-201",
      "classification": "NASA_STANDARD",
      "source_title": "NASA-STD-3001 Volume 2",
      "locator": "V2 6012–6013; V2 6017; V2 6108",
      "url": "https://www.nasa.gov/reference/6-0-natural-and-induced-environments-vol-2/",
      "supports": "Thermal and atmosphere functions must remain controlled during off-nominal operations."
    },
    {
      "evidence_id": "EVID-ARES_REL-201",
      "classification": "ARES_RELEASE_CONFIGURATION",
      "source_title": "ARES-1 release scenario",
      "locator": "essential, discretionary, thermal-control, EVA-support and communications load configuration",
      "url": "",
      "supports": "Defines current load categories and reserves."
    },
    {
      "evidence_id": "EVID-ARES_ASM-201",
      "classification": "ARES_ASSUMPTION",
      "source_title": "ARES-1 ActionExecutor",
      "locator": "reduce_power_load behavior",
      "url": "",
      "supports": "Defines selectable load reduction and thermal coupling."
    }
  ],
  "release_configuration_dependencies": [
    "power essential/discretionary/thermal/EVA/communications loads",
    "battery capacity, reserve, charge/discharge efficiency",
    "reduce_power_load accepted percent and load_groups",
    "thermal limits and stabilization hold"
  ],
  "last_reviewed": "2026-07-15",
  "supersedes": [],
  "superseded_by": [],
  "notes": "The filename describes the emergency domain; the exact simulator action is reduce_power_load.",
  "domain_aliases": [
    "power rationing",
    "load shedding",
    "powerdown",
    "battery preservation"
  ],
  "chunk_boundary_notes": [
    "Keep protected-load constraints with each load-reduction recommendation.",
    "Keep thermal consequences adjacent to power actions."
  ]
}
```

## Purpose

Provide controlled evidence for reducing discretionary electrical demand and preserving battery energy during generation shortfall. The exact simulator action is `reduce_power_load`; “power rationing” is the document domain, not an action alias.

## Scope and applicability

Apply when power generation cannot support current loads, `power_margin_kw` is negative, or `battery_soc_percent` is declining toward the configured reserve. The procedure supports the compound atmosphere-and-solar release scenario and must preserve essential atmosphere, thermal, EVA-support, and communications capabilities as required by the active plan.

## Entry conditions

- Negative or deteriorating `power_margin_kw`.
- Declining `battery_soc_percent` under degraded `solar_generation_percent`.
- A forecast that essential operations or repair cannot complete before reserve depletion.
- A planned EVA or communications transmission that requires preserved electrical margin.

## Relevant telemetry

| Field | JSON location | Unit | Role | Condition | Evidence |
|---|---|---:|---|---|---|
| `power_margin_kw` | `telemetry_history[].habitat.power_margin_kw` | kW | Entry / monitoring / success | Seek a sustainable nonnegative or otherwise simulator-acceptable trend. | EVID-NASA_REF-202 |
| `battery_soc_percent` | `telemetry_history[].habitat.battery_soc_percent` | % | Entry / monitoring / abort | Compare with configured reserve and task deadlines. | EVID-NASA_REF-201; EVID-ARES_REL-201 |
| `solar_generation_percent` | `telemetry_history[].habitat.solar_generation_percent` | % | Cause / monitoring | Establish available generation. | EVID-NASA_REF-202 |
| `cabin_temperature_c` | `telemetry_history[].habitat.cabin_temperature_c` | °C | Safety monitoring | Detect consequences of thermal-control load changes. | EVID-NASA_STD-201 |
| `temperature_margin_c` | `telemetry_history[].habitat.temperature_margin_c` | °C | Abort | Do not preserve power by crossing thermal safety limits. | EVID-NASA_STD-201; EVID-ARES_REL-201 |
| `oxygen_hours_remaining` | `telemetry_history[].habitat.oxygen_hours_remaining` | hr | Coupled safety | Ensure power actions do not compromise atmosphere recovery. | EVID-NASA_STD-201 |
| `mission_status` | `telemetry_history[].habitat.mission_status` | enum | Monitoring / termination | Exact serialized status only. | EVID-ARES_REL-201 |
| `events` | `telemetry_history[].events` | list | Confirmation | Confirm action start/completion and warnings. | EVID-ARES_ASM-201 |

## Immediate priorities

1. Preserve essential life support.
2. Reduce discretionary demand early enough to affect the resource deadline.
3. Preserve thermal safety.
4. Reserve EVA and rover energy for critical repair when required.
5. Avoid unnecessary communications load outside valid windows.
6. Reassess after every authoritative telemetry sample.

## Ordered procedure

### Step 1 — Establish the deficit and deadline

- **Action mapping:** `INFORMATIONAL_ONLY`
- Determine generation, load margin, battery reserve and the time required for critical recovery.
- Escalate when no feasible powerdown can bridge the gap.
- **Evidence:** EVID-NASA_REF-201; EVID-NASA_REF-202.

### Step 2 — Identify protected and discretionary loads

- **Action mapping:** `INFORMATIONAL_ONLY`
- Protect atmosphere control, minimum thermal control, required EVA support, and required communications.
- Use only load groups exposed by the current action contract.
- **Evidence:** EVID-NASA_STD-201; EVID-ARES_REL-201.

### Step 3 — Reduce discretionary load

- **Action mapping:** `reduce_power_load`
- **Required fields:** `type="reduce_power_load"`, `percent`, `start_min`.
- **Optional:** `load_groups` only when accepted by production.
- Monitor power margin, battery SOC and thermal response.
- Abort or revise when thermal margin worsens toward failure or protected functions are compromised.
- **Evidence:** EVID-NASA_REF-201; EVID-ARES_ASM-201.

### Step 4 — Preserve rover energy when repair depends on it

- **Action mapping:** `delay_rover_use`
- Use the production-supported `hours` field.
- Do not delay use beyond the point at which repair becomes impossible.
- **Evidence:** EVID-ARES_REL-201.

### Step 5 — Schedule communications deliberately

- **Action mapping:** `send_emergency_packet`
- Transmit only during a valid configured window.
- Treat transmission as coordination, not a direct physical recovery.
- **Evidence:** EVID-ARES_REL-201.

### Step 6 — Verify coupled safety

- **Action mapping:** `INFORMATIONAL_ONLY`
- Confirm battery, power margin, temperature, atmosphere reserve, EVA support and crew state remain acceptable.
- The simulator determines whether the load reduction is sufficient.
- **Evidence:** EVID-NASA_STD-201; EVID-ARES_ASM-201.

### Step 7 — Maintain or restore loads only through a new validated plan

- **Action mapping:** `INFORMATIONAL_ONLY`
- The current action library does not provide a general restore-load action.
- Do not claim restoration or manually mutate state.
- **Evidence:** EVID-ARES_ASM-201.

## Operational constraints

- Power is a coupled subsystem. Reducing thermal-control load can conserve energy while creating a thermal failure.
- Essential loads must not be silently disabled.
- The accepted `percent` range and load-group vocabulary come from the strict production schema.
- A reduction that improves battery trend may still produce `FAILURE` through atmosphere, thermal, EVA, or crew constraints.
- NASA powerdown references provide operational philosophy, not the exact ARES load percentages.

## Prohibited or unsupported actions

Do not invent generator startup, battery swapping, bus reconfiguration, external power transfer, manual breaker operations, fuel-cell activation, or load restoration.

## Abort and escalation conditions

- Battery reserve becomes insufficient for essential operations.
- Temperature margin reaches the configured critical boundary.
- Powerdown prevents required atmosphere control or EVA return.
- Action is rejected or fails.
- Final outcome becomes `FAILURE` or `REJECTED`.

## Success and termination conditions

- Action completion is simulator-recorded completion of `reduce_power_load`.
- Powerdown effectiveness requires a sustainable power/battery trend without violating coupled constraints.
- Mission success is only the simulator's `STABILIZED` result.

## Simulator action mapping

| Procedure step | Exact action type | Required fields | Optional fields | Preconditions | Simulator authority notes |
|---|---|---|---|---|---|
| Reduce demand | `reduce_power_load` | `type`, `percent`, `start_min` | `load_groups` | Protected loads retained | Executor applies configured reductions and heat coupling. |
| Reserve rover | `delay_rover_use` | `type`, `hours`, `start_min` | None unless proven | Delay does not block critical repair | Field discrepancy must follow production schema. |
| Transmit packet | `send_emergency_packet` | `type`, `start_min` | None unless proven | Open comm window; power available | No direct survival effect. |

## Evidence and source classifications

| Evidence ID | Classification | Source | Supported use |
|---|---|---|---|
| EVID-NASA_REF-201 | NASA_REFERENCE | *Space Vehicle Powerdown Philosophies Derived from the Space Shuttle Program* | Real-time powerdown and equipment management philosophy. |
| EVID-NASA_REF-202 | NASA_REFERENCE | *Spacecraft Electrical Power Systems* | Energy balance, protection, battery and load control. |
| EVID-NASA_STD-201 | NASA_STANDARD | NASA-STD-3001 Vol. 2 | Atmosphere/thermal functions to preserve during off-nominal operation. |
| EVID-ARES_REL-201 | ARES_RELEASE_CONFIGURATION | Release scenario | Load categories, battery reserve and subsystem demands. |
| EVID-ARES_ASM-201 | ARES_ASSUMPTION | ActionExecutor and procedure | Load-reduction behavior and prioritization. |

## ARES assumptions and release-configuration dependencies

The scenario defines battery capacity, reserve, efficiencies and categorized loads. The procedure assumes discretionary loads can be reduced without directly mutating essential loads. Exact reduction effects are simulator-owned.

## Known limitations

- No restore-load action exists.
- No electrical bus or component-level telemetry is serialized.
- The release model is energy-balance oriented, not a detailed spacecraft EPS simulation.
- NASA references do not validate the scenario's percentages or reserve values.

## Retrieval test cases

| Query | Expected section | Relevant actions | Expected behavior |
|---|---|---|---|
| battery draining because solar power is low | Entry; Steps 1–3 | `reduce_power_load` | Retrieve this procedure. |
| shed nonessential habitat loads | Steps 2–3 | `reduce_power_load` | Return protected-load constraints. |
| powerdown is making cabin too cold | Step 6; abort | revise/abort | Retrieve thermal coupling. |
| save rover battery for EVA | Step 4 | `delay_rover_use` | Cross-retrieve EVA procedure. |
| isolate leaking lab | Exclusion | `isolate_module` | Prefer oxygen procedure. |

## Revision history

| Version | Date | Phase | Summary | Evidence basis | Activation status |
|---|---|---|---|---|---|
| 1.0.0 | 2026-07-15 | Phase 2 manual authoring | Initial load-reduction and battery-preservation procedure. | NASA power references, NASA-STD-3001, simulator contract. | `PARTIAL_EVIDENCE`; pending repository schema validation and approval. |
