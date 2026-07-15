# Cabin Carbon-Dioxide Accumulation and Scrubber-Degradation Response

> **Status and use:** ARES-1 simulated mission emergency procedure. Informed by NASA technical and operational references. It is not an official NASA procedure, is not flight-certified, and must not be used for real mission operations. The planner may recommend actions; the deterministic C++ simulator alone determines feasibility, state evolution, validation, and outcome.

## Procedure metadata

```json
{
  "procedure_id": "ARES-PROC-CO2-001",
  "procedure_version": "1.0.0",
  "title": "Cabin Carbon-Dioxide Accumulation and Scrubber-Degradation Response",
  "filename": "co2_scrubber_failure.md",
  "status": "DEFERRED_SOURCE_REQUIRED",
  "applicable_faults": [],
  "applicable_scenarios": [
    "mars_hab_atmosphere_solar_failure"
  ],
  "primary_actions": [],
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
      "field": "co2_one_hour_avg_mmhg",
      "json_location": "telemetry_history[].habitat.co2_one_hour_avg_mmhg",
      "unit": "mmHg",
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
        "monitoring",
        "abort"
      ]
    },
    {
      "field": "battery_soc_percent",
      "json_location": "telemetry_history[].habitat.battery_soc_percent",
      "unit": "%",
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
      "field": "heart_rate_bpm",
      "json_location": "telemetry_history[].crew[].heart_rate_bpm",
      "unit": "bpm",
      "condition_roles": [
        "monitoring",
        "abort"
      ]
    },
    {
      "field": "cognitive_performance_percent",
      "json_location": "telemetry_history[].crew[].cognitive_performance_percent",
      "unit": "%",
      "condition_roles": [
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
    "ARES_ASSUMPTION",
    "ARES_RELEASE_CONFIGURATION"
  ],
  "evidence_references": [
    {
      "evidence_id": "EVID-NASA_STD-501",
      "classification": "NASA_STANDARD",
      "source_title": "NASA-STD-3001 Volume 2",
      "locator": "V2 6004; V2 6020–6022; V2 6107–6108",
      "url": "https://www.nasa.gov/reference/6-0-natural-and-induced-environments-vol-2/",
      "supports": "One-hour CO2 limit, recording/display/alerting, ventilation and off-nominal control."
    },
    {
      "evidence_id": "EVID-NASA_REF-501",
      "classification": "NASA_REFERENCE",
      "source_title": "OCHMO-TB-004 Carbon Dioxide",
      "locator": "CO2 limits and human-performance background",
      "url": "https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-004-carbon-dioxide.pdf",
      "supports": "Operational and health rationale for controlling ppCO2."
    },
    {
      "evidence_id": "EVID-NASA_REF-502",
      "classification": "NASA_REFERENCE",
      "source_title": "Environmental Control and Life Support Systems",
      "locator": "Atmosphere revitalization and CO2-removal technologies",
      "url": "https://ntrs.nasa.gov/api/citations/20210010644/downloads/132-1-Final.pdf",
      "supports": "CO2 removal system context."
    },
    {
      "evidence_id": "EVID-NASA_REF-503",
      "classification": "NASA_REFERENCE",
      "source_title": "NASA ECLSS Technology Development Overview",
      "locator": "CDRA, oxygen generation and exploration needs",
      "url": "https://ntrs.nasa.gov/api/citations/20220010093/downloads/ICES-2022-281%20ECLSS_Overview_July%205th.pdf",
      "supports": "Exploration ECLSS architecture context."
    },
    {
      "evidence_id": "EVID-NASA_REF-504",
      "classification": "NASA_REFERENCE",
      "source_title": "CO2 Removal Onboard the International Space Station",
      "locator": "ISS CO2-removal experience and technology evolution",
      "url": "https://ntrs.nasa.gov/api/citations/20190030370/downloads/20190030370.pdf",
      "supports": "Scrubber technology reference."
    },
    {
      "evidence_id": "EVID-ARES_REL-501",
      "classification": "ARES_RELEASE_CONFIGURATION",
      "source_title": "ARES-1 release scenario",
      "locator": "initial scrubber efficiency, capacity, CO2 thresholds",
      "url": "",
      "supports": "Defines executable CO2 behavior."
    },
    {
      "evidence_id": "EVID-ARES_ASM-501",
      "classification": "ARES_ASSUMPTION",
      "source_title": "ARES physiology and resource model",
      "locator": "Crew CO2 production, modeled exposure and performance response",
      "url": "",
      "supports": "Defines simulated response and limited supporting actions."
    }
  ],
  "release_configuration_dependencies": [
    "initial scrubber efficiency",
    "scrubber capacity",
    "CO2 one-hour warning/failure threshold",
    "crew metabolic profiles and CO2 production",
    "ventilation abstraction",
    "power loads"
  ],
  "last_reviewed": "2026-07-15",
  "supersedes": [],
  "superseded_by": [],
  "notes": "No standalone scrubber-failure fault or scrubber-repair action exists. Exclude from active RAG until direct recovery support is approved.",
  "domain_aliases": [
    "CO2 accumulation",
    "scrubber degradation",
    "hypercapnia risk",
    "atmosphere revitalization failure"
  ],
  "chunk_boundary_notes": [
    "Keep the NASA one-hour average requirement with the monitoring condition.",
    "Keep absence of a direct repair action explicit in every recovery chunk."
  ]
}
```

