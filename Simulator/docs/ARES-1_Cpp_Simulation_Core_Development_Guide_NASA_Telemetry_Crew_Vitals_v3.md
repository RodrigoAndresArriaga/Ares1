

ARES-1 C++ Simulation Core Development Guide | Page 1
## ARES-1
## C++ Simulation Core Development Guide
NASA-Calibrated Habitat Telemetry + Simulated Crew Vitals
Ownership rule
You define every data type and implement every line of simulator logic. Cursor creates the project
boilerplate, function declarations in the functional .hpp files, and matching empty function definitions in
the .cpp files with the correct header imports.
Development philosophy
The AI proposes. The simulator decides. The dashboard explains.
Supersedes the original simplified C++ guide and uses the revised NASA-calibrated telemetry specification.

ARES-1 C++ Simulation Core Development Guide | Page 2
## Document Contents
1. Boundary and ownership rules
2. What the simulator now models
3. Locked architecture and timestep flow
4. Project file structure
5. Cursor boilerplate scope
6. Your header-development sequence
7. Source classifications and calibration honesty
8. Core enums and data definitions
9. NASA-calibrated habitat telemetry
10. Live simulated crew vital telemetry
11. Crew physiology response design
12. Function implementation guide
13. Recovery action behavior
14. Validation, failure, and stabilization rules
15. JSON and frontend telemetry contract
16. Recommended coding order
17. Deterministic test plan
18. Cursor scaffold prompt
19. Build and run commands
20. Final self-check
How to use this guide
Build one data contract or one implementation card at a time. You declare the data being manipulated.
Cursor creates the function contracts and empty definitions. You then implement and test each TODO
behavior described here.

ARES-1 C++ Simulation Core Development Guide | Page 3
- Boundary and Ownership Rules
This guide is primarily for the deterministic ARES-1 C++ simulation core. It also defines the telemetry JSON
contract required by FastAPI, Open MCT, and the crew-vitals frontend, but it does not implement those
frontend systems.
Core authority
The planner can choose only permitted actions. It cannot write physical state, crew vital signs, mission
status, validation results, or the final outcome.
1.1 Your responsibility
Write every enum, data struct, configuration field, mutable state field, telemetry field, action field, result field,
and physical constant.
Implement every equation, state transition, action effect, validation branch, simulation loop, failure check, and
telemetry calculation.
Choose and document every ARES assumption and every crew-response coefficient.
Be able to explain the unit and ownership of every variable.
1.2 Cursor responsibility
Create directories, filenames, CMake boilerplate, and dependency wiring.
After the data-only headers are defined, create the functional class declarations, constructors, and function
signatures in the appropriate .hpp files.
Create matching out-of-class function definitions in each .cpp file, import the matching header, and leave every
body as a clear TODO with only a neutral placeholder return when compilation requires one.
Create the thin main.cpp/CLI function shell without implementing parsing, simulation, or I/O behavior.
Create empty test cases and test function shells without assertions or expected values.
1.3 Forbidden Cursor output
No enums, data structs, member fields, constants, thresholds, coefficients, defaults, or scenario values unless
you already declared them.
No function-body logic, equations, helper algorithms, branch conditions, or meaningful return values.
No JSON parsing or serialization logic.
No validation conditions, action behavior, simulation loops, vital-response equations, or test assertions.

ARES-1 C++ Simulation Core Development Guide | Page 4
- What the Simulator Now Models
ARES-1 remains a fixed-timestep C++17 mission-survival simulator. The revised version models physical
habitat resources, operational constraints, and individual simulated crewmember response to the
environment.
SubsystemWhat it contributes
Habitat atmosphereO2, inert gas, CO2, mixed-gas leak, pressure, inspired
oxygen, scrubber behavior.
Electrical powerMars solar generation, categorized loads, battery energy,
state of charge, reserve time.
Thermal controlCrew/equipment heat, environmental heat, TCS rejection,
cabin temperature, margins.
EVA and mobilityPreparation, egress, work, ingress, consumables, rover
energy, repair progress.
CommunicationsScheduled windows, transmission timing, packet status,
communications load.
Crew physiologyPer-crewmember metabolic demand, heart rate, respiratory
rate, SpO2, core temperature, fatigue, performance, health
state.
Mission authorityPlan validation, hard failures, stabilization hold, deterministic
result, event timeline.
Simulation claim
The environment limits and metabolic baselines are NASA-calibrated. The individual vital-response
mapping is a deterministic ARES model until separately calibrated against an approved physiological
source. It must be labeled ARES_ASSUMPTION, not NASA_STANDARD.

ARES-1 C++ Simulation Core Development Guide | Page 5
- Locked Architecture and Timestep Flow
3.1 Component responsibilities
ComponentResponsibility
SimulationOwns the run, state copies, timestep order, termination,
metrics, and result assembly.
ResourceModelUpdates habitat gas inventories, CO2 removal, solar power,
battery energy, loads, and thermal state.
CrewPhysiologyModelUpdates each crewmember response, metabolic outputs,
cumulative exposure, performance, and health status.
ActionExecutorApplies valid scheduled actions by changing model inputs
and operational state.
ValidatorPerforms schema/static checks before the run and evaluates
dynamic constraints after/during the run.
JsonIOLoads scenario/plan data and writes deterministic
result/telemetry JSON.
MathUtilsContains small unit conversions, clamping, interpolation, and
normalized-severity helpers.
3.2 Dependency mental model
main.cpp
loads scenario + plan through JsonIO
creates Simulation
runs baseline or plan
writes SimulationResult
## Simulation
owns ScenarioConfig, SimulationState, and telemetry history
coordinates ActionExecutor, CrewPhysiologyModel, ResourceModel, Validator
never trusts planner-declared success
CrewPhysiologyModel
reads current environment + crew activity
updates per-crew response and metabolic outputs
ResourceModel
consumes crew O2 / CO2 / heat outputs
updates physical habitat state
DerivedTelemetry
is calculated from state
is never independently mutated

ARES-1 C++ Simulation Core Development Guide | Page 6
3.3 One-minute deterministic step order
1.Apply actions scheduled at the current simulation minute.
2.Resolve each crewmember location, activity, EVA phase, and rationing mode.
3.Calculate the pre-step environmental telemetry from the current physical state.
4.Update each crewmember physiology once using the pre-step environment and the fixed timestep.
5.Aggregate crew oxygen demand, CO2 generation, and heat output.
6.Update atmosphere inventories and mixed-gas leak.
7.Update CO2 scrubbing and rolling one-hour CO2 history.
8.Update Mars solar generation and categorized electrical loads.
9.Update battery energy and state-dependent power constraints.
10.Update cabin thermal state.
11.Update EVA consumables, rover energy, and repair progress.
12.Calculate the complete post-step habitat and crew telemetry snapshot.
13.Evaluate warnings, hard failures, action aborts, and stabilization hold state.
14.Record telemetry and timeline events, then advance the clock.
Why physiology is separate
Crew response affects metabolic loads and work capability, but it must not be mixed into the atmosphere
or battery functions. Keeping it separate prevents hidden feedback loops and makes every model testable.

ARES-1 C++ Simulation Core Development Guide | Page 7
## 4. Project File Structure
Cursor creates exactly this structure. You populate the data-only headers. Cursor then adds functional
declarations and matching empty .cpp definitions. You implement every function body afterward.
sim_core/
|-- CMakeLists.txt
|-- include/
## |   |-- Enums.hpp
|   |-- PhysicalConstants.hpp
|   |-- ScenarioConfig.hpp
|   |-- CrewMember.hpp
|   |-- SimulationState.hpp
|   |-- DerivedTelemetry.hpp
## |   |-- Action.hpp
## |   |-- Plan.hpp
|   |-- TelemetrySample.hpp
|   |-- SimulationMetrics.hpp
|   |-- SimulationResult.hpp
|   |-- ValidationResult.hpp
|   |-- ResourceModel.hpp
|   |-- CrewPhysiologyModel.hpp
|   |-- ActionExecutor.hpp
## |   |-- Validator.hpp
## |   |-- Simulation.hpp
|   |-- JsonIO.hpp
|   `-- MathUtils.hpp
|-- src/
|   |-- main.cpp
|   |-- ResourceModel.cpp
|   |-- CrewPhysiologyModel.cpp
|   |-- ActionExecutor.cpp
## |   |-- Validator.cpp
## |   |-- Simulation.cpp
|   |-- JsonIO.cpp
|   `-- MathUtils.cpp
`-- tests/
|-- CMakeLists.txt
|-- test_math_utils.cpp
|-- test_atmosphere.cpp
|-- test_power.cpp
|-- test_thermal.cpp
|-- test_crew_physiology.cpp
|-- test_actions.cpp
|-- test_validator.cpp
`-- test_simulation.cpp
4.1 File responsibility table
HeaderContainsOwner
Enums.hppAll enum classes used by state, actions,
health, EVA, and mission status.
## You
PhysicalConstants.hppGas constant, molar masses, conversion
constants.
## You
ScenarioConfig.hppImmutable habitat, thresholds, faults, crew
configs, vital-response parameters.
## You

ARES-1 C++ Simulation Core Development Guide | Page 8
HeaderContainsOwner
CrewMember.hppCrew config, dynamic state, and per-crew
telemetry data types.
## You
SimulationState.hppAll mutable physical and operational state.You
DerivedTelemetry.hppCalculated habitat and mission telemetry.You
Action.hpp / Plan.hppAllowed action data and planner plan
contract.
## You
TelemetrySample.hppTimestamped habitat + crew snapshot for
result/frontend.
## You

ARES-1 C++ Simulation Core Development Guide | Page 9
4.1 File responsibility table - continued
ComponentResponsibility splitOwner
ResourceModelCursor declares the interface and creates
TODO definitions; you implement habitat
equations and derived telemetry.
## Shared
CrewPhysiologyModelCursor declares the interface and creates
TODO definitions; you implement crew
response and metabolic outputs.
## Shared
ActionExecutorCursor declares routing functions and
creates TODO definitions; you implement
action effects.
## Shared
ValidatorCursor declares validation functions and
creates TODO definitions; you implement
every rule.
## Shared
SimulationCursor declares orchestration functions
and creates TODO definitions; you
implement all loops and state logic.
## Shared
JsonIOCursor declares I/O functions and creates
TODO definitions; you implement strict
parsing and serialization.
## Shared
MathUtilsCursor declares helpers and creates
TODO definitions; you implement the
calculations.
## Shared
CMake + boilerplateBuild wiring, functional declarations,
matching empty definitions, and compile-
safe placeholders.
## Cursor

ARES-1 C++ Simulation Core Development Guide | Page 10
## 5. Cursor Boilerplate Scope
Cursor createsCursor must not create
Directories, filenames, CMake, and dependency wiring.Enums, data structs, fields, constants, thresholds,
coefficients, defaults, or scenario values.
CMake target and nlohmann/json dependency wiring.Physical constants, thresholds, coefficients, or scenario
values.
Functional class declarations, constructors, and function
signatures after your data types exist.
Any modification to your data declarations unless explicitly
requested.
Matching #include and empty out-of-class function definitions
in every .cpp.
Equations, state transitions, action effects, validation
branches, simulation loops, or crew-response logic.
Test files and empty test-function shells registered by
CMake.
Test assertions, fixtures, numerical expectations, or pass/fail
logic.
Thin main.cpp declarations/definitions and TODO call flow.CLI parsing logic, file loading behavior, simulation execution
logic, or result writing logic.
Updated rule
You own the data model and all executable logic. Cursor owns mechanical function boilerplate:
declarations in .hpp files and matching empty definitions in .cpp files. This keeps you in control of every
variable while removing repetitive signature work.

ARES-1 C++ Simulation Core Development Guide | Page 11
- Data Declaration and Interface Generation Sequence
First, you define the data-only headers in dependency order. After those types compile, Cursor generates the
functional interfaces and matching empty source definitions from the implementation cards in this guide.
StepHeaderWhat you decide before continuing
1Enums.hppEvery legal state, action, activity, health
status, EVA phase, and outcome.
2PhysicalConstants.hppUnits and universal constants; no
mission tuning values.
3CrewMember.hppIndividual crew identity/configuration,
dynamic exposure state, and output
vitals.
4ScenarioConfig.hppHabitat configuration, limits, faults, crew
roster, and response coefficients.
5SimulationState.hppOnly mutable physical and operational
values.
6DerivedTelemetry.hppOnly values calculated from
configuration and state.
7Action.hpp and Plan.hppAllowed planner commands and fields.
8TelemetrySample.hppOne complete authoritative
timestamped snapshot.

