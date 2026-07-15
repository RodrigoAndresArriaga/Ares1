# ARES-1 Procedure Index

Controlled index for planned emergency procedure manuals. No operational instructions.

Authority: `PROCEDURE_STANDARD.md`, `PHASE_2_CONTRACT_AUDIT.md`, `procedure_metadata.schema.json`, `corpus_manifest.json`.

**File existence does not automatically make a document active RAG evidence.** Only procedures with `status: ACTIVE` that pass the acceptance checklist may enter the active RAG corpus. `READY_FOR_AUTHORING`, `PARTIAL_EVIDENCE`, `DEFERRED_SOURCE_REQUIRED`, `DRAFT`, and `SUPERSEDED` are excluded from active evidence. `ACTIVE_CANDIDATE` in the corpus manifest marks future-RAG eligibility under `PARTIAL_EVIDENCE`; it is not activation.

---

## Planned procedures

| Procedure ID | File path | Filename | Title | Current status | Corpus state | Applicable scenario or condition | Primary simulator actions | Main telemetry dependencies | Current evidence readiness | Known gap | Next authoring priority |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `ARES-PROC-OXY-001` | `docs/procedures/manuals/oxygen_leak.md` | `oxygen_leak.md` | Oxygen / atmosphere leak response | `PARTIAL_EVIDENCE` | `ACTIVE_CANDIDATE` | Release `mars_hab_atmosphere_solar_failure`; fault `atmosphere_and_solar`; leak module `lab` | `isolate_module`, `oxygen_rationing` | `cabin_pressure_kpa`, `inspired_oxygen_mmhg`, `oxygen_hours_remaining`, `co2_one_hour_avg_mmhg`, `mission_status`, crew `spo2_percent` / `alarms` | Strong for fault + isolate path; sparse NASA tagging beyond CO2 | No dedicated oxygen-only fault scenario; scrubber efficiency is not an action | 1 — author first |
| `ARES-PROC-SOLAR-001` | `docs/procedures/manuals/solar_array_failure.md` | `solar_array_failure.md` | Solar array degradation response | `PARTIAL_EVIDENCE` | `ACTIVE_CANDIDATE` | Dual fault solar degradation under release scenario | `repair_solar_array`, `reduce_power_load` | `solar_generation_percent`, `power_margin_kw`, `battery_soc_percent`, `eva_safe_return_margin_min` | Strong in STABILIZED / baseline FAILURE fixtures | Rover-required path not exercised (`eva.rover_required: false`) | 2 |
| `ARES-PROC-PWR-001` | `docs/procedures/manuals/power_rationing.md` | `power_rationing.md` | Habitat electrical demand reduction | `PARTIAL_EVIDENCE` | `ACTIVE_CANDIDATE` | Low power margin / discretionary load shed under dual fault | `reduce_power_load` | `power_margin_kw`, `battery_soc_percent`, action timeline events | Executor load-group vocabulary clear; sample plan uses discretionary shed | Title domain is not the action name; maps to `reduce_power_load` only; no standalone power-only fault | 3 |
| `ARES-PROC-EVA-001` | `docs/procedures/manuals/eva_repair.md` | `eva_repair.md` | EVA solar repair operations | `PARTIAL_EVIDENCE` | `ACTIVE_CANDIDATE` | Solar repair EVA lifecycle under release EVA config | `repair_solar_array` | crew `activity` EVA_*, `eva_safe_return_margin_min`, `active_actions` progress, metrics `eva_completed` | Strong phase durations in release scenario | Separating EVA procedure narrative from solar-array repair mapping requires careful sectioning | 4 |
| `ARES-PROC-COMMS-001` | `docs/procedures/manuals/comms_blackout.md` | `comms_blackout.md` | Communications blackout recovery | `DEFERRED_SOURCE_REQUIRED` | `EXCLUDED` | True closed/missing windows; emergency packet need | `send_emergency_packet` | metrics `communications_sent`; events; window state **not** in habitat JSON | Action + validator strong; no blackout fault type in release | No true blackout scenario; release window stays long-open; only invalid-plan REJECTED demos closed-window scheduling | 5 — only after source approval |
| `ARES-PROC-CO2-001` | `docs/procedures/manuals/co2_scrubber_failure.md` | `co2_scrubber_failure.md` | CO2 scrubber failure response | `DEFERRED_SOURCE_REQUIRED` | `EXCLUDED` | Standalone scrubber degradation / elevated CO2 fault | none dedicated (deferred) | `co2_one_hour_avg_mmhg`, metrics `maximum_co2_one_hour_avg_mmhg`, crew `HYPERCAPNIA` | Atmosphere fields + tagged CO2 limit exist; no scrubber-failure exercise | No scrubber-failure fault; no scrubber-repair action; release fault is leak+solar | 6 — only after source approval |

Supporting actions (index notes; not operational steps):

| Procedure ID | Supporting actions (exact) | Prohibited inventions |
|---|---|---|
| `ARES-PROC-OXY-001` | `reduce_power_load` | Modules/assets outside inventory |
| `ARES-PROC-SOLAR-001` | `delay_rover_use` when rover-required scenarios appear | Non-existent repair tools/assets |
| `ARES-PROC-PWR-001` | — | Shedding protected groups as recommended success path; inventing load groups |
| `ARES-PROC-EVA-001` | `reduce_power_load`, `delay_rover_use` when needed | Non-qualified crew recommendations that ignore simulator checks |
| `ARES-PROC-COMMS-001` | — | Alternate comms modalities |
| `ARES-PROC-CO2-001` | — (deferred) | Invented `repair_scrubber` or scrubber-efficiency actions |

---

## Locked authoring order

1. `oxygen_leak.md`
2. `solar_array_failure.md`
3. `power_rationing.md`
4. `eva_repair.md`
5. `comms_blackout.md` — only after source approval
6. `co2_scrubber_failure.md` — only after source approval

Do not promote items 5–6 out of `DEFERRED_SOURCE_REQUIRED` without approved higher-precedence sources.

---

## Locked naming decisions

| Topic | Decision |
|---|---|
| Canonical filenames | The six names above only |
| Domain vs action | Filename describes emergency/operational domain; need not equal action type |
| Power domain mapping | `power_rationing.md` maps primarily to `reduce_power_load` |
| Comms filename | `comms_blackout.md` (locked) |
| Untagged release numerics | Cite only as `ARES_RELEASE_CONFIGURATION` |

---

## Deferred evidence gaps (summary)

### `comms_blackout.md`

- Missing: true communications-blackout fault/scenario
- Missing: serialized habitat window-open telemetry (window state not in habitat JSON)
- Present but insufficient alone: `send_emergency_packet`, window validator codes, metrics `communications_sent`

### `co2_scrubber_failure.md`

- Missing: scrubber-failure fault type
- Missing: dedicated scrubber repair or efficiency action
- Missing: release scenario exercise of scrubber degradation
- Present but insufficient alone: CO2 telemetry fields and tagged `co2_one_hour_limit_mmhg` as `NASA_STANDARD`

---

## Index change control

- Update this index when procedure status, IDs, or evidence readiness changes
- Keep statuses aligned with `PROCEDURE_STANDARD.md` enums
- Do not add operational steps here
