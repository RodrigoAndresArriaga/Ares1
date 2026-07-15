# ARES-1 Procedure Document Standard

Controlled format for every ARES-1 emergency procedure manual. Companion artifacts: `PROCEDURE_INDEX.md`, `procedure_metadata.schema.json`. Authority inventory: `PHASE_2_CONTRACT_AUDIT.md`.

---

## 1. Purpose and authority

The procedure collection is the controlled RAG knowledge base for ARES-1.

Procedures provide:

- evidence-backed operational recommendations
- permitted simulator action mappings
- telemetry monitoring and abort framing
- citation anchors for frontend explanations

Procedures do not:

- determine whether a plan works
- decide action feasibility, physical state changes, crew physiology, action completion or abort, mission status, metrics, timeline, failure reasons, or outcome

Boundary:

| Role | Authority |
|---|---|
| Procedure manuals | Evidence and permitted recommendations |
| Planner | Proposes actions and plan narrative |
| C++ simulator | Sole authority for validation, execution effects, and results |
| Frontend explanations | Must remain traceable to procedure section IDs and simulator output fields |

Source precedence (must not be inverted):

1. Current C++ implementation and serializer
2. Current release scenario and plan fixtures
3. Captured simulator result fixtures
4. Strict Phase 1 backend schemas
5. Current development guides and repository documentation
6. Original project-overview examples (lowest priority; missing overview must not override higher contracts)

---

## 2. Canonical document layout

Every procedure Markdown file must use this exact section order. Do not reorder, rename, or omit required headings.

```markdown
# Procedure title

## Procedure metadata

## Purpose

## Scope and applicability

## Entry conditions

## Relevant telemetry

## Immediate priorities

## Ordered procedure

## Operational constraints

## Prohibited or unsupported actions

## Abort and escalation conditions

## Success and termination conditions

## Simulator action mapping

## Evidence and source classifications

## ARES assumptions and release-configuration dependencies

## Known limitations

## Retrieval test cases

## Revision history
```

### Section content rules

| Section | May contain | Must not contain |
|---|---|---|
| Procedure title (`#`) | Human-readable domain title | Simulator action aliases as the sole title identity |
| Procedure metadata | Machine fields listed in §3 (YAML front matter or structured block matching the schema) | Retrieval/rerank scores; outcome/metrics/`valid_plan`/`mission_status` as planner-controlled data |
| Purpose | Why the procedure exists; operational objective in plain language | Guarantees of survival or mission success |
| Scope and applicability | Applicable faults, scenarios, crew/asset context from contract audit | Invented modules, equipment, or fault types |
| Entry conditions | Observable serialized telemetry conditions with evidence classification | Untagged numerics upgraded to NASA claims |
| Relevant telemetry | Exact JSON field table per §5 | Non-serialized or invented field names alone |
| Immediate priorities | Short ranked operational intents before numbered steps | Action success claims |
| Ordered procedure | Numbered steps per §9 | Fake steps for unsupported domains |
| Operational constraints | Resource, crew, timing, load-group, and window constraints | Direct physical-state mutation instructions |
| Prohibited or unsupported actions | Explicit bans and deferred capabilities | Silent omission of known unsupported inventable actions |
| Abort and escalation conditions | Conditional abort/escalate rules tied to telemetry or action status | Claims that abort restores a safe state without simulator validation |
| Success and termination conditions | Observable completion evidence; expected operational objectives | Guarantees that the plan will stabilize |
| Simulator action mapping | Exact mapping table per §7 | Aliased action type strings in planner-facing rows |
| Evidence and source classifications | Evidence IDs, classifications, repository references | Test-only tags presented as release authority |
| ARES assumptions and release-configuration dependencies | Explicit ARES_ASSUMPTION and ARES_RELEASE_CONFIGURATION dependencies | NASA labeling of those dependencies |
| Known limitations | Evidence gaps, deferred sections, contract discrepancies | Placeholder operational instructions |
| Retrieval test cases | Query → expected procedure/section/chunk identifiers | Hard-coded retrieval or rerank scores |
| Revision history | Version, date, author/role, change summary, re-embed flag | Undocumented supersession |