ARES-1 C++ Simulation Core Development Guide | Page 12
- Interface-generation sequence - continued
StepFile/groupResponsibility before continuing
9Metrics / Result / Validation dataYou declare final output fields, tracked
extrema, and error containers.
10Compile data contractsYou verify every enum and data struct
compiles before interface generation.
11MathUtils.hpp/.cppCursor declares recommended helpers
and creates matching TODO definitions.
12ResourceModel.hpp/.cppCursor declares habitat calculation
contracts and creates TODO definitions.
13CrewPhysiologyModel.hpp/.cppCursor declares crew-response
contracts and creates TODO definitions.
14ActionExecutor + ValidatorCursor declares routing/validation
contracts and creates TODO definitions.
15Simulation.hpp/.cppCursor declares orchestration, history,
metrics, and termination functions.
16JsonIO + main.cppCursor declares the strict I/O and CLI
shell; you implement all behavior.
Header checkpoint
Do not let Cursor generate functional interfaces until your data contracts compile and you can explain
which type owns each input, output, and mutable field. Review every generated signature before
implementing its TODO body.

ARES-1 C++ Simulation Core Development Guide | Page 13
- Source Classifications and Calibration Honesty
ClassificationMeaningExamples
NASA_STANDARDPublished exposure requirement or limit.Cabin pressure range, CO2 one-hour limit,
inspired-O2 limits.
NASA_REFERENCEPublished design or metabolic reference,
not a universal requirement.
Crew O2 use, CO2 production, heat
output, EMU duration.
DERIVED_PHYSICSCalculated from conservation laws or unit
conversions.
Ideal gas pressure, SOC, power balance,
time-to-limit.
ARES_ASSUMPTIONFictional habitat design, scenario tuning,
or response coefficient.
Battery reserve, repair time, vital-response
coefficients.
7.1 Non-negotiable claims
The telemetry is simulated, not authentic NASA mission telemetry.
Environmental limits and metabolic baselines are calibrated from NASA source material.
Crew vital signs are generated by an ARES deterministic response model unless a separate source explicitly
calibrates them.
No survival probability is emitted by the deterministic MVP. Add it only after Monte Carlo uncertainty exists.
7.2 Configuration metadata
Every threshold or coefficient in ScenarioConfig should carry a source classification and a short source label.
The simulator does not need to expose every source tag every timestep, but the scenario and final report
must preserve traceability.

ARES-1 C++ Simulation Core Development Guide | Page 14
- Declare the Complete Data Model
What Section 8 produces
When this section is finished, every data-only header compiles. You will know exactly where every variable
lives before Cursor generates any functional class declaration. Do not implement simulator functions in this
section.
8.0 Complete these files in this exact order
StepFile you editWhat you finish
1include/Enums.hppEvery enum used by configuration, state,
actions, crew health, validation, and
results.
2include/PhysicalConstants.hppUnit-conversion and physical constants
only.
3include/CrewMember.hppCrew configuration, mutable crew state,
and crew telemetry structs.
4include/Action.hppPlanner action data and long-running
action progress data.
5include/Plan.hppRecovery plan container.
6include/ScenarioConfig.hppAll immutable scenario, limits, subsystem,
fault, crew, and physiology configuration.
7include/SimulationState.hppAll values that physically or operationally
change during a run.
8include/DerivedTelemetry.hppAll values calculated from state and
configuration.
9include/TelemetrySample.hppOne atomic timestamped frontend/result
snapshot and timeline event type.
10include/SimulationMetrics.hppTracked extrema and final metrics.
11include/SimulationResult.hppFinal simulator output structure.
12include/ValidationResult.hppStatic and dynamic validation messages.
Rule for every data header
You declare the enum, struct, fields, units, and ownership. Do not add equations or behavior. Cursor does
not invent fields. After all twelve files compile, Cursor may generate functional declarations and matching
empty .cpp definitions.

ARES-1 C++ Simulation Core Development Guide | Page 15
8.1 Declare include/Enums.hpp
OPEN THIS FILE: include/Enums.hpp
Create the vocabulary used by the rest of the simulator. This file should contain enum class declarations
only.
Add or verify these includes:
#pragma once
Do this in the file:
- Declare MissionStatus.
- Declare OutcomeStatus.
- Declare ActionType.
- Declare ActionExecutionStatus for long-running action state.
- Declare CrewActivity.
- Declare CrewHealthStatus.
- Declare CrewAlarmType.
- Declare EVAStatus.
- Declare ConstraintSeverity.
- Declare SourceClassification.
Cursor boundary
Cursor created the empty file. You write all enum declarations and values.
## DONE WHEN
The header compiles by itself and no other header needs a raw string to represent these concepts.
EnumValues to declare
MissionStatusNominal, Warning, Critical, Stabilized, Failure, Rejected
OutcomeStatusStabilized, Failure, Rejected
ActionTypeReducePowerLoad, IsolateModule, OxygenRationing,
RepairSolarArray, DelayRoverUse, SendEmergencyPacket,
## Unknown
ActionExecutionStatusPending, Active, Complete, Failed, Aborted
CrewActivitySleep, Resting, NominalWork, HighWorkload, EVAPrep,
EVATransit, EVAWork, Recovery, Incapacitated
CrewHealthStatusNominal, ElevatedStress, Impaired, Critical, Incapacitated
CrewAlarmTypeHypoxia, Hypercapnia, Pressure, Tachycardia, Respiratory,
Thermal, Fatigue, Performance, EVAReturn
EVAStatusIdle, Preparing, Egress, Working, Ingress, Complete, Aborted
ConstraintSeverityInfo, Warning, Critical, Failure
SourceClassificationNASAStandard, NASAReference, DerivedPhysics,
ARESAssumption

ARES-1 C++ Simulation Core Development Guide | Page 16
8.2 Declare include/PhysicalConstants.hpp
OPEN THIS FILE: include/PhysicalConstants.hpp
Centralize true physical and conversion constants. Do not put scenario limits, repair durations, battery
reserves, or physiology tuning here.
Add or verify these includes:
#pragma once
Do this in the file:
- Choose a namespace such as ares::constants.
- Declare each constant as inline constexpr double unless it is an integer count.
- Add a short comment with units beside every value.
- Keep NASA limits out of this file; those are scenario configuration because they are checked and reported with
source metadata.
Cursor boundary
Cursor created the file only. You declare every constant.
## DONE WHEN
No .cpp file contains duplicated conversion numbers or molar masses.
Constant meaningRecommended identifier / value
Universal gas constantGAS_CONSTANT_J_PER_MOL_K = 8.314462618
O2 molar massOXYGEN_MOLAR_MASS_KG_PER_MOL = 0.031998
N2-equivalent molar massINERT_MOLAR_MASS_KG_PER_MOL = 0.0280134
CO2 molar massCO2_MOLAR_MASS_KG_PER_MOL = 0.04401
Celsius to kelvin offsetCELSIUS_TO_KELVIN = 273.15
Pressure conversionKPA_TO_MMHG = 7.50062
Respiratory water-vapor referenceWATER_VAPOR_PRESSURE_MMHG = 47.0
Solar flux at 1 AUSOLAR_FLUX_1_AU_W_M2 = 1361.0
Time conversionsSECONDS_PER_MINUTE, MINUTES_PER_HOUR,
## SECONDS_PER_HOUR
Mass/power conversionsGRAMS_PER_KILOGRAM, WATTS_PER_KILOWATT

ARES-1 C++ Simulation Core Development Guide | Page 17
8.3 Declare include/CrewMember.hpp
OPEN THIS FILE: include/CrewMember.hpp
Declare three structs in this order: CrewMemberConfig, CrewMemberState, CrewVitalsTelemetry.
Add or verify these includes:
#pragma once
## #include <string>
## #include <vector>
#include "Enums.hpp"
Do this in the file:
- Add the required standard-library and enum includes.
- Declare CrewMemberConfig first because ScenarioConfig stores a vector of it.
- Declare CrewMemberState second because SimulationState stores a vector of it.
- Declare CrewVitalsTelemetry last because DerivedTelemetry exposes a vector of it.
- Put units in comments beside all numeric fields.
Cursor boundary
Cursor must not add any crew field. You define the complete crew data contract.
## DONE WHEN
You can instantiate each struct in a trivial compile-only test and explain which fields are immutable,
mutable, or output-only.
8.3.1 CrewMemberConfig fields
FieldTypePurpose
crew_idstd::stringStable internal identifier used by actions and
telemetry.
display_namestd::stringFrontend label.
assigned_rolestd::stringOperational role; does not automatically
change physiology.
body_mass_kgdoubleOptional response scaling input; ARES
assumption.
baseline_heart_rate_bpmdoubleIndividual baseline.
baseline_respiratory_rate_bpmdoubleIndividual baseline.
baseline_spo2_percentdoubleIndividual nominal displayed saturation.
baseline_core_temperature_cdoubleIndividual nominal core temperature.
fitness_factordoubleBounded workload/fatigue modifier.
hypoxia_sensitivitydoubleIndividual low-O2 response multiplier.
co2_sensitivitydoubleIndividual CO2 response multiplier.
thermal_sensitivitydoubleIndividual thermal response multiplier.
fatigue_recovery_factordoubleIndividual recovery modifier.
eva_qualifiedboolStatic eligibility for EVA assignment.

ARES-1 C++ Simulation Core Development Guide | Page 18
8.3.2 CrewMemberState fields
FieldTypeOwner during run
crew_idstd::stringLinks state to CrewMemberConfig.
activityCrewActivityActionExecutor / Simulation.
location_modulestd::stringActionExecutor / Simulation.
eva_statusEVAStatusActionExecutor / Simulation.
oxygen_rationing_activeboolActionExecutor.
heart_rate_bpmdoubleCrewPhysiologyModel.
respiratory_rate_bpmdoubleCrewPhysiologyModel.
spo2_percentdoubleCrewPhysiologyModel.
core_temperature_cdoubleCrewPhysiologyModel.
hypoxia_exposure_indexdoubleCrewPhysiologyModel.
co2_exposure_indexdoubleCrewPhysiologyModel.
thermal_exposure_indexdoubleCrewPhysiologyModel.
fatigue_indexdoubleCrewPhysiologyModel.

ARES-1 C++ Simulation Core Development Guide | Page 19
8.3.2 CrewMemberState fields - continued
FieldTypeOwner during run
cognitive_performance_factordoubleCrewPhysiologyModel; range 0-1.
physical_performance_factordoubleCrewPhysiologyModel; range 0-1.
oxygen_consumption_g_mindoubleCrewPhysiologyModel; consumed by
ResourceModel.
co2_production_g_mindoubleCrewPhysiologyModel; consumed by
ResourceModel.
heat_output_wdoubleCrewPhysiologyModel; consumed by
ResourceModel.
health_statusCrewHealthStatusCrewPhysiologyModel.
active_alarmsstd::vector<CrewAlarmType>CrewPhysiologyModel.
8.3.3 CrewVitalsTelemetry fields
Copy/output field groupFields
Identity/contextcrew_id, display_name, assigned_role, activity, eva_status,
location_module
Vitalsheart_rate_bpm, respiratory_rate_bpm, spo2_percent,
core_temperature_c
Metabolismoxygen_consumption_g_min, co2_production_g_min,
heat_output_w
Exposure/performancefatigue_percent, hypoxia_exposure, co2_exposure,
thermal_exposure, cognitive_performance_percent,
physical_performance_percent
Statushealth_status, active_alarms

