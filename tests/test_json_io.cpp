#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>
#include <nlohmann/json.hpp>
#include <string>

#include "Enums.hpp"
#include "JsonIO.hpp"
#include "Plan.hpp"
#include "ScenarioConfig.hpp"
#include "Simulation.hpp"
#include "SimulationResult.hpp"
#include "TelemetrySample.hpp"

using Catch::Approx;
using json = nlohmann::json;
using namespace std;

namespace {

json makeActivityProfile(const string& activity){
    return json{
        {"activity", activity},
        {"oxygen_g_min", 0.8},
        {"co2_g_min", 0.9},
        {"heat_w", 120.0},
        {"activity_load", 0.5},
    };
}

json makeCrew(const string& crew_id){
    return json{
        {"crew_id", crew_id},
        {"display_name", crew_id},
        {"assigned_role", "Specialist"},
        {"body_mass_kg", 70.0},
        {"baseline_heart_rate_bpm", 65.0},
        {"baseline_respiratory_rate_bpm", 14.0},
        {"baseline_spo2_percent", 98.0},
        {"baseline_core_temperature_c", 36.8},
        {"fitness_factor", 1.0},
        {"hypoxia_sensitivity", 1.0},
        {"co2_sensitivity", 1.0},
        {"thermal_sensitivity", 1.0},
        {"fatigue_recovery_factor", 1.0},
        {"eva_qualified", true},
        {"initial_activity", "NOMINAL_WORK"},
        {"initial_location_module", "core"},
        {"initial_eva_status", "IDLE"},
        {"initial_oxygen_rationing_active", false},
    };
}

json makeValidScenarioJson(){
    json vital = json::object();
    vital["activity_profiles"] = json::array({
        makeActivityProfile("NOMINAL_WORK"),
        makeActivityProfile("RESTING"),
        makeActivityProfile("EVA_PREP"),
        makeActivityProfile("EVA_TRANSIT"),
        makeActivityProfile("EVA_WORK"),
        makeActivityProfile("RECOVERY"),
        makeActivityProfile("INCAPACITATED"),
    });
    vital["hypoxia_accumulation_rate"] = 0.0;
    vital["co2_accumulation_rate"] = 0.0;
    vital["thermal_accumulation_rate"] = 0.0;
    vital["hypoxia_recovery_rate"] = 0.1;
    vital["co2_recovery_rate"] = 0.1;
    vital["thermal_recovery_rate"] = 0.1;
    vital["fatigue_work_rate"] = 0.0;
    vital["fatigue_eva_rate"] = 0.0;
    vital["fatigue_recovery_rate"] = 0.1;
    vital["hr_activity_gain"] = 0.0;
    vital["hr_hypoxia_gain"] = 0.0;
    vital["hr_co2_gain"] = 0.0;
    vital["hr_thermal_gain"] = 0.0;
    vital["hr_fatigue_gain"] = 0.0;
    vital["hr_min_bpm"] = 40.0;
    vital["hr_max_bpm"] = 180.0;
    vital["rr_activity_gain"] = 0.0;
    vital["rr_hypoxia_gain"] = 0.0;
    vital["rr_co2_gain"] = 0.0;
    vital["rr_thermal_gain"] = 0.0;
    vital["rr_min_bpm"] = 8.0;
    vital["rr_max_bpm"] = 40.0;
    vital["spo2_hypoxia_gain"] = 0.0;
    vital["spo2_pressure_gain"] = 0.0;
    vital["spo2_activity_gain"] = 0.0;
    vital["spo2_exposure_gain"] = 0.0;
    vital["spo2_min_percent"] = 70.0;
    vital["spo2_max_percent"] = 100.0;
    vital["core_temp_environment_gain"] = 0.0;
    vital["core_temp_activity_gain"] = 0.0;
    vital["core_temp_time_constant_min"] = 30.0;
    vital["core_temp_min_c"] = 34.0;
    vital["core_temp_max_c"] = 40.0;
    vital["cognitive_hypoxia_weight"] = 0.25;
    vital["cognitive_co2_weight"] = 0.25;
    vital["cognitive_thermal_weight"] = 0.25;
    vital["cognitive_fatigue_weight"] = 0.25;
    vital["physical_hypoxia_weight"] = 0.25;
    vital["physical_co2_weight"] = 0.25;
    vital["physical_thermal_weight"] = 0.25;
    vital["physical_fatigue_weight"] = 0.25;
    vital["spo2_warning_percent"] = 94.0;
    vital["spo2_critical_percent"] = 88.0;
    vital["heart_rate_warning_bpm"] = 120.0;
    vital["respiratory_rate_warning_bpm"] = 30.0;
    vital["core_temp_low_c"] = 35.0;
    vital["core_temp_high_c"] = 38.5;
    vital["fatigue_warning_fraction"] = 0.7;
    vital["performance_abort_fraction"] = 0.3;

    json root = json::object();
    root["scenario_id"] = "ares_json";
    root["name"] = "JSON Scenario";
    root["time_step_s"] = 60;
    root["maximum_duration_min"] = 5;
    root["stabilization_hold_min"] = 2;
    root["habitat"] = {
        {"initial_habitable_volume_m3", 100.0},
        {"isolated_habitable_volume_m3", 60.0},
        {"nominal_temperature_c", 22.0},
        {"initial_relative_humidity_percent", 40.0},
        {"effective_thermal_capacitance_kj_c", 500.0},
    };
    root["atmosphere"] = {
        {"initial_oxygen_mass_kg", 20.0},
        {"initial_inert_gas_mass_kg", 40.0},
        {"initial_co2_mass_kg", 0.2},
        {"scrubber_capacity_g_min", 5.0},
        {"initial_scrubber_efficiency", 1.0},
        {"pressure_warning_low_kpa", 70.0},
        {"pressure_failure_low_kpa", 50.0},
        {"pressure_high_limit_kpa", 110.0},
        {"inspired_o2_nominal_mmhg", 150.0},
        {"inspired_o2_warning_mmhg", 120.0},
        {"inspired_o2_failure_mmhg", 90.0},
        {"co2_one_hour_limit_mmhg", 8.0},
        {"minimum_inert_fraction", 0.2},
    };
    root["power"] = {
        {"initial_battery_energy_kwh", 90.0},
        {"battery_capacity_kwh", 100.0},
        {"battery_reserve_percent", 10.0},
        {"charge_efficiency", 0.9},
        {"discharge_efficiency", 0.9},
        {"essential_load_kw", 0.5},
        {"discretionary_load_kw", 0.2},
        {"thermal_control_load_kw", 0.2},
        {"eva_support_load_kw", 0.0},
        {"communications_load_kw", 0.0},
    };
    root["solar"] = {
        {"array_area_m2", 120.0},
        {"cell_efficiency", 0.35},
        {"mars_sun_distance_au", 1.5},
        {"initial_incidence_angle_deg", 0.0},
        {"initial_atmospheric_transmission", 1.0},
        {"initial_deposited_dust_factor", 1.0},
    };
    root["thermal"] = {
        {"initial_equipment_heat_w", 100.0},
        {"initial_environmental_heat_w", 0.0},
        {"initial_heater_heat_w", 0.0},
        {"tcs_rejection_capacity_w", 3000.0},
        {"comfort_low_c", 18.0},
        {"comfort_high_c", 27.0},
        {"critical_low_c", 10.0},
        {"critical_high_c", 35.0},
        {"humidity_low_percent", 20.0},
        {"humidity_high_percent", 70.0},
    };
    root["eva"] = {
        {"available", true},
        {"preparation_min", 5},
        {"egress_min", 5},
        {"repair_work_min", 10},
        {"ingress_min", 5},
        {"reserve_min", 5},
        {"maximum_duration_min", 360},
        {"rover_required", false},
        {"rover_minimum_reserve_percent", 20.0},
    };
    root["communications"] = {
        {"windows", json::array({json{{"open_min", 0}, {"close_min", 1000}}})},
        {"transmission_duration_min", 5},
        {"transmission_power_kw", 0.1},
    };
    root["fault"] = {
        {"failure_type", "none"},
        {"leak_module", "lab"},
        {"total_gas_leak_kg_hr", 0.0},
        {"isolation_leak_multiplier", 0.4},
        {"solar_fault_factor", 1.0},
        {"repaired_solar_fault_factor", 1.0},
        {"stabilized_leak_kg_hr", 0.1},
    };
    root["vital_response"] = vital;
    root["crew_roster"] = json::array({makeCrew("crew_01")});
    root["parameter_sources"] = json::array({
        json{
            {"parameter_name", "time_step_s"},
            {"classification", "ARES_ASSUMPTION"},
            {"source_label", "test"},
            {"note", "unit test"},
        },
    });
    return root;
}

json makeValidPlanJson(){
    return json{
        {"plan_id", "plan_01"},
        {"summary", "send packet"},
        {"actions",
         json::array({
             json{
                 {"type", "send_emergency_packet"},
                 {"start_min", 1},
             },
         })},
        {"rationale", "report status"},
        {"expected_risk", "low"},
        {"constraints_checked", json::array({"comms_window"})},
    };
}

}