Informational-only documents at `READY_FOR_AUTHORING` may ship structural shells with empty operational bodies marked for authoring. They must not invent steps.

---

## 3. Procedure metadata fields

### 3.1 Required fields

| Field | Type | Meaning |
|---|---|---|
| `procedure_id` | string | Stable identifier (`ARES-PROC-[DOMAIN]-[NNN]`) |
| `procedure_version` | string | SemVer `MAJOR.MINOR.PATCH` |
| `title` | string | Human-readable title |
| `filename` | string | Canonical `.md` filename |
| `status` | enum | Lifecycle status (§3.3) |
| `applicable_faults` | string[] | Fault or condition labels (e.g. release `failure_type`) |
| `applicable_scenarios` | string[] | Scenario IDs (e.g. `mars_hab_atmosphere_solar_failure`) |
| `primary_actions` | string[] | Exact serialized simulator action types this procedure centers on |
| `supporting_actions` | string[] | Exact serialized actions that may assist |
| `prohibited_actions` | string[] | Exact serialized actions this procedure forbids recommending in context (subset of inventory or declared unsupported inventable names as prose notes only; array itself holds only inventory action strings when banning inventory use) |
| `telemetry_dependencies` | object[] | Structured telemetry refs (§5) |
| `source_classifications` | string[] | Classification enums used in the document |
| `evidence_references` | object[] | Structured evidence refs (§4) |
| `release_configuration_dependencies` | string[] | Untagged or release-config parameter paths described as ARES_RELEASE_CONFIGURATION |
| `last_reviewed` | string | ISO date `YYYY-MM-DD` |
| `supersedes` | string[] | Prior `procedure_id` values (may be empty) |
| `superseded_by` | string[] | Replacement `procedure_id` values (may be empty) |

`primary_actions` may be empty only when `status` is `PARTIAL_EVIDENCE` or `DEFERRED_SOURCE_REQUIRED` and no dedicated primary action exists in the inventory.

### 3.2 Optional fields (justified)

| Field | Type | When allowed |
|---|---|---|
| `notes` | string | Non-normative authoring notes |
| `domain_aliases` | string[] | Display/prose labels only; never replace exact action or telemetry names |
| `chunk_boundary_notes` | string[] | Chunking review notes for RAG pipeline |

Do not author `retrieval_score`, `rerank_score`, `outcome`, `valid_plan`, `metrics`, `failure_reasons`, `survival_probability`, or `mission_status` as procedure metadata.

### 3.3 Status values

| Status | Meaning | Active RAG evidence |
|---|---|---|
| `DRAFT` | Incomplete shell | No |
| `READY_FOR_AUTHORING` | Structure and metadata ready; operational content may follow | No (not active evidence until `ACTIVE`) |
| `PARTIAL_EVIDENCE` | Some sections supportable; gaps documented | No |
| `DEFERRED_SOURCE_REQUIRED` | Insufficient repository evidence for credible procedure | No |
| `ACTIVE` | Passed acceptance checklist; eligible for RAG corpus | Yes |
| `SUPERSEDED` | Replaced by another procedure version/id | No |

File existence does not make a document active RAG evidence. Only `ACTIVE` documents are eligible.

### 3.4 Identifier formats

All IDs are deterministic, human-readable, and stable across re-indexing.

| Identifier | Format | Example |
|---|---|---|
| `procedure_id` | `ARES-PROC-[DOMAIN]-[NNN]` | `ARES-PROC-OXY-001` |
| `section_id` | `[procedure_id]-SEC-[NNN]` | `ARES-PROC-OXY-001-SEC-007` |
| `chunk_id` | `[procedure_id]-v[MAJOR.MINOR.PATCH]-CH-[NNN]` | `ARES-PROC-OXY-001-v1.0.0-CH-003` |
| `evidence_id` | `EVID-[CLASS_SHORT]-[NNN]` | `EVID-NASA_STD-001` |
| `procedure_version` | `MAJOR.MINOR.PATCH` | `1.0.0` |

Domain codes (locked to planned manuals):