ARES-1 C++ Simulation Core Development Guide | Page 20
8.4 Declare include/Action.hpp and include/Plan.hpp
OPEN THIS FILE: include/Action.hpp
Declare the action received from the planner and the separate mutable progress state used while an action
executes.
Add or verify these includes:
#pragma once
## #include <optional>
## #include <string>
## #include <vector>
#include "Enums.hpp"
Do this in the file:
- Declare Action with required common fields first.
- Add optional action-specific fields rather than one separate struct per action for the MVP.
- Declare ActiveActionState after Action.
- Do not place action effects in this header.
## DONE WHEN
A plan can represent every allowed action, and long-running EVA/transmission actions have a place to
store progress without changing the original planner action.
StructFields to declare
Actiontype, type_raw, start_min, percent, module, level, duration_min,
hours, crew_id, load_groups
ActiveActionStateaction_index, type, status, actual_start_min, elapsed_min,
progress_fraction, assigned_crew_id, failure_reason
OPEN THIS FILE: include/Plan.hpp
Declare the planner-supplied recovery plan as data only.
Add or verify these includes:
#pragma once
## #include <string>
## #include <vector>
#include "Action.hpp"
Do this in the file:
## 1. Include Action.hpp.
- Declare plan_id, summary, actions, rationale, expected_risk, and constraints_checked.
- Do not include valid_plan, outcome, or simulator metrics; the planner is not allowed to declare those.
## DONE WHEN
Plan contains only planner input data and cannot claim simulator success.

ARES-1 C++ Simulation Core Development Guide | Page 21
8.5 Declare include/ScenarioConfig.hpp
OPEN THIS FILE: include/ScenarioConfig.hpp
Declare every value that remains fixed during one simulation run. This is the main scenario schema
translated into C++ data.
Add or verify these includes:
#pragma once
## #include <string>
## #include <vector>
#include "CrewMember.hpp"
#include "Enums.hpp"
Do this in the file:
- Add all required includes.
- Declare supporting structs before the top-level ScenarioConfig.
- Use the declaration order shown below so types are available when referenced.
- Keep all thresholds, repair durations, reserve policies, and physiology coefficients here instead of hiding them
in .cpp files.
- Add parameter source metadata so every configured constant can be classified.
Cursor boundary
You declare all config structs and fields. Cursor later declares JsonIO functions that populate them.
## DONE WHEN
ScenarioConfig can represent the complete scenario JSON without relying on hardcoded values in logic
files.
8.5.1 Declare these supporting structs in order
OrderStructFields
1ParameterSourceparameter_name, classification,
source_label, note
2CommunicationWindowopen_min, close_min
3ActivityMetabolicProfileactivity, oxygen_g_min, co2_g_min, heat_w,
activity_load
4HabitatConfiginitial_habitable_volume_m3,
isolated_habitable_volume_m3,
nominal_temperature_c,
initial_relative_humidity_percent,
effective_thermal_capacitance_kj_c
5AtmosphereConfiginitial gas inventories, scrubber parameters,
pressure/O2/CO2 thresholds, minimum inert
fraction
6PowerConfigbattery energy/capacity/reserve,
charge/discharge efficiency, categorized
initial loads

ARES-1 C++ Simulation Core Development Guide | Page 22
8.5.1 Supporting structs - continued
OrderStructFields
7SolarConfigarray area, cell efficiency, Mars-Sun
distance, incidence angle, atmosphere
factor, deposited-dust factor
8ThermalConfigequipment/environment/heater heat, TCS
capacity, comfort and critical temperature
limits, humidity limits
9EVAConfigavailability, prep, egress, work, ingress,
reserve, maximum duration, rover
requirement and reserve
10CommunicationsConfigwindows vector, transmission duration,
communications load
11FaultConfigfault type, leak module/rate, isolation
multiplier, solar fault factor, repaired factor
12VitalResponseConfigmetabolic profiles, severity/exposure rates,
vital coefficients, performance weights, alarm
thresholds
13ScenarioConfigmetadata, timestep/duration/hold time, all
config groups, crew roster,
parameter_sources

ARES-1 C++ Simulation Core Development Guide | Page 23
8.5.2 AtmosphereConfig fields
Field groupDeclare these fields
Initial inventoryinitial_oxygen_mass_kg, initial_inert_gas_mass_kg,
initial_co2_mass_kg
Scrubberscrubber_capacity_g_min, initial_scrubber_efficiency
Pressure checkspressure_warning_low_kpa, pressure_failure_low_kpa,
pressure_high_limit_kpa
Inspired O2 checksinspired_o2_nominal_mmhg, inspired_o2_warning_mmhg,
inspired_o2_failure_mmhg
CO2 checkco2_one_hour_limit_mmhg
Composition checkminimum_inert_fraction
8.5.3 PowerConfig and SolarConfig fields
StructDeclare these fields
PowerConfiginitial_battery_energy_kwh, battery_capacity_kwh,
battery_reserve_percent, charge_efficiency,
discharge_efficiency, essential_load_kw, discretionary_load_kw,
thermal_control_load_kw, eva_support_load_kw,
communications_load_kw
SolarConfigarray_area_m2, cell_efficiency, mars_sun_distance_au,
initial_incidence_angle_deg, initial_atmospheric_transmission,
initial_deposited_dust_factor

ARES-1 C++ Simulation Core Development Guide | Page 24
8.5.4 Thermal, EVA, communications, and fault fields
StructDeclare these fields
ThermalConfiginitial_equipment_heat_w, initial_environmental_heat_w,
initial_heater_heat_w, tcs_rejection_capacity_w, comfort_low_c,
comfort_high_c, critical_low_c, critical_high_c,
humidity_low_percent, humidity_high_percent
EVAConfigavailable, preparation_min, egress_min, repair_work_min,
ingress_min, reserve_min, maximum_duration_min,
rover_required, rover_minimum_reserve_percent
CommunicationsConfigwindows, transmission_duration_min, transmission_power_kw
FaultConfigfailure_type, leak_module, total_gas_leak_kg_hr,
isolation_leak_multiplier, solar_fault_factor,
repaired_solar_fault_factor

ARES-1 C++ Simulation Core Development Guide | Page 25
8.5.5 VitalResponseConfig fields
These values are ARES assumptions. You need them in configuration so the physiology logic remains visible
and tunable.
Coefficient groupFields to declare
Activity profilesstd::vector<ActivityMetabolicProfile> activity_profiles
Exposure accumulationhypoxia_accumulation_rate, co2_accumulation_rate,
thermal_accumulation_rate
Exposure recoveryhypoxia_recovery_rate, co2_recovery_rate, thermal_recovery_rate
Fatiguefatigue_work_rate, fatigue_eva_rate, fatigue_recovery_rate
Heart-rate responsehr_activity_gain, hr_hypoxia_gain, hr_co2_gain, hr_thermal_gain,
hr_fatigue_gain, hr_min_bpm, hr_max_bpm
Respiratory responserr_activity_gain, rr_hypoxia_gain, rr_co2_gain, rr_thermal_gain,
rr_min_bpm, rr_max_bpm

ARES-1 C++ Simulation Core Development Guide | Page 26
8.5.5 VitalResponseConfig fields - continued
Coefficient groupFields to declare
SpO2 responsespo2_hypoxia_gain, spo2_pressure_gain, spo2_activity_gain,
spo2_exposure_gain, spo2_min_percent, spo2_max_percent
Core-temperature responsecore_temp_environment_gain, core_temp_activity_gain,
core_temp_time_constant_min, core_temp_min_c,
core_temp_max_c
Performance weightscognitive_hypoxia_weight, cognitive_co2_weight,
cognitive_thermal_weight, cognitive_fatigue_weight, physical
equivalents
Alarm thresholdsspo2_warning_percent, spo2_critical_percent,
heart_rate_warning_bpm, respiratory_rate_warning_bpm,
core_temp_low/high_c, fatigue_warning_fraction,
performance_abort_fraction

ARES-1 C++ Simulation Core Development Guide | Page 27
8.6 Declare include/SimulationState.hpp
OPEN THIS FILE: include/SimulationState.hpp
Declare only values that change while the simulator runs. Do not duplicate derived pressure, SOC,
oxygen-hours, or mission status here.
Add or verify these includes:
#pragma once
## #include <deque>
## #include <string>
## #include <vector>
#include "Action.hpp"
#include "CrewMember.hpp"
Do this in the file:
- Include CrewMember.hpp, Action.hpp, deque, string, and vector.
- Group fields with comments: clock/habitat, atmosphere, power, thermal, EVA/comms, crew/actions.
- Initialize actual values later from ScenarioConfig in Simulation logic; avoid meaningful in-class defaults that hide
missing JSON.
## DONE WHEN
Every mutable quantity has one authoritative owner, and no derived dashboard metric is stored as mutable
state.
State groupFields to declare
Clock/habitattime_min, habitable_volume_m3, cabin_temperature_c,
cabin_relative_humidity_percent
Atmosphereoxygen_mass_kg, inert_gas_mass_kg, co2_mass_kg,
total_gas_leak_kg_hr, leak_fault_factor, scrubber_efficiency
Solar/powerbattery_energy_kwh, solar_incidence_angle_deg,
atmospheric_transmission, deposited_dust_factor, solar_fault_factor,
essential_load_kw, discretionary_load_kw, thermal_control_load_kw,
eva_support_load_kw, communications_load_kw
Thermalequipment_heat_w, environmental_heat_w, heater_heat_w,
tcs_rejection_capacity_w
EVA/rovereva_available, eva_elapsed_min, eva_work_elapsed_min,
solar_repair_progress, rover_battery_percent, rover_available
Communicationsemergency_packet_sent, transmission_elapsed_min
Collectionsactive_faults, crew, rolling_co2_samples, active_actions
Do not declare these in SimulationState
cabin_pressure_kpa, inspired_oxygen_mmhg, battery_soc_percent, solar_generation_percent,
oxygen_hours_remaining, temperature_margin_c, mission_status. These belong in DerivedTelemetry.

ARES-1 C++ Simulation Core Development Guide | Page 28
8.7 Declare include/DerivedTelemetry.hpp
OPEN THIS FILE: include/DerivedTelemetry.hpp
Declare the calculated telemetry groups. ResourceModel and CrewPhysiologyModel produce these
values; actions never edit them directly.
Add or verify these includes:
#pragma once
## #include <string>
## #include <vector>
#include "CrewMember.hpp"
#include "Enums.hpp"
Do this in the file:
- Declare AtmosphereTelemetry.
- Declare PowerTelemetry.
- Declare ThermalTelemetry.
- Declare EVATelemetry.
- Declare CommunicationsTelemetry.
- Declare MissionTelemetry.
- Declare DerivedTelemetry last and compose the groups plus crew_vitals.
## DONE WHEN
A single DerivedTelemetry object can represent the complete post-step mission-control view.
StructFields
AtmosphereTelemetrycabin_pressure_kpa, oxygen_fraction, inspired_oxygen_mmhg,
co2_partial_pressure_mmhg, co2_one_hour_avg_mmhg,
oxygen_hours_remaining, time_to_pressure_limit_hr,
time_to_co2_limit_hr
PowerTelemetrysolar_generation_kw, healthy_solar_generation_kw,
solar_generation_percent, total_habitat_load_kw, power_margin_kw,
battery_soc_percent, battery_hours_to_reserve
ThermalTelemetrycrew_heat_w, tcs_commanded_rejection_w, net_thermal_power_w,
thermal_margin_w, temperature_margin_c
EVATelemetryeva_consumables_remaining_min, eva_safe_return_margin_min,
repair_progress_percent, active_crew_id
CommunicationsTelemetrycomms_window_open, next_comms_window_min,
transmission_in_progress, emergency_packet_sent
MissionTelemetrymission_status, stabilization_elapsed_min, violated_constraints,
warnings
DerivedTelemetryatmosphere, power, thermal, eva, communications, mission,
crew_vitals

ARES-1 C++ Simulation Core Development Guide | Page 29
8.8 Declare snapshot, metrics, result, and validation headers
OPEN THIS FILE: include/TelemetrySample.hpp
Declare TimelineEvent and one atomic TelemetrySample.
Add or verify these includes:
#pragma once
## #include <string>
## #include <vector>
#include "Action.hpp"
#include "DerivedTelemetry.hpp"
#include "Enums.hpp"
Do this in the file:
- Declare TimelineEvent with time_min, event_type/category, message, and severity.
- Declare TelemetrySample with simulation_time_min, DerivedTelemetry telemetry, events_this_step,
active_actions, warning/critical flags.
- Do not store references or pointers to mutable simulator state in a sample; it must own a copy.
## DONE WHEN
A sample remains unchanged after it is pushed into history or serialized.

ARES-1 C++ Simulation Core Development Guide | Page 30
OPEN THIS FILE: include/SimulationMetrics.hpp
Declare extrema and final-run metrics that are updated by Simulation, not by the planner.
Add or verify these includes:
#pragma once
Do this in the file:
- Declare minimum inspired O2, minimum cabin pressure, maximum one-hour CO2, minimum battery SOC,
minimum power margin, minimum temperature margin, minimum EVA return margin.
- Declare minimum crew SpO2 and maximum crew fatigue.
- Declare EVA completed, communications sent, and time to stabilization.
## DONE WHEN
Every metric can be updated from TelemetrySample without recomputing physics.

