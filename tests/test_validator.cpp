#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>
#include <string>
#include <vector>
#include "Enums.hpp"
#include "Plan.hpp"
#include "ScenarioConfig.hpp"
#include "Validator.hpp"

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

ScenarioConfig makeValidConfig(){
    ScenarioConfig config{};
    config.scenario_id = "ares_valid";
    config.name = "Valid Scenario";
    config.time_step_s = 60;
    config.maximum_duration_min = 120;
    config.stabilization_hold_min = 10;

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

    config.power.initial_battery_energy_kwh = 80.0;
    config.power.battery_capacity_kwh = 100.0;
    config.power.battery_reserve_percent = 20.0;
    config.power.charge_efficiency = 0.9;
    config.power.discharge_efficiency = 0.9;
    config.power.essential_load_kw = 1.0;
    config.power.discretionary_load_kw = 0.5;
    config.power.thermal_control_load_kw = 0.5;
    config.power.eva_support_load_kw = 0.0;
    config.power.communications_load_kw = 0.1;

    config.solar.array_area_m2 = 100.0;
    config.solar.cell_efficiency = 0.3;
    config.solar.mars_sun_distance_au = 1.5;
    config.solar.initial_incidence_angle_deg = 0.0;
    config.solar.initial_atmospheric_transmission = 1.0;
    config.solar.initial_deposited_dust_factor = 1.0;

    config.thermal.initial_equipment_heat_w = 200.0;
    config.thermal.initial_environmental_heat_w = 0.0;
    config.thermal.initial_heater_heat_w = 0.0;
    config.thermal.tcs_rejection_capacity_w = 2000.0;
    config.thermal.comfort_low_c = 18.0;
    config.thermal.comfort_high_c = 27.0;
    config.thermal.critical_low_c = 10.0;
    config.thermal.critical_high_c = 35.0;
    config.thermal.humidity_low_percent = 20.0;
    config.thermal.humidity_high_percent = 70.0;

    config.eva.available = true;
    config.eva.preparation_min = 10;
    config.eva.egress_min = 10;
    config.eva.repair_work_min = 20;
    config.eva.ingress_min = 10;
    config.eva.reserve_min = 10;
    config.eva.maximum_duration_min = 360;
    config.eva.rover_required = true;
    config.eva.rover_minimum_reserve_percent = 20.0;

    config.communications.windows = {{100, 200}};
    config.communications.transmission_duration_min = 5;
    config.communications.transmission_power_kw = 0.5;

    config.fault.failure_type = "leak_and_solar";
    config.fault.leak_module = "lab";
    config.fault.total_gas_leak_kg_hr = 1.0;
    config.fault.isolation_leak_multiplier = 0.4;
    config.fault.solar_fault_factor = 0.5;
    config.fault.repaired_solar_fault_factor = 1.0;
    config.fault.stabilized_leak_kg_hr = 0.2;

    config.vital_response.activity_profiles = {
        makeProfile(CrewActivity::NominalWork),
        makeProfile(CrewActivity::Resting),
        makeProfile(CrewActivity::EVAPrep),
        makeProfile(CrewActivity::EVATransit),
        makeProfile(CrewActivity::EVAWork),
        makeProfile(CrewActivity::Recovery),
    };
    config.vital_response.spo2_warning_percent = 94.0;
    config.vital_response.spo2_critical_percent = 88.0;
    config.vital_response.heart_rate_warning_bpm = 120.0;
    config.vital_response.respiratory_rate_warning_bpm = 30.0;
    config.vital_response.core_temp_low_c = 35.0;
    config.vital_response.core_temp_high_c = 38.5;
    config.vital_response.fatigue_warning_fraction = 0.7;
    config.vital_response.performance_abort_fraction = 0.3;
    config.vital_response.hypoxia_accumulation_rate = 0.01;
    config.vital_response.co2_accumulation_rate = 0.01;
    config.vital_response.thermal_accumulation_rate = 0.01;
    config.vital_response.hypoxia_recovery_rate = 0.02;
    config.vital_response.co2_recovery_rate = 0.02;
    config.vital_response.thermal_recovery_rate = 0.02;
    config.vital_response.fatigue_work_rate = 0.001;
    config.vital_response.fatigue_eva_rate = 0.002;
    config.vital_response.fatigue_recovery_rate = 0.001;
    config.vital_response.hr_min_bpm = 40.0;
    config.vital_response.hr_max_bpm = 180.0;
    config.vital_response.rr_min_bpm = 8.0;
    config.vital_response.rr_max_bpm = 40.0;
    config.vital_response.spo2_min_percent = 70.0;
    config.vital_response.spo2_max_percent = 100.0;
    config.vital_response.core_temp_min_c = 34.0;
    config.vital_response.core_temp_max_c = 40.0;
    config.vital_response.core_temp_time_constant_min = 30.0;
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
        makeCrew("crew_02", false),
    };
    return config;
}

}