| Domain | Canonical filename |
|---|---|
| `OXY` | `oxygen_leak.md` |
| `SOLAR` | `solar_array_failure.md` |
| `PWR` | `power_rationing.md` |
| `EVA` | `eva_repair.md` |
| `COMMS` | `comms_blackout.md` |
| `CO2` | `co2_scrubber_failure.md` |

Evidence class short codes:

| Classification | CLASS_SHORT |
|---|---|
| `NASA_STANDARD` | `NASA_STD` |
| `NASA_REFERENCE` | `NASA_REF` |
| `DERIVED_PHYSICS` | `DER_PHYS` |
| `ARES_ASSUMPTION` | `ARES_ASM` |
| `ARES_RELEASE_CONFIGURATION` | `ARES_REL` |

Canonical filenames (exact):

- `oxygen_leak.md`
- `solar_array_failure.md`
- `power_rationing.md`
- `eva_repair.md`
- `comms_blackout.md`
- `co2_scrubber_failure.md`

The filename describes the emergency or operational domain. It does not have to equal a simulator action type. Example: `power_rationing.md` maps primarily to `reduce_power_load`.

### 3.5 Allowed simulator action strings

Planner-facing metadata and mapping tables may use only these exact serialized types:

- `reduce_power_load`
- `isolate_module`
- `oxygen_rationing`
- `repair_solar_array`
- `delay_rover_use`
- `send_emergency_packet`

No invented actions. No action aliases in planner-facing data.

### 3.6 Oxygen rationing `level` values

When mapping `oxygen_rationing`, `level` must be one of the exact strings accepted by current production executor parsing:

- `sleep`
- `rest`
- `resting`
- `nominal`
- `nominal_work`
- `nominalwork`
- `high`
- `high_workload`
- `highworkload`
- `recovery`

Do not introduce aliases such as `low`, `severe`, `maximum`, `emergency`, or `conservative`.

---

## 4. Evidence classifications

Procedures may use only these classifications.

| Classification | Allowed claim strength | Required citation | May define entry condition | May define abort condition | May define simulator behavior | Uncertainty / limitations |
|---|---|---|---|---|---|---|
| `NASA_STANDARD` | Strong limit/exposure claim when release (or higher-precedence) source attaches the tag | Repository path + `parameter_name` / evidence_id | Yes, when tagged | Yes, when tagged | No | State if only warning vs failure semantics differ |
| `NASA_REFERENCE` | Design/metabolic reference claim when tagged | Repository path + parameter/evidence | Yes, when tagged | Yes, when tagged | No | Do not imply certification |
| `DERIVED_PHYSICS` | Unit conversion / conservation framing | Derivation note + repository reference | Yes, when applied to observable fields | Yes, when applied to observable fields | No — may describe relations, not rewrite executor physics | Mark as derived, not empirical NASA publication |
| `ARES_ASSUMPTION` | Scenario tuning / fictional habitat claim | Explicit assumption statement + evidence_id | Yes, if labeled as assumption | Yes, if labeled as assumption | No | Must stay labeled assumption; never upgrade to NASA_* |
| `ARES_RELEASE_CONFIGURATION` | Untagged numeric values present in the release scenario | Scenario path + parameter path; classify as release configuration only | Yes, only as release-config dependency | Yes, only as release-config dependency | No | Must not be upgraded to NASA_STANDARD or NASA_REFERENCE |

### 4.1 Forbidden practices

- Converting ARES assumptions or release-configuration values into NASA claims
- Citing the project overview as proof of executable behavior
- Citing tests as external scientific authority for manuals
- Presenting simulated telemetry as authentic NASA telemetry
- Using test-only `parameter_sources` (e.g. physiology test helpers) as authoritative manual source metadata
- Inventing thresholds not present in higher-precedence contracts

### 4.2 Evidence reference object shape

Each evidence reference must include:

| Field | Required | Meaning |
|---|---|---|
| `evidence_id` | Yes | `EVID-[CLASS_SHORT]-[NNN]` |
| `classification` | Yes | One of the five classifications |
| `source_title` | Yes | Source document title |
| `locator` | Yes | Section, parameter, or contract locator |
| `supports` | Yes | Supported claim / use of this evidence |
| `url` | No | Optional URL; empty string allowed when repository-local |