ARES-1 C++ Simulation Core Development Guide | Page 31
OPEN THIS FILE: include/SimulationResult.hpp
Declare the final deterministic output container.
Add or verify these includes:
#pragma once
## #include <string>
## #include <vector>
#include "Enums.hpp"
#include "SimulationMetrics.hpp"
#include "TelemetrySample.hpp"
Do this in the file:
- Declare scenario_id, plan_id, outcome, valid_plan, metrics, timeline, telemetry_history, and failure_reasons.
- Optionally declare ConstraintResult data if you want named pass/fail fields.
- Do not add survival_probability to the deterministic MVP.
## DONE WHEN
The struct matches the final JSON contract and cannot contain planner-claimed outcome data.

ARES-1 C++ Simulation Core Development Guide | Page 32
OPEN THIS FILE: include/ValidationResult.hpp
Declare reusable validation messages for schema/static and dynamic validation.
Add or verify these includes:
#pragma once
## #include <string>
## #include <vector>
#include "Enums.hpp"
Do this in the file:
- Declare ValidationMessage with code, message, severity, action_index, and simulation_time_min as applicable.
- Declare ValidationResult with valid, errors, and warnings.
## DONE WHEN
Validator can collect multiple useful errors instead of stopping after the first failure.
## SECTION 8 EXIT CHECK
All data-only headers compile. You can point to the exact header that owns any variable. Only now give
Cursor the interface-generation prompt for MathUtils, ResourceModel, CrewPhysiologyModel,
ActionExecutor, Validator, Simulation, and JsonIO.

ARES-1 C++ Simulation Core Development Guide | Page 33
- Implement NASA-Calibrated Habitat Telemetry
What you will edit in Section 9
src/MathUtils.cpp, src/ResourceModel.cpp, tests/test_math_utils.cpp, tests/test_atmosphere.cpp,
tests/test_power.cpp, and tests/test_thermal.cpp. Cursor creates the declarations and empty definitions
first; you implement every TODO body.
9.0 First ask Cursor for these interfaces
After Section 8 compiles, use the Section 18 Pass 2 prompt and tell Cursor to generate only the MathUtils
and ResourceModel declarations/empty definitions listed below.
HeaderCursor-generated function contracts
MathUtils.hppclamp, lowSideSeverity, highSideSeverity, percentToFraction,
celsiusToKelvin, kpaToMmhg, secondsToHours,
minutesToHours
ResourceModel.hppupdateAtmosphere, updateCarbonDioxide,
calculateSolarGenerationKw,
calculateHealthySolarGenerationKw, updateElectricalPower,
updateThermalState, calculateAtmosphereTelemetry,
calculatePowerTelemetry, calculateThermalTelemetry,
calculateEVATelemetry, calculateCommunicationsTelemetry,
calculateDerivedTelemetry
Stop Cursor after boilerplate
Every .cpp definition must contain only its matching header include, a TODO, and a neutral placeholder
return where required. Review signatures before writing logic.

ARES-1 C++ Simulation Core Development Guide | Page 34
9.1 Implement and test MathUtils
9.1.1 Bounded values and severity helpers
ItemInstruction
Editsrc/MathUtils.cpp
Function bodyMathUtils::clamp, lowSideSeverity, highSideSeverity
ReadsA numeric value and explicit safe/critical bounds.
Writes / returnsA bounded value or a deterministic 0-1 severity.
Test intests/test_math_utils.cpp
Implement the TODO body in this order:
- Implement clamp without hiding invalid min/max ordering.
- For low-side severity, return 0 at or above safe, 1 at or below critical, and linearly interpolate between.
- For high-side severity, reverse the direction: 0 at or below safe and 1 at or above critical.
- Clamp only the normalized severity result, not the physical state being checked.
## ACCEPTANCE CHECK
Boundary, midpoint, and outside-range cases return exact expected values.
Do not do this
Do not use these helpers to silently convert a failed physical state into a safe state.

ARES-1 C++ Simulation Core Development Guide | Page 35
9.1.2 Unit conversions
ItemInstruction
Editsrc/MathUtils.cpp
Function bodyMathUtils conversion helpers
ReadsValues with documented source units.
Writes / returnsConverted values only.
Test intests/test_math_utils.cpp
Implement the TODO body in this order:
- Use PhysicalConstants.hpp for conversion values.
- Implement each conversion as a small independent function.
- Do not combine physical equations with unit conversion helpers.
## ACCEPTANCE CHECK
Known conversion pairs pass and no integer division occurs.
Run this checkpoint before continuing:
cmake --build build
ctest --test-dir build -R math --output-on-failure

ARES-1 C++ Simulation Core Development Guide | Page 36
9.2 Implement atmosphere state updates
9.2.1 Mixed-gas leak and crew oxygen use
ItemInstruction
Editsrc/ResourceModel.cpp
Function bodyResourceModel::updateAtmosphere
ReadsSimulationState gas masses/leak state, ScenarioConfig,
aggregated crew O2 demand, dt_seconds.
Writes / returnsMutates oxygen_mass_kg, inert_gas_mass_kg, co2_mass_kg
only.
Test intests/test_atmosphere.cpp
Implement the TODO body in this order:
- Convert dt_seconds to hours for leak mass and to minutes for metabolic oxygen.
- Subtract crew oxygen demand from oxygen mass.
- Calculate total mixed-gas leak mass from base leak rate and leak_fault_factor.
- Calculate current mass fractions before removal.
- Remove leaked O2, inert gas, and CO2 in those proportions.
- Clamp inventories at zero only after recording that depletion would occur; failure logic is handled later by
## Simulation.
## ACCEPTANCE CHECK
No-leak/no-crew state remains constant; a mixed leak removes all species proportionally; two crew
consume twice a one-crew test rate.
Do not do this
Do not remove only oxygen for the habitat leak. Do not calculate cabin pressure inside this mutating
function.

ARES-1 C++ Simulation Core Development Guide | Page 37
9.2.2 CO2 generation, scrubbing, and history
ItemInstruction
Editsrc/ResourceModel.cpp
Function bodyResourceModel::updateCarbonDioxide
ReadsCrew CO2 total, scrubber capacity/efficiency, current CO2 mass,
leak loss already applied, dt_seconds.
Writes / returnsMutates co2_mass_kg and rolling_co2_samples.
Test intests/test_atmosphere.cpp
Implement the TODO body in this order:
- Add crew CO2 production for the timestep.
- Calculate rated scrubber removal times current efficiency.
- Limit removal so CO2 cannot become negative.
- Store the post-step instantaneous CO2 partial-pressure source sample or enough data to calculate the rolling
hour consistently.
- Keep exactly the number of samples corresponding to one simulated hour at the configured timestep.
## ACCEPTANCE CHECK
Scrubber removal never exceeds available CO2; rolling history drops the oldest sample; a 60-second
timestep keeps 60 one-minute samples.
Do not do this
Do not compare against the one-hour NASA limit using only one instantaneous sample.

ARES-1 C++ Simulation Core Development Guide | Page 38
9.2.3 Atmosphere telemetry calculation
ItemInstruction
Editsrc/ResourceModel.cpp
Function bodyResourceModel::calculateAtmosphereTelemetry
ReadsConst SimulationState and ScenarioConfig.
Writes / returnsReturns AtmosphereTelemetry without mutating state.
Test intests/test_atmosphere.cpp
Implement the TODO body in this order:
- Convert O2, inert gas, and CO2 masses to moles using PhysicalConstants.hpp.
- Calculate total moles and cabin temperature in kelvin.
- Calculate cabin pressure from the ideal gas law and connected volume.
- Calculate oxygen mole fraction and inspired oxygen using the 47 mmHg respiratory water-vapor term.
- Calculate CO2 partial pressure and rolling one-hour average.
- Calculate current-rate forecasts for oxygen, pressure, and CO2 limits; return null/optional/infinity according to
the data contract when the trend is safe.
## ACCEPTANCE CHECK
Pressure matches an independently calculated fixture; lowering volume raises pressure for fixed moles;
forecasts agree with a forward-simulation check within tolerance.
Do not do this
Do not store these values back into SimulationState.
Run this checkpoint before continuing:
cmake --build build
ctest --test-dir build -R atmosphere --output-on-failure

ARES-1 C++ Simulation Core Development Guide | Page 39
9.3 Implement solar generation and battery
9.3.1 Solar generation
ItemInstruction
Editsrc/ResourceModel.cpp
Function bodycalculateSolarGenerationKw and
calculateHealthySolarGenerationKw
ReadsSolarConfig and current incidence, atmospheric transmission,
dust, and fault factors from SimulationState.
Writes / returnsActual and healthy generation in kW.
Test intests/test_power.cpp
Implement the TODO body in this order:
- Calculate orbital flux as 1-AU flux divided by Mars-Sun distance squared.
- Convert incidence angle to radians and apply max(0, cos(angle)).
- Apply array area and cell efficiency.
- Apply atmosphere and deposited-dust factors.
- Apply solar_fault_factor only to actual generation, not healthy reference generation.
- Convert watts to kilowatts once at the end.
## ACCEPTANCE CHECK
Zero or greater-than-90-degree incidence produces zero; a 0.55 fault factor produces 55% of healthy
generation under identical conditions.
Do not do this
Do not hardcode 55%; it is scenario state.

ARES-1 C++ Simulation Core Development Guide | Page 40
9.3.2 Electrical load and battery energy
ItemInstruction
Editsrc/ResourceModel.cpp
Function bodyResourceModel::updateElectricalPower
ReadsState load categories, actual solar generation, PowerConfig
efficiencies/capacity, dt_seconds.
Writes / returnsMutates battery_energy_kwh only.
Test intests/test_power.cpp
Implement the TODO body in this order:
- Sum essential, discretionary, thermal-control, EVA-support, and communications loads.
- Calculate the generation-load difference in kW.
- Convert the timestep to hours.
- Use charge efficiency when positive and discharge efficiency when negative.
- Clamp battery energy to [0, capacity] after calculating the physical delta.
## ACCEPTANCE CHECK
Energy conservation fixtures pass; battery cannot exceed capacity or go below zero; one hour at a 1 kW
deficit changes stored energy by the expected efficiency-adjusted amount.
Do not do this
Do not update battery_soc_percent; it is derived telemetry.

ARES-1 C++ Simulation Core Development Guide | Page 41
9.3.3 Power telemetry
ItemInstruction
Editsrc/ResourceModel.cpp
Function bodyResourceModel::calculatePowerTelemetry
ReadsConst state/config plus actual and healthy solar generation.
Writes / returnsReturns PowerTelemetry.
Test intests/test_power.cpp
Implement the TODO body in this order:
- Calculate total load and power margin.
- Calculate SOC from energy divided by capacity.
- Calculate solar generation percentage from actual divided by healthy generation, handling zero healthy
generation.
- Calculate battery time to reserve only while net discharging and above reserve.
## ACCEPTANCE CHECK
SOC, power margin, solar percent, and time-to-reserve fixtures pass.
Run this checkpoint before continuing:
cmake --build build
ctest --test-dir build -R power --output-on-failure

ARES-1 C++ Simulation Core Development Guide | Page 42
9.4 Implement thermal, EVA, communications, and complete telemetry
9.4.1 Thermal integration
ItemInstruction
Editsrc/ResourceModel.cpp
Function bodyResourceModel::updateThermalState
ReadsState heat terms/TCS capacity, aggregated crew heat,
ThermalConfig, dt_seconds.
Writes / returnsMutates cabin_temperature_c and any explicitly modeled TCS
state.
Test intests/test_thermal.cpp
Implement the TODO body in this order:
- Sum crew, equipment, environmental, and heater heat inputs.
- Determine commanded/available heat rejection without exceeding TCS capacity.
- Calculate net heat in watts.
- Convert effective thermal capacitance from kJ/C to J/C.
- Integrate the cabin temperature for the fixed timestep.
## ACCEPTANCE CHECK
Zero net heat leaves temperature unchanged; positive net heat increases it by the expected amount;
capacity-limited rejection produces the expected margin.
Do not do this
Do not directly count down a temperature margin variable.

