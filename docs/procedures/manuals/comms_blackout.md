# Communications Interruption, Autonomous Operations, and Emergency Packet Transmission

> **Status and use:** ARES-1 simulated mission emergency procedure. Informed by NASA technical and operational references. It is not an official NASA procedure, is not flight-certified, and must not be used for real mission operations. The planner may recommend actions; the deterministic C++ simulator alone determines feasibility, state evolution, validation, and outcome.

## Procedure metadata

```json
{
  "procedure_id": "ARES-PROC-COMMS-001",
  "procedure_version": "1.0.0",
  "title": "Communications Interruption, Autonomous Operations, and Emergency Packet Transmission",
  "filename": "comms_blackout.md",
  "status": "DEFERRED_SOURCE_REQUIRED",
  "applicable_faults": [],
  "applicable_scenarios": [
    "mars_hab_atmosphere_solar_failure"
  ],
  "primary_actions": [
    "send_emergency_packet"
  ],
  "supporting_actions": [
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
        "success"
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
      "field": "power_margin_kw",
      "json_location": "telemetry_history[].habitat.power_margin_kw",
      "unit": "kW",
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
        "entry",
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
    "NASA_REFERENCE",
    "ARES_ASSUMPTION",
    "ARES_RELEASE_CONFIGURATION"
  ],
  "evidence_references": [
    {
      "evidence_id": "EVID-NASA_REF-401",
      "classification": "NASA_REFERENCE",
      "source_title": "SCaN: Communicating with Missions",
      "locator": "Mission communications purpose and infrastructure",
      "url": "https://www.nasa.gov/communicating-with-missions/",
      "supports": "Communications carry commands, telemetry and mission data."
    },
    {
      "evidence_id": "EVID-NASA_REF-402",
      "classification": "NASA_REFERENCE",
      "source_title": "Autonomous Mission Operations",
      "locator": "Time-delay effects and onboard autonomy",
      "url": "https://ntrs.nasa.gov/api/citations/20170011337/downloads/20170011337.pdf",
      "supports": "Deep-space operations require greater onboard decision capability."
    },
    {
      "evidence_id": "EVID-NASA_REF-403",
      "classification": "NASA_REFERENCE",
      "source_title": "Exploration Communications and Navigation Architecture",
      "locator": "Mars one-way light time and loss of near-real-time control",
      "url": "https://ntrs.nasa.gov/api/citations/20100015613/downloads/20100015613.pdf",
      "supports": "Mars delay prevents terrestrial-style real-time control."
    },
    {
      "evidence_id": "EVID-NASA_REF-404",
      "classification": "NASA_REFERENCE",
      "source_title": "LunaNet Architecture",
      "locator": "Delay/Disruption Tolerant Networking and store-and-forward bundles",
      "url": "https://ntrs.nasa.gov/api/citations/20200001555/downloads/20200001555.pdf",
      "supports": "Disruption-tolerant concepts support delayed delivery."
    },
    {
      "evidence_id": "EVID-NASA_REF-405",
      "classification": "NASA_REFERENCE",
      "source_title": "Autonomy Lessons from Deep-Space Human Missions",
      "locator": "Mars communications delay and periodic blackout context",
      "url": "https://ntrs.nasa.gov/citations/20250006447",
      "supports": "Operational rationale for autonomous response during outages."
    },
    {
      "evidence_id": "EVID-ARES_REL-401",
      "classification": "ARES_RELEASE_CONFIGURATION",
      "source_title": "ARES-1 release scenario",
      "locator": "Configured communication windows, transmission duration and power",
      "url": "",
      "supports": "Defines when send_emergency_packet can execute."
    },
    {
      "evidence_id": "EVID-ARES_ASM-401",
      "classification": "ARES_ASSUMPTION",
      "source_title": "ARES communications action",
      "locator": "Emergency packet content and scheduling sequence",
      "url": "",
      "supports": "Maps NASA autonomy principles to the limited simulator action."
    }
  ],
  "release_configuration_dependencies": [
    "communications windows",
    "transmission duration",
    "communications power load",
    "send_emergency_packet timing validation"
  ],
  "last_reviewed": "2026-07-15",
  "supersedes": [],
  "superseded_by": [],
  "notes": "Current serialized telemetry does not expose communication-window state, and no standalone blackout fault exists. Exclude from active RAG until code support is approved.",
  "domain_aliases": [
    "communications blackout",
    "loss of signal",
    "comms outage",
    "delayed contact"
  ],
  "chunk_boundary_notes": [
    "Keep window validation with packet transmission.",
    "Keep future DTN concepts explicitly separate from current simulator capability."
  ]
}
```

## Purpose

Provide NASA-informed operational context for continuing autonomous emergency response during delayed or unavailable Earth communications and for using the current `send_emergency_packet` action during a valid communication window.

## Scope and applicability

Mars communications delay eliminates continuous near-real-time terrestrial control, and disruptions can require onboard autonomy and store-and-forward concepts. Current ARES-1 support is limited: it models scheduled communication windows, transmission power/duration, and one emergency-packet action. It does not model link quality, routing, acknowledgments, retransmission, DTN bundles, antenna pointing, ground-station availability, or a standalone blackout fault.

Because the communication-window state is not currently serialized in habitat telemetry, this manual is `DEFERRED_SOURCE_REQUIRED` and must remain outside the active RAG corpus until the backend exposes an authoritative window/status contract or the planner receives validated window context separately.

## Entry conditions

- Current time is outside a configured communication window.
- An emergency requires independent onboard action before Earth response is possible.
- A communication window is approaching and an emergency status packet must be prepared.
- A prior packet has no simulator-confirmed completion event.

Do not infer a blackout solely from absence of an event. The orchestration layer must provide validated window state.

## Relevant telemetry

| Field | JSON location | Unit | Role | Condition | Evidence |
|---|---|---:|---|---|---|
| `simulation_time_min` | `telemetry_history[].simulation_time_min` | min | Timing | Compare with server-owned configured windows. | EVID-ARES_REL-401 |
| `battery_soc_percent` | `telemetry_history[].habitat.battery_soc_percent` | % | Transmission feasibility | Preserve required communications load without compromising survival. | EVID-ARES_REL-401 |
| `power_margin_kw` | `telemetry_history[].habitat.power_margin_kw` | kW | Transmission feasibility | Transmission consumes configured power. | EVID-ARES_REL-401 |
| `mission_status` | `telemetry_history[].habitat.mission_status` | enum | Packet content / prioritization | Include exact status in backend-generated packet context, not planner-invented state. | EVID-ARES_ASM-401 |
| `events` | `telemetry_history[].events` | list | Completion | Confirm packet action start/completion when emitted. | EVID-ARES_REL-401 |

**Missing authoritative dependency:** communication-window open/closed state is not serialized in the current telemetry snapshot.

## Immediate priorities

1. Continue local emergency response without waiting for Earth when delay or outage makes waiting unsafe.
2. Preserve authoritative telemetry and event history.
3. Prepare a concise packet containing scenario/run identity, current telemetry, actions taken, unresolved risks and simulator result state.
4. Schedule transmission only inside a validated communication window.
5. Preserve enough power for transmission without compromising life support.
6. Do not assume delivery, acknowledgment or Earth intervention.

## Ordered procedure

### Step 1 — Enter autonomous emergency operations

- **Action mapping:** `INFORMATIONAL_ONLY`
- Continue using current procedures and simulator validation.
- NASA autonomy research supports greater onboard authority under deep-space delay; ARES does not model a ground approval dependency.
- **Evidence:** EVID-NASA_REF-402, 403, 405.

### Step 2 — Preserve mission evidence

- **Action mapping:** `INFORMATIONAL_ONLY`
- Retain exact telemetry, timeline, failure reasons, plan and result hashes through backend artifacts.
- **Evidence:** ARES Phase 1 artifact contract; EVID-ARES_ASM-401.

### Step 3 — Build the emergency packet

- **Action mapping:** `INFORMATIONAL_ONLY`
- Packet composition is backend/planner context and must not alter simulator state.
- Include current mission status, fault summary, actions, crew/resource risks and requested support.
- **Evidence:** EVID-NASA_REF-401; EVID-ARES_ASM-401.

### Step 4 — Validate the communication window

- **Action mapping:** `INFORMATIONAL_ONLY`
- Use the trusted scenario configuration or future backend session state.
- Do not derive window status from missing telemetry.
- **Evidence:** EVID-ARES_REL-401.

### Step 5 — Send the emergency packet