---

## 5. Telemetry reference rules

Procedures may reference only fields proven by the current serializer and listed in `PHASE_2_CONTRACT_AUDIT.md` §4.1.

Non-serialized in-memory fields (§4.2 of the audit) are forbidden until they appear in the serialized contract.

### 5.1 Required attributes per telemetry reference

| Attribute | Requirement |
|---|---|
| Exact JSON field name | Mandatory; no alias replacement |
| JSON location | Mandatory (e.g. `telemetry_history[].habitat`, `metrics`, root) |
| Unit | Mandatory (or `—` when unitless) |
| Condition type / role | `entry`, `monitoring`, `abort`, and/or `success` |
| Comparison operator | Where applicable (`<`, `<=`, `>`, `>=`, `==`, `present`) |
| Threshold source | Classification + evidence_id or release-config dependency |
| Expected monitoring cadence | e.g. per sample, final metrics, per event |
| Condition role classification | Entry / monitoring / abort / success |

Display labels may appear in addition to the exact field name, never instead of it.

### 5.2 Recommended table format

| Field | JSON location | Unit | Role | Condition | Evidence |
|---|---|---|---|---|---|
| `cabin_pressure_kpa` | `telemetry_history[].habitat` | kPa | entry / monitoring / abort | `field` compared to release-configuration or tagged limit | `EVID-...` |

Do not insert new numerical emergency thresholds in this standard document.

### 5.3 Metadata object shape (`telemetry_dependencies`)

| Field | Required | Meaning |
|---|---|---|
| `field` | Yes | Exact JSON field name |
| `json_location` | Yes | Nested path in result/sample JSON |
| `unit` | Yes | Unit string |
| `condition_roles` | Yes | Array of `entry` \| `monitoring` \| `abort` \| `success` |
| `display_label` | No | Human label only |

---

## 6. Condition representation

Use a machine-readable style for conditions.

### 6.1 Permitted forms

- `field < configured threshold`
- `field <= release configuration value`
- `field > configured threshold`
- `field >= configured threshold`
- `enum == exact serialized value`
- `boolean == true` / `boolean == false`
- `event code present`
- `action status == exact serialized value`

Exact serialized examples for status/outcome enums must match production contracts (e.g. action `status` ∈ `PENDING`, `ACTIVE`, `COMPLETE`, `FAILED`, `ABORTED`; result `outcome` ∈ `STABILIZED`, `FAILURE`, `REJECTED`).

### 6.2 Numerical threshold source

Every numerical condition must identify exactly one of:

- `NASA_STANDARD`
- `NASA_REFERENCE`
- `DERIVED_PHYSICS`
- `ARES_ASSUMPTION`
- `ARES_RELEASE_CONFIGURATION`

This standard does not insert actual new thresholds. Authors must pull values from higher-precedence sources and label them correctly.

---

## 7. Simulator action mapping rules

### 7.1 Required mapping table

| Procedure step | Exact action type | Required fields | Optional fields | Preconditions | Simulator authority notes |
|---|---|---|---|---|---|

### 7.2 Requirements

- Use exact serialized action names (§3.5)
- Use exact action field names from the contract audit
- Use exact units (`percent`, minutes, hours, etc.)
- No invented actions
- No direct physical-state mutation as a “step”
- No claim that an action will succeed
- No action aliases in planner-facing data

Manual prose may say “reduce habitat electrical demand.” The mapped simulator action must still be `reduce_power_load`.

Likewise:

- EVA solar repair prose → `repair_solar_array`
- Module isolation prose → `isolate_module`

### 7.3 Field authority reminders (from contract audit)

| Action | Required fields (planner/schema strictness) | Notes |
|---|---|---|
| `reduce_power_load` | `percent`, `load_groups` | Protected groups fail at runtime |
| `isolate_module` | `module` | Fails if crew trapped |
| `oxygen_rationing` | `level`, `target_crew_ids` (Python); executor may apply to all if targets empty | Levels restricted to §3.6 |
| `repair_solar_array` | at least one of `eva_crew_id`, `assigned_crew_ids`, `crew_id` | Feasibility owns EVA/repair outcome |
| `delay_rover_use` | `hours` (validator/Python) | Executor may also accept `duration_min` |
| `send_emergency_packet` | `type`, `start_min` only | Window must be open |