ARES-1 C++ Simulation Core Development Guide | Page 43
9.4.2 Thermal telemetry
ItemInstruction
Editsrc/ResourceModel.cpp
Function bodyResourceModel::calculateThermalTelemetry
ReadsConst state/config and aggregate crew heat.
Writes / returnsReturns ThermalTelemetry.
Test intests/test_thermal.cpp
Implement the TODO body in this order:
- Recalculate heat input and actual rejection using the same definitions as the update.
- Return net thermal power and remaining rejection margin.
- Calculate temperature margin as distance to the nearest configured critical limit.
## ACCEPTANCE CHECK
Telemetry values match the state update fixture and margin becomes negative only when a limit is
crossed.

ARES-1 C++ Simulation Core Development Guide | Page 44
9.4.3 EVA and communications derived telemetry
ItemInstruction
Editsrc/ResourceModel.cpp
Function bodycalculateEVATelemetry and calculateCommunicationsTelemetry
ReadsConst state/config and current simulation time.
Writes / returnsReturns EVATelemetry and CommunicationsTelemetry.
Test intests/test_power.cpp or a dedicated test_operations.cpp
Implement the TODO body in this order:
- Calculate consumables remaining from maximum duration minus elapsed EVA time.
- Subtract required ingress and reserve for safe-return margin.
- Convert repair progress fraction to percentage for output.
- Determine whether current time lies inside any communication window.
- Find the next future communication opening or mark no future window.
## ACCEPTANCE CHECK
Boundary minutes at window open/close behave according to one documented inclusive/exclusive rule;
EVA return margin matches the configured time budget.

ARES-1 C++ Simulation Core Development Guide | Page 45
9.4.4 Complete DerivedTelemetry
ItemInstruction
Editsrc/ResourceModel.cpp
Function bodyResourceModel::calculateDerivedTelemetry
ReadsConst state/config, current crew vital telemetry, and mission data
supplied by Simulation.
Writes / returnsReturns one complete DerivedTelemetry object.
Test intests/test_atmosphere.cpp plus later integration test
Implement the TODO body in this order:
- Call the atmosphere, power, thermal, EVA, and communications calculation functions.
- Attach the crew_vitals vector supplied by CrewPhysiologyModel.
- Attach mission status, warnings, violations, and stabilization timer supplied by Simulation.
- Do not mutate state and do not evaluate plan success here.
## ACCEPTANCE CHECK
Every field is populated from one coherent state and repeated calls with unchanged inputs are identical.
Run this checkpoint before continuing:
cmake --build build
## SECTION 9 EXIT CHECK
ResourceModel can update physical habitat state and calculate complete habitat telemetry in isolation. All
subsystem tests pass before you connect the main Simulation loop.

ARES-1 C++ Simulation Core Development Guide | Page 46
- Build the Individual Crew Telemetry Pipeline
What Section 10 does
This section creates the crew initialization and output pipeline before the response equations. At the end,
every configured crewmember appears in a deterministic CrewVitalsTelemetry vector and therefore has a
place in the frontend snapshot.
10.0 Files you edit
FileWhat you implement now
src/CrewPhysiologyModel.cppCrew-state initialization and CrewVitalsTelemetry construction
only.
tests/test_crew_physiology.cppRoster mapping, baseline initialization, and telemetry-copy tests.
No frontend files yetSection 15 defines JSON; FastAPI/Next.js streaming is
implemented after the C++ core.
10.1 Ask Cursor for the initial crew interfaces
Function contractPurpose
initializeCrewStates(const ScenarioConfig&)Create one CrewMemberState per CrewMemberConfig.
buildCrewVitalsTelemetry(const SimulationState&, const
ScenarioConfig&) const
Create output objects without changing state.
findCrewConfig(crew_id, config) constResolve an individual configuration deterministically.
Cursor responsibility
Cursor puts these declarations in include/CrewPhysiologyModel.hpp and matching TODO definitions in
src/CrewPhysiologyModel.cpp. You implement the bodies.

ARES-1 C++ Simulation Core Development Guide | Page 47
10.2 Initialize crew state from the roster
ItemInstruction
Editsrc/CrewPhysiologyModel.cpp
Function bodyCrewPhysiologyModel::initializeCrewStates
ReadsScenarioConfig.crew and VitalResponseConfig.
Writes / returnsReturns std::vector<CrewMemberState>.
Test intests/test_crew_physiology.cpp
Implement the TODO body in this order:
- Create one state object for each CrewMemberConfig in roster order.
- Copy crew_id and set initial activity/location/EVA state from explicit scenario defaults.
- Initialize HR, RR, SpO2, and core temperature from individual baselines.
- Initialize exposure/fatigue indices to configured initial values or zero.
- Initialize cognitive/physical performance to 1.0 unless the scenario explicitly starts impaired.
- Resolve the initial activity metabolic profile and initialize O2 consumption, CO2 production, and heat output.
- Initialize health status and alarm list without inventing an alarm.
## ACCEPTANCE CHECK
Roster size and order match configuration; every baseline value matches its crew config; repeated
initialization is identical.
Do not do this
Do not use random values. Do not silently skip a crew member with an invalid ID; surface configuration
validation later.

ARES-1 C++ Simulation Core Development Guide | Page 48
10.3 Build frontend-ready crew telemetry
ItemInstruction
Editsrc/CrewPhysiologyModel.cpp
Function bodyCrewPhysiologyModel::buildCrewVitalsTelemetry
ReadsConst SimulationState crew vector and ScenarioConfig roster.
Writes / returnsReturns std::vector<CrewVitalsTelemetry>.
Test intests/test_crew_physiology.cpp
Implement the TODO body in this order:
- For each CrewMemberState, find the matching CrewMemberConfig.
- Copy identity/context from config and current activity/EVA/location from state.
- Copy authoritative vital and metabolic values from state.
- Convert 0-1 fatigue and performance factors to percentages only in the telemetry object.
- Copy health status and alarms.
- Keep roster/state ordering deterministic so frontend cards do not reorder between samples.
## ACCEPTANCE CHECK
One telemetry object exists per crew state; percentage conversions are correct; building telemetry does
not mutate crew state.
10.4 How this reaches the live frontend later
- Simulation calls buildCrewVitalsTelemetry after the post-step crew and habitat updates.
- The returned vector is placed in DerivedTelemetry.crew_vitals.
- Simulation copies DerivedTelemetry into one TelemetrySample.
- JsonIO serializes the complete TelemetrySample.
- FastAPI later replays or streams each sample through WebSocket or SSE.
- Next.js/Open MCT displays one crew card and time series per crew_id.
Not implemented in Section 10
No WebSocket, FastAPI, React, or Open MCT code belongs in the C++ simulator guide. This section
guarantees that the C++ output contains complete live-simulation data for those layers to consume later.
Run this checkpoint before continuing:
cmake --build build
ctest --test-dir build -R crew --output-on-failure
## SECTION 10 EXIT CHECK
A baseline crew roster can be initialized and converted into frontend-ready telemetry, even before
environmental response equations are implemented.

ARES-1 C++ Simulation Core Development Guide | Page 49
- Implement the Crew Physiology Response Model
What you will edit in Section 11
src/CrewPhysiologyModel.cpp and tests/test_crew_physiology.cpp. Cursor creates all declarations/empty
definitions. You implement deterministic physiology, exposure, metabolism, performance, health status,
and alarms.
11.0 Ask Cursor for the remaining crew interfaces
FunctionRole
findActivityProfileResolve NASA-reference/ARES activity metabolic parameters.
calculateHypoxiaSeverityNormalize inspired-O2 shortfall.
calculateCo2SeverityNormalize rolling CO2 excess.
calculatePressureSeverityNormalize cabin-pressure shortfall.
calculateThermalSeverityNormalize hot/cold cabin stress.
updateExposureIndicesAdd exposure memory and recovery.
updateFatigueAccumulate workload/stress and recover at rest.
updateMetabolicOutputsSet O2 consumption, CO2 production, and heat.
updateVitalSignsUpdate HR, RR, SpO2, and core temperature.
updatePerformanceUpdate cognitive and physical factors.
updateHealthStatusAndAlarmsApply transparent thresholds.
updateCrewMemberRun the ordered update for one person.
updateAllCrewRun one deterministic physiology step for the roster.

ARES-1 C++ Simulation Core Development Guide | Page 50
11.1 Implement activity and environmental severity
11.1.1 Activity metabolic profile lookup
ItemInstruction
Editsrc/CrewPhysiologyModel.cpp
Function bodyCrewPhysiologyModel::findActivityProfile
ReadsCrewActivity and VitalResponseConfig.activity_profiles.
Writes / returnsReturns the matching ActivityMetabolicProfile or an explicit error
path.
Test intests/test_crew_physiology.cpp
Implement the TODO body in this order:
- Search for exactly one matching profile.
- Use Sleep, NominalWork, and HighWorkload values calibrated from the NASA baseline where available.
- Treat EVA and other operational modes as explicit profiles configured in the scenario.
- Do not silently fall back to nominal if a profile is missing.
## ACCEPTANCE CHECK
Every declared CrewActivity used by the scenario resolves to exactly one profile.

ARES-1 C++ Simulation Core Development Guide | Page 51
11.1.2 Environmental severity functions
ItemInstruction
Editsrc/CrewPhysiologyModel.cpp
Function bodycalculateHypoxiaSeverity / calculateCo2Severity /
calculatePressureSeverity / calculateThermalSeverity
ReadsPre-step DerivedTelemetry, ScenarioConfig limits, and individual
sensitivities where appropriate.
Writes / returnsDeterministic bounded 0-1 severity values.
Test intests/test_crew_physiology.cpp
Implement the TODO body in this order:
- Use MathUtils low-side severity for inspired O2 and pressure.
- Use high-side severity for CO2.
- Calculate hot and cold thermal severity separately and use the larger value.
- Apply individual sensitivity as a multiplier, then clamp the final severity.
- Document which safe and critical threshold fields each function uses.
## ACCEPTANCE CHECK
Severity is zero in the safe zone, monotonic through the transition, and one at/beyond critical.
Do not do this
Do not use SpO2 as an input to hypoxia severity; environmental state drives the response.
Run this checkpoint before continuing:
cmake --build build
ctest --test-dir build -R crew --output-on-failure

ARES-1 C++ Simulation Core Development Guide | Page 52
11.2 Implement exposure memory and fatigue
11.2.1 Accumulated environmental exposure
ItemInstruction
Editsrc/CrewPhysiologyModel.cpp
Function bodyCrewPhysiologyModel::updateExposureIndices
ReadsCurrent exposure indices, severity values, config
accumulation/recovery rates, dt_minutes.
Writes / returnsMutates hypoxia_exposure_index, co2_exposure_index,
thermal_exposure_index.
Test intests/test_crew_physiology.cpp
Implement the TODO body in this order:
- For each exposure, add severity * accumulation_rate * dt.
- When severity is below one, subtract the configured recovery term based on (1 - severity).
- Clamp lower bound at zero.
- Use a documented upper bound only if the data contract defines one; otherwise allow values above one for
prolonged exposure and clamp only when converting to performance.
## ACCEPTANCE CHECK
Sustained severity increases exposure, safe conditions recover it, and one bad minute is less severe than
a prolonged exposure.

ARES-1 C++ Simulation Core Development Guide | Page 53
11.2.2 Fatigue accumulation and recovery
ItemInstruction
Editsrc/CrewPhysiologyModel.cpp
Function bodyCrewPhysiologyModel::updateFatigue
ReadsActivity load, EVA state, environmental severities, current
fatigue, crew fitness/recovery factors, dt_minutes.
Writes / returnsMutates fatigue_index in range 0-1.
Test intests/test_crew_physiology.cpp
Implement the TODO body in this order:
- Calculate workload fatigue from configured activity load.
- Add EVA-specific fatigue only during active EVA phases.
- Add configured environmental-stress contribution.
- Apply recovery during sleep/rest/recovery activities.
- Scale accumulation/recovery by fitness_factor and fatigue_recovery_factor transparently.
- Clamp final fatigue to 0-1.
## ACCEPTANCE CHECK
High workload increases fatigue faster than nominal work; rest reduces it; identical inputs reproduce
identical fatigue.