## Purpose

Provide NASA-grounded evidence for recognizing increasing cabin carbon dioxide, monitoring the one-hour average, reducing crew generation when supported, and protecting atmosphere-revitalization power. The current simulator has no standalone scrubber-failure fault and no action that repairs or replaces the scrubber.

## Scope and applicability

NASA-STD-3001 V2 6004 requires the average one-hour cabin CO2 partial pressure to be no more than 3 mmHg for nominal vehicle/habitat conditions. NASA also requires recording, display and alerting for ppCO2 and adequate ventilation/off-nominal control. ARES serializes `co2_one_hour_avg_mmhg` and models scrubber efficiency/capacity, but the current release scenario does not exercise a dedicated scrubber failure.

This manual is `DEFERRED_SOURCE_REQUIRED` and excluded from active RAG until the simulator adds a supported fault/action path or the project explicitly accepts a no-direct-repair procedure.

## Entry conditions

- `co2_one_hour_avg_mmhg` trends upward toward or beyond the configured warning limit.
- A fault/event identifies scrubber degradation in a future scenario.
- Crew respiratory, cognitive, health or alarm telemetry degrades consistently with the ARES CO2-response model.
- Power degradation threatens scrubber/ventilation capability.

## Relevant telemetry

| Field | JSON location | Unit | Role | Condition | Evidence |
|---|---|---:|---|---|---|
| `co2_one_hour_avg_mmhg` | `telemetry_history[].habitat.co2_one_hour_avg_mmhg` | mmHg | Entry / monitoring / abort | Compare with the NASA nominal 3 mmHg one-hour limit and stricter/alternate scenario thresholds. | EVID-NASA_STD-501; EVID-NASA_REF-501 |
| `simulation_time_min` | `telemetry_history[].simulation_time_min` | min | Averaging context | Preserve the one-hour interpretation. | EVID-NASA_STD-501 |
| `power_margin_kw` | `telemetry_history[].habitat.power_margin_kw` | kW | Supporting cause | Detect loss of atmosphere-revitalization power. | EVID-ARES_REL-501 |
| `battery_soc_percent` | `telemetry_history[].habitat.battery_soc_percent` | % | Supporting cause | Determine power availability for life support. | EVID-ARES_REL-501 |
| `respiratory_rate_bpm` | `telemetry_history[].crew[].respiratory_rate_bpm` | breaths/min | Crew monitoring | ARES-modeled response only. | EVID-ARES_ASM-501 |
| `heart_rate_bpm` | `telemetry_history[].crew[].heart_rate_bpm` | bpm | Crew monitoring | ARES-modeled response only. | EVID-ARES_ASM-501 |
| `cognitive_performance_percent` | `telemetry_history[].crew[].cognitive_performance_percent` | % | Crew monitoring / abort | ARES-modeled performance effect. | EVID-ARES_ASM-501 |
| `health_status` | `telemetry_history[].crew[].health_status` | enum | Abort | Escalate critical/incapacitated crew. | EVID-ARES_ASM-501 |
| `alarms` | `telemetry_history[].crew[].alarms` | list | Entry / abort support | Use exact emitted alarm values. | EVID-ARES_ASM-501 |
| `mission_status` | `telemetry_history[].habitat.mission_status` | enum | Monitoring / termination | Exact serialized state only. | EVID-ARES_REL-501 |
| `events` | `telemetry_history[].events` | list | Fault/action confirmation | Future scrubber fault/event or current supporting actions. | EVID-ARES_REL-501 |

