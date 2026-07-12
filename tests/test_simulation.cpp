#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>
#include <limits>
#include <string>
#include <vector>
#include "ActionExecutor.hpp"
#include "Enums.hpp"
#include "Plan.hpp"
#include "ScenarioConfig.hpp"
#include "Simulation.hpp"
#include "SimulationState.hpp"

using Catch::Approx;

namespace {

CrewMemberConfig makeCrew(const string& id, bool eva_qualified){
    CrewMemberConfig crew{};
    crew.crew_id = id;
    crew.display_name = id;
    crew.assigned_role = "Specialist";
    crew.body_mass_kg = 70.0;
    crew.baseline_heart_rate_bpm = 65.0;
    crew.baseline_respiratory_rate_bpm = 14.0;
    crew.baseline_spo2_percent = 98.0;
    crew.baseline_core_temperature_c = 36.8;
    crew.fitness_factor = 1.0;
    crew.hypoxia_sensitivity = 1.0;
    crew.co2_sensitivity = 1.0;
    crew.thermal_sensitivity = 1.0;
    crew.fatigue_recovery_factor = 1.0;
    crew.eva_qualified = eva_qualified;
    crew.initial_activity = CrewActivity::NominalWork;
    crew.initial_location_module = "core";
    crew.initial_eva_status = EVAStatus::Idle;
    crew.initial_oxygen_rationing_active = false;
    return crew;
}

ActivityMetabolicProfile makeProfile(CrewActivity activity){
    ActivityMetabolicProfile profile{};
    profile.activity = activity;
    profile.oxygen_g_min = 0.8;
    profile.co2_g_min = 0.9;
    profile.heat_w = 120.0;
    profile.activity_load = 0.5;
    return profile;
}

ScenarioConfig makeSimConfig(){
    ScenarioConfig config{};
    config.scenario_id = "ares_sim";
    config.name = "Sim Scenario";
    config.time_step_s = 60;
    config.maximum_duration_min = 60;
    config.stabilization_hold_min = 5;

    config.habitat.initial_habitable_volume_m3 = 100.0;
    config.habitat.isolated_habitable_volume_m3 = 60.0;
    config.habitat.nominal_temperature_c = 22.0;
    config.habitat.initial_relative_humidity_percent = 40.0;
    config.habitat.effective_thermal_capacitance_kj_c = 500.0;

    config.atmosphere.initial_oxygen_mass_kg = 20.0;
    config.atmosphere.initial_inert_gas_mass_kg = 40.0;
    config.atmosphere.initial_co2_mass_kg = 0.2;
    config.atmosphere.scrubber_capacity_g_min = 5.0;
    config.atmosphere.initial_scrubber_efficiency = 1.0;
    config.atmosphere.pressure_warning_low_kpa = 70.0;
    config.atmosphere.pressure_failure_low_kpa = 50.0;
    config.atmosphere.pressure_high_limit_kpa = 110.0;
    config.atmosphere.inspired_o2_nominal_mmhg = 150.0;
    config.atmosphere.inspired_o2_warning_mmhg = 120.0;
    config.atmosphere.inspired_o2_failure_mmhg = 90.0;
    config.atmosphere.co2_one_hour_limit_mmhg = 8.0;
    config.atmosphere.minimum_inert_fraction = 0.2;

    config.power.initial_battery_energy_kwh = 90.0;
    config.power.battery_capacity_kwh = 100.0;
    config.power.battery_reserve_percent = 10.0;
    config.power.charge_efficiency = 0.9;
    config.power.discharge_efficiency = 0.9;
    config.power.essential_load_kw = 0.5;
    config.power.discretionary_load_kw = 0.2;
    config.power.thermal_control_load_kw = 0.2;
    config.power.eva_support_load_kw = 0.0;
    config.power.communications_load_kw = 0.0;

    config.solar.array_area_m2 = 120.0;
    config.solar.cell_efficiency = 0.35;
    config.solar.mars_sun_distance_au = 1.5;
    config.solar.initial_incidence_angle_deg = 0.0;
    config.solar.initial_atmospheric_transmission = 1.0;
    config.solar.initial_deposited_dust_factor = 1.0;

    config.thermal.initial_equipment_heat_w = 100.0;
    config.thermal.initial_environmental_heat_w = 0.0;
    config.thermal.initial_heater_heat_w = 0.0;
    config.thermal.tcs_rejection_capacity_w = 3000.0;
    config.thermal.comfort_low_c = 18.0;
    config.thermal.comfort_high_c = 27.0;
    config.thermal.critical_low_c = 10.0;
    config.thermal.critical_high_c = 35.0;
    config.thermal.humidity_low_percent = 20.0;
    config.thermal.humidity_high_percent = 70.0;

    config.eva.available = true;
    config.eva.preparation_min = 5;
    config.eva.egress_min = 5;
    config.eva.repair_work_min = 10;
    config.eva.ingress_min = 5;
    config.eva.reserve_min = 5;
    config.eva.maximum_duration_min = 360;
    config.eva.rover_required = false;
    config.eva.rover_minimum_reserve_percent = 20.0;

    config.communications.windows = {{0, 1000}};
    config.communications.transmission_duration_min = 5;
    config.communications.transmission_power_kw = 0.1;

    config.fault.failure_type = "none";
    config.fault.leak_module = "lab";
    config.fault.total_gas_leak_kg_hr = 0.0;
    config.fault.isolation_leak_multiplier = 0.4;
    config.fault.solar_fault_factor = 1.0;
    config.fault.repaired_solar_fault_factor = 1.0;
    config.fault.stabilized_leak_kg_hr = 0.1;

    config.vital_response.activity_profiles = {
        makeProfile(CrewActivity::NominalWork),
        makeProfile(CrewActivity::Resting),
        makeProfile(CrewActivity::EVAPrep),
        makeProfile(CrewActivity::EVATransit),
        makeProfile(CrewActivity::EVAWork),
        makeProfile(CrewActivity::Recovery),
        makeProfile(CrewActivity::Incapacitated),
    };
    config.vital_response.spo2_warning_percent = 94.0;
    config.vital_response.spo2_critical_percent = 88.0;
    config.vital_response.heart_rate_warning_bpm = 120.0;
    config.vital_response.respiratory_rate_warning_bpm = 30.0;
    config.vital_response.core_temp_low_c = 35.0;
    config.vital_response.core_temp_high_c = 38.5;
    config.vital_response.fatigue_warning_fraction = 0.7;
    config.vital_response.performance_abort_fraction = 0.3;
    config.vital_response.hypoxia_accumulation_rate = 0.0;
    config.vital_response.co2_accumulation_rate = 0.0;
    config.vital_response.thermal_accumulation_rate = 0.0;
    config.vital_response.hypoxia_recovery_rate = 0.1;
    config.vital_response.co2_recovery_rate = 0.1;
    config.vital_response.thermal_recovery_rate = 0.1;
    config.vital_response.fatigue_work_rate = 0.0;
    config.vital_response.fatigue_eva_rate = 0.0;
    config.vital_response.fatigue_recovery_rate = 0.1;
    config.vital_response.hr_activity_gain = 0.0;
    config.vital_response.hr_hypoxia_gain = 0.0;
    config.vital_response.hr_co2_gain = 0.0;
    config.vital_response.hr_thermal_gain = 0.0;
    config.vital_response.hr_fatigue_gain = 0.0;
    config.vital_response.hr_min_bpm = 40.0;
    config.vital_response.hr_max_bpm = 180.0;
    config.vital_response.rr_activity_gain = 0.0;
    config.vital_response.rr_hypoxia_gain = 0.0;
    config.vital_response.rr_co2_gain = 0.0;
    config.vital_response.rr_thermal_gain = 0.0;
    config.vital_response.rr_min_bpm = 8.0;
    config.vital_response.rr_max_bpm = 40.0;
    config.vital_response.spo2_hypoxia_gain = 0.0;
    config.vital_response.spo2_pressure_gain = 0.0;
    config.vital_response.spo2_activity_gain = 0.0;
    config.vital_response.spo2_exposure_gain = 0.0;
    config.vital_response.spo2_min_percent = 70.0;
    config.vital_response.spo2_max_percent = 100.0;
    config.vital_response.core_temp_environment_gain = 0.0;
    config.vital_response.core_temp_activity_gain = 0.0;
    config.vital_response.core_temp_time_constant_min = 30.0;
    config.vital_response.core_temp_min_c = 34.0;
    config.vital_response.core_temp_max_c = 40.0;
    config.vital_response.cognitive_hypoxia_weight = 0.25;
    config.vital_response.cognitive_co2_weight = 0.25;
    config.vital_response.cognitive_thermal_weight = 0.25;
    config.vital_response.cognitive_fatigue_weight = 0.25;
    config.vital_response.physical_hypoxia_weight = 0.25;
    config.vital_response.physical_co2_weight = 0.25;
    config.vital_response.physical_thermal_weight = 0.25;
    config.vital_response.physical_fatigue_weight = 0.25;

    config.crew_roster = {
        makeCrew("crew_01", true),
        makeCrew("crew_02", true),
    };
    return config;
}

DerivedTelemetry makeSafeTelemetry(){
    DerivedTelemetry telemetry{};
    telemetry.atmosphere.inspired_oxygen_mmhg = 150.0;
    telemetry.atmosphere.cabin_pressure_kpa = 80.0;
    telemetry.atmosphere.co2_one_hour_avg_mmhg = 1.0;
    telemetry.atmosphere.oxygen_hours_remaining = 100.0;
    telemetry.atmosphere.time_to_pressure_limit_hr = 100.0;
    telemetry.atmosphere.time_to_co2_limit_hr = 100.0;
    telemetry.power.battery_soc_percent = 80.0;
    telemetry.power.power_margin_kw = 1.0;
    telemetry.power.battery_hours_to_reserve = std::numeric_limits<double>::infinity();
    telemetry.thermal.temperature_margin_c = 10.0;
    telemetry.eva.eva_safe_return_margin_min = 100.0;
    return telemetry;
}

SimulationState makeSafeState(const ScenarioConfig& config){
    SimulationState state{};
    state.time_min = 0;
    state.habitable_volume_m3 = config.habitat.initial_habitable_volume_m3;
    state.cabin_temperature_c = 22.0;
    state.oxygen_mass_kg = config.atmosphere.initial_oxygen_mass_kg;
    state.inert_gas_mass_kg = config.atmosphere.initial_inert_gas_mass_kg;
    state.co2_mass_kg = config.atmosphere.initial_co2_mass_kg;
    state.total_gas_leak_kg_hr = 0.0;
    state.leak_fault_factor = 1.0;
    state.battery_energy_kwh = 80.0;
    state.solar_fault_factor = 1.0;
    state.solar_repair_progress = 1.0;
    state.crew = {
        {},
        {},
    };
    state.crew[0].crew_id = "crew_01";
    state.crew[0].health_status = CrewHealthStatus::Nominal;
    state.crew[0].eva_status = EVAStatus::Idle;
    state.crew[0].physical_performance_factor = 1.0;
    state.crew[1].crew_id = "crew_02";
    state.crew[1].health_status = CrewHealthStatus::Nominal;
    state.crew[1].eva_status = EVAStatus::Idle;
    state.crew[1].physical_performance_factor = 1.0;
    return state;
}

}