ARES-1 C++ Simulation Core Development Guide | Page 54
11.3 Implement metabolic outputs and vital signs
11.3.1 Metabolic outputs
ItemInstruction
Editsrc/CrewPhysiologyModel.cpp
Function bodyCrewPhysiologyModel::updateMetabolicOutputs
ReadsActivity profile, crew config, rationing state, current
stress/performance modifiers.
Writes / returnsMutates oxygen_consumption_g_min, co2_production_g_min,
heat_output_w.
Test intests/test_crew_physiology.cpp
Implement the TODO body in this order:
- Start from the selected activity profile values.
- Apply only documented individual scaling and rationing modifiers.
- Do not allow rationing to reduce metabolism below the configured physiological floor.
- Ensure the same activity/stress assumptions are used consistently for O2, CO2, and heat.
## ACCEPTANCE CHECK
NASA-reference profile fixtures produce expected rates; rationing changes future rates rather than current
oxygen inventory.

ARES-1 C++ Simulation Core Development Guide | Page 55
11.3.2 Heart rate and respiratory rate
ItemInstruction
Editsrc/CrewPhysiologyModel.cpp
Function bodyPart of CrewPhysiologyModel::updateVitalSigns
ReadsIndividual baselines, activity load, severities, fatigue, config
gains.
Writes / returnsMutates heart_rate_bpm and respiratory_rate_bpm.
Test intests/test_crew_physiology.cpp
Implement the TODO body in this order:
- Calculate target HR from baseline plus configured activity, hypoxia, CO2, thermal, and fatigue components.
- Calculate target RR from baseline plus configured activity, hypoxia, CO2, and thermal components.
- Optionally apply a configured first-order time response rather than instantaneous jumps; if used, keep the time
constant in config.
- Clamp values only to configured display/physiology bounds.
## ACCEPTANCE CHECK
Higher activity or severity never lowers the target response; values return toward baseline under safe rest
conditions.
Do not do this
Do not add unseeded random noise to authoritative state.

ARES-1 C++ Simulation Core Development Guide | Page 56
11.3.3 SpO2 and core temperature
ItemInstruction
Editsrc/CrewPhysiologyModel.cpp
Function bodyRemaining logic in CrewPhysiologyModel::updateVitalSigns
ReadsInspired O2, pressure severity, activity, exposure indices, cabin
temperature, current core temperature, response config.
Writes / returnsMutates spo2_percent and core_temperature_c.
Test intests/test_crew_physiology.cpp
Implement the TODO body in this order:
- Calculate a bounded SpO2 target from baseline minus configured hypoxia, pressure, activity, and cumulative-
exposure components.
- Apply individual hypoxia sensitivity.
- Use a configured lag/time constant so SpO2 can recover rather than teleport unless the model intentionally uses
direct response.
- Calculate core-temperature movement from cabin thermal stress and activity heat, with a configured time
response.
- Clamp only to explicit model bounds and preserve the underlying environment independently.
## ACCEPTANCE CHECK
SpO2 declines monotonically as inspired O2 severity increases, recovers under safe conditions, and
prolonged exposure is worse than a brief excursion; core temperature responds slowly and directionally.
Run this checkpoint before continuing:
cmake --build build
ctest --test-dir build -R crew --output-on-failure

ARES-1 C++ Simulation Core Development Guide | Page 57
11.4 Implement performance, status, and alarms
11.4.1 Cognitive and physical performance
ItemInstruction
Editsrc/CrewPhysiologyModel.cpp
Function bodyCrewPhysiologyModel::updatePerformance
ReadsExposure indices, fatigue, activity load, config weights.
Writes / returnsMutates cognitive_performance_factor and
physical_performance_factor.
Test intests/test_crew_physiology.cpp
Implement the TODO body in this order:
- Calculate separate weighted impairment totals for cognitive and physical performance.
- Subtract impairment from 1.0.
- Clamp each result to 0-1.
- Keep all weights in VitalResponseConfig and make the formula readable enough to explain.
## ACCEPTANCE CHECK
Each adverse input can only reduce or preserve performance; recovery inputs can improve it; factors
remain bounded.

ARES-1 C++ Simulation Core Development Guide | Page 58
11.4.2 Health status and alarms
ItemInstruction
Editsrc/CrewPhysiologyModel.cpp
Function bodyCrewPhysiologyModel::updateHealthStatusAndAlarms
ReadsCurrent vitals, exposure indices, performance, EVA return
margin, configured thresholds.
Writes / returnsMutates health_status and active_alarms.
Test intests/test_crew_physiology.cpp
Implement the TODO body in this order:
- Clear and rebuild the alarm vector from the authoritative current state each step or explicitly maintain alarm
lifecycle.
- Add specific alarm types for crossed thresholds.
- Choose health status from transparent ordered rules: incapacitated, critical, impaired, elevated stress, nominal.
- Use sustained exposure/performance where appropriate rather than one opaque risk score.
- Do not decide mission success here; expose crew status to Simulation and Validator.
## ACCEPTANCE CHECK
Each threshold produces the expected alarm/status; clearing conditions removes non-latched alarms
according to the documented lifecycle.

ARES-1 C++ Simulation Core Development Guide | Page 59
11.5 Assemble the one-person and roster update
11.5.1 One crewmember update order
ItemInstruction
Editsrc/CrewPhysiologyModel.cpp
Function bodyCrewPhysiologyModel::updateCrewMember
ReadsCrewMemberState, matching CrewMemberConfig, pre-step
DerivedTelemetry, ScenarioConfig, dt_seconds.
Writes / returnsMutates exactly one CrewMemberState.
Test intests/test_crew_physiology.cpp
Implement the TODO body in this order:
- Resolve activity profile.
- Calculate environmental severities from pre-step telemetry.
- Update exposure indices.
- Update fatigue.
- Update metabolic outputs.
- Update vital signs.
- Update performance.
- Update health status and alarms.
## ACCEPTANCE CHECK
A complete safe-step fixture stays near baseline; a controlled low-O2 fixture changes every expected field
in the documented direction.

ARES-1 C++ Simulation Core Development Guide | Page 60
11.5.2 Full roster update
ItemInstruction
Editsrc/CrewPhysiologyModel.cpp
Function bodyCrewPhysiologyModel::updateAllCrew
ReadsSimulationState crew vector, ScenarioConfig roster, pre-step
DerivedTelemetry, dt_seconds.
Writes / returnsMutates every CrewMemberState exactly once.
Test intests/test_crew_physiology.cpp
Implement the TODO body in this order:
- Verify roster/state cardinality or resolve each state by crew_id.
- Call updateCrewMember in deterministic roster order.
- Do not aggregate gas/heat here beyond storing each person's metabolic outputs.
- Return or expose no nondeterministic ordering.
## ACCEPTANCE CHECK
Two crew with different sensitivity/fitness values respond differently but reproducibly to the same
environment.

ARES-1 C++ Simulation Core Development Guide | Page 61
11.6 Connection to the habitat model
- Simulation calculates pre-step DerivedTelemetry from the current physical state.
- Simulation calls CrewPhysiologyModel::updateAllCrew once.
- Simulation sums crew oxygen_consumption_g_min, co2_production_g_min, and heat_output_w.
- Simulation passes those totals into ResourceModel atmosphere/CO2/thermal updates.
- ResourceModel calculates the post-step habitat telemetry.
- CrewPhysiologyModel builds the post-step crew telemetry from the updated crew states.
- Simulation records one atomic TelemetrySample.
## SECTION 11 EXIT CHECK
Safe, hypoxic, high-CO2, thermal-stress, high-workload, recovery, and individual-sensitivity tests all pass.
You can explain every coefficient and identify it as NASA reference, derived physics, or ARES assumption.

ARES-1 C++ Simulation Core Development Guide | Page 62
## 12. Function Implementation Guide
Function ownership
The names and contracts below are the basis for Cursor-generated declarations. Cursor places each
declaration in the correct .hpp file and creates the matching empty .cpp definition. You review the
signature, then implement and test the TODO body.
12.1 MathUtils - clamp and normalized severity
Purpose: Provide bounded numeric helpers used by every subsystem.
Inputs: Value, minimum, maximum; or current value plus safe and critical thresholds.
Outputs / modified state: A bounded value or normalized 0-1 severity.
Implementation logic: Implement clamp first. Then implement separate high-side and low-side severity helpers
so temperature and pressure logic are readable.
Common mistakes: Using clamp to hide a physical failure; reversing safe and critical thresholds; integer
division.
Ownership: Cursor creates the declaration and matching empty .cpp definition. You implement and test the
TODO logic.
12.2 MathUtils - unit conversions
Purpose: Keep time, pressure, energy, and temperature conversions explicit.
Inputs: Seconds/minutes/hours, kPa/mmHg, C/K, W/kW, g/kg.
Outputs / modified state: Converted double.
Implementation logic: Create small single-purpose helpers and test round trips. Internal physics uses SI units;
JSON can use mission-friendly units.
Common mistakes: Mixing kW with kWh; using Celsius in ideal gas law; converting a value twice.
Ownership: Cursor creates the declaration and matching empty .cpp definition. You implement and test the
TODO logic.

ARES-1 C++ Simulation Core Development Guide | Page 63
12.3 ResourceModel - calculate environmental telemetry
Purpose: Compute pressure, gas fractions, inspired O2, CO2 partial pressure, and forecasts without mutating
state.
Inputs: ScenarioConfig and current SimulationState.
Outputs / modified state: Atmosphere portion of DerivedTelemetry.
Implementation logic: Convert masses to moles, calculate ideal-gas pressure and partial pressures, then
calculate current-rate forecasts. Return null/infinity for safe non-depleting rates.
Common mistakes: Storing pressure separately; using mass fraction as mole fraction; changing state inside a
derived calculation.
Ownership: Cursor creates the declaration and matching empty .cpp definition. You implement and test the
TODO logic.
12.4 ResourceModel - update mixed-gas atmosphere
Purpose: Apply leak loss and aggregated crew gas exchange for one timestep.
Inputs: State, aggregate crew O2 demand/CO2 output, timestep.
Outputs / modified state: Updated O2, inert gas, and CO2 masses.
Implementation logic: Calculate total leak mass, remove constituents by current composition, subtract crew O2
use, add crew CO2, and clamp inventories at zero while recording invalid states.
Common mistakes: Leaking only oxygen; applying per-hour rate as per-minute mass; dividing after total gas
reaches zero.
Ownership: Cursor creates the declaration and matching empty .cpp definition. You implement and test the
TODO logic.

ARES-1 C++ Simulation Core Development Guide | Page 64
12.5 ResourceModel - update CO2 scrubbing
Purpose: Remove CO2 and maintain the one-hour rolling average input.
Inputs: CO2 mass, rated scrubber capacity, efficiency, timestep.
Outputs / modified state: Updated CO2 mass and rolling sample buffer.
Implementation logic: Removal equals rated rate times efficiency but cannot exceed available CO2. Add one
sample per fixed timestep and expire samples older than one hour.
Common mistakes: Letting CO2 go negative; averaging fewer samples without tracking the actual window
duration.
Ownership: Cursor creates the declaration and matching empty .cpp definition. You implement and test the
TODO logic.
12.6 ResourceModel - update solar generation
Purpose: Calculate healthy and faulted Mars solar power.
Inputs: Distance, incidence, area, efficiency, atmosphere, dust, fault factor.
Outputs / modified state: Current generation values used by the power update.
Implementation logic: Calculate orbital flux, clamp cosine below zero, apply environment factors, then apply
fault factor only to actual generation.
Common mistakes: Applying the fault factor to the healthy reference; passing degrees directly to cos.
Ownership: Cursor creates the declaration and matching empty .cpp definition. You implement and test the
TODO logic.

ARES-1 C++ Simulation Core Development Guide | Page 65
12.7 ResourceModel - update battery energy
Purpose: Integrate charge/discharge energy and preserve energy accounting.
Inputs: Solar power, load power, battery energy/capacity, efficiencies, timestep.
Outputs / modified state: Updated battery energy; SOC remains derived.
Implementation logic: Use separate charge and discharge equations. Clamp physical storage to zero/capacity
but still record if a hard limit was crossed.
Common mistakes: Treating percent as energy; losing the timestep conversion; charging and discharging
simultaneously.
Ownership: Cursor creates the declaration and matching empty .cpp definition. You implement and test the
TODO logic.
12.8 ResourceModel - update thermal state
Purpose: Integrate cabin temperature from net heat.
Inputs: Crew heat, equipment/environment/heater heat, TCS capacity, thermal capacitance, timestep.
Outputs / modified state: Updated cabin temperature and thermal intermediate values.
Implementation logic: Calculate total heat input, actual rejected heat, net power, then integrate temperature
using J/C.
Common mistakes: Using kJ/C as J/C without conversion; assuming power shedding always improves
temperature.
Ownership: Cursor creates the declaration and matching empty .cpp definition. You implement and test the
TODO logic.