## Immediate priorities

1. Confirm a sustained one-hour CO2 increase rather than relying on a single unsupported instantaneous value.
2. Preserve ventilation and scrubber power.
3. Reduce crew metabolic CO2 generation only through production-valid action vocabulary.
4. Avoid high-workload or EVA tasks when crew performance is degraded.
5. Identify that the current action library has no direct scrubber repair.
6. Return no-safe-plan/rejected-plan evidence when supporting actions cannot hold CO2 below failure conditions.

## Ordered procedure

### Step 1 — Confirm the CO2 trend

- **Action mapping:** `INFORMATIONAL_ONLY`
- Use `co2_one_hour_avg_mmhg` and authoritative history.
- NASA's 3 mmHg value is a nominal one-hour standard, not a universal off-nominal emergency threshold.
- **Evidence:** EVID-NASA_STD-501; EVID-NASA_REF-501.

### Step 2 — Verify atmosphere-revitalization power is preserved

- **Action mapping:** `INFORMATIONAL_ONLY`
- Assess battery and power margin.
- Do not shed scrubber/ventilation power through load reduction.
- **Evidence:** EVID-NASA_REF-502; EVID-ARES_REL-501.

### Step 3 — Reduce metabolic generation when supported

- **Action mapping:** `oxygen_rationing`
- Use only production-valid `level` vocabulary.
- This action can reduce modeled O2 consumption and CO2 generation but may reduce performance and action availability.
- **Evidence:** EVID-ARES_ASM-501.

### Step 4 — Reduce unrelated discretionary electrical demand

- **Action mapping:** `reduce_power_load`
- Preserve atmosphere-revitalization and thermal loads.
- Monitor thermal and power consequences.
- **Evidence:** EVID-ARES_REL-501.

### Step 5 — Monitor crew performance and alarms

- **Action mapping:** `INFORMATIONAL_ONLY`
- Track respiratory rate, heart rate, cognitive performance, health status and alarms as ARES outputs.
- Do not use these simulated mappings as medical diagnosis.
- **Evidence:** EVID-ARES_ASM-501.

### Step 6 — Declare absence of a direct recovery action

- **Action mapping:** `INFORMATIONAL_ONLY`
- If CO2 continues rising and no supported action can stabilize it, the planner should return a rejected/no-safe-plan object rather than inventing scrubber repair.
- **Evidence:** EVID-ARES_ASM-501.

## Operational constraints

- NASA-STD-3001 V2 6004 specifies a nominal one-hour average; off-nominal limits are mission-specific lower-level requirements.
- Current ARES thresholds are release configuration.
- No direct scrubber repair or replacement action exists.
- `oxygen_rationing` is metabolic-demand control, not CO2 removal.
- `reduce_power_load` must preserve atmosphere revitalization and ventilation.
- Crew physiology outputs are ARES assumptions.

## Prohibited or unsupported actions