TEST_CASE("validator: valid scenario and empty plan pass", "[validator]"){
    Validator validator;
    ScenarioConfig config = makeValidConfig();

    ValidationResult scenario = validator.validateScenario(config);
    REQUIRE(scenario.valid);
    REQUIRE(scenario.errors.empty());

    Plan plan{};
    plan.plan_id = "empty";
    ValidationResult plan_result = validator.validatePlan(plan, config);
    REQUIRE(plan_result.valid);
}

TEST_CASE("validator: duplicate crew ids are rejected", "[validator][sec17]"){
    Validator validator;
    ScenarioConfig config = makeValidConfig();
    config.crew_roster.push_back(makeCrew("crew_01", true));

    ValidationResult result = validator.validateScenario(config);
    REQUIRE_FALSE(result.valid);
    bool found = false;
    for(const auto& error : result.errors){
        if(error.code == "crew_id_duplicate"){
            found = true;
        }
    }
    REQUIRE(found);
}

TEST_CASE("validator: incoherent atmosphere thresholds are rejected", "[validator]"){
    Validator validator;
    ScenarioConfig config = makeValidConfig();
    config.atmosphere.inspired_o2_warning_mmhg = 80.0;
    config.atmosphere.inspired_o2_failure_mmhg = 90.0;

    ValidationResult result = validator.validateScenario(config);
    REQUIRE_FALSE(result.valid);
}

TEST_CASE("validator: unknown action is rejected", "[validator][sec17]"){
    Validator validator;
    ScenarioConfig config = makeValidConfig();
    Plan plan{};
    plan.plan_id = "bad_plan";
    Action action{};
    action.type = ActionType::Unknown;
    action.type_raw = "teleport_home";
    action.start_min = 0;
    plan.actions.push_back(action);

    ValidationResult result = validator.validatePlan(plan, config);
    REQUIRE_FALSE(result.valid);
    REQUIRE(result.errors[0].code == "unknown_action");
}

TEST_CASE("validator: unqualified EVA crew is rejected", "[validator][sec17]"){
    Validator validator;
    ScenarioConfig config = makeValidConfig();
    Plan plan{};
    plan.plan_id = "eva_bad";
    Action action{};
    action.type = ActionType::RepairSolarArray;
    action.type_raw = "repair_solar_array";
    action.start_min = 10;
    action.eva_crew_id = "crew_02";
    plan.actions.push_back(action);

    ValidationResult result = validator.validatePlan(plan, config);
    REQUIRE_FALSE(result.valid);
    bool found = false;
    for(const auto& error : result.errors){
        if(error.code == "repair_crew_unqualified"){
            found = true;
        }
    }
    REQUIRE(found);
}

TEST_CASE("validator: packet outside window is rejected", "[validator][sec17]"){
    Validator validator;
    ScenarioConfig config = makeValidConfig();
    Plan plan{};
    plan.plan_id = "packet_bad";
    Action action{};
    action.type = ActionType::SendEmergencyPacket;
    action.type_raw = "send_emergency_packet";
    action.start_min = 10;
    plan.actions.push_back(action);

    ValidationResult result = validator.validatePlan(plan, config);
    REQUIRE_FALSE(result.valid);
    bool found = false;
    for(const auto& error : result.errors){
        if(error.code == "comms_window_closed"){
            found = true;
        }
    }
    REQUIRE(found);
}

TEST_CASE("validator: collects multiple plan errors", "[validator]"){
    Validator validator;
    ScenarioConfig config = makeValidConfig();
    Plan plan{};
    plan.plan_id = "multi";

    Action unknown{};
    unknown.type = ActionType::Unknown;
    unknown.type_raw = "nope";
    unknown.start_min = 0;
    plan.actions.push_back(unknown);

    Action repair{};
    repair.type = ActionType::RepairSolarArray;
    repair.type_raw = "repair_solar_array";
    repair.start_min = 5;
    repair.eva_crew_id = "missing_crew";
    plan.actions.push_back(repair);

    ValidationResult result = validator.validatePlan(plan, config);
    REQUIRE_FALSE(result.valid);
    REQUIRE(result.errors.size() >= 2);
}