TEST_CASE("jsonio: loads valid scenario and plan", "[jsonio]"){
    ScenarioConfig config{};
    string error;
    REQUIRE(loadScenarioFromString(makeValidScenarioJson().dump(), config, error));
    REQUIRE(config.scenario_id == "ares_json");
    REQUIRE(config.crew_roster.size() == 1);
    REQUIRE(config.crew_roster[0].initial_activity == CrewActivity::NominalWork);
    REQUIRE(config.parameter_sources[0].classification == SourceClassification::ARESAssumption);

    Plan plan{};
    REQUIRE(loadPlanFromString(makeValidPlanJson().dump(), plan, error));
    REQUIRE(plan.plan_id == "plan_01");
    REQUIRE(plan.actions.size() == 1);
    REQUIRE(plan.actions[0].type == ActionType::SendEmergencyPacket);
    REQUIRE(plan.actions[0].type_raw == "send_emergency_packet");
}

TEST_CASE("jsonio: rejects missing required scenario field", "[jsonio]"){
    json root = makeValidScenarioJson();
    root.erase("scenario_id");
    ScenarioConfig config{};
    string error;
    REQUIRE_FALSE(loadScenarioFromString(root.dump(), config, error));
    REQUIRE(error.find("missing key") != string::npos);
}

TEST_CASE("jsonio: rejects unknown scenario key", "[jsonio]"){
    json root = makeValidScenarioJson();
    root["extra_field"] = 1;
    ScenarioConfig config{};
    string error;
    REQUIRE_FALSE(loadScenarioFromString(root.dump(), config, error));
    REQUIRE(error.find("unknown key") != string::npos);
}