Do not invent cartridge replacement, bed switching, sorbent regeneration, fan repair, emergency lithium-hydroxide deployment, venting, oxygen flushing, mask use, medical treatment, or module evacuation.

## Abort and escalation conditions

- `co2_one_hour_avg_mmhg` reaches the configured hard-failure threshold.
- Crew become critical/incapacitated.
- Atmosphere-revitalization power is lost.
- Supporting actions are rejected or worsen coupled constraints.
- No supported plan can prevent failure.
- Final outcome is `FAILURE` or `REJECTED`.

## Success and termination conditions

- CO2 trend becomes controlled according to authoritative telemetry.
- Supporting action completion is not equivalent to scrubber recovery.
- Only simulator `STABILIZED` establishes mission stabilization.
- Current release cannot demonstrate standalone scrubber repair success.

## Simulator action mapping

| Procedure step | Exact action type | Required fields | Optional fields | Preconditions | Simulator authority notes |
|---|---|---|---|---|---|
| Reduce metabolic generation | `oxygen_rationing` | `type`, `level`, `start_min` | `crew_id` if accepted | Production-valid level; performance trade accepted | No CO2 removal, only lower generation. |
| Preserve life-support power | `reduce_power_load` | `type`, `percent`, `start_min` | `load_groups` if accepted | Scrubber/ventilation/thermal loads protected | Can only indirectly support CO2 control. |

## Evidence and source classifications

| Evidence ID | Classification | Source | Supported use |
|---|---|---|---|
| EVID-NASA_STD-501 | NASA_STANDARD | NASA-STD-3001 Vol. 2, V2 6004, 6020–6022, 6107–6108 | One-hour nominal limit and atmosphere monitoring/control. |
| EVID-NASA_REF-501 | NASA_REFERENCE | OCHMO-TB-004 | CO2 health/performance context. |
| EVID-NASA_REF-502 | NASA_REFERENCE | *Environmental Control and Life Support Systems* | CO2-removal architecture and technology context. |
| EVID-NASA_REF-503 | NASA_REFERENCE | NASA ECLSS technology overview | Exploration ECLSS context. |
| EVID-NASA_REF-504 | NASA_REFERENCE | *CO2 Removal Onboard the ISS* | Operational technology history. |
| EVID-ARES_REL-501 | ARES_RELEASE_CONFIGURATION | Scenario configuration | Scrubber capacity/efficiency and thresholds. |
| EVID-ARES_ASM-501 | ARES_ASSUMPTION | ARES resource/physiology models | Crew generation and response behavior. |

## ARES assumptions and release-configuration dependencies

The simulator uses configured scrubber efficiency and capacity, rolling one-hour history and deterministic crew response. It does not model actual CDRA bed cycles, sorbent chemistry, valves, fans or repair.

## Known limitations

- No standalone failure injection.
- No direct recovery action.
- No instantaneous/local CO2 pocket telemetry.
- Crew response is simulated, not medically validated.
- Must remain outside active RAG until the project approves this constrained behavior.

## Retrieval test cases

| Query | Expected section | Relevant actions | Expected behavior |
|---|---|---|---|
| cabin one-hour CO2 average is rising | Entry; Step 1 | none direct | Retrieve this procedure and deferred warning. |
| reduce crew CO2 production | Step 3 | `oxygen_rationing` | Require valid vocabulary and performance warning. |
| scrubber hardware failed | Steps 2 and 6 | no direct repair | Return no-supported-repair limitation. |
| replace CO2 cartridge | Unsupported actions | none | Do not invent action. |
| oxygen leak in lab | Exclusion | `isolate_module` | Prefer oxygen procedure. |

## Revision history

| Version | Date | Phase | Summary | Evidence basis | Activation status |
|---|---|---|---|---|---|
| 1.0.0 | 2026-07-15 | Phase 2 manual authoring | Initial CO2 accumulation and scrubber-degradation procedure. | NASA-STD-3001, NASA ECLSS references, simulator contract. | `DEFERRED_SOURCE_REQUIRED`; exclude from active RAG. |