Always required on every action JSON object: `type`, `start_min`.

---

## 8. Procedural language rules

### 8.1 Permitted wording

- recommend
- initiate
- monitor
- verify through simulator
- abort if
- simulator evaluates
- expected operational objective

### 8.2 Forbidden unless directly supported by higher-precedence evidence

- guarantees survival
- ensures stabilization
- safe plan
- successful repair
- NASA-approved procedure
- flight-certified
- validated by NASA
- survival probability

Use concise imperative steps. Keep feasibility statements conditional on simulator validation.

---

## 9. Ordered-step requirements

Each operational step must include:

| Element | Requirement |
|---|---|
| Step number | Integer sequence |
| Operational objective | One short objective |
| Exact simulator action mapping | Exact `type` or `SIMULATOR_ACTION: none` |
| Telemetry prerequisites | Exact fields / conditions |
| Resources or crew dependencies | Crew IDs, modules, load groups, windows as applicable |
| Monitoring conditions | Fields and roles |
| Abort condition | Conditional abort framing |
| Completion evidence | Observable serialized evidence only |
| Source/evidence reference | Evidence ID or classification |

Informational steps with no simulator action must be labeled:

```text
SIMULATOR_ACTION: none
```

Such steps may recommend monitoring or verification only. They must not imply an unmapped executable intervention.

---

## 10. Chunking standard

### 10.1 RAG chunking rules

- One coherent operational subsection per chunk
- Do not split numbered action sequences from their constraints
- Do not separate an abort condition from the action it governs
- Do not separate a threshold from its source classification
- Target approximately 250–600 tokens per chunk
- Allow smaller chunks for compact tables when semantically complete
- Include procedure and section metadata in every chunk
- Preserve revision (`procedure_version`) and evidence IDs
- Never mix unrelated failure domains in one chunk

### 10.2 Recommended chunk metadata

| Field | Meaning |
|---|---|
| `chunk_id` | `[procedure_id]-v[version]-CH-[NNN]` |
| `procedure_id` | Parent procedure |
| `procedure_version` | SemVer |
| `section_id` | Parent section |
| `section_title` | H2 title |
| `content` | Chunk text |
| `applicable_faults` | Fault labels |
| `applicable_actions` | Exact action type strings |
| `telemetry_fields` | Exact JSON field names |
| `source_classifications` | Classification enums |
| `evidence_ids` | Evidence IDs |
| `authoring_status` | Document or section lifecycle status |

Do not embed `retrieval_score` or `rerank_score` in authored procedure files or chunk source Markdown.

Unsupported or deferred sections must not enter the active RAG corpus.

---

## 11. Retrieval and reranking expectations

A correct future retrieval result must return:

| Field | Source |
|---|---|
| Procedure identity | `procedure_id`, `filename`, `title`, `procedure_version` |
| Section identity | `section_id`, `section_title` |
| Exact content | Chunk `content` |
| Applicable telemetry | Exact field names / locations |
| Mapped actions | Exact action type strings |
| Evidence references | Evidence IDs and classifications |
| Source classifications | Classification enums |
| Retrieval score | Pipeline metadata |
| Rerank score | Pipeline metadata |

Retrieval and rerank scores are future pipeline metadata. They are not manually authored into procedure files.

---

## 12. Unsupported-content policy

When evidence is missing:

1. Do not invent instructions
2. Mark the procedure or section `PARTIAL_EVIDENCE` or `DEFERRED_SOURCE_REQUIRED`
3. Document the exact missing source
4. Allow structural placeholders only in the index (and empty shells), not fake operational steps
5. Do not let unsupported sections enter the active RAG corpus
6. Separate current executable behavior from future planned capability

### 12.1 True communications-blackout recovery

`comms_blackout.md` remains `DEFERRED_SOURCE_REQUIRED` until a true blackout fault/scenario and observable window telemetry (or equivalent higher-precedence evidence) exist. Current repository evidence covers:

- `send_emergency_packet` when a window is open
- REJECTED scheduling when start is outside an open window

It does not cover authentic blackout recovery procedures.

### 12.2 Standalone CO2 scrubber failure response

`co2_scrubber_failure.md` remains `DEFERRED_SOURCE_REQUIRED` until a scrubber-failure fault, scrubber-repair (or other dedicated) action, and supporting scenario evidence exist. Current inventory has no scrubber-repair action. Do not invent `repair_scrubber` or similar.

---

## 13. Versioning and change control

### 13.1 Document versioning

Use SemVer on `procedure_version`:

| Bump | When |
|---|---|
| MAJOR | Incompatible step/mapping/telemetry contract change; supersession |
| MINOR | New supported steps/sections with backward-compatible mappings |
| PATCH | Clarifications, citation fixes, non-semantic edits |

### 13.2 Review dates

- Set `last_reviewed` on every accepted revision
- Re-review when simulator action/telemetry contracts change
- Re-review when source classification of cited parameters changes

### 13.3 Supersession

- Set `superseded_by` on the old document and `supersedes` on the new
- Move old status to `SUPERSEDED`
- Remove superseded content from the active RAG corpus

### 13.4 Re-embedding triggers

Re-embed when any of the following change on an `ACTIVE` procedure:

- Operational step text affecting recommendations
- Action mappings or required fields
- Telemetry field names or condition roles
- Evidence IDs or source classifications
- `procedure_version` MAJOR or MINOR bump

PATCH-only typographical fixes that do not alter retrieval semantics still require review; re-embed if chunk text identity changes.

### 13.5 Retrieval regression tests

Rerun retrieval regression cases (§ Retrieval test cases) when:

- Re-embedding occurs
- Chunk boundaries change
- Status transitions to or from `ACTIVE`
- Applicable fault/action metadata changes

### 13.6 Simulator contract invalidation

If C++ serialization, action types/fields, telemetry names, or outcome enums change incompatibly:

- Mark affected procedures non-`ACTIVE` until remapped
- Update mapping tables and telemetry tables
- Bump MAJOR (or supersede)

### 13.7 Source-classification changes

If a cited parameter’s classification changes (e.g. untagged → tagged `NASA_STANDARD`):

- Update evidence references and condition labels
- Re-review claim strength wording
- Do not back-date prior assumptions as NASA claims without repository evidence

---

## 14. Procedure acceptance checklist

Every future procedure must pass this checklist before `status: ACTIVE` (active RAG evidence).

- [ ] Valid metadata per `procedure_metadata.schema.json`
- [ ] Exact telemetry names only (audit §4.1 allowlist)
- [ ] Exact action mappings (inventory strings only)
- [ ] Evidence classification for every numerical threshold
- [ ] Explicit ARES assumptions and release-configuration dependencies
- [ ] Abort conditions present and conditioned
- [ ] Success/termination conditions present and observable
- [ ] No unsupported NASA claims
- [ ] No simulator-success guarantee
- [ ] Chunk boundaries reviewed per §10
- [ ] Retrieval test cases included
- [ ] Status is `READY_FOR_AUTHORING` only when structure is justified without fake steps; `ACTIVE` only when this checklist passes
- [ ] Deferred/unsupported domains remain `DEFERRED_SOURCE_REQUIRED` or `PARTIAL_EVIDENCE` until sources exist
- [ ] Oxygen rationing levels restricted to §3.6 when used
- [ ] `power_rationing` domain maps to `reduce_power_load` (no renamed action)

Mark `READY_FOR_AUTHORING` when the shell and metadata are ready for content authoring without inventing unsupported operations.

---

## Appendix A — Companion files

| File | Role |
|---|---|
| `PHASE_2_CONTRACT_AUDIT.md` | Frozen contract inventory (Section 1) |
| `PROCEDURE_INDEX.md` | Controlled index of planned procedures |
| `procedure_metadata.schema.json` | Strict JSON Schema for procedure metadata |

## Appendix B — Explicit non-goals of this standard

This standard does not implement NVIDIA clients, embeddings, vector indexes, retrieval, reranking, planner prompts, mission sessions, telemetry replay, frontend code, databases, or authentication.

This standard does not author the six operational procedure manuals.