TEST_CASE("simulation: rejected plan never runs physics", "[simulation][rejection]"){
    Simulation sim;
    ScenarioConfig config = makeSimConfig();
    Plan plan{};
    plan.plan_id = "bad";
    Action action{};
    action.type = ActionType::Unknown;
    action.type_raw = "teleport";
    action.start_min = 0;
    plan.actions.push_back(action);

    SimulationResult result = sim.runWithPlan(config, plan);
    REQUIRE(result.outcome == OutcomeStatus::Rejected);
    REQUIRE_FALSE(result.valid_plan);
    REQUIRE(result.telemetry_history.empty());
    REQUIRE_FALSE(result.failure_reasons.empty());
}

TEST_CASE("simulation: baseline fails from hard atmosphere constraint", "[simulation][failure]"){
    Simulation sim;
    ScenarioConfig config = makeSimConfig();
    config.fault.total_gas_leak_kg_hr = 80.0;
    config.atmosphere.initial_oxygen_mass_kg = 2.0;
    config.atmosphere.initial_inert_gas_mass_kg = 4.0;
    config.maximum_duration_min = 30;
    config.fault.solar_fault_factor = 1.0;

    SimulationResult result = sim.runBaseline(config);
    REQUIRE(result.outcome == OutcomeStatus::Failure);
    REQUIRE(result.valid_plan);
    REQUIRE_FALSE(result.failure_reasons.empty());
    REQUIRE_FALSE(result.telemetry_history.empty());
}

TEST_CASE("simulation: valid plan can still fail dynamically", "[simulation][failure]"){
    Simulation sim;
    ScenarioConfig config = makeSimConfig();
    config.fault.total_gas_leak_kg_hr = 80.0;
    config.atmosphere.initial_oxygen_mass_kg = 2.0;
    config.atmosphere.initial_inert_gas_mass_kg = 4.0;
    config.maximum_duration_min = 30;

    Plan plan{};
    plan.plan_id = "late_packet";
    Action action{};
    action.type = ActionType::SendEmergencyPacket;
    action.type_raw = "send_emergency_packet";
    action.start_min = 0;
    plan.actions.push_back(action);

    SimulationResult result = sim.runWithPlan(config, plan);
    REQUIRE(result.outcome == OutcomeStatus::Failure);
    REQUIRE(result.valid_plan);
    REQUIRE_FALSE(result.failure_reasons.empty());
}

TEST_CASE("simulation: stabilization requires full hold time", "[simulation][stabilized]"){
    Simulation sim;
    ScenarioConfig config = makeSimConfig();
    config.stabilization_hold_min = 5;

    SimulationState state = makeSafeState(config);
    MissionTelemetry mission = {};
    mission.mission_status = MissionStatus::Nominal;
    mission.stabilization_elapsed_min = 0.0;
    DerivedTelemetry telemetry = makeSafeTelemetry();
    vector<TimelineEvent> events;

    for(int i = 0; i < 4; ++i){
        MissionEvaluation evaluation = sim.evaluateMissionState(
            state, config, telemetry, mission, events, 1.0);
        REQUIRE_FALSE(evaluation.terminate);
        REQUIRE(mission.stabilization_elapsed_min == Approx(static_cast<double>(i + 1)));
    }

    MissionEvaluation final_eval = sim.evaluateMissionState(
        state, config, telemetry, mission, events, 1.0);
    REQUIRE(final_eval.terminate);
    REQUIRE(final_eval.outcome == OutcomeStatus::Stabilized);
    REQUIRE(mission.mission_status == MissionStatus::Stabilized);
    REQUIRE(mission.stabilization_elapsed_min == Approx(5.0));
}

TEST_CASE("simulation: hold timer resets when conditions break", "[simulation][stabilized]"){
    Simulation sim;
    ScenarioConfig config = makeSimConfig();
    config.stabilization_hold_min = 5;

    SimulationState state = makeSafeState(config);
    MissionTelemetry mission{};
    DerivedTelemetry telemetry = makeSafeTelemetry();
    vector<TimelineEvent> events;

    sim.evaluateMissionState(state, config, telemetry, mission, events, 1.0);
    sim.evaluateMissionState(state, config, telemetry, mission, events, 1.0);
    REQUIRE(mission.stabilization_elapsed_min == Approx(2.0));

    state.total_gas_leak_kg_hr = 5.0;
    MissionEvaluation broken = sim.evaluateMissionState(
        state, config, telemetry, mission, events, 1.0);
    REQUIRE_FALSE(broken.terminate);
    REQUIRE(mission.stabilization_elapsed_min == Approx(0.0));
}

TEST_CASE("simulation: all crew incapacitated is mission failure", "[simulation][failure][crew]"){
    Simulation sim;
    ScenarioConfig config = makeSimConfig();
    SimulationState state = makeSafeState(config);
    state.crew[0].health_status = CrewHealthStatus::Incapacitated;
    state.crew[1].health_status = CrewHealthStatus::Incapacitated;

    MissionTelemetry mission{};
    DerivedTelemetry telemetry = makeSafeTelemetry();
    vector<TimelineEvent> events;

    MissionEvaluation evaluation = sim.evaluateMissionState(
        state, config, telemetry, mission, events, 1.0);
    REQUIRE(evaluation.terminate);
    REQUIRE(evaluation.outcome == OutcomeStatus::Failure);
    REQUIRE(mission.mission_status == MissionStatus::Failure);

    bool found = false;
    for(const string& reason : mission.violated_constraints){
        if(reason == "all_crew_incapacitated"){
            found = true;
        }
    }
    REQUIRE(found);
}

TEST_CASE("simulation: EVA incapacitation is mission failure", "[simulation][failure][crew]"){
    Simulation sim;
    ScenarioConfig config = makeSimConfig();
    SimulationState state = makeSafeState(config);
    state.crew[0].health_status = CrewHealthStatus::Incapacitated;
    state.crew[0].eva_status = EVAStatus::Working;

    MissionTelemetry mission{};
    DerivedTelemetry telemetry = makeSafeTelemetry();
    vector<TimelineEvent> events;

    MissionEvaluation evaluation = sim.evaluateMissionState(
        state, config, telemetry, mission, events, 1.0);
    REQUIRE(evaluation.terminate);
    REQUIRE(evaluation.outcome == OutcomeStatus::Failure);

    bool found = false;
    for(const string& reason : mission.violated_constraints){
        if(reason.find("eva_crew_incapacitated") != string::npos){
            found = true;
        }
    }
    REQUIRE(found);
}

TEST_CASE("simulation: safe baseline can stabilize", "[simulation][stabilized]"){
    Simulation sim;
    ScenarioConfig config = makeSimConfig();
    config.stabilization_hold_min = 3;
    config.maximum_duration_min = 20;
    config.fault.total_gas_leak_kg_hr = 0.0;
    config.fault.solar_fault_factor = 1.0;
    config.fault.stabilized_leak_kg_hr = 0.1;

    SimulationResult result = sim.runBaseline(config);
    REQUIRE(result.outcome == OutcomeStatus::Stabilized);
    REQUIRE(result.valid_plan);
    REQUIRE(result.metrics.time_to_stabilization_hr >= 0.0);
    REQUIRE(result.failure_reasons.empty());
}

TEST_CASE("actions: impaired crew cannot start EVA repair", "[actions][crew]"){
    ActionExecutor exec;
    ScenarioConfig config = makeSimConfig();
    SimulationState state{};
    state.time_min = 0;
    state.rover_available = true;
    state.rover_battery_percent = 100.0;
    state.eva_available = true;
    CrewMemberState crew{};
    crew.crew_id = "crew_01";
    crew.eva_status = EVAStatus::Idle;
    crew.health_status = CrewHealthStatus::Impaired;
    crew.physical_performance_factor = 0.7;
    state.crew.push_back(crew);

    Plan plan{};
    plan.plan_id = "impaired";
    Action action{};
    action.type = ActionType::RepairSolarArray;
    action.type_raw = "repair_solar_array";
    action.start_min = 0;
    action.eva_crew_id = "crew_01";
    plan.actions.push_back(action);

    vector<TimelineEvent> events;
    exec.applyScheduledActions(plan, state, config, events);

    REQUIRE(state.active_actions.size() == 1);
    REQUIRE(state.active_actions[0].status == ActionExecutionStatus::Failed);
    REQUIRE(state.active_actions[0].failure_reason.find("health") != string::npos);
}