TEST_CASE("jsonio: rejects wrong type", "[jsonio]"){
    json root = makeValidScenarioJson();
    root["time_step_s"] = "sixty";
    ScenarioConfig config{};
    string error;
    REQUIRE_FALSE(loadScenarioFromString(root.dump(), config, error));
    REQUIRE(error.find("expected integer") != string::npos);
}

TEST_CASE("jsonio: rejects non-finite number", "[jsonio]"){
    json root = makeValidScenarioJson();
    root["habitat"]["nominal_temperature_c"] = json::parse("null");
    // replace with an explicit non-finite through string injection
    string text = root.dump();
    const string needle = "\"nominal_temperature_c\":null";
    const size_t pos = text.find(needle);
    REQUIRE(pos != string::npos);
    text.replace(pos, needle.size(), "\"nominal_temperature_c\":NaN");

    ScenarioConfig config{};
    string error;
    REQUIRE_FALSE(loadScenarioFromString(text, config, error));
}

TEST_CASE("jsonio: rejects unknown enum and action", "[jsonio]"){
    json root = makeValidScenarioJson();
    root["crew_roster"][0]["initial_activity"] = "JOGGING";
    ScenarioConfig config{};
    string error;
    REQUIRE_FALSE(loadScenarioFromString(root.dump(), config, error));
    REQUIRE(error.find("CrewActivity") != string::npos);

    json plan = makeValidPlanJson();
    plan["actions"][0]["type"] = "teleport";
    Plan loaded{};
    REQUIRE_FALSE(loadPlanFromString(plan.dump(), loaded, error));
    REQUIRE(error.find("unknown action type") != string::npos);
}