ARES-1 C++ Simulation Core Development Guide | Page 66
12.9 CrewPhysiologyModel - select metabolic baseline
Purpose: Map each CrewActivity to NASA reference O2, CO2, and heat rates.
Inputs: Crew activity, scenario metabolic table, permitted modifiers.
Outputs / modified state: Per-crew O2 consumption, CO2 production, and heat output.
Implementation logic: Select the explicit activity row, apply rationing/workload modifiers with documented
floors/ceilings, and write outputs into CrewMemberState.
Common mistakes: Interpolating activity from heart rate; applying rationing by directly changing habitat oxygen.
Ownership: Cursor creates the declaration and matching empty .cpp definition. You implement and test the
TODO logic.
12.10 CrewPhysiologyModel - calculate severity
Purpose: Convert current environment into transparent bounded stress inputs.
Inputs: Inspired O2, CO2 rolling average, pressure, temperature, humidity, crew sensitivity.
Outputs / modified state: Hypoxia, CO2, pressure, heat, and cold severity values.
Implementation logic: Use separately named normalized functions and sensitivity scaling. Preserve raw
environmental telemetry for alarms.
Common mistakes: Combining all environment conditions into one unexplainable risk score.
Ownership: Cursor creates the declaration and matching empty .cpp definition. You implement and test the
TODO logic.

ARES-1 C++ Simulation Core Development Guide | Page 67
12.11 CrewPhysiologyModel - update cumulative exposure
Purpose: Give the crew response memory across timesteps.
Inputs: Previous exposure states, current severities, recovery rates, timestep.
Outputs / modified state: Updated exposure and fatigue indices.
Implementation logic: Accumulate under stress and recover when safe. Bound only where the model definition
requires a maximum.
Common mistakes: Resetting exposure instantly; making recovery occur while the same stress remains critical.
Ownership: Cursor creates the declaration and matching empty .cpp definition. You implement and test the
TODO logic.
12.12 CrewPhysiologyModel - update vital signs
Purpose: Update HR, RR, SpO2, and core temperature deterministically.
Inputs: Crew config/state, severity values, environment, activity, timestep.
Outputs / modified state: Updated vital state.
Implementation logic: Apply bounded response functions and time constants. Use per-person
baselines/sensitivities. Store all coefficients in configuration.
Common mistakes: Claiming NASA calibration for ARES coefficients; using an unrestricted linear SpO2
formula; adding unseeded noise.
Ownership: Cursor creates the declaration and matching empty .cpp definition. You implement and test the
TODO logic.

ARES-1 C++ Simulation Core Development Guide | Page 68
12.13 CrewPhysiologyModel - update performance and health status
Purpose: Convert exposure and fatigue into action capability and alert state.
Inputs: Vitals, exposure indices, activity, configured thresholds.
Outputs / modified state: Cognitive/physical performance factors, health status, alarm flags.
Implementation logic: Calculate performance from named weighted terms, then select health status through
ordered threshold rules. Emit transition events only when status changes.
Common mistakes: Letting a soft score override a hard crew-incapacitation threshold; emitting duplicate alarm
events every step.
Ownership: Cursor creates the declaration and matching empty .cpp definition. You implement and test the
TODO logic.
12.14 CrewPhysiologyModel - aggregate crew loads
Purpose: Provide habitat models with total O2, CO2, and heat loads.
Inputs: Vector of CrewMemberState.
Outputs / modified state: Aggregate crew load object or totals.
Implementation logic: Sum only active crewmembers whose consumables come from the habitat. Handle EVA
suit isolation explicitly if modeled.
Common mistakes: Double-counting an EVA crewmember in habitat and suit systems.
Ownership: Cursor creates the declaration and matching empty .cpp definition. You implement and test the
TODO logic.

ARES-1 C++ Simulation Core Development Guide | Page 69
12.15 ResourceModel - update EVA and repair resources
Purpose: Advance EVA phases, consumables, rover energy, and repair progress.
Inputs: EVA state, assigned crew performance, timing config, rover state, timestep.
Outputs / modified state: Updated EVA phase/progress/resources and events.
Implementation logic: Advance only the active phase. Scale work progress by physical performance. Protect
ingress and reserve time. Abort when safe return is no longer possible.
Common mistakes: Restoring solar at EVA start; allowing repair progress during preparation or ingress.
Ownership: Cursor creates the declaration and matching empty .cpp definition. You implement and test the
TODO logic.
12.16 ActionExecutor - apply scheduled actions
Purpose: Start actions exactly once at their scheduled time.
Inputs: Plan, current time, mutable state, event list.
Outputs / modified state: Changed operational/model inputs and action-progress state.
Implementation logic: Find actions whose start time equals current time and have not already started. Route to
action-specific logic and emit one start event.
Common mistakes: Applying the same action every timestep; performing validation again inside every action.
Ownership: Cursor creates the declaration and matching empty .cpp definition. You implement and test the
TODO logic.

ARES-1 C++ Simulation Core Development Guide | Page 70
12.17 Validator - validate scenario data
Purpose: Reject invalid configuration before any simulation.
Inputs: ScenarioConfig.
Outputs / modified state: ValidationResult with all errors.
Implementation logic: Check positive volumes/capacities, valid thresholds, complete crew IDs, valid sensitivity
values, coherent communication/EVA windows, and source metadata.
Common mistakes: Silently replacing missing fields with defaults; accepting duplicate crew IDs.
Ownership: Cursor creates the declaration and matching empty .cpp definition. You implement and test the
TODO logic.
12.18 Validator - validate plan statically
Purpose: Reject unknown or impossible plans before the physics loop.
Inputs: Plan and ScenarioConfig.
Outputs / modified state: ValidationResult.
Implementation logic: Check action types, required fields, ranges, assets, crew assignments, timing, EVA
qualifications, and window constraints. Collect useful errors.
Common mistakes: Treating resource failure during the run as a parse rejection; trusting planner
constraints_checked.
Ownership: Cursor creates the declaration and matching empty .cpp definition. You implement and test the
TODO logic.

ARES-1 C++ Simulation Core Development Guide | Page 71
12.19 Simulation - run baseline
Purpose: Prove the unmitigated scenario outcome from equations.
Inputs: ScenarioConfig and no recovery actions.
Outputs / modified state: SimulationResult and full telemetry history.
Implementation logic: Copy the initial state, activate the fault, iterate the locked timestep order, record metrics,
and stop on failure or max duration.
Common mistakes: Hardcoding the baseline to fail; using different equations than the plan run.
Ownership: Cursor creates the declaration and matching empty .cpp definition. You implement and test the
TODO logic.
12.20 Simulation - run with plan
Purpose: Run the same scenario with the validated action sequence.
Inputs: ScenarioConfig and Plan.
Outputs / modified state: SimulationResult and full telemetry history.
Implementation logic: Use the identical timestep and failure logic as baseline. The only difference is scheduled
action execution.
Common mistakes: Changing constants to make the plan succeed; skipping failed actions.
Ownership: Cursor creates the declaration and matching empty .cpp definition. You implement and test the
TODO logic.

ARES-1 C++ Simulation Core Development Guide | Page 72
12.21 Simulation - evaluate mission state
Purpose: Select warning, critical, failure, or stabilized from complete telemetry.
Inputs: Post-step DerivedTelemetry, crew statuses, action state, stabilization timer.
Outputs / modified state: Mission status, constraint list, events, termination decision.
Implementation logic: Check hard constraints first, then stabilization criteria. Require the configured hold time.
Crew incapacity and EVA abort rules must be explicit.
Common mistakes: Using risk score as the authority; declaring stabilized immediately after one safe sample.
Ownership: Cursor creates the declaration and matching empty .cpp definition. You implement and test the
TODO logic.
12.22 Simulation - update extrema and metrics
Purpose: Track the values required by the final report.
Inputs: Current telemetry and previous metrics.
Outputs / modified state: Updated min/max values and timestamps.
Implementation logic: Track minimum inspired O2, pressure, SOC, temperature margin, EVA return margin,
maximum CO2 average, worst crew SpO2, maximum HR/RR, and time to stabilization.
Common mistakes: Calculating extrema only at the end; mixing baseline and plan histories.
Ownership: Cursor creates the declaration and matching empty .cpp definition. You implement and test the
TODO logic.

ARES-1 C++ Simulation Core Development Guide | Page 73
12.23 JsonIO - load strict scenario and plan
Purpose: Create typed inputs without silent assumptions.
Inputs: JSON files.
Outputs / modified state: ScenarioConfig and Plan or parse errors.
Implementation logic: Validate presence/type of fields, map strings to enums, preserve source classifications,
and reject unknown action names.
Common mistakes: Defaulting a missing critical number to zero; accepting NaN or infinite values.
Ownership: Cursor creates the declaration and matching empty .cpp definition. You implement and test the
TODO logic.
12.24 JsonIO - write deterministic result
Purpose: Produce stable JSON for FastAPI, tests, and Open MCT.
Inputs: SimulationResult and telemetry history.
Outputs / modified state: Output file with stable schema and field order.
Implementation logic: Serialize physical state, derived telemetry, crew array, events, metrics, failures, and
source/assumption metadata needed for the report.
Common mistakes: Writing planner-claimed outcome; omitting crew alarms or failure reasons.
Ownership: Cursor creates the declaration and matching empty .cpp definition. You implement and test the
TODO logic.

ARES-1 C++ Simulation Core Development Guide | Page 74
## 13. Recovery Action Behavior
ActionRevised behavior
reduce_power_loadSelects discretionary load groups and reduction amount. It may
reduce equipment heat but must not silently disable protected life
support. TCS shedding can worsen thermal safety.
isolate_moduleChanges hatch/module state, transfers crew if required, reduces
connected volume, and multiplies the remaining mixed-gas leak.
It does not automatically stop the leak.
oxygen_rationingChanges crew activity/metabolic mode and performance. It
modifies future O2 use, CO2 generation, heat, fatigue, and
action availability; it does not add oxygen.
repair_solar_arrayAssigns qualified crew, starts EVA preparation, advances
phases, consumes EVA/rover resources, scales work by
physical performance, and restores the solar fault factor only on
completion.
delay_rover_useReserves rover availability and energy until a defined time. It can
delay the repair and create action conflicts.
send_emergency_packetRequires an open communication window, consumes configured
communications power for a duration, and marks completion. It
does not directly improve physical survival resources.
13.1 New crew-related action fields
repair_solar_array should identify assigned_crew_ids or a single eva_crew_id.
oxygen_rationing may target all crew or a defined list.
isolate_module must confirm no crewmember remains trapped in the isolated volume.
Action progress should store start/completion/abort state instead of reusing the original planner object as
mutable state.

ARES-1 C++ Simulation Core Development Guide | Page 75
- Validation, Failure, and Stabilization Rules
14.1 Rejection versus failure
OutcomeMeaning
REJECTEDThe plan or scenario is invalid before a valid physical run can
occur: unknown action, missing field, impossible timing,
unavailable asset, unqualified crew, invalid window.
FAILUREA valid run crosses a hard physical, operational, or crew
safety constraint before stabilization.
STABILIZEDAll required post-fault conditions remain safe for the
configured hold time.
14.2 Hard mission failure candidates
Inspired oxygen or total pressure reaches the configured hard limit.
CO2 rolling average reaches the configured hard limit.
Battery energy reaches zero or the mission-defined failure reserve condition.
Cabin temperature crosses a configured critical limit.
EVA safe-return margin becomes negative while a crewmember is outside.
Required crew become incapacitated with no valid recovery path.
All crew become incapacitated.
A critical required repair becomes impossible before the remaining resource deadline.