- **Action mapping:** `send_emergency_packet`
- **Required fields:** `type="send_emergency_packet"`, `start_min`.
- **Prerequisites:** Open configured window and sufficient power.
- **Monitor:** Events, battery SOC and power margin.
- **Completion evidence:** Simulator marks transmission complete.
- **Evidence:** EVID-ARES_REL-401.

### Step 6 — Continue autonomous recovery after transmission

- **Action mapping:** `INFORMATIONAL_ONLY`
- Transmission does not directly improve atmosphere, power, thermal or crew survival.
- Do not wait for an acknowledgment that the simulator cannot represent.
- **Evidence:** EVID-NASA_REF-402; EVID-ARES_ASM-401.

## Operational constraints

- Mars light-time delay and outages are real mission-architecture concerns; exact ARES windows are fictional release configuration.
- DTN/store-and-forward is NASA reference context only and is not implemented.
- `send_emergency_packet` outside a window is rejected.
- Communications consume configured electrical power.
- No packet content schema or acknowledgment field is currently part of the simulator result.

## Prohibited or unsupported actions

Do not claim or invent:

- link reacquisition
- antenna repointing
- relay selection
- retransmission
- packet acknowledgment
- Earth command receipt
- DTN bundle routing
- emergency frequency changes
- ground-station scheduling

## Abort and escalation conditions

- Packet scheduling is outside the window.
- Transmission power would violate critical survival constraints.
- Action is rejected.
- Emergency conditions require immediate local action rather than waiting for communications.
- Final mission result is `FAILURE` or `REJECTED`.

## Success and termination conditions

The simulator may confirm only that `send_emergency_packet` completed. It does not confirm receipt, interpretation or ground response. Mission stabilization remains independent of communications completion.

## Simulator action mapping

| Procedure step | Exact action type | Required fields | Optional fields | Preconditions | Simulator authority notes |
|---|---|---|---|---|---|
| Send status packet | `send_emergency_packet` | `type`, `start_min` | None unless proven | Open configured window; power available | Completion is transmission-state only. |
| Preserve transmission power | `reduce_power_load` | `type`, `percent`, `start_min` | `load_groups` if accepted | Essential loads protected | Supporting action only. |

## Evidence and source classifications

| Evidence ID | Classification | Source | Supported use |
|---|---|---|---|
| EVID-NASA_REF-401 | NASA_REFERENCE | NASA SCaN | Role of communications in commands and telemetry. |
| EVID-NASA_REF-402 | NASA_REFERENCE | Autonomous Mission Operations | Onboard autonomy under communication delay. |
| EVID-NASA_REF-403 | NASA_REFERENCE | Exploration communications architecture | Mars light-time operational constraint. |
| EVID-NASA_REF-404 | NASA_REFERENCE | LunaNet / DTN | Store-and-forward reference concept. |
| EVID-NASA_REF-405 | NASA_REFERENCE | Deep-space autonomy lessons | Delay/blackout context. |
| EVID-ARES_REL-401 | ARES_RELEASE_CONFIGURATION | Release scenario | Window, duration and power parameters. |
| EVID-ARES_ASM-401 | ARES_ASSUMPTION | This procedure/action | Packet content and sequencing. |

## ARES assumptions and release-configuration dependencies

Communication windows are deterministic schedule entries. The packet is an abstract mission-coordination event. No RF, network or ground-segment physics are modeled.

## Known limitations

- No standalone blackout fault.
- No serialized window state.
- No packet payload or acknowledgment.
- No DTN implementation.
- This document must remain excluded from active RAG until authoritative window context is available.

## Retrieval test cases

| Query | Expected section | Relevant actions | Expected behavior |
|---|---|---|---|
| Earth communications unavailable during habitat emergency | Scope; Steps 1–3 | none initially | Retrieve autonomy guidance but flag deferred status. |
| send emergency packet at next Mars comm window | Steps 4–5 | `send_emergency_packet` | Require validated window state. |
| did mission control receive the packet | Limitations | none | State that receipt is not modeled. |
| isolate leaking lab | Exclusion | `isolate_module` | Prefer oxygen procedure. |

## Revision history

| Version | Date | Phase | Summary | Evidence basis | Activation status |
|---|---|---|---|---|---|
| 1.0.0 | 2026-07-15 | Phase 2 manual authoring | Initial communications interruption and packet procedure. | NASA SCaN/autonomy/DTN references and ARES comm-window contract. | `DEFERRED_SOURCE_REQUIRED`; exclude from active RAG. |