TEST_CASE("jsonio: serializes simulation result with section 15 habitat fields", "[jsonio]"){
    ScenarioConfig config{};
    string error;
    REQUIRE(loadScenarioFromString(makeValidScenarioJson().dump(), config, error));

    Simulation simulation;
    SimulationResult result = simulation.runBaseline(config);
    REQUIRE_FALSE(result.telemetry_history.empty());

    string text;
    REQUIRE(writeResultToString(result, text, error));
    json document = json::parse(text);

    REQUIRE(document["scenario_id"] == "ares_json");
    REQUIRE(document.contains("plan_id"));
    REQUIRE(document.contains("outcome"));
    REQUIRE(document.contains("valid_plan"));
    REQUIRE(document.contains("metrics"));
    REQUIRE(document.contains("timeline"));
    REQUIRE(document.contains("telemetry_history"));
    REQUIRE(document.contains("failure_reasons"));
    REQUIRE(document["metrics"].contains("minimum_inspired_o2_mmhg"));

    const json& sample = document["telemetry_history"].at(0);
    REQUIRE(sample.contains("simulation_time_min"));
    REQUIRE(sample.contains("habitat"));
    REQUIRE(sample.contains("crew"));
    REQUIRE(sample.contains("events"));
    REQUIRE(sample.contains("active_actions"));
    REQUIRE(sample.contains("has_warning"));
    REQUIRE(sample.contains("has_critical"));

    const json& habitat = sample["habitat"];
    REQUIRE(habitat.contains("cabin_pressure_kpa"));
    REQUIRE(habitat.contains("inspired_oxygen_mmhg"));
    REQUIRE(habitat.contains("co2_one_hour_avg_mmhg"));
    REQUIRE(habitat.contains("oxygen_hours_remaining"));
    REQUIRE(habitat.contains("battery_soc_percent"));
    REQUIRE(habitat.contains("solar_generation_percent"));
    REQUIRE(habitat.contains("power_margin_kw"));
    REQUIRE(habitat.contains("cabin_temperature_c"));
    REQUIRE(habitat.contains("temperature_margin_c"));
    REQUIRE(habitat.contains("eva_safe_return_margin_min"));
    REQUIRE(habitat.contains("mission_status"));
    REQUIRE(habitat["cabin_temperature_c"].get<double>() ==
            Approx(result.telemetry_history[0].telemetry.thermal.cabin_temperature_c));
    REQUIRE(habitat["mission_status"].is_string());

    REQUIRE_FALSE(sample["crew"].empty());
    const json& crew = sample["crew"].at(0);
    REQUIRE(crew.contains("crew_id"));
    REQUIRE(crew.contains("display_name"));
    REQUIRE(crew.contains("activity"));
    REQUIRE(crew.contains("heart_rate_bpm"));
    REQUIRE(crew.contains("respiratory_rate_bpm"));
    REQUIRE(crew.contains("spo2_percent"));
    REQUIRE(crew.contains("core_temperature_c"));
    REQUIRE(crew.contains("fatigue_percent"));
    REQUIRE(crew.contains("cognitive_performance_percent"));
    REQUIRE(crew.contains("physical_performance_percent"));
    REQUIRE(crew.contains("health_status"));
    REQUIRE(crew.contains("alarms"));
    REQUIRE(crew["activity"] == "NOMINAL_WORK");
    REQUIRE(crew["alarms"].is_array());
}

TEST_CASE("jsonio: serializes hand-built sample fields and enums", "[jsonio]"){
    SimulationResult result{};
    result.scenario_id = "hand";
    result.plan_id = "none";
    result.outcome = OutcomeStatus::Failure;
    result.valid_plan = true;
    result.failure_reasons = {"cabin_temperature_critical"};
    result.metrics.minimum_inspired_o2_mmhg = 140.0;
    result.metrics.eva_completed = false;
    result.metrics.communications_sent = true;

    TimelineEvent event{};
    event.time_min = 3;
    event.event_type = "alarm";
    event.message = "hypoxia";
    event.severity = ConstraintSeverity::Warning;
    result.timeline.push_back(event);

    TelemetrySample sample{};
    sample.simulation_time_min = 3;
    sample.telemetry.atmosphere.cabin_pressure_kpa = 64.1;
    sample.telemetry.atmosphere.inspired_oxygen_mmhg = 139.5;
    sample.telemetry.atmosphere.co2_one_hour_avg_mmhg = 2.4;
    sample.telemetry.atmosphere.oxygen_hours_remaining = 12.8;
    sample.telemetry.power.battery_soc_percent = 32.0;
    sample.telemetry.power.solar_generation_percent = 55.0;
    sample.telemetry.power.power_margin_kw = -1.3;
    sample.telemetry.thermal.cabin_temperature_c = 23.4;
    sample.telemetry.thermal.temperature_margin_c = 8.4;
    sample.telemetry.eva.eva_safe_return_margin_min = 264.0;
    sample.telemetry.mission.mission_status = MissionStatus::Critical;

    CrewVitalsTelemetry crew{};
    crew.crew_id = "crew_01";
    crew.display_name = "Commander";
    crew.activity = CrewActivity::NominalWork;
    crew.heart_rate_bpm = 96.0;
    crew.respiratory_rate_bpm = 21.0;
    crew.spo2_percent = 93.8;
    crew.core_temperature_c = 37.1;
    crew.fatigue_percent = 28.0;
    crew.cognitive_performance_percent = 91.0;
    crew.physical_performance_percent = 88.0;
    crew.health_status = CrewHealthStatus::ElevatedStress;
    crew.active_alarms = {CrewAlarmType::Hypoxia};
    sample.telemetry.crew_vitals.push_back(crew);

    ActiveActionState active{};
    active.action_index = 0;
    active.type = ActionType::RepairSolarArray;
    active.status = ActionExecutionStatus::Active;
    active.actual_start_min = 1;
    active.elapsed_min = 2;
    active.progress_fraction = 0.25;
    active.assigned_crew_id = "crew_01";
    active.assigned_crew_ids = {"crew_01"};
    sample.active_actions.push_back(active);
    sample.events_this_step.push_back(event);
    sample.has_warning = true;
    sample.has_critical = true;
    result.telemetry_history.push_back(sample);

    string text;
    string error;
    REQUIRE(writeResultToString(result, text, error));
    json document = json::parse(text);

    REQUIRE(document["outcome"] == "FAILURE");
    REQUIRE(document["failure_reasons"][0] == "cabin_temperature_critical");
    REQUIRE(document["timeline"][0]["severity"] == "WARNING");

    const json& habitat = document["telemetry_history"][0]["habitat"];
    REQUIRE(habitat["cabin_temperature_c"] == Approx(23.4));
    REQUIRE(habitat["mission_status"] == "CRITICAL");

    const json& crew_json = document["telemetry_history"][0]["crew"][0];
    REQUIRE(crew_json["health_status"] == "ELEVATED_STRESS");
    REQUIRE(crew_json["alarms"][0] == "HYPOXIA");

    const json& action = document["telemetry_history"][0]["active_actions"][0];
    REQUIRE(action["type"] == "repair_solar_array");
    REQUIRE(action["status"] == "ACTIVE");
}