ARES-1 C++ Simulation Core Development Guide | Page 76
14.3 Crew alarms and action aborts
ConditionRecommended response
Soft vital warningEmit alarm, continue run, and adjust performance if
configured.
Sustained impairmentPrevent new complex/EVA action assignment; extend current
work duration through performance factor.
Critical EVA vital or negative safe-return marginAbort work and transition to ingress if physically possible.
Crew incapacitation in habitatMark person unavailable; mission may continue only if
scenario criteria and staffing allow.
Crew incapacitation during EVAApply explicit rescue/failure rule; do not resolve
automatically.
14.4 Stabilization conditions
Leak severity is below the configured stabilized threshold.
Inspired O2, pressure, CO2, battery reserve, and temperature are safe.
Power trend is sustainable or solar repair is complete.
No EVA crew is outside without a non-negative safe-return margin.
No required crew is in a critical or incapacitated state.
All conditions remain satisfied for the full stabilization hold duration.

ARES-1 C++ Simulation Core Development Guide | Page 77
- JSON and Frontend Telemetry Contract
15.1 Telemetry snapshot shape
## {
## "simulation_time_min": 126,
## "habitat": {
## "cabin_pressure_kpa": 64.1,
## "inspired_oxygen_mmhg": 139.5,
## "co2_one_hour_avg_mmhg": 2.4,
## "oxygen_hours_remaining": 12.8,
## "battery_soc_percent": 32.0,
## "solar_generation_percent": 55.0,
## "power_margin_kw": -1.3,
## "cabin_temperature_c": 23.4,
## "temperature_margin_c": 8.4,
## "eva_safe_return_margin_min": 264,
"mission_status": "CRITICAL"
## },
## "crew": [
## {
## "crew_id": "crew_01",
"display_name": "Commander",
"activity": "NOMINAL_WORK",
## "heart_rate_bpm": 96,
## "respiratory_rate_bpm": 21,
## "spo2_percent": 93.8,
## "core_temperature_c": 37.1,
## "fatigue_percent": 28,
## "cognitive_performance_percent": 91,
## "physical_performance_percent": 88,
"health_status": "ELEVATED_STRESS",
"alarms": ["HYPOXIA_TREND"]
## }
## ],
## "events": []
## }
The numerical crew values shown above are schema examples only, not approved calibration values.

ARES-1 C++ Simulation Core Development Guide | Page 78
15.2 Live replay behavior
15.The C++ simulator writes or emits authoritative one-minute snapshots.
16.FastAPI reads the snapshot stream or completed telemetry array.
17.The demo replay scheduler sends snapshots by WebSocket or SSE at the selected wall-clock speed.
18.Open MCT plots habitat and crew telemetry using simulation_time_min as mission time.
19.React/Three.js may animate between snapshots, but the displayed numeric value should remain the latest
authoritative sample unless explicitly labeled interpolated.
15.3 Frontend panels
PanelRequired content
Habitat atmospherePressure, inspired O2, CO2 average, leak rate, remaining-
time forecasts.
Power/thermalSolar, load, power margin, battery SOC/reserve, cabin
temperature, thermal margin.
Crew overviewStatus cards for all crew with vitals, activity, performance,
and alarms.
Crew detailHR/RR/SpO2/core-temperature plots and environmental
overlay.
EVA operationsAssigned crew, phase, suit time, safe-return margin, repair
progress, rover state.
TimelineFaults, actions, crew alarm transitions, repairs,
communications, failure/stabilization.

ARES-1 C++ Simulation Core Development Guide | Page 79
## 16. Recommended Coding Order
StepTaskReason
1Run Cursor scaffold pass 1.Creates the project shell and data-header
placeholders.
2Build the empty project.Proves CMake and dependency wiring.
3Write Enums.hpp and
PhysicalConstants.hpp.
Establishes vocabulary and units.
4Write CrewMember.hpp.Defines individual crew state before
habitat state.
5Write ScenarioConfig.hpp.Defines immutable inputs and all source
classes.
6Write SimulationState.hpp and
DerivedTelemetry.hpp.
Separates physical state from calculated
outputs.
7Write action, plan, telemetry, result, and
validation data headers.
Locks the data contracts.
8Run Cursor scaffold pass 2 and review
every generated signature.
Creates functional declarations and
matching TODO definitions.
9Implement and test MathUtils, then strict
scenario/plan parsing.
Starts with isolated logic and rejects bad
input early.
10Implement atmosphere and derived
pressure/O2/CO2.
First physical subsystem; function shells
already exist.

ARES-1 C++ Simulation Core Development Guide | Page 80
- Recommended coding order - continued
StepTaskReason
11Implement crew metabolic baselines.Supplies habitat O2/CO2/heat loads.
12Implement crew severity, exposure, vitals,
and performance.
Adds individual live telemetry.
13Implement solar and battery.Builds the power deadline.
14Implement thermal model.Connects crew/equipment heat and load
shedding.
15Implement EVA phases and repair
progress.
Builds the main recovery operation.
16Implement ActionExecutor one action at a
time.
Controlled state mutations.
17Implement Validator.Separates rejection from run failure.
18Implement baseline Simulation.Must fail because of equations, not a
hardcoded result.
19Implement plan Simulation.Uses the same physics plus actions.
20Implement result/telemetry serialization.Completes backend/frontend contract.

ARES-1 C++ Simulation Core Development Guide | Page 81
- Recommended coding order - final
StepTaskReason
21Add deterministic unit tests.Verifies each equation independently.
22Add integration tests for baseline,
stabilized, rejected, and crew-critical
cases.
Verifies full control flow.
23Calibrate ARES scenario assumptions.Makes baseline failure and recovery
emerge naturally.
24Connect FastAPI replay and frontend
panels.
Visualizes authoritative C++ telemetry.
Coding discipline
Do not begin frontend animation until the C++ output produces stable, explainable habitat and crew
telemetry for the same input every run.

ARES-1 C++ Simulation Core Development Guide | Page 82
## 17. Deterministic Test Plan
17.1 Atmosphere and resource tests
Ideal-gas pressure matches a hand calculation.
No leak and no crew load preserve gas inventory.
Mixed-gas leak removes constituents proportionally.
Module isolation reduces leak factor and connected volume.
CO2 removal cannot exceed available CO2.
One-hour CO2 average uses the correct window.
Solar generation is zero with no illumination and scales with the fault factor.
Battery energy conservation and SOC are correct.
Zero net heat keeps cabin temperature constant.
17.2 Crew physiology tests
Nominal environment and activity converge toward individual baseline vitals.
Lower inspired O2 never improves hypoxia severity or SpO2 response.
Higher CO2 never reduces CO2 severity.
Higher activity increases metabolic O2, CO2, and heat according to the selected baseline.
Exposure accumulates under stress and recovers under safe conditions.
Same input and seed produce identical vital telemetry.
Performance factors remain bounded and decline monotonically with configured stress inputs.
Health transition events occur once per transition, not every timestep.

ARES-1 C++ Simulation Core Development Guide | Page 83
17.3 Actions, validation, and full-run tests
Unknown actions and duplicate crew IDs are rejected.
An unqualified crew member cannot be assigned to EVA.
Isolation fails if a crew member would be trapped.
Repair does not progress before EVA work phase.
Repair progress is slower when physical performance is lower.
Solar output changes only after successful repair completion.
Packet outside a communication window is rejected or fails according to the defined rule.
Baseline and plan runs use identical physics and initial state.
A valid plan can still fail dynamically.
Stabilization requires the full hold time.
All crew incapacitated produces a deterministic mission failure.
Result JSON includes full failure reasons and crew telemetry.
Calibration test rule
Do not tune a coefficient solely to make the demo succeed. Tune it against an explicit scenario
requirement, source, or documented ARES design assumption, then rerun all tests.

ARES-1 C++ Simulation Core Development Guide | Page 84
## 18. Cursor Scaffold Prompt
Use this as a two-pass prompt. Pass 1 creates the project and data-header placeholders. After you declare
the data model, Pass 2 creates function declarations and matching empty definitions. Never ask Cursor to
implement the TODO logic.
## PASS 1 - PROJECT AND DATA-HEADER SCAFFOLD
Create the sim_core C++17 CMake project for ARES-1 using the exact file structure from Section 4.
- Create directories, filenames, CMake wiring, the nlohmann/json dependency, and the tests target.
- Data-only headers must contain #pragma once and a TODO for the developer to declare the enums, constants, structs, and
fields.
- Do not invent or add any data type, field, constant, threshold, coefficient, default, or scenario value.
- Source files may contain only their matching include and a TODO until Pass 2.
- The scaffold must compile as far as possible without inventing the missing data model.
After Pass 1, stop. The developer will define and compile all data types.
## PASS 2 - FUNCTION INTERFACES AND EMPTY DEFINITIONS
After the developer confirms that all data-only headers compile:
- Use Section 12 implementation cards and the existing data types to create the functional class declarations, constructors,
and function signatures in MathUtils.hpp, ResourceModel.hpp, CrewPhysiologyModel.hpp, ActionExecutor.hpp,
Validator.hpp, Simulation.hpp, and JsonIO.hpp.
- Create each matching out-of-class function definition in its .cpp file.
- Every .cpp file must include its matching header.
- Every function body must contain a clear TODO describing the implementation card number.
- Use only neutral compile-safe placeholder returns when a non-void function requires one. Do not compute or guess a
meaningful result.
- Create the thin main.cpp CLI function shell and TODO call sequence, but do not implement argument parsing, file I/O,
simulation execution, or error behavior.
- Create test function/case shells, but do not add assertions, fixtures, numerical expectations, or test logic.
## NEVER GENERATE:
- Enums, data structs, member fields, constants, thresholds, coefficients, defaults, or scenario values.
- Equations, algorithms, branches, loops, validation rules, action effects, physiology behavior, telemetry calculations, JSON
behavior, or result metrics.
- Hidden helper functions that are not explicitly listed in the guide.
The completed boilerplate must compile, and all executable behavior must remain TODO for the developer.
After generation
Review every generated signature and definition before implementing logic. Delete any data field, tuning
value, helper algorithm, branch, or meaningful placeholder behavior Cursor added beyond the prompt.

ARES-1 C++ Simulation Core Development Guide | Page 85
- Build and Run Commands
19.1 Initial empty scaffold
cd sim_core
cmake -S . -B build -G Ninja
cmake --build build
## .\build\sim_core.exe
19.2 After CLI implementation
## .\build\sim_core.exe ^
## --scenario ..\scenarios\mars_hab_atmosphere_solar_failure.json ^
## --plan ..\plans\sample_plan.json ^
## --output ..\results\sim_result.json
19.3 Run tests
cmake --build build
ctest --test-dir build --output-on-failure
If Ninja is unavailable, omit -G Ninja and use the default CMake generator.

ARES-1 C++ Simulation Core Development Guide | Page 86
- Final Self-Check
20.1 Can you follow the guide without guessing?
For every data structure, can you identify the exact header where it is declared?
For every implementation step, can you identify the exact .cpp file, function TODO, input fields, output fields,
and test file?
Did you stop at every section exit check and compile before moving forward?
Did Cursor generate only declarations, matching empty definitions, includes, and neutral placeholders?
20.2 Ownership checks
Did you personally write every data declaration and every function body?
Did you review every Cursor-generated function declaration and matching definition?
Can you identify which fields are configuration, mutable state, derived telemetry, or output history?
Can you explain every unit and source classification?
Are there any hidden tuning values in .cpp files?
20.3 Physics and crew checks
Can you derive cabin pressure, inspired O2, CO2, solar power, battery SOC, and temperature updates?
Can you explain how each crew activity changes O2, CO2, and heat?
Can you explain every crew vital-response coefficient and why it is an ARES assumption?
Does low O2/elevated CO2/thermal stress affect vitals and performance monotonically and deterministically?
Can a crew alarm change an action without directly changing physical resources?
20.4 Authority and demo checks
Does baseline failure emerge from the same equations used by the plan run?
Can a planner-generated valid plan still fail?
Can an invented action or impossible crew assignment be rejected?
Does the frontend contract contain only complete authoritative snapshots?
Can the same inputs reproduce exactly the same habitat and crew telemetry?
Is survival_probability absent until Monte Carlo exists?
Final rule
If the guide tells you a concept but not the file, function, action, and verification step, treat that as a guide
defect and correct it before coding. You should never need to guess where a required simulator
responsibility belongs.
Source basis
This guide is derived from the ARES-1 NASA-Calibrated Telemetry and Simulation Function Specification
and supersedes both the simplified C++ guide and the previous v2 crew-vitals guide. Environmental limits
and metabolic baselines are NASA-calibrated; the individual vital-response coefficients remain explicit ARES
assumptions pending separate physiological calibration.