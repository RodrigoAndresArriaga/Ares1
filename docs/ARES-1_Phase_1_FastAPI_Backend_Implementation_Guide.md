

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 1
## ARES-1
Phase 1 FastAPI Backend
## Implementation Guide
Frozen C++ Simulator Bridge + Validated HTTP Contract
Ownership rule
Cursor implements the complete Phase 1 backend described in this guide. The user reviews architecture, contracts, and
release gates. The C++ simulation core is frozen and remains the sole authority for mission physics, validation, telemetry, and
outcome.
Development principle
The API transports. The simulator decides. The artifacts prove.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 2
## Document Contents
1. Boundary, authority, and ownership rules
2. Phase 1 objective and locked scope
3. System architecture and request lifecycle
4. Required repository structure
5. Cursor implementation standards
6. Environment, dependencies, and configuration
7. Freeze verification and contract capture
8. Pydantic data contracts
9. Application bootstrap and health readiness
10. Scenario registry
11. Run artifact store
12. C++ simulator subprocess client
13. Simulation orchestration service
14. HTTP API routes and response semantics
15. Error handling and structured logging
16. Security, concurrency, and determinism
17. Testing strategy and release fixtures
18. Exact implementation order
19. Cursor execution prompts
20. Build and run commands
21. Final release gate and self-check
Appendix A. File responsibility matrix
Appendix B. Source traceability
How to use this guide
Give Cursor one implementation section at a time. Cursor must inspect the existing repository before editing, implement the
section completely, run the named tests, report changed files and command results, then stop. Do not give Cursor the entire
guide as one unconstrained request.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 3
- Boundary, Authority, and Ownership Rules
This guide covers only the Python FastAPI foundation that exposes the already-completed deterministic C++ simulator. It does not
redesign the simulation core and it does not begin the AI, RAG, telemetry replay, or frontend phases.
1.1 Frozen C++ authority
The C++ simulator owns all physical state transitions, crew physiology, action execution, validation rules, failure detection,
stabilization logic, mission outcome, metrics, timeline, and telemetry history.
The backend may validate JSON structure before launching the process, but it may not reproduce engineering constraints in
## Python.
A simulator result of FAILURE or REJECTED is a valid technical result, not a backend error.
The backend must return the simulator result without changing values, removing failure reasons, or inventing derived values.
No Phase 1 task may modify sim_core source, tests, release fixtures, or numerical behavior.
1.2 Cursor responsibility
Inspect the current repository and identify the real simulator executable, release scenario, valid plan, invalid plan, and result
JSON shape.
Create and implement the complete backend package, including configuration, schemas, services, routes, exception handlers,
logging, tests, and documentation.
Use strict type annotations and production implementations. Do not leave TODO bodies, placeholder returns, temporary
mocks, or commented-out alternate implementations.
Run the required build and test commands after each implementation section and repair failures within the section scope.
Stop after each section acceptance check so the user can review the change before continuing.
1.3 User responsibility
Approve architecture and field contracts.
Review Cursor diffs and test evidence.
Reject any backend logic that duplicates simulator physics or weakens schema validation.
Authorize progression to the next section only after the current acceptance check passes.
Non-negotiable rule
The backend is a controlled process boundary around the simulator. It is not a second simulator and it is not allowed to repair,
reinterpret, or override simulator results.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 4
- Phase 1 Objective and Locked Scope
2.1 Final Phase 1 flow
HTTP request
-> FastAPI request validation
-> registered scenario resolution
-> isolated run workspace
-> C++ subprocess execution
-> result JSON parsing
-> strict output validation
-> artifact persistence
-> HTTP response
2.2 Included deliverables
DeliverableRequired result
FastAPI applicationApplication starts locally and exposes OpenAPI documentation.
Configuration layerEnvironment settings resolve and validate project paths and
execution limits.
Strict Pydantic contractsPlan, telemetry, metrics, timeline, and final result match the frozen
C++ JSON contract.
Scenario registryClients select approved scenario IDs; arbitrary filesystem paths are
impossible.
Run artifact storeEvery request has an isolated, auditable directory with input,
output, logs, hashes, and metadata.
Simulator clientAsync, timeout-controlled, shell-free subprocess invocation of the
frozen executable.
Simulation serviceOne orchestration layer coordinates validation, artifacts, process
execution, and response assembly.
Health endpointReports whether the backend is ready to execute the simulator.
Simulation endpointRuns baseline, valid, and invalid-plan cases through HTTP.
TestsUnit, integration, determinism, concurrency, malformed-output, and
timeout behavior are verified.
2.3 Excluded work
Excluded itemReason
NVIDIA NIM clientsPhase 5 planner work.
RAG manuals and embeddingsManual authoring is Phase 2; RAG implementation is Phase 4.
Accident trigger and mission sessionPhase 3 mission lifecycle.
Telemetry replay, WebSocket, or SSEPhase 3 transport after the static bridge is proven.
Next.js, Open MCT, and Three.jsPhase 6 frontend.
Database and authenticationNot required for the hackathon Phase 1 bridge.
C++ modificationsThe core has passed its release gate and is frozen.
## PHASE EXIT CONDITION
The same frozen scenario must produce FAILURE without a plan, STABILIZED with the valid release plan, and REJECTED
with the invalid release plan when invoked through FastAPI.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 5
- System Architecture and Request Lifecycle
3.1 Component responsibilities
ComponentResponsibility
FastAPI routeHTTP parsing, dependency injection, status-code mapping, and
response serialization only.
SimulationServiceCoordinates one complete run without containing subprocess details or
physics.
ScenarioRegistryMaps approved scenario IDs to trusted files inside the configured
scenario root.
RunStoreCreates isolated workspaces and persists exact artifacts and
metadata.
SimulatorClientBuilds the argument vector, launches the executable, enforces
timeout/concurrency, and returns raw process evidence.
Pydantic schemasValidate request and result structure using exact frozen JSON field
names.
C++ simulatorPerforms all engineering calculations and decides outcome.
Exception handlersConvert typed infrastructure failures into stable API error responses.
Logging layerRecords one structured event trail keyed by run_id.
3.2 One-request sequence
1.FastAPI validates the request body and resolves the requested scenario ID.
2.SimulationService requests a new UUID run workspace from RunStore.
3.RunStore copies the trusted scenario and writes the canonical request JSON.
4.If a plan is supplied, the validated plan is written to plan.json.
5.SimulatorClient acquires the concurrency semaphore and launches the executable with argument-list invocation.
6.The client captures stdout/stderr, enforces the timeout, and waits for process completion.
7.The output file is parsed as JSON and validated against SimulationResult.
8.RunStore writes logs, hashes, execution metadata, and the validated result.
9.The route returns run metadata plus the unchanged simulator result.
3.3 Dependency direction
routes -> SimulationService
SimulationService -> ScenarioRegistry + RunStore + SimulatorClient
SimulatorClient -> operating system process API
Pydantic schemas <- routes/services/result parser
C++ simulator <- invoked only by SimulatorClient
Architecture rule
Routes must remain thin. The simulator client must not know HTTP. The run store must not launch processes. Pydantic models
must not perform filesystem or subprocess work.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 6
## 4. Required Repository Structure
Cursor creates the following backend structure beside the existing sim_core, scenarios, plans, and results directories. Existing
simulator paths must be discovered rather than assumed when the repository differs from this diagram.
ares-1/
|-- backend/
|   |-- pyproject.toml
## |   |-- .env.example
|   |-- README.md
|   |-- app/
## |   |   |-- __init__.py
|   |   |-- main.py
|   |   |-- api/
|   |   |   |-- router.py
|   |   |   `-- routes/
|   |   |       |-- health.py
|   |   |       `-- simulation.py
|   |   |-- core/
|   |   |   |-- config.py
|   |   |   |-- errors.py
|   |   |   `-- logging.py
|   |   |-- schemas/
|   |   |   |-- actions.py
|   |   |   |-- plan.py
|   |   |   |-- crew.py
|   |   |   |-- telemetry.py
|   |   |   |-- result.py
|   |   |   `-- api.py
|   |   `-- services/
|   |       |-- scenario_registry.py
|   |       |-- run_store.py
|   |       |-- simulator_client.py
|   |       `-- simulation_service.py
|   |-- data/runs/.gitkeep
|   `-- tests/
|       |-- conftest.py
|       |-- fixtures/
|       |-- unit/
|       `-- integration/
|-- sim_core/              FROZEN
|-- scenarios/             EXISTING RELEASE FIXTURES
|-- plans/                 EXISTING RELEASE FIXTURES
`-- results/               EXISTING CLI OUTPUTS
4.1 Core and schema file responsibilities
FileContains
app/main.pyApplication factory/lifespan, router registration, and exception-handler
registration.
core/config.pyPydantic settings and validated path resolution.
core/errors.pyTyped backend exception hierarchy and stable error codes.
core/logging.pyStructured logging configuration and run context helpers.
schemas/actions.pyExact serialized action values and action payload fields.
schemas/plan.pyPlanner input contract only; no simulator-owned outcome fields.
schemas/crew.pyCrew telemetry models copied from real output.
schemas/telemetry.pyHabitat snapshot, events, active actions, and telemetry history models.
schemas/result.pyMetrics, final outcome, timeline, failure reasons, and full result model.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 7
4.2 Service, route, and test file responsibilities
FileContains
schemas/api.pyHTTP request, success response, health response, and error response
models.
services/scenario_registry.pyTrusted scenario ID mapping and path-containment checks.
services/run_store.pyWorkspace creation, copies, atomic JSON writes, hashes, and
metadata.
services/simulator_client.pyAsync subprocess boundary and output parsing.
services/simulation_service.pyEnd-to-end run orchestration.
api/routes/*.pyThin HTTP route definitions.
tests/Unit and real-executable integration evidence.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 8
## 5. Cursor Implementation Standards
5.1 Cursor may implement
All Phase 1 Python production logic described in this guide.
All Pydantic schemas derived from the actual frozen JSON fixtures.
All unit and integration tests, including assertions and expected outcomes.
Backend configuration, package metadata, documentation, and local run commands.
Small test-only fake executables or scripts used to verify timeout, malformed output, and process failures.
5.2 Cursor must not implement
Any physics, telemetry calculation, mission constraint, action effect, or outcome decision in Python.
Any change to the simulator to make backend tests easier.
Any permissive result type such as dict[str, Any] as the final contract.
Any arbitrary path request field such as scenario_path or plan_path.
Any shell-based process execution, shell=True, os.system, or string-concatenated command.
Any automatic fallback that fabricates a result when the simulator fails.
Any NVIDIA, RAG, frontend, replay, database, authentication, or deployment implementation.
Any unknown field, enum value, default, or optionality not proven by current release JSON or C++ serializers.
5.3 Code-quality requirements
AreaRequired standard
TypingComplete parameter and return annotations. Avoid Any except at the
immediate json.loads boundary before validation.
PydanticUse extra="forbid" for request and simulator-contract models.
PathsUse pathlib.Path, resolve trusted roots, and verify containment.
Async processUse asyncio.create_subprocess_exec and asyncio.wait_for.
ExceptionsRaise typed domain/infrastructure errors with exception chaining.
JSON writesUse UTF-8, deterministic indentation/key policy, and atomic
replacement where artifacts could be partially written.
TestsNo test may pass solely because a subprocess was mocked; real CLI
integration is mandatory.
DocumentationREADME commands must match the implemented package and
current repository paths.
Scope controlEvery Cursor response lists changed files, tests run, results, and any
unresolved issue, then stops.
Implementation style change from the C++ guide
In the simulator guide, Cursor was restricted to boilerplate while the user implemented logic. In this Phase 1 guide, Cursor
owns the full Python implementation. The restriction is now architectural: Cursor may implement backend logic, but may not
cross into simulator authority or later project phases.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 9
- Environment, Dependencies, and Configuration
6.1 Runtime requirements
RequirementDecision
PythonPython 3.11 or newer. Use the repository-selected version if
already locked.
FrameworkFastAPI with Uvicorn.
Validation/settingsPydantic v2 and pydantic-settings.
Testingpytest, pytest-asyncio, and httpx.
Quality toolingRuff and mypy are recommended and should be configured if not
already present.
Process modelLocal executable invocation; no Python binding and no pybind11.
StorageFilesystem run artifacts only; no database in Phase 1.
6.2 pyproject.toml expectations
Define the package metadata and a supported Python range.
Separate runtime and development dependencies.
Configure pytest test paths and asyncio mode.
Configure Ruff for a practical line length and import sorting.
Configure mypy for the backend package; do not disable all strictness globally.
Do not introduce NVIDIA, FAISS, database, WebSocket, or frontend dependencies.
6.3 Environment variables
## ARES_PROJECT_ROOT=..
ARES_SIM_BINARY=../sim_core/build/sim_core
ARES_SCENARIO_DIR=../scenarios
ARES_RUNS_DIR=./data/runs
## ARES_SIM_TIMEOUT_SECONDS=30
## ARES_MAX_CONCURRENT_RUNS=2
## ARES_LOG_LEVEL=INFO
SettingValidation rule
ARES_PROJECT_ROOTResolve to an existing directory.
ARES_SIM_BINARYResolve to an existing file. On Windows, allow the actual .exe path.
ARES_SCENARIO_DIRResolve to an existing directory contained in the project root unless
intentionally configured otherwise.
ARES_RUNS_DIRCreate when missing; verify it is writable.
ARES_SIM_TIMEOUT_SECONDSPositive finite value.
ARES_MAX_CONCURRENT_RUNSInteger greater than zero.
ARES_LOG_LEVELOne of the supported logging levels.
Configuration rule
Paths shown above are examples. Cursor must inspect the repository and write .env.example values that match the actual
executable and fixture locations. Production code must not depend on the current working directory.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 10
- Freeze Verification and Contract Capture
What Section 7 produces
The simulator release is reconfirmed, the three authoritative result fixtures are captured, and every later Pydantic decision can
be traced to real output rather than memory or the older project overview examples.
7.1 Re-run the C++ release gate
cmake --build build
ctest --test-dir build --output-on-failure
Confirm the current test count remains 114/114 or document the exact current release count if the repository has intentionally
changed.
Do not edit the simulator to repair a backend setup problem.
Record the executable path and the exact release fixture paths.
7.2 Capture three result fixtures
FixtureCLI caseExpected outcome
baseline_result.jsonRelease scenario with no --plan argument.FAILURE
valid_plan_result.jsonRelease scenario plus sample_plan.json.STABILIZED
invalid_plan_result.jsonRelease scenario plus invalid_plan.json.REJECTED
7.3 Schema discovery procedure
10.Open all three result JSON files and the C++ JsonIO serializer implementation.
11.List every top-level field and every nested field.
12.Mark fields present in all outcomes as required.
13.Mark a field optional only when at least one authoritative output omits it by design.
14.Record exact enum/string serialization, including case and underscore style.
15.Confirm telemetry_history contains full authoritative samples and per-sample crew vital data.
16.Confirm survival_probability is absent from the deterministic contract.
17.Copy the three files into backend/tests/fixtures/results without normalizing or editing their content.
18.Generate a short schema inventory document in tests/fixtures/results/README.md for traceability.
## DO NOT USE THE OLD EXAMPLE AS THE CONTRACT
The original ARES-1 overview contains illustrative JSON that includes survival_probability and simplified metrics. The revised
C++ guide and current executable supersede those examples. The current serializer and captured outputs are the source of
truth.
## SECTION 7 EXIT CHECK
The C++ build/tests pass, three unedited result fixtures exist, their SHA-256 hashes are recorded, and Cursor can point to
evidence for every required/optional field decision.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 11
## 8. Pydantic Data Contracts
What Section 8 produces
Strict request and output models that accept the three real release fixtures, reject malformed structures, preserve exact
serialized field names, and do not grant the backend authority over simulator decisions.
8.0 Complete these files in dependency order
StepFilePurpose
1schemas/actions.pySerialized action enum/value contract and
action payload fields.
2schemas/plan.pyPlanner-supplied plan fields only.
3schemas/crew.pyPer-crew identity, vital, activity, performance,
health, and alarm fields.
4schemas/telemetry.pyHabitat snapshot, events, active actions, and
telemetry sample/history.
5schemas/result.pyMetrics, outcome, validity, timeline, failure
reasons, and full SimulationResult.
6schemas/api.pyHTTP request/success/health/error envelopes.
Rule for every model
Use exact JSON field names and extra="forbid". A default or Optional type is allowed only when proven by real release
input/output or the active C++ serializer.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 12
8.1 Implement schemas/actions.py
ItemInstruction
## Editbackend/app/schemas/actions.py
ResponsibilityRepresent every action the frozen simulator accepts without
implementing action effects.
ReadsThe current Action.hpp/Plan.hpp declarations, current plan JSON
fixtures, and JsonIO plan parsing.
Writes / returnsStrict Python enums/models used by PlanRequest and serialized
back to the exact C++ plan shape.
Test intests/unit/test_action_schema.py
Cursor implements the production code in this order:
19.Inspect Action.hpp, Plan.hpp, JsonIO parsing, sample_plan.json, and invalid_plan.json.
20.Declare string enums using the exact serialized action values accepted by the CLI.
21.Declare common fields and action-specific optional fields exactly as the plan contract defines them.
22.Use validators only for structural facts that are independent of mission state, such as non-negative start_min and required
fields for a selected action type.
23.Do not reject an action because battery, EVA, thermal, or communications conditions are unsafe; the simulator must evaluate
those constraints.
24.Configure the model to forbid extra fields and serialize by field name without aliases unless the C++ JSON uses a name that
cannot be represented directly.
25.Add unit tests for every allowed action fixture and malformed structural combinations.
## ACCEPTANCE CHECK
Every current release plan parses and round-trips to the same JSON structure; unknown action types and unknown fields fail;
no engineering feasibility rule exists in Python.
## DO NOT DO THIS
Do not implement battery reserve, EVA timing, comms-window, oxygen, thermal, or stabilization validation in Pydantic.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 13
8.2 Implement schemas/plan.py
ItemInstruction
## Editbackend/app/schemas/plan.py
ResponsibilityRepresent planner input data only. The plan must be unable to
claim success or provide simulator-owned metrics.
ReadsPlan.hpp, sample_plan.json, invalid_plan.json, and JsonIO plan
parsing.
Writes / returnsA strict RecoveryPlan model used by SimulationRunRequest.
Test intests/unit/test_plan_schema.py
Cursor implements the production code in this order:
26.Declare plan_id, summary, actions, rationale, expected_risk, and constraints_checked when these fields are confirmed in the
active contract.
27.Match current required/optional behavior exactly; do not rely on the original overview if the current C++ contract differs.
28.Forbid fields such as outcome, valid_plan, mission_status, metrics, failure_reasons, risk score, or survival probability when
they are not planner inputs.
29.Validate only structural constraints such as non-empty identifiers where the C++ parser requires them.
30.Add round-trip tests using both release plan files.
## ACCEPTANCE CHECK
Both current plan fixtures validate and produce the exact plan JSON expected by the simulator. Attempts to include simulator-
owned outcome data fail before process execution.
## DO NOT DO THIS
Do not let a plan declare that it is valid, stabilized, safe, successful, or physically feasible.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 14
8.3 Implement schemas/crew.py
ItemInstruction
## Editbackend/app/schemas/crew.py
ResponsibilityValidate each authoritative crew telemetry record without changing
values or inventing units.
ReadsCrew sections of all telemetry_history samples plus the C++
snapshot serializer.
Writes / returnsStrict per-crew telemetry models nested inside telemetry samples.
Test intests/unit/test_crew_schema.py
Cursor implements the production code in this order:
31.Build the field list from the real telemetry_history rather than from the schema example alone.
32.Preserve exact numeric types, string enum values, list names, and alarm field name used by the serializer.
33.Include identity/context, vital signs, metabolism when emitted, exposure/performance values when emitted, health status, and
active alarms.
34.Use finite-number validation only where JSON NaN/Infinity is forbidden by the actual output contract.
35.Do not clamp, round, normalize, or rename values.
36.Add fixture-driven tests that validate every crew sample in all three result files.
## ACCEPTANCE CHECK
Every crew record in every release result validates unchanged, and a missing required vital or unknown field fails with a precise
validation path.
## DO NOT DO THIS
Do not recalculate SpO2, fatigue, performance, alarms, or health status in Python.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 15
8.4 Implement schemas/telemetry.py
ItemInstruction
## Editbackend/app/schemas/telemetry.py
ResponsibilityValidate the complete authoritative per-minute snapshot and its
event/action collections.
ReadsSection 15 of the C++ guide, all telemetry_history samples,
TimelineEvent serialization, and active-action serialization.
Writes / returnsTelemetrySample and nested habitat/event/action models.
Test intests/unit/test_telemetry_schema.py
Cursor implements the production code in this order:
37.Determine whether the active result uses a flattened habitat object or nested telemetry groups and model the actual output
exactly.
38.At minimum, confirm cabin pressure, inspired oxygen, one-hour CO2 average, oxygen hours, battery SOC, solar generation
percent, power margin, cabin temperature, temperature margin, EVA return margin, and mission status when present.
39.Model the crew array with the strict CrewTelemetry model.
40.Model per-step events and any active-action or warning flags exactly as emitted.
41.Require simulation_time_min and preserve its numeric type.
42.Validate every telemetry_history element from all release fixtures.
43.Add tests proving telemetry samples remain immutable as parsed data and are not post-processed by the API.
## ACCEPTANCE CHECK
The complete telemetry_history validates for all outcomes with no dropped fields. Removing cabin_temperature_c or a crew
vital fails validation.
## DO NOT DO THIS
Do not interpolate, synthesize, thin, or recompute telemetry in Phase 1.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 16
8.5 Implement schemas/result.py
ItemInstruction
## Editbackend/app/schemas/result.py
ResponsibilityValidate the complete deterministic simulator result returned by the
## CLI.
ReadsAll three captured outputs, SimulationResult.hpp,
SimulationMetrics.hpp, TelemetrySample.hpp, and JsonIO
serialization.
Writes / returnsStrict SimulationMetrics, TimelineEvent, and SimulationResult
models.
Test intests/unit/test_result_schema.py
Cursor implements the production code in this order:
44.Declare the exact outcome enum values emitted by the current serializer.
45.Declare scenario_id, plan_id behavior, outcome, valid_plan, metrics, timeline, telemetry_history, and failure_reasons
according to real output.
46.Model every metrics field present in any release output and determine required/optional status from evidence.
47.Do not include survival_probability.
48.Forbid unknown fields so backend drift is detected immediately.
49.Add positive fixture tests for baseline, valid, and invalid results.
50.Add negative tests for missing telemetry_history, missing failure_reasons, unknown top-level fields, invalid outcome strings,
and survival_probability.
## ACCEPTANCE CHECK
All three unmodified release results validate. The deterministic contract rejects survival_probability and rejects any unmodeled
field until the schema is intentionally updated.
## DO NOT DO THIS
Do not make most fields Optional merely to make fixtures pass. Optionality must reflect actual outcome-dependent behavior.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 17
8.6 Implement schemas/api.py
ItemInstruction
## Editbackend/app/schemas/api.py
ResponsibilityDefine HTTP envelopes without altering the nested simulator
result.
ReadsThe approved Phase 1 route contract and the strict
RecoveryPlan/SimulationResult models.
Writes / returnsSimulationRunRequest, SimulationRunResponse,
HealthResponse, and ErrorResponse.
Test intests/unit/test_api_schema.py
Cursor implements the production code in this order:
51.Define SimulationRunRequest with scenario_id and an optional inline plan.
52.Do not accept scenario_path, plan_path, output_path, executable path, or command arguments from the client.
53.Define SimulationRunResponse with run_id, duration_ms, and result.
54.Keep backend metadata outside result so canonical simulator comparison remains possible.
55.Define a stable error envelope with code, message, and optional run_id.
56.Define a health response that separates application liveness from simulator readiness.
57.Add OpenAPI examples for baseline, plan, success, and infrastructure error responses.
## ACCEPTANCE CHECK
OpenAPI shows the intended request/response shapes, and the result field is the strict SimulationResult model rather than a
dictionary.
## DO NOT DO THIS
Do not expose absolute paths, command lines, stack traces, or raw exception representations in API schemas.
## SECTION 8 EXIT CHECK
All three release results and both release plans validate through strict models. Invalid extra fields fail. No survival_probability
exists. No backend model contains engineering outcome logic.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 18
- Application Bootstrap and Health Readiness
9.1 Implement core/config.py
ItemInstruction
## Editbackend/app/core/config.py
ResponsibilityLoad environment settings, resolve paths independently of working
directory, and expose validated immutable configuration.
ReadsEnvironment variables, backend location, repository layout, and
current platform.
Writes / returnsA cached Settings object with resolved Path values and validated
numeric limits.
Test intests/unit/test_config.py
Cursor implements the production code in this order:
58.Use pydantic-settings and an explicit environment-variable prefix or aliases matching .env.example.
59.Resolve relative paths against a documented base, preferably the backend or project root rather than process CWD.
60.Validate that the project root, simulator binary, and scenario directory exist.
61.Create the runs directory when allowed and verify writability with a safe temporary file test.
62.Validate timeout and concurrency values.
63.Provide test overrides without mutating global process environment unpredictably.
64.Add Windows-aware executable handling without hardcoding .exe for non-Windows systems.
## ACCEPTANCE CHECK
Configuration works from the project root and from backend/ as CWD, invalid paths produce clear startup errors, and tests can
create isolated temporary settings.
## DO NOT DO THIS
Do not silently fall back to guessed paths when an explicitly configured path is wrong.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 19
9.2 Implement app/main.py and API router
ItemInstruction
Editbackend/app/main.py, backend/app/api/router.py
ResponsibilityCreate the FastAPI application, lifespan readiness checks, route
registration, and exception-handler registration.
ReadsValidated settings and route modules.
Writes / returnsA deterministic application factory usable by Uvicorn and tests.
Test intests/integration/test_app_startup.py
Cursor implements the production code in this order:
65.Prefer create_app(settings_override=None) so tests can instantiate isolated applications.
66.Run non-destructive startup readiness checks during lifespan.
67.Register one /api router and keep route modules separate.
68.Register typed exception handlers from core/errors.py.
69.Set project title/version metadata without claiming later-phase capabilities.
70.Do not enable wildcard CORS in Phase 1; either omit CORS or configure only explicit future development origins through
settings.
71.Add an application startup integration test.
## ACCEPTANCE CHECK
The app starts, /docs renders, /openapi.json contains only Phase 1 routes, and a missing simulator binary makes readiness fail
clearly rather than crashing on the first request.
## DO NOT DO THIS
Do not execute a full simulation during every application startup or every health request.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 20
9.3 Implement GET /api/health
ItemInstruction
## Editbackend/app/api/routes/health.py
ResponsibilityReport application liveness and simulator readiness without
running a full mission simulation.
ReadsSettings, binary path, release scenario availability, and runs-
directory writability.
Writes / returnsHealthResponse with status and simulator readiness details.
Test intests/integration/test_health.py
Cursor implements the production code in this order:
72.Return a healthy response when the application is alive and all Phase 1 execution prerequisites are available.
73.Return a degraded/not-ready response with an appropriate service status when prerequisites are missing.
74.Check existence/readability/writability only; do not launch the simulator for each request.
75.Avoid returning absolute paths or operating-system error details to the client.
76.Log the diagnostic cause server-side.
77.Add tests for ready and not-ready configurations.
## ACCEPTANCE CHECK
Health accurately distinguishes a running HTTP process from a backend ready to execute the C++ simulator.
## DO NOT DO THIS
Do not always return healthy merely because FastAPI is responding.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 21
## 10. Scenario Registry
Security objective
The client chooses a logical scenario ID. Only the server chooses filesystem paths.
10.1 Implement ScenarioRegistry
ItemInstruction
## Editbackend/app/services/scenario_registry.py
ResponsibilityResolve approved scenario identifiers to trusted files and prevent
path traversal.
ReadsConfigured scenario root and the actual release scenario filename.
Writes / returnsResolved trusted Path values or ScenarioNotFoundError.
Test intests/unit/test_scenario_registry.py
Cursor implements the production code in this order:
78.Create an explicit registry mapping for the Phase 1 release scenario.
79.Use the real scenario_id and real filename found during Section 7.
80.Resolve the candidate path and verify it is contained within the resolved scenario root.
81.Verify the target exists and is a regular file.
82.Return a typed not-found error for unknown IDs.
83.Provide list_scenarios for internal/testing use without adding a public route unless explicitly approved.
84.Add tests for valid resolution, unknown IDs, traversal strings, absolute-path strings, symlinks where supported, and missing
registered files.
## ACCEPTANCE CHECK
Only registered IDs resolve, no client string can escape the scenario root, and the release scenario resolves consistently
across operating systems.
## DO NOT DO THIS
Do not derive a filename by appending .json to arbitrary client input.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 22
## 11. Run Artifact Store
11.1 Per-run directory contract
backend/data/runs/<run_id>/
|-- request.json
|-- scenario.json
|-- plan.json              # absent for baseline
|-- result.json            # present after valid simulator output
|-- stdout.log
|-- stderr.log
`-- metadata.json
11.2 Implement RunStore
ItemInstruction
## Editbackend/app/services/run_store.py
ResponsibilityCreate isolated workspaces and persist exact evidence for every
simulation request.
ReadsRuns root, validated request/plan, trusted scenario file, raw
process output, validated result, and execution metadata.
Writes / returnsRunWorkspace paths and durable JSON/log/hash artifacts.
Test intests/unit/test_run_store.py
Cursor implements the production code in this order:
85.Generate a UUID4 run_id and create a directory using exclusive creation semantics.
86.Copy the exact trusted scenario to scenario.json without changing its content.
87.Write request.json from the validated HTTP request using deterministic JSON formatting.
88.Write plan.json only when a plan is supplied.
89.Provide paths for result.json, stdout.log, stderr.log, and metadata.json.
90.Use atomic temporary-file plus replace behavior for JSON metadata and response artifacts.
91.Calculate SHA-256 for scenario, plan when present, and result when present.
92.Preserve partial evidence when process execution fails after workspace creation.
93.Ensure concurrent runs never share files.
94.Return relative identifiers to higher layers; never expose absolute paths to clients.
## ACCEPTANCE CHECK
Two concurrent runs produce distinct complete workspaces; hashes match file bytes; baseline has no plan.json; failed runs
retain request, scenario, logs, and failure metadata.
## DO NOT DO THIS
Do not use the repository-level results/sim_result.json as the API output path.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 23
11.3 Implement execution metadata
ItemInstruction
Editbackend/app/services/run_store.py and schemas/internal types if
needed
ResponsibilityRecord infrastructure evidence separately from the simulator
result.
Readsrun_id, timestamps, mode, identifiers, hashes, duration, process
exit code, and simulator outcome when available.
Writes / returnsmetadata.json with stable keys and no secrets.
Test intests/unit/test_run_metadata.py
Cursor implements the production code in this order:
95.Record created_at in UTC ISO-8601 format.
96.Record mode as baseline or plan.
97.Record scenario_id and plan_id when available.
98.Record input/output hashes.
99.Record process_exit_code and duration_ms.
100.Record the simulator outcome only after output validation succeeds.
101.Record a stable infrastructure error code when execution fails.
102.Do not record environment secrets or full absolute paths.
## ACCEPTANCE CHECK
metadata.json is sufficient to audit what ran and whether infrastructure or mission logic produced the final state, without
modifying result.json.
## DO NOT DO THIS
Do not merge backend metadata into the simulator-owned result object.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 24
## 12. C++ Simulator Subprocess Client
Process boundary
SimulatorClient is the only production module allowed to launch the C++ executable.
12.1 Command contract
## Baseline:
sim_core --scenario <workspace>/scenario.json --output <workspace>/result.json
Plan run:
sim_core --scenario <workspace>/scenario.json --plan <workspace>/plan.json --output
## <workspace>/result.json
12.2 Implement SimulatorClient construction
ItemInstruction
## Editbackend/app/services/simulator_client.py
ResponsibilityOwn executable settings, timeout, and shared concurrency control.
ReadsResolved simulator binary, timeout seconds, maximum concurrent
runs.
Writes / returnsA reusable async client instance.
Test intests/unit/test_simulator_client_command.py
Cursor implements the production code in this order:
103.Accept validated settings through constructor injection.
104.Create an asyncio.Semaphore using ARES_MAX_CONCURRENT_RUNS.
105.Verify binary availability before launch and raise SimulatorUnavailableError when missing.
106.Keep command construction in a small private function that returns list[str].
107.Include --plan only when the workspace contains an approved plan path.
108.Never accept extra command arguments from the HTTP request.
109.Add command-construction unit tests for baseline and plan modes.
## ACCEPTANCE CHECK
The generated argument list exactly matches the CLI contract and contains no shell syntax or user-controlled paths.
## DO NOT DO THIS
Do not use shell=True, os.system, subprocess string commands, or platform-specific quoting logic.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 25
12.3 Implement async process execution
ItemInstruction
## Editbackend/app/services/simulator_client.py
ResponsibilityLaunch, wait, timeout, terminate, capture, and report the external
process safely.
ReadsRunWorkspace paths and validated settings.
Writes / returnsSimulatorProcessResult containing exit code, stdout bytes/text,
stderr bytes/text, and duration.
Test intests/unit/test_simulator_client_process.py and
tests/integration/test_sim_timeout.py
Cursor implements the production code in this order:
110.Acquire the shared semaphore before process creation and release it in all paths.
111.Use asyncio.create_subprocess_exec with stdout/stderr pipes.
112.Measure duration with a monotonic clock.
113.Use asyncio.wait_for around process.communicate().
114.On timeout, kill the process, await termination, preserve captured output when possible, and raise SimulatorTimeoutError with
run_id context.
115.Decode output as UTF-8 with a documented safe error policy and persist exact text.
116.Do not treat a mission FAILURE or REJECTED as a process exception.
117.Return the numeric exit code for later validation.
## ACCEPTANCE CHECK
Normal executions complete asynchronously, timeout reliably terminates the child, and the semaphore prevents more than the
configured number of simultaneous processes.
## DO NOT DO THIS
Do not block the event loop with subprocess.run or synchronous communicate in the request path.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 26
12.4 Implement output parsing and validation
ItemInstruction
## Editbackend/app/services/simulator_client.py
ResponsibilityConvert the simulator output file into a strict SimulationResult or a
typed bridge failure.
ReadsProcess result, output path, and SimulationResult schema.
Writes / returnsValidated SimulationResult plus process evidence.
Test intests/unit/test_simulator_output.py and
tests/integration/test_malformed_output.py
Cursor implements the production code in this order:
118.After process completion, verify result.json exists and is a regular non-empty file.
119.Read UTF-8 JSON and catch syntax errors with exception chaining.
120.Validate the decoded object through SimulationResult.model_validate.
121.Treat malformed/missing/contract-invalid output as a 502-class bridge error even if the process exit code is zero.
122.When a valid result exists, use its outcome as mission truth regardless of whether it is FAILURE, STABILIZED, or REJECTED.
123.Define and test the policy for a nonzero exit code plus valid result. Prefer preserving the valid result only if the current CLI
contract intentionally uses nonzero mission exit codes; otherwise classify as execution failure. Base this decision on actual
release behavior.
124.Never repair or default missing fields.
## ACCEPTANCE CHECK
All three real outputs parse; missing, empty, malformed, or schema-invalid files raise distinct typed errors; no fabricated result
is returned.
## DO NOT DO THIS
Do not convert stderr text into failure_reasons or outcome.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 27
## 13. Simulation Orchestration Service
13.1 Implement SimulationService.run_simulation
ItemInstruction
## Editbackend/app/services/simulation_service.py
ResponsibilityCoordinate one request from trusted scenario resolution through
artifact completion.
ReadsSimulationRunRequest, ScenarioRegistry, RunStore, and
SimulatorClient.
Writes / returnsSimulationRunResponse or a typed infrastructure error with run_id
when available.
Test intests/unit/test_simulation_service.py
Cursor implements the production code in this order:
125.Resolve scenario_id before creating process arguments.
126.Create the run workspace and persist request/scenario/plan inputs.
127.Invoke SimulatorClient with only workspace-owned paths.
128.Persist stdout/stderr immediately after process completion or failure.
129.Validate and persist result.json without changing its content.
130.Write success metadata including hashes, duration, exit code, and outcome.
131.On any typed execution error, write failure metadata and re-raise with run_id attached.
132.Return run_id, duration_ms, and the validated unchanged SimulationResult.
133.Keep HTTP status decisions out of this service.
## ACCEPTANCE CHECK
The service completes baseline, valid, and invalid-plan runs; partial artifacts survive infrastructure failures; the route can call
one method without knowing process or storage details.
## DO NOT DO THIS
Do not catch every exception and return a fake ErrorResponse from the service. Use typed exceptions and centralized HTTP
handlers.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 28
- HTTP API Routes and Response Semantics
14.1 Required routes
MethodPathPurpose
GET/api/healthReport liveness and simulator readiness.
POST/api/sim/runExecute one registered scenario with an
optional inline recovery plan.
14.2 Simulation request examples
Baseline request:
## {
## "scenario_id": "<registered_release_scenario_id>",
"plan": null
## }
Plan request:
## {
## "scenario_id": "<registered_release_scenario_id>",
## "plan": {
## "plan_id": "...",
## "summary": "...",
## "actions": [...],
## "rationale": "...",
## "expected_risk": "...",
## "constraints_checked": [...]
## }
## }
14.3 HTTP status contract
ConditionHTTP statusMeaning
Simulator outcome STABILIZED200Successful infrastructure execution with
stabilized mission result.
Simulator outcome FAILURE200Successful infrastructure execution with failed
mission result.
Simulator outcome REJECTED200Successful infrastructure execution with
rejected engineering plan.
Request schema invalid422Client supplied structurally invalid JSON.
Scenario ID unknown404Requested logical scenario is not registered.
Simulator unavailable/not ready503Backend cannot launch the configured
executable.
Simulator timeout504External process exceeded configured time
limit.
Process/output bridge failure502Process crashed or result was
missing/malformed/contract-invalid.
Artifact persistence failure500Backend could not create or preserve required
evidence.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 29
14.4 Implement POST /api/sim/run
ItemInstruction
## Editbackend/app/api/routes/simulation.py
ResponsibilityExpose SimulationService through a thin typed HTTP route.
ReadsSimulationRunRequest and injected SimulationService.
Writes / returnsSimulationRunResponse with HTTP 200 for every valid simulator
outcome.
Test intests/integration/test_sim_baseline.py, test_sim_valid_plan.py,
test_sim_rejected_plan.py
Cursor implements the production code in this order:
134.Declare the route response_model as SimulationRunResponse.
135.Inject or retrieve the service through an application dependency rather than constructing new global state per request.
136.Call run_simulation exactly once.
137.Do not inspect result.outcome to choose an error status.
138.Allow centralized exception handlers to map infrastructure errors.
139.Add OpenAPI descriptions clarifying that FAILURE and REJECTED are valid results.
140.Add integration tests using the real executable for all three release cases.
## ACCEPTANCE CHECK
All three release outcomes return HTTP 200 and strict response JSON. Unknown scenario and malformed request statuses
match the contract.
## DO NOT DO THIS
Do not return 400/422/500 merely because the simulator rejects a plan or predicts mission failure.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 30
- Error Handling and Structured Logging
15.1 Typed error hierarchy
ExceptionStable codeHTTP mapping
ScenarioNotFoundErrorSCENARIO_NOT_FOUND404
SimulatorUnavailableErrorSIMULATOR_UNAVAILABLE503
SimulatorTimeoutErrorSIMULATOR_TIMEOUT504
SimulatorExecutionErrorSIMULATOR_EXECUTION_FAILED502
SimulatorOutputMissingErrorSIMULATOR_OUTPUT_MISSING502
SimulatorOutputParseErrorSIMULATOR_OUTPUT_INVALID_JSON502
SimulatorOutputValidationErrorSIMULATOR_OUTPUT_CONTRACT_ERRO
## R
## 502
ArtifactStorageErrorARTIFACT_STORAGE_ERROR500
15.2 Implement core/errors.py and handlers
ItemInstruction
Editbackend/app/core/errors.py and backend/app/main.py
ResponsibilityProvide precise infrastructure errors and stable client responses
while preserving internal causes.
ReadsTyped exceptions raised by registry, store, client, and service.
Writes / returnsErrorResponse JSON and correct HTTP status.
Test intests/unit/test_error_mapping.py
Cursor implements the production code in this order:
141.Create a shared AresBackendError base carrying code, safe message, and optional run_id.
142.Create one subclass for each defined failure category.
143.Raise with `from` to preserve the original exception internally.
144.Register explicit FastAPI handlers for AresBackendError and a guarded final handler for unexpected exceptions.
145.Return only safe stable fields to the client.
146.Log stack traces for unexpected errors and concise context for expected infrastructure errors.
147.Ensure Pydantic request validation retains FastAPI 422 behavior.
## ACCEPTANCE CHECK
Every defined failure returns the documented code/status and no traceback, absolute path, or raw OS error is exposed.
## DO NOT DO THIS
Do not collapse all failures into one generic 500 response.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 31
15.3 Implement structured logging
ItemInstruction
Editbackend/app/core/logging.py and service/client call sites
ResponsibilityCreate an auditable run event trail without flooding logs with full
telemetry.
ReadsApplication settings and run context.
Writes / returnsStructured log records containing stable event names and
identifiers.
Test intests/unit/test_logging.py
Cursor implements the production code in this order:
148.Configure log level from settings and a consistent timestamp format.
149.Include event, run_id, scenario_id, plan_id when present, duration_ms, process_exit_code, and outcome when known.
150.Log simulation_run_created, simulator_process_started, simulator_process_completed, simulator_output_validated,
simulation_run_completed, and simulation_run_failed.
151.Do not log complete request plans at INFO if later phases may contain sensitive prompt context; artifact files already preserve
inputs.
152.Do not log the complete telemetry_history to the console.
153.Never log future NVIDIA API keys or the full environment.
154.Add caplog-based tests for key events.
## ACCEPTANCE CHECK
A single run can be traced by run_id from request creation through result/error without dumping megabytes of telemetry or
secrets.
## DO NOT DO THIS
Do not use print statements for production diagnostics.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 32
- Security, Concurrency, and Determinism
16.1 Security controls
RiskRequired control
Command injectionArgument-list subprocess invocation only; no shell.
Path traversalRegistered scenario IDs and workspace-owned plan/output paths.
Arbitrary executableExecutable path only from validated server configuration.
Artifact collisionUUID workspace per request and exclusive directory creation.
Data leakageNo absolute paths, tracebacks, environment dumps, or secrets in
HTTP responses.
Schema driftStrict Pydantic models with unknown fields forbidden.
Resource exhaustionSemaphore limit and process timeout.
Partial filesAtomic JSON/metadata writes and preserved failure artifacts.
16.2 Concurrency policy
One shared semaphore belongs to the application-level SimulatorClient.
The configured maximum controls concurrent external processes, not concurrent HTTP parsing.
Queued requests wait asynchronously and do not block the event loop.
Every run uses a separate scenario copy, plan, result path, stdout, stderr, and metadata.
No process writes to the shared repository-level result file.
16.3 Determinism policy
Identical scenario bytes and plan bytes must produce identical simulator result content.
Backend run_id, timestamps, duration, filesystem paths, and metadata hashes are excluded from canonical result comparison.
Canonical comparison should parse SimulationResult and compare model_dump(mode="json") values, not raw file
whitespace.
If raw result bytes are expected to be deterministic by the current C++ release, also preserve and compare SHA-256 as a
stronger test.
The backend may not insert current timestamps or run identifiers into result.json.
Determinism invariant
The backend must not make deterministic simulator output nondeterministic.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 33
- Testing Strategy and Release Fixtures
17.1 Test layers
LayerPurposeProcess use
Schema fixture testsProve strict models match frozen JSON.No process.
Service unit testsProve orchestration and errors using
controlled fakes.
Usually mocked/fake client.
Client failure testsTimeout, missing output, malformed JSON,
nonzero exit behavior.
Test-only fake executable/script.
Real integration testsProve actual FastAPI -> C++ bridge.Real frozen simulator.
Concurrency testProve workspace isolation and semaphore
behavior.
Real or deterministic fake process.
Determinism testProve identical request returns identical
simulator result.
Real frozen simulator.
17.2 Required unit tests
Settings path and numeric validation.
Scenario ID resolution and traversal rejection.
Plan/action structural validation.
Crew, telemetry, metrics, and final result fixture validation.
Unknown field rejection and survival_probability rejection.
Run workspace uniqueness, hashes, atomic writes, and partial-failure evidence.
Command argument generation for baseline and plan modes.
Typed error-to-status mapping.
Structured logging context.
17.3 Required real integration tests
TestRequired assertions
BaselineHTTP 200; outcome FAILURE; populated failure_reasons;
telemetry_history and crew data present; artifacts complete.
Valid planHTTP 200; outcome STABILIZED; valid_plan according to output;
stabilization metric present; failure_reasons empty when current
release emits empty.
Invalid planHTTP 200; outcome REJECTED; simulator rejection reasons
preserved; not converted to 422/500.
DeterminismTwo identical requests produce equal canonical SimulationResult
values and, when release guarantees it, equal result SHA-256.
ConcurrencyMultiple simultaneous runs use distinct workspaces and return their
own result.
Unavailable binaryHealth not ready and simulation returns 503-class error.
TimeoutChild is killed, 504 returned, and partial artifacts/logs preserved.
Malformed output502 returned with stable error code; no fabricated result.
17.4 Test isolation rules
Use pytest temporary directories for runs and fake fixtures.
Do not write integration-test output into repository release fixtures.
Mark real simulator tests so they can be selected, but include them in the Phase 1 release gate.
Tests must discover or receive the configured executable path; they must not assume CWD.
Do not weaken production validation only to simplify tests.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 34
## 18. Exact Implementation Order
Cursor must follow this sequence. Each step ends with tests and a user review before the next step begins.
StepImplementationCheckpoint
1Audit repository and re-run frozen C++ release
gate.
C++ tests pass; no files changed.
2Capture baseline, valid, and invalid result
fixtures.
Three exact outputs and hashes recorded.
3Create backend package structure and
pyproject.
Import/start smoke test passes.
4Implement strict Pydantic contracts.All real fixtures pass; negative schema tests
pass.
5Implement settings and application factory.Startup/config tests pass.
6Implement ScenarioRegistry.Registry security tests pass.
7Implement RunStore.Artifact and concurrency-isolation unit tests
pass.
8Implement SimulatorClient.Command, timeout, malformed-output, and
process tests pass.
9Implement SimulationService.Orchestration unit tests pass.
10Implement health and simulation routes plus
handlers.
HTTP integration tests pass.
11Run real baseline/valid/invalid integration
tests.
Expected outcomes through API.
12Run determinism and concurrency tests.Canonical equality and isolation proven.
13Finalize README, .env.example, lint, typing,
and release report.
Full Phase 1 gate passes.
Stop rule
Cursor must stop at the checkpoint for the requested step. It must not begin later steps because they appear straightforward.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 35
## 19. Cursor Execution Prompts
19.1 Master operating prompt
You are implementing ARES-1 Phase 1 only: the FastAPI backend foundation and frozen C++ simulator
bridge.
Read the Phase 1 implementation guide and inspect the current repository before editing.
Non-negotiable rules:
- The C++ simulator is frozen. Do not modify sim_core, its tests, equations, serializers,
scenarios, plans, or release behavior.
- The C++ simulator owns mission physics, crew physiology, action feasibility, validation,
metrics, telemetry, timeline, and final outcome.
- Python may validate JSON structure but must not duplicate engineering or mission rules.
- FAILURE and REJECTED are valid simulator results and must return HTTP 200 when infrastructure
execution succeeds.
- Use exact current JSON field names and enum strings discovered from the executable, fixtures,
headers, and JsonIO serializer.
- Do not add survival_probability.
- Use strict Pydantic v2 models with extra fields forbidden. Do not use dict[str, Any] as the
final contract.
- Use pathlib and registered scenario IDs. Never accept arbitrary paths or command arguments from
the client.
- Launch the simulator only with asyncio.create_subprocess_exec. Never use shell=True or
os.system.
- Use isolated UUID run directories, timeout control, a shared concurrency semaphore, typed
errors, and preserved artifacts.
- Implement production code completely. No TODOs, placeholders, temporary bypasses, or untested
fallbacks.
- Do not implement NVIDIA, RAG, accident lifecycle, replay, frontend, database, authentication,
or deployment work.
For the requested section only:
- Inspect relevant current files.
- State the exact files you will create or edit.
- Implement the section fully.
- Add or update the named tests.
- Run the required commands.
- Fix failures within scope.
- Report changed files, command results, and unresolved issues.
- Stop and wait for review.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 36
19.2 Section 1 prompt: audit and contract capture
Implement only Phase 1 Guide Section 7: Freeze Verification and Contract Capture.
## Tasks:
- Inspect the repository and identify the real C++ build directory, executable, release scenario,
sample plan, invalid plan, and output paths.
- Run the existing C++ build and full CTest suite. Do not change any C++ file.
- Run the release scenario with no plan, with the valid sample plan, and with the invalid plan.
- Copy the exact three outputs into backend/tests/fixtures/results/ as baseline_result.json,
valid_plan_result.json, and invalid_plan_result.json.
- Record SHA-256 hashes and create a concise README.md inventory of top-level fields, nested field
groups, exact outcome strings, and outcome-dependent field presence.
- Explicitly verify that full telemetry_history and per-sample crew vitals are present and that
survival_probability is absent.
- Do not scaffold the full backend yet.
Run the relevant commands, report results, and stop.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 37
19.3 Section 2 prompt: scaffold and schemas
Implement only Phase 1 Guide Sections 4, 6, and 8: backend project scaffold, dependency
configuration, and strict Pydantic contracts.
Use the captured fixtures and current C++ declarations/JsonIO as source of truth.
Create the approved backend directory structure and pyproject.toml. Implement schemas/actions.py,
plan.py, crew.py, telemetry.py, result.py, and api.py. Use exact field names and serialized enum
values. Use Pydantic v2 and extra="forbid". Model the complete telemetry_history and crew vitals.
Do not add survival_probability. Do not make fields optional without fixture or serializer
evidence. Do not implement routes/services beyond minimal imports needed for schema tests.
Add fixture-driven positive and negative tests. All three result fixtures and both plan fixtures
must validate. Unknown fields, missing required telemetry, invalid enum values, and
survival_probability must fail.
Run pytest for schema tests and static checks configured in pyproject. Report changed files and
results, then stop.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 38
19.4 Section 3 prompt: configuration and health
Implement only Phase 1 Guide Sections 6 and 9: Settings, application factory/lifespan, API router,
and GET /api/health.
## Requirements:
- Use pydantic-settings.
- Resolve paths independently of current working directory.
- Validate simulator binary, scenario directory, runs directory writability, timeout, concurrency,
and log level.
- Support Windows executable paths without breaking other platforms.
- Create create_app() for isolated tests.
- Health must distinguish HTTP liveness from simulator readiness and must not run a full simulation
on every request.
- Do not add the simulation route yet.
- Do not enable wildcard CORS.
Add unit/integration tests for valid/invalid settings, startup, ready health, and not-ready health.
Run tests and stop.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 39
19.5 Section 4 prompt: registry and artifacts
Implement only Phase 1 Guide Sections 10 and 11: ScenarioRegistry and RunStore.
## Requirements:
- Register the real release scenario ID to the trusted release JSON file.
- Never derive paths from arbitrary client strings.
- Resolve and verify path containment.
- Create UUID4 run workspaces with exclusive creation.
- Copy scenario.json exactly; write deterministic request.json and optional plan.json.
- Define result/stdout/stderr/metadata paths.
- Use atomic JSON/metadata writes.
- Compute SHA-256 hashes.
- Preserve partial evidence on failures.
- Never use the shared repository results/sim_result.json.
- Never expose absolute paths through public models.
Add path traversal, unknown ID, symlink where supported, workspace uniqueness, hash, atomic-write,
baseline-no-plan, and concurrent-isolation tests. Run tests and stop.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 40
19.6 Section 5 prompt: simulator client
Implement only Phase 1 Guide Section 12: SimulatorClient.
## Requirements:
- Constructor-inject validated settings.
- One shared asyncio.Semaphore for maximum concurrent processes.
- Build argument lists for baseline and plan modes.
- Use asyncio.create_subprocess_exec only; no shell.
- Capture stdout/stderr, use monotonic timing, enforce timeout with asyncio.wait_for, kill and
await on timeout.
- Verify result file exists and is non-empty.
- Parse UTF-8 JSON and validate with strict SimulationResult.
- Raise distinct typed errors for unavailable binary, timeout, execution failure, missing output,
invalid JSON, and output contract error.
- Treat valid FAILURE/STABILIZED/REJECTED results as data, not exceptions.
- Base nonzero-exit-code policy on actual release CLI behavior.
Create test-only fake process scripts for timeout and malformed output where needed. Add command,
process, timeout, output, and concurrency tests. Run tests and stop.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 41
19.7 Section 6 prompt: service, route, errors, logging
Implement only Phase 1 Guide Sections 13, 14, and 15: SimulationService, POST /api/sim/run, typed
exception handlers, and structured logging.
## Requirements:
- SimulationService resolves scenario, creates workspace, persists inputs, invokes SimulatorClient,
persists logs/result/metadata/hashes, and returns run_id + duration_ms + unchanged
SimulationResult.
- Preserve failure artifacts and attach run_id to typed errors when available.
- The route is thin and uses the strict request/response models.
- FAILURE and REJECTED return HTTP 200.
- Map unknown scenario 404, unavailable 503, timeout 504, process/output bridge failures 502,
artifact failures 500, and request validation 422.
- Do not expose paths, tracebacks, raw OS errors, or environment values.
- Add structured run events without logging full telemetry_history.
Add service unit tests, error mapping tests, logging tests, and HTTP tests. Run tests and stop.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 42
19.8 Section 7 prompt: real integration and release gate
Implement only Phase 1 Guide Sections 16, 17, 20, and 21: real integration tests,
determinism/concurrency verification, README, and final quality gate.
## Requirements:
- Run the real frozen executable through FastAPI for baseline, valid plan, and invalid plan.
- Assert HTTP 200 and exact expected simulator outcomes.
- Verify failure reasons, metrics, timeline, full telemetry_history, crew vitals, and artifacts are
preserved.
- Run two identical requests and compare canonical SimulationResult values; compare result SHA-256
too when the current release guarantees byte determinism.
- Run concurrent requests and prove workspace isolation.
- Verify unavailable binary, timeout, and malformed output status/error contracts.
- Complete backend README and .env.example with real repository commands/paths.
- Run C++ build/tests, full backend pytest, Ruff, and mypy if configured.
- Do not begin Phase 2 or Phase 3 work.
Report the full release gate with command output summaries and stop.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 43
- Build and Run Commands
20.1 C++ release verification
# From the simulator build context used by the repository
cmake --build build
ctest --test-dir build --output-on-failure
20.2 Backend environment - PowerShell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn app.main:app --reload
20.3 Backend environment - Bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload
20.4 Tests and quality checks
pytest
pytest tests/unit
pytest tests/integration
ruff check .
mypy app
20.5 Manual smoke calls
GET  http://127.0.0.1:8000/api/health
POST http://127.0.0.1:8000/api/sim/run
Content-Type: application/json
## {
## "scenario_id": "<registered_release_scenario_id>",
"plan": null
## }
Command accuracy rule
Cursor must update README command examples to the actual repository build directory, executable name, and scenario ID
discovered during implementation.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 44
- Final Release Gate and Self-Check
21.1 Functional release gate
[ ] C++ simulator remains unmodified and its complete test suite passes.
[ ] FastAPI starts with validated configuration from both project-root and backend working directories.
[ ] GET /api/health reports ready only when the simulator and artifact store are usable.
[ ] POST /api/sim/run accepts a registered scenario ID and optional inline plan.
[ ] Baseline request returns HTTP 200 and simulator outcome FAILURE.
[ ] Valid release plan returns HTTP 200 and simulator outcome STABILIZED.
[ ] Invalid release plan returns HTTP 200 and simulator outcome REJECTED.
[ ] The backend returns complete metrics, timeline, failure_reasons, telemetry_history, and crew vitals unchanged.
[ ] No survival_probability exists anywhere in the deterministic API contract.
[ ] Unknown fields and malformed output are rejected by strict models.
[ ] Every request creates an isolated run artifact directory.
[ ] Timeout and concurrency controls work and do not block the event loop.
[ ] No route accepts arbitrary paths, executables, output locations, or command arguments.
[ ] No shell-based process execution exists.
[ ] No backend module duplicates simulator physics or engineering constraints.
[ ] Unit, integration, determinism, and concurrency tests pass.
[ ] README and .env.example match the actual implementation.
[ ] No NVIDIA, RAG, mission lifecycle, replay, frontend, database, authentication, or deployment code entered Phase 1.
21.2 Required release evidence
EvidenceRequired artifact
C++ release statusBuild and CTest command summaries.
Schema evidenceThree captured result fixtures and their hashes.
API evidenceIntegration-test results for FAILURE, STABILIZED, and REJECTED.
Determinism evidenceCanonical result equality and optional result SHA-256 equality.
Concurrency evidenceDistinct run IDs/workspaces and successful independent responses.
Failure-path evidenceUnavailable, timeout, malformed-output, and artifact-error tests.
Quality evidencepytest, Ruff, and mypy results where configured.
Scope evidenceGit diff proving no simulator or later-phase implementation changes.
## PHASE 1 COMPLETE
Phase 1 is complete only when the HTTP bridge reproduces all three frozen CLI outcomes, preserves the complete
deterministic result contract, and proves that infrastructure failures are distinguishable from mission failures.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 45
## Appendix A. File Responsibility Matrix
File/groupCursor implementation responsibilityForbidden responsibility
pyproject.tomlDependencies, test/lint/type configuration.Later-phase packages.
core/config.pySettings and readiness path validation.Guessing invalid paths silently.
core/errors.pyTyped infrastructure errors.Mission failure/rejection decisions.
core/logging.pyStructured run events.Full telemetry or secrets.
schemas/*Exact strict JSON contracts.Physics, clamps, feasibility, invented defaults.
scenario_registry.pyTrusted ID-to-file mapping.Arbitrary client path construction.
run_store.pyIsolated artifacts, hashes, metadata.Shared output file or exposed absolute paths.
simulator_client.pyAsync safe process invocation and result
validation.
HTTP semantics or simulator calculations.
simulation_service.pyRun orchestration.Process shell details in routes or mission
decisions.
health.pyReadiness reporting.Full simulation on each health call.
simulation.pyThin POST route.Outcome reinterpretation.
tests/unitPrecise component and contract tests.Weakening production code for test convenience.
tests/integrationReal executable and failure-path evidence.Mock-only release gate.
README.mdActual local setup and contracts.Claims that AI/RAG/frontend already exist.

ARES-1 Phase 1 Backend Implementation Guide
ARES-1 | Cursor-Owned FastAPI Backend | Page 46
## Appendix B. Source Traceability
This guide is derived from the project files supplied for ARES-1. No external research was used.
SourceRelevant authority
ARES-1 Project OverviewOverall architecture: Next.js -> FastAPI -> hosted NVIDIA NIM; C++
CLI boundary; original repository shape; API and MVP phase
sequence.
ARES-1 C++ Simulation Core Development Guide - NASA Telemetry +
Crew Vitals v3
Frozen simulator authority, source-classification honesty, exact
telemetry snapshot expectations, live replay principle, no deterministic
survival probability.
C++ Simulation CompletionCurrent release status: build success, 114/114 tests, baseline
FAILURE, valid-plan STABILIZED, invalid-plan REJECTED,
deterministic SHA-256, complete telemetry history and crew vitals.
API Call Testing StepsNVIDIA API connectivity is verified but explicitly outside Phase 1
implementation scope.
NASA Telemetry Simulation noteTerminology reference only; no additional implementation authority.
Source-of-truth hierarchy
For backend contracts: current executable output and C++ serializer first, revised C++ guide second, project overview
examples third. When sources differ, the active frozen implementation wins.