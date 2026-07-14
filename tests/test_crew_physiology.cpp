#include <catch2/catch_test_macros.hpp>
#include <catch2/catch_approx.hpp>
#include <stdexcept>
#include "CrewPhysiologyModel.hpp"
#include "Enums.hpp"
#include "PhysicalConstants.hpp"
#include "ResourceModel.hpp"
#include "ScenarioConfig.hpp"
#include "SimulationState.hpp"
#include "TelemetrySample.hpp"

using Catch::Approx;

namespace {

CrewMemberConfig makeCrew(
    const string& id,
    const string& name,
    const string& role,
    double hr,
    double rr,
    double spo2,
    double temp,
    CrewActivity activity,
    const string& location) {
    CrewMemberConfig crew{};
    crew.crew_id = id;
    crew.display_name = name;
    crew.assigned_role = role;
    crew.body_mass_kg = 70.0;
    crew.baseline_heart_rate_bpm = hr;
    crew.baseline_respiratory_rate_bpm = rr;
    crew.baseline_spo2_percent = spo2;
    crew.baseline_core_temperature_c = temp;
    crew.fitness_factor = 1.0;
    crew.hypoxia_sensitivity = 1.0;
    crew.co2_sensitivity = 1.0;
    crew.thermal_sensitivity = 1.0;
    crew.fatigue_recovery_factor = 1.0;
    crew.eva_qualified = true;
    crew.initial_activity = activity;
    crew.initial_location_module = location;
    crew.initial_eva_status = EVAStatus::Idle;
    crew.initial_oxygen_rationing_active = false;
    return crew;
}

ScenarioConfig makeCrewConfig() {
    ScenarioConfig config{};

    ActivityMetabolicProfile resting{};
    resting.activity = CrewActivity::Resting;
    resting.oxygen_g_min = 0.5;
    resting.co2_g_min = 0.6;
    resting.heat_w = 100.0;
    resting.activity_load = 0.2;

    ActivityMetabolicProfile work{};
    work.activity = CrewActivity::NominalWork;
    work.oxygen_g_min = 0.9;
    work.co2_g_min = 1.0;
    work.heat_w = 150.0;
    work.activity_load = 0.5;

    config.vital_response.activity_profiles = {resting, work};

    config.crew_roster = {
        makeCrew("crew_01", "Alex Rivera", "Commander", 62.0, 12.0, 98.0, 36.8,
                 CrewActivity::Resting, "hab_core"),
        makeCrew("crew_02", "Jordan Lee", "Engineer", 68.0, 14.0, 97.5, 36.9,
                 CrewActivity::NominalWork, "lab_module"),
    };

    return config;
}

}

TEST_CASE("crew: roster mapping preserves size and order", "[crew]") {
    CrewPhysiologyModel model;
    ScenarioConfig config = makeCrewConfig();

    vector<CrewMemberState> states = model.initializeCrewStates(config);

    REQUIRE(states.size() == 2);
    REQUIRE(states[0].crew_id == "crew_01");
    REQUIRE(states[1].crew_id == "crew_02");
}

TEST_CASE("crew: baseline initialization matches config and profiles", "[crew]") {
    CrewPhysiologyModel model;
    ScenarioConfig config = makeCrewConfig();

    vector<CrewMemberState> states = model.initializeCrewStates(config);

    REQUIRE(states[0].heart_rate_bpm == Approx(62.0));
    REQUIRE(states[0].respiratory_rate_bpm == Approx(12.0));
    REQUIRE(states[0].spo2_percent == Approx(98.0));
    REQUIRE(states[0].core_temperature_c == Approx(36.8));
    REQUIRE(states[0].actvity == CrewActivity::Resting);
    REQUIRE(states[0].location_module == "hab_core");
    REQUIRE(states[0].eva_status == EVAStatus::Idle);
    REQUIRE_FALSE(states[0].oxygen_rationing_active);
    REQUIRE(states[0].hypoxia_exposure_index == Approx(0.0));
    REQUIRE(states[0].co2_exposure_index == Approx(0.0));
    REQUIRE(states[0].thermal_exposure_index == Approx(0.0));
    REQUIRE(states[0].fatigue_index == Approx(0.0));
    REQUIRE(states[0].cognitive_performance_factor == Approx(1.0));
    REQUIRE(states[0].physical_performance_factor == Approx(1.0));
    REQUIRE(states[0].oxygen_consumption_g_min == Approx(0.5));
    REQUIRE(states[0].co2_production_g_min == Approx(0.6));
    REQUIRE(states[0].heat_output_w == Approx(100.0));
    REQUIRE(states[0].health_status == CrewHealthStatus::Nominal);
    REQUIRE(states[0].active_alarms.empty());

    REQUIRE(states[1].heart_rate_bpm == Approx(68.0));
    REQUIRE(states[1].actvity == CrewActivity::NominalWork);
    REQUIRE(states[1].location_module == "lab_module");
    REQUIRE(states[1].oxygen_consumption_g_min == Approx(0.9));
    REQUIRE(states[1].co2_production_g_min == Approx(1.0));
    REQUIRE(states[1].heat_output_w == Approx(150.0));
}

TEST_CASE("crew: repeated initialization is identical", "[crew]") {
    CrewPhysiologyModel model;
    ScenarioConfig config = makeCrewConfig();

    vector<CrewMemberState> first = model.initializeCrewStates(config);
    vector<CrewMemberState> second = model.initializeCrewStates(config);

    REQUIRE(first.size() == second.size());
    for (size_t i = 0; i < first.size(); ++i) {
        REQUIRE(first[i].crew_id == second[i].crew_id);
        REQUIRE(first[i].heart_rate_bpm == Approx(second[i].heart_rate_bpm));
        REQUIRE(first[i].respiratory_rate_bpm == Approx(second[i].respiratory_rate_bpm));
        REQUIRE(first[i].spo2_percent == Approx(second[i].spo2_percent));
        REQUIRE(first[i].core_temperature_c == Approx(second[i].core_temperature_c));
        REQUIRE(first[i].oxygen_consumption_g_min == Approx(second[i].oxygen_consumption_g_min));
        REQUIRE(first[i].co2_production_g_min == Approx(second[i].co2_production_g_min));
        REQUIRE(first[i].heat_output_w == Approx(second[i].heat_output_w));
        REQUIRE(first[i].actvity == second[i].actvity);
        REQUIRE(first[i].location_module == second[i].location_module);
    }
}

TEST_CASE("crew: telemetry copy converts percentages and does not mutate state", "[crew]") {
    CrewPhysiologyModel model;
    ScenarioConfig config = makeCrewConfig();
    SimulationState state{};
    state.crew = model.initializeCrewStates(config);

    state.crew[0].fatigue_index = 0.28;
    state.crew[0].cognitive_performance_factor = 0.91;
    state.crew[0].physical_performance_factor = 0.85;
    state.crew[0].hypoxia_exposure_index = 0.12;
    state.crew[0].co2_exposure_index = 0.05;
    state.crew[0].thermal_exposure_index = 0.08;

    vector<CrewMemberState> before = state.crew;
    vector<CrewVitalsTelemetry> vitals = model.buildCrewVitalsTelemetry(state, config);

    REQUIRE(vitals.size() == 2);
    REQUIRE(vitals[0].crew_id == "crew_01");
    REQUIRE(vitals[0].display_name == "Alex Rivera");
    REQUIRE(vitals[0].assigned_role == "Commander");
    REQUIRE(vitals[0].location_module == "hab_core");
    REQUIRE(vitals[0].activity == CrewActivity::Resting);
    REQUIRE(vitals[0].heart_rate_bpm == Approx(62.0));
    REQUIRE(vitals[0].oxygen_consumption_g_min == Approx(0.5));
    REQUIRE(vitals[0].fatigue_percent == Approx(28.0));
    REQUIRE(vitals[0].cognitive_performance_percent == Approx(91.0));
    REQUIRE(vitals[0].physical_performance_percent == Approx(85.0));
    REQUIRE(vitals[0].hypoxia_exposure == Approx(0.12));
    REQUIRE(vitals[0].co2_exposure == Approx(0.05));
    REQUIRE(vitals[0].thermal_exposure == Approx(0.08));
    REQUIRE(vitals[0].health_status == CrewHealthStatus::Nominal);

    REQUIRE(vitals[1].crew_id == "crew_02");
    REQUIRE(vitals[1].display_name == "Jordan Lee");
    REQUIRE(vitals[1].assigned_role == "Engineer");

    REQUIRE(state.crew[0].fatigue_index == Approx(before[0].fatigue_index));
    REQUIRE(state.crew[0].cognitive_performance_factor == Approx(before[0].cognitive_performance_factor));
    REQUIRE(state.crew[0].physical_performance_factor == Approx(before[0].physical_performance_factor));
    REQUIRE(state.crew[0].hypoxia_exposure_index == Approx(before[0].hypoxia_exposure_index));
}

TEST_CASE("crew: findCrewConfig resolves known ids and rejects unknown", "[crew]") {
    CrewPhysiologyModel model;
    ScenarioConfig config = makeCrewConfig();

    const CrewMemberConfig& found = model.findCrewConfig("crew_02", config);
    REQUIRE(found.crew_id == "crew_02");
    REQUIRE(found.display_name == "Jordan Lee");

    REQUIRE_THROWS_AS(model.findCrewConfig("crew_missing", config), std::runtime_error);
}

TEST_CASE("crew: findActivityProfile resolves NASA-baseline and EVA profiles", "[crew]") {
    CrewPhysiologyModel model;
    VitalResponseConfig vital_response{};

    ActivityMetabolicProfile sleep{};
    sleep.activity = CrewActivity::Sleep;
    sleep.oxygen_g_min = 0.35;
    sleep.co2_g_min = 0.40;
    sleep.heat_w = 75.0;
    sleep.activity_load = 0.1;

    ActivityMetabolicProfile nominal{};
    nominal.activity = CrewActivity::NominalWork;
    nominal.oxygen_g_min = 0.90;
    nominal.co2_g_min = 1.00;
    nominal.heat_w = 150.0;
    nominal.activity_load = 0.5;

    ActivityMetabolicProfile high{};
    high.activity = CrewActivity::HighWorkload;
    high.oxygen_g_min = 1.40;
    high.co2_g_min = 1.55;
    high.heat_w = 220.0;
    high.activity_load = 0.8;

    ActivityMetabolicProfile eva{};
    eva.activity = CrewActivity::EVAWork;
    eva.oxygen_g_min = 1.80;
    eva.co2_g_min = 2.00;
    eva.heat_w = 300.0;
    eva.activity_load = 1.0;

    vital_response.activity_profiles = {sleep, nominal, high, eva};

    const ActivityMetabolicProfile& sleep_profile =
        model.findActivityProfile(CrewActivity::Sleep, vital_response);
    REQUIRE(sleep_profile.oxygen_g_min == Approx(0.35));
    REQUIRE(sleep_profile.co2_g_min == Approx(0.40));
    REQUIRE(sleep_profile.heat_w == Approx(75.0));
    REQUIRE(sleep_profile.activity_load == Approx(0.1));

    const ActivityMetabolicProfile& work_profile =
        model.findActivityProfile(CrewActivity::NominalWork, vital_response);
    REQUIRE(work_profile.oxygen_g_min == Approx(0.90));
    REQUIRE(work_profile.heat_w == Approx(150.0));

    const ActivityMetabolicProfile& high_profile =
        model.findActivityProfile(CrewActivity::HighWorkload, vital_response);
    REQUIRE(high_profile.oxygen_g_min == Approx(1.40));
    REQUIRE(high_profile.activity_load == Approx(0.8));

    const ActivityMetabolicProfile& eva_profile =
        model.findActivityProfile(CrewActivity::EVAWork, vital_response);
    REQUIRE(eva_profile.oxygen_g_min == Approx(1.80));
    REQUIRE(eva_profile.co2_g_min == Approx(2.00));
    REQUIRE(eva_profile.heat_w == Approx(300.0));
}

TEST_CASE("crew: findActivityProfile rejects missing and duplicate profiles", "[crew]") {
    CrewPhysiologyModel model;
    VitalResponseConfig vital_response{};

    ActivityMetabolicProfile nominal{};
    nominal.activity = CrewActivity::NominalWork;
    nominal.oxygen_g_min = 0.90;
    nominal.co2_g_min = 1.00;
    nominal.heat_w = 150.0;
    nominal.activity_load = 0.5;

    vital_response.activity_profiles = {nominal};

    REQUIRE_THROWS_AS(
        model.findActivityProfile(CrewActivity::Recovery, vital_response),
        std::runtime_error);
    REQUIRE_THROWS_AS(
        model.findActivityProfile(CrewActivity::Sleep, vital_response),
        std::runtime_error);

    ActivityMetabolicProfile duplicate = nominal;
    vital_response.activity_profiles = {nominal, duplicate};

    REQUIRE_THROWS_AS(
        model.findActivityProfile(CrewActivity::NominalWork, vital_response),
        std::runtime_error);
}

namespace {

ScenarioConfig makeSeverityConfig() {
    ScenarioConfig config{};
    config.atmosphere.inspired_o2_nominal_mmhg = 150.0;
    config.atmosphere.inspired_o2_warning_mmhg = 120.0;
    config.atmosphere.inspired_o2_failure_mmhg = 90.0;
    config.atmosphere.pressure_warning_low_kpa = 70.0;
    config.atmosphere.pressure_failure_low_kpa = 50.0;
    config.atmosphere.co2_one_hour_limit_mmhg = 8.0;
    config.thermal.comfort_low_c = 18.0;
    config.thermal.comfort_high_c = 27.0;
    config.thermal.critical_low_c = 10.0;
    config.thermal.critical_high_c = 35.0;
    return config;
}

CrewMemberConfig makeSensitiveCrew(double hypoxia, double co2, double thermal) {
    CrewMemberConfig crew = makeCrew(
        "crew_sev", "Severity Tester", "Pilot", 70.0, 14.0, 98.0, 36.8,
        CrewActivity::NominalWork, "hab_core");
    crew.hypoxia_sensitivity = hypoxia;
    crew.co2_sensitivity = co2;
    crew.thermal_sensitivity = thermal;
    return crew;
}

DerivedTelemetry makeEnvTelemetry(double inspired_o2, double pressure_kpa, double co2_avg) {
    DerivedTelemetry telemetry{};
    telemetry.atmosphere.inspired_oxygen_mmhg = inspired_o2;
    telemetry.atmosphere.cabin_pressure_kpa = pressure_kpa;
    telemetry.atmosphere.co2_one_hour_avg_mmhg = co2_avg;
    return telemetry;
}

}

TEST_CASE("crew: hypoxia severity safe mid critical and sensitivity", "[crew]") {
    CrewPhysiologyModel model;
    ScenarioConfig config = makeSeverityConfig();
    CrewMemberConfig crew = makeSensitiveCrew(1.0, 1.0, 1.0);

    REQUIRE(model.calculateHypoxiaSeverity(
        makeEnvTelemetry(130.0, 80.0, 1.0), config, crew) == Approx(0.0));
    REQUIRE(model.calculateHypoxiaSeverity(
        makeEnvTelemetry(120.0, 80.0, 1.0), config, crew) == Approx(0.0));
    REQUIRE(model.calculateHypoxiaSeverity(
        makeEnvTelemetry(105.0, 80.0, 1.0), config, crew) == Approx(0.5));
    REQUIRE(model.calculateHypoxiaSeverity(
        makeEnvTelemetry(90.0, 80.0, 1.0), config, crew) == Approx(1.0));
    REQUIRE(model.calculateHypoxiaSeverity(
        makeEnvTelemetry(80.0, 80.0, 1.0), config, crew) == Approx(1.0));

    double low = model.calculateHypoxiaSeverity(
        makeEnvTelemetry(115.0, 80.0, 1.0), config, crew);
    double high = model.calculateHypoxiaSeverity(
        makeEnvTelemetry(100.0, 80.0, 1.0), config, crew);
    REQUIRE(high > low);

    crew.hypoxia_sensitivity = 2.0;
    REQUIRE(model.calculateHypoxiaSeverity(
        makeEnvTelemetry(105.0, 80.0, 1.0), config, crew) == Approx(1.0));
}

TEST_CASE("crew: co2 severity safe mid critical and sensitivity", "[crew]") {
    CrewPhysiologyModel model;
    ScenarioConfig config = makeSeverityConfig();
    CrewMemberConfig crew = makeSensitiveCrew(1.0, 1.0, 1.0);

    REQUIRE(model.calculateCo2Severity(
        makeEnvTelemetry(150.0, 80.0, 0.0), config, crew) == Approx(0.0));
    REQUIRE(model.calculateCo2Severity(
        makeEnvTelemetry(150.0, 80.0, 4.0), config, crew) == Approx(0.5));
    REQUIRE(model.calculateCo2Severity(
        makeEnvTelemetry(150.0, 80.0, 8.0), config, crew) == Approx(1.0));
    REQUIRE(model.calculateCo2Severity(
        makeEnvTelemetry(150.0, 80.0, 10.0), config, crew) == Approx(1.0));

    double low = model.calculateCo2Severity(
        makeEnvTelemetry(150.0, 80.0, 2.0), config, crew);
    double high = model.calculateCo2Severity(
        makeEnvTelemetry(150.0, 80.0, 6.0), config, crew);
    REQUIRE(high > low);

    crew.co2_sensitivity = 2.0;
    REQUIRE(model.calculateCo2Severity(
        makeEnvTelemetry(150.0, 80.0, 4.0), config, crew) == Approx(1.0));
}

TEST_CASE("crew: pressure severity safe mid critical", "[crew]") {
    CrewPhysiologyModel model;
    ScenarioConfig config = makeSeverityConfig();
    CrewMemberConfig crew = makeSensitiveCrew(1.0, 1.0, 1.0);

    REQUIRE(model.calculatePressureSeverity(
        makeEnvTelemetry(150.0, 80.0, 1.0), config, crew) == Approx(0.0));
    REQUIRE(model.calculatePressureSeverity(
        makeEnvTelemetry(150.0, 70.0, 1.0), config, crew) == Approx(0.0));
    REQUIRE(model.calculatePressureSeverity(
        makeEnvTelemetry(150.0, 60.0, 1.0), config, crew) == Approx(0.5));
    REQUIRE(model.calculatePressureSeverity(
        makeEnvTelemetry(150.0, 50.0, 1.0), config, crew) == Approx(1.0));
    REQUIRE(model.calculatePressureSeverity(
        makeEnvTelemetry(150.0, 40.0, 1.0), config, crew) == Approx(1.0));

    double low = model.calculatePressureSeverity(
        makeEnvTelemetry(150.0, 65.0, 1.0), config, crew);
    double high = model.calculatePressureSeverity(
        makeEnvTelemetry(150.0, 55.0, 1.0), config, crew);
    REQUIRE(high > low);
}

TEST_CASE("crew: thermal severity cold hot and sensitivity", "[crew]") {
    CrewPhysiologyModel model;
    ScenarioConfig config = makeSeverityConfig();
    CrewMemberConfig crew = makeSensitiveCrew(1.0, 1.0, 1.0);
    DerivedTelemetry telemetry = makeEnvTelemetry(150.0, 80.0, 1.0);

    REQUIRE(model.calculateThermalSeverity(telemetry, config, crew, 22.0) == Approx(0.0));
    REQUIRE(model.calculateThermalSeverity(telemetry, config, crew, 18.0) == Approx(0.0));
    REQUIRE(model.calculateThermalSeverity(telemetry, config, crew, 27.0) == Approx(0.0));
    REQUIRE(model.calculateThermalSeverity(telemetry, config, crew, 14.0) == Approx(0.5));
    REQUIRE(model.calculateThermalSeverity(telemetry, config, crew, 10.0) == Approx(1.0));
    REQUIRE(model.calculateThermalSeverity(telemetry, config, crew, 31.0) == Approx(0.5));
    REQUIRE(model.calculateThermalSeverity(telemetry, config, crew, 35.0) == Approx(1.0));
    REQUIRE(model.calculateThermalSeverity(telemetry, config, crew, 40.0) == Approx(1.0));

    double mild_cold = model.calculateThermalSeverity(telemetry, config, crew, 16.0);
    double deep_cold = model.calculateThermalSeverity(telemetry, config, crew, 12.0);
    REQUIRE(deep_cold > mild_cold);

    crew.thermal_sensitivity = 2.0;
    REQUIRE(model.calculateThermalSeverity(telemetry, config, crew, 14.0) == Approx(1.0));
}

TEST_CASE("crew: exposure accumulates under stress and recovers when safe", "[crew][sec17]") {
    CrewPhysiologyModel model;
    VitalResponseConfig config{};
    config.hypoxia_accumulation_rate = 0.10;
    config.co2_accumulation_rate = 0.08;
    config.thermal_accumulation_rate = 0.06;
    config.hypoxia_recovery_rate = 0.05;
    config.co2_recovery_rate = 0.04;
    config.thermal_recovery_rate = 0.03;

    CrewMemberState crew{};
    crew.hypoxia_exposure_index = 0.0;
    crew.co2_exposure_index = 0.0;
    crew.thermal_exposure_index = 0.0;

    model.updateExposureIndices(crew, 1.0, 1.0, 1.0, config, 1.0);
    REQUIRE(crew.hypoxia_exposure_index == Approx(0.10));
    REQUIRE(crew.co2_exposure_index == Approx(0.08));
    REQUIRE(crew.thermal_exposure_index == Approx(0.06));

    model.updateExposureIndices(crew, 1.0, 1.0, 1.0, config, 1.0);
    REQUIRE(crew.hypoxia_exposure_index == Approx(0.20));
    REQUIRE(crew.co2_exposure_index == Approx(0.16));
    REQUIRE(crew.thermal_exposure_index == Approx(0.12));

    model.updateExposureIndices(crew, 0.0, 0.0, 0.0, config, 1.0);
    REQUIRE(crew.hypoxia_exposure_index == Approx(0.15));
    REQUIRE(crew.co2_exposure_index == Approx(0.12));
    REQUIRE(crew.thermal_exposure_index == Approx(0.09));
}

TEST_CASE("crew: brief exposure is less than prolonged exposure", "[crew]") {
    CrewPhysiologyModel model;
    VitalResponseConfig config{};
    config.hypoxia_accumulation_rate = 0.10;
    config.co2_accumulation_rate = 0.10;
    config.thermal_accumulation_rate = 0.10;
    config.hypoxia_recovery_rate = 0.05;
    config.co2_recovery_rate = 0.05;
    config.thermal_recovery_rate = 0.05;

    CrewMemberState brief{};
    CrewMemberState prolonged{};

    model.updateExposureIndices(brief, 1.0, 1.0, 1.0, config, 1.0);
    for (int i = 0; i < 5; ++i) {
        model.updateExposureIndices(prolonged, 1.0, 1.0, 1.0, config, 1.0);
    }

    REQUIRE(brief.hypoxia_exposure_index == Approx(0.10));
    REQUIRE(prolonged.hypoxia_exposure_index == Approx(0.50));
    REQUIRE(prolonged.hypoxia_exposure_index > brief.hypoxia_exposure_index);
    REQUIRE(prolonged.co2_exposure_index > brief.co2_exposure_index);
    REQUIRE(prolonged.thermal_exposure_index > brief.thermal_exposure_index);
}

TEST_CASE("crew: exposure clamps at zero and may exceed one", "[crew]") {
    CrewPhysiologyModel model;
    VitalResponseConfig config{};
    config.hypoxia_accumulation_rate = 0.50;
    config.co2_accumulation_rate = 0.50;
    config.thermal_accumulation_rate = 0.50;
    config.hypoxia_recovery_rate = 0.20;
    config.co2_recovery_rate = 0.20;
    config.thermal_recovery_rate = 0.20;

    CrewMemberState crew{};
    crew.hypoxia_exposure_index = 0.05;
    crew.co2_exposure_index = 0.05;
    crew.thermal_exposure_index = 0.05;

    model.updateExposureIndices(crew, 0.0, 0.0, 0.0, config, 1.0);
    REQUIRE(crew.hypoxia_exposure_index == Approx(0.0));
    REQUIRE(crew.co2_exposure_index == Approx(0.0));
    REQUIRE(crew.thermal_exposure_index == Approx(0.0));

    for (int i = 0; i < 5; ++i) {
        model.updateExposureIndices(crew, 1.0, 1.0, 1.0, config, 1.0);
    }
    REQUIRE(crew.hypoxia_exposure_index == Approx(2.5));
    REQUIRE(crew.co2_exposure_index == Approx(2.5));
    REQUIRE(crew.thermal_exposure_index == Approx(2.5));
}

namespace {

VitalResponseConfig makeFatigueConfig() {
    VitalResponseConfig config{};
    config.fatigue_work_rate = 0.10;
    config.fatigue_eva_rate = 0.05;
    config.fatigue_recovery_rate = 0.08;
    return config;
}

ActivityMetabolicProfile makeLoadProfile(CrewActivity activity, double load) {
    ActivityMetabolicProfile profile{};
    profile.activity = activity;
    profile.activity_load = load;
    profile.oxygen_g_min = 1.0;
    profile.co2_g_min = 1.0;
    profile.heat_w = 100.0;
    return profile;
}

CrewMemberState makeFatigueState(CrewActivity activity, EVAStatus eva, double fatigue) {
    CrewMemberState crew{};
    crew.actvity = activity;
    crew.eva_status = eva;
    crew.fatigue_index = fatigue;
    return crew;
}

}

TEST_CASE("crew: high workload fatigues faster than nominal work", "[crew]") {
    CrewPhysiologyModel model;
    VitalResponseConfig config = makeFatigueConfig();
    CrewMemberConfig member = makeSensitiveCrew(1.0, 1.0, 1.0);
    member.fitness_factor = 1.0;
    member.fatigue_recovery_factor = 1.0;

    ActivityMetabolicProfile nominal = makeLoadProfile(CrewActivity::NominalWork, 0.5);
    ActivityMetabolicProfile high = makeLoadProfile(CrewActivity::HighWorkload, 0.8);

    CrewMemberState nominal_crew =
        makeFatigueState(CrewActivity::NominalWork, EVAStatus::Idle, 0.0);
    CrewMemberState high_crew =
        makeFatigueState(CrewActivity::HighWorkload, EVAStatus::Idle, 0.0);

    model.updateFatigue(nominal_crew, member, nominal, 0.0, 0.0, 0.0, config, 1.0);
    model.updateFatigue(high_crew, member, high, 0.0, 0.0, 0.0, config, 1.0);

    REQUIRE(high_crew.fatigue_index > nominal_crew.fatigue_index);
    REQUIRE(nominal_crew.fatigue_index == Approx(0.05));
    REQUIRE(high_crew.fatigue_index == Approx(0.08));
}

TEST_CASE("crew: rest recovers fatigue and identical inputs match", "[crew]") {
    CrewPhysiologyModel model;
    VitalResponseConfig config = makeFatigueConfig();
    CrewMemberConfig member = makeSensitiveCrew(1.0, 1.0, 1.0);
    member.fitness_factor = 1.0;
    member.fatigue_recovery_factor = 1.0;

    ActivityMetabolicProfile rest = makeLoadProfile(CrewActivity::Resting, 0.2);

    CrewMemberState first = makeFatigueState(CrewActivity::Resting, EVAStatus::Idle, 0.50);
    CrewMemberState second = makeFatigueState(CrewActivity::Resting, EVAStatus::Idle, 0.50);

    model.updateFatigue(first, member, rest, 0.0, 0.0, 0.0, config, 1.0);
    model.updateFatigue(second, member, rest, 0.0, 0.0, 0.0, config, 1.0);

    // accumulate 0.2*0.10=0.02, recover 0.08 → net -0.06
    REQUIRE(first.fatigue_index == Approx(0.44));
    REQUIRE(second.fatigue_index == Approx(first.fatigue_index));
}

TEST_CASE("crew: active EVA adds fatigue and fitness slows accumulation", "[crew]") {
    CrewPhysiologyModel model;
    VitalResponseConfig config = makeFatigueConfig();
    ActivityMetabolicProfile work = makeLoadProfile(CrewActivity::EVAWork, 0.5);

    CrewMemberConfig baseline = makeSensitiveCrew(1.0, 1.0, 1.0);
    baseline.fitness_factor = 1.0;
    baseline.fatigue_recovery_factor = 1.0;

    CrewMemberConfig fit = baseline;
    fit.fitness_factor = 2.0;

    CrewMemberState idle =
        makeFatigueState(CrewActivity::EVAWork, EVAStatus::Idle, 0.0);
    CrewMemberState eva =
        makeFatigueState(CrewActivity::EVAWork, EVAStatus::Working, 0.0);
    CrewMemberState fit_eva =
        makeFatigueState(CrewActivity::EVAWork, EVAStatus::Working, 0.0);

    model.updateFatigue(idle, baseline, work, 0.0, 0.0, 0.0, config, 1.0);
    model.updateFatigue(eva, baseline, work, 0.0, 0.0, 0.0, config, 1.0);
    model.updateFatigue(fit_eva, fit, work, 0.0, 0.0, 0.0, config, 1.0);

    REQUIRE(eva.fatigue_index > idle.fatigue_index);
    REQUIRE(eva.fatigue_index == Approx(0.10));
    REQUIRE(fit_eva.fatigue_index == Approx(0.05));
}

TEST_CASE("crew: fatigue clamps to 0-1", "[crew]") {
    CrewPhysiologyModel model;
    VitalResponseConfig config = makeFatigueConfig();
    config.fatigue_work_rate = 1.0;
    CrewMemberConfig member = makeSensitiveCrew(1.0, 1.0, 1.0);
    member.fitness_factor = 1.0;
    member.fatigue_recovery_factor = 1.0;

    ActivityMetabolicProfile high = makeLoadProfile(CrewActivity::HighWorkload, 1.0);
    CrewMemberState crew =
        makeFatigueState(CrewActivity::HighWorkload, EVAStatus::Working, 0.95);

    model.updateFatigue(crew, member, high, 1.0, 1.0, 1.0, config, 1.0);
    REQUIRE(crew.fatigue_index == Approx(1.0));

    ActivityMetabolicProfile sleep = makeLoadProfile(CrewActivity::Sleep, 0.0);
    crew = makeFatigueState(CrewActivity::Sleep, EVAStatus::Idle, 0.02);
    config.fatigue_recovery_rate = 0.50;
    model.updateFatigue(crew, member, sleep, 0.0, 0.0, 0.0, config, 1.0);
    REQUIRE(crew.fatigue_index == Approx(0.0));
}

TEST_CASE("crew: metabolic outputs match NASA-reference profile fixtures", "[crew]") {
    CrewPhysiologyModel model;
    VitalResponseConfig config{};

    ActivityMetabolicProfile sleep{};
    sleep.activity = CrewActivity::Sleep;
    sleep.oxygen_g_min = 0.35;
    sleep.co2_g_min = 0.40;
    sleep.heat_w = 75.0;
    sleep.activity_load = 0.1;

    ActivityMetabolicProfile nominal{};
    nominal.activity = CrewActivity::NominalWork;
    nominal.oxygen_g_min = 0.90;
    nominal.co2_g_min = 1.00;
    nominal.heat_w = 150.0;
    nominal.activity_load = 0.5;

    ActivityMetabolicProfile high{};
    high.activity = CrewActivity::HighWorkload;
    high.oxygen_g_min = 1.40;
    high.co2_g_min = 1.55;
    high.heat_w = 220.0;
    high.activity_load = 0.8;

    config.activity_profiles = {sleep, nominal, high};

    CrewMemberConfig member = makeSensitiveCrew(1.0, 1.0, 1.0);
    CrewMemberState crew{};
    crew.physical_performance_factor = 1.0;
    crew.oxygen_rationing_active = false;

    model.updateMetabolicOutputs(crew, member, nominal, config);
    REQUIRE(crew.oxygen_consumption_g_min == Approx(0.90));
    REQUIRE(crew.co2_production_g_min == Approx(1.00));
    REQUIRE(crew.heat_output_w == Approx(150.0));

    model.updateMetabolicOutputs(crew, member, high, config);
    REQUIRE(crew.oxygen_consumption_g_min == Approx(1.40));
    REQUIRE(crew.co2_production_g_min == Approx(1.55));
    REQUIRE(crew.heat_output_w == Approx(220.0));
}

TEST_CASE("crew: rationing reduces metabolic rates but not below Sleep floor", "[crew]") {
    CrewPhysiologyModel model;
    VitalResponseConfig config{};

    ActivityMetabolicProfile sleep{};
    sleep.activity = CrewActivity::Sleep;
    sleep.oxygen_g_min = 0.35;
    sleep.co2_g_min = 0.40;
    sleep.heat_w = 75.0;
    sleep.activity_load = 0.1;

    ActivityMetabolicProfile nominal{};
    nominal.activity = CrewActivity::NominalWork;
    nominal.oxygen_g_min = 0.90;
    nominal.co2_g_min = 1.00;
    nominal.heat_w = 150.0;
    nominal.activity_load = 0.5;

    config.activity_profiles = {sleep, nominal};

    CrewMemberConfig member = makeSensitiveCrew(1.0, 1.0, 1.0);
    CrewMemberState crew{};
    crew.physical_performance_factor = 1.0;
    crew.oxygen_rationing_active = true;

    model.updateMetabolicOutputs(crew, member, nominal, config);
    REQUIRE(crew.oxygen_consumption_g_min == Approx(0.675));
    REQUIRE(crew.co2_production_g_min == Approx(0.75));
    REQUIRE(crew.heat_output_w == Approx(112.5));

    ActivityMetabolicProfile near_sleep = sleep;
    near_sleep.activity = CrewActivity::Resting;
    near_sleep.oxygen_g_min = 0.40;
    near_sleep.co2_g_min = 0.45;
    near_sleep.heat_w = 80.0;
    config.activity_profiles.push_back(near_sleep);

    model.updateMetabolicOutputs(crew, member, near_sleep, config);
    REQUIRE(crew.oxygen_consumption_g_min == Approx(0.35));
    REQUIRE(crew.co2_production_g_min == Approx(0.40));
    REQUIRE(crew.heat_output_w == Approx(75.0));
}

TEST_CASE("crew: performance scales O2 CO2 and heat consistently", "[crew]") {
    CrewPhysiologyModel model;
    VitalResponseConfig config{};

    ActivityMetabolicProfile sleep{};
    sleep.activity = CrewActivity::Sleep;
    sleep.oxygen_g_min = 0.35;
    sleep.co2_g_min = 0.40;
    sleep.heat_w = 75.0;

    ActivityMetabolicProfile nominal{};
    nominal.activity = CrewActivity::NominalWork;
    nominal.oxygen_g_min = 1.00;
    nominal.co2_g_min = 1.20;
    nominal.heat_w = 200.0;

    config.activity_profiles = {sleep, nominal};

    CrewMemberConfig member = makeSensitiveCrew(1.0, 1.0, 1.0);
    CrewMemberState crew{};
    crew.physical_performance_factor = 0.5;
    crew.oxygen_rationing_active = false;

    model.updateMetabolicOutputs(crew, member, nominal, config);
    REQUIRE(crew.oxygen_consumption_g_min == Approx(0.50));
    REQUIRE(crew.co2_production_g_min == Approx(0.60));
    REQUIRE(crew.heat_output_w == Approx(100.0));
}

namespace {

VitalResponseConfig makeVitalGainsConfig() {
    VitalResponseConfig config{};
    config.hr_activity_gain = 40.0;
    config.hr_hypoxia_gain = 30.0;
    config.hr_co2_gain = 20.0;
    config.hr_thermal_gain = 15.0;
    config.hr_fatigue_gain = 25.0;
    config.hr_min_bpm = 40.0;
    config.hr_max_bpm = 180.0;

    config.rr_activity_gain = 10.0;
    config.rr_hypoxia_gain = 8.0;
    config.rr_co2_gain = 6.0;
    config.rr_thermal_gain = 4.0;
    config.rr_min_bpm = 8.0;
    config.rr_max_bpm = 40.0;

    config.spo2_hypoxia_gain = 10.0;
    config.spo2_pressure_gain = 5.0;
    config.spo2_activity_gain = 2.0;
    config.spo2_exposure_gain = 4.0;
    config.spo2_min_percent = 70.0;
    config.spo2_max_percent = 100.0;

    config.core_temp_environment_gain = 0.5;
    config.core_temp_activity_gain = 0.4;
    config.core_temp_time_constant_min = 1.0;
    config.core_temp_min_c = 35.0;
    config.core_temp_max_c = 40.0;
    return config;
}

}

TEST_CASE("crew: HR and RR rise with activity and severity", "[crew]") {
    CrewPhysiologyModel model;
    VitalResponseConfig config = makeVitalGainsConfig();
    CrewMemberConfig member = makeSensitiveCrew(1.0, 1.0, 1.0);
    member.baseline_heart_rate_bpm = 60.0;
    member.baseline_respiratory_rate_bpm = 12.0;

    ActivityMetabolicProfile rest = makeLoadProfile(CrewActivity::Resting, 0.2);
    ActivityMetabolicProfile high = makeLoadProfile(CrewActivity::HighWorkload, 0.8);
    DerivedTelemetry telemetry{};

    CrewMemberState rest_crew{};
    rest_crew.fatigue_index = 0.0;
    model.updateVitalSigns(
        rest_crew, member, rest, telemetry, 0.0, 0.0, 0.0, 0.0, config, 1.0, 22.0);

    CrewMemberState high_crew{};
    high_crew.fatigue_index = 0.0;
    model.updateVitalSigns(
        high_crew, member, high, telemetry, 0.0, 0.0, 0.0, 0.0, config, 1.0, 22.0);

    REQUIRE(high_crew.heart_rate_bpm > rest_crew.heart_rate_bpm);
    REQUIRE(high_crew.respiratory_rate_bpm > rest_crew.respiratory_rate_bpm);
    REQUIRE(rest_crew.heart_rate_bpm == Approx(68.0));
    REQUIRE(rest_crew.respiratory_rate_bpm == Approx(14.0));
    REQUIRE(high_crew.heart_rate_bpm == Approx(92.0));
    REQUIRE(high_crew.respiratory_rate_bpm == Approx(20.0));

    CrewMemberState stressed = rest_crew;
    model.updateVitalSigns(
        stressed, member, rest, telemetry, 1.0, 1.0, 0.0, 1.0, config, 1.0, 22.0);
    REQUIRE(stressed.heart_rate_bpm > rest_crew.heart_rate_bpm);
    REQUIRE(stressed.respiratory_rate_bpm > rest_crew.respiratory_rate_bpm);
    REQUIRE(stressed.heart_rate_bpm == Approx(133.0));
    REQUIRE(stressed.respiratory_rate_bpm == Approx(32.0));
}

TEST_CASE("crew: HR and RR return toward baseline under safe rest", "[crew]") {
    CrewPhysiologyModel model;
    VitalResponseConfig config = makeVitalGainsConfig();
    CrewMemberConfig member = makeSensitiveCrew(1.0, 1.0, 1.0);
    member.baseline_heart_rate_bpm = 62.0;
    member.baseline_respiratory_rate_bpm = 12.0;

    ActivityMetabolicProfile rest = makeLoadProfile(CrewActivity::Resting, 0.0);
    DerivedTelemetry telemetry{};

    CrewMemberState crew{};
    crew.fatigue_index = 0.0;
    crew.heart_rate_bpm = 140.0;
    crew.respiratory_rate_bpm = 30.0;

    model.updateVitalSigns(
        crew, member, rest, telemetry, 0.0, 0.0, 0.0, 0.0, config, 1.0, 22.0);

    REQUIRE(crew.heart_rate_bpm == Approx(62.0));
    REQUIRE(crew.respiratory_rate_bpm == Approx(12.0));
}

TEST_CASE("crew: HR and RR clamp to configured bounds", "[crew]") {
    CrewPhysiologyModel model;
    VitalResponseConfig config = makeVitalGainsConfig();
    config.hr_activity_gain = 200.0;
    config.rr_activity_gain = 100.0;
    config.hr_max_bpm = 120.0;
    config.rr_max_bpm = 25.0;

    CrewMemberConfig member = makeSensitiveCrew(1.0, 1.0, 1.0);
    member.baseline_heart_rate_bpm = 60.0;
    member.baseline_respiratory_rate_bpm = 12.0;

    ActivityMetabolicProfile high = makeLoadProfile(CrewActivity::HighWorkload, 1.0);
    DerivedTelemetry telemetry{};
    CrewMemberState crew{};
    crew.fatigue_index = 1.0;

    model.updateVitalSigns(
        crew, member, high, telemetry, 1.0, 1.0, 0.0, 1.0, config, 1.0, 22.0);

    REQUIRE(crew.heart_rate_bpm == Approx(120.0));
    REQUIRE(crew.respiratory_rate_bpm == Approx(25.0));
}

TEST_CASE("crew: SpO2 declines with hypoxia and recovers when safe", "[crew]") {
    CrewPhysiologyModel model;
    VitalResponseConfig config = makeVitalGainsConfig();
    config.core_temp_time_constant_min = 0.0;

    CrewMemberConfig member = makeSensitiveCrew(1.0, 1.0, 1.0);
    member.baseline_spo2_percent = 98.0;
    member.baseline_core_temperature_c = 36.8;

    ActivityMetabolicProfile rest = makeLoadProfile(CrewActivity::Resting, 0.0);
    DerivedTelemetry telemetry{};

    CrewMemberState mild{};
    mild.spo2_percent = 98.0;
    mild.core_temperature_c = 36.8;
    mild.hypoxia_exposure_index = 0.0;
    model.updateVitalSigns(
        mild, member, rest, telemetry, 0.5, 0.0, 0.0, 0.0, config, 1.0, 22.0);

    CrewMemberState severe{};
    severe.spo2_percent = 98.0;
    severe.core_temperature_c = 36.8;
    severe.hypoxia_exposure_index = 0.0;
    model.updateVitalSigns(
        severe, member, rest, telemetry, 1.0, 0.0, 0.0, 0.0, config, 1.0, 22.0);

    REQUIRE(severe.spo2_percent < mild.spo2_percent);
    REQUIRE(mild.spo2_percent == Approx(93.0));
    REQUIRE(severe.spo2_percent == Approx(88.0));

    severe.hypoxia_exposure_index = 0.0;
    model.updateVitalSigns(
        severe, member, rest, telemetry, 0.0, 0.0, 0.0, 0.0, config, 1.0, 22.0);
    REQUIRE(severe.spo2_percent == Approx(98.0));
}

TEST_CASE("crew: prolonged hypoxia exposure lowers SpO2 more than brief", "[crew]") {
    CrewPhysiologyModel model;
    VitalResponseConfig config = makeVitalGainsConfig();
    config.core_temp_time_constant_min = 0.0;

    CrewMemberConfig member = makeSensitiveCrew(1.0, 1.0, 1.0);
    member.baseline_spo2_percent = 98.0;
    member.baseline_core_temperature_c = 36.8;

    ActivityMetabolicProfile rest = makeLoadProfile(CrewActivity::Resting, 0.0);
    DerivedTelemetry telemetry{};

    CrewMemberState brief{};
    brief.spo2_percent = 98.0;
    brief.core_temperature_c = 36.8;
    brief.hypoxia_exposure_index = 0.0;
    model.updateVitalSigns(
        brief, member, rest, telemetry, 1.0, 0.0, 0.0, 0.0, config, 1.0, 22.0);

    CrewMemberState prolonged{};
    prolonged.spo2_percent = 98.0;
    prolonged.core_temperature_c = 36.8;
    prolonged.hypoxia_exposure_index = 1.0;
    model.updateVitalSigns(
        prolonged, member, rest, telemetry, 1.0, 0.0, 0.0, 0.0, config, 1.0, 22.0);

    REQUIRE(prolonged.spo2_percent < brief.spo2_percent);
    REQUIRE(brief.spo2_percent == Approx(88.0));
    REQUIRE(prolonged.spo2_percent == Approx(84.0));
}

TEST_CASE("crew: core temperature lags and follows cabin direction", "[crew]") {
    CrewPhysiologyModel model;
    VitalResponseConfig config = makeVitalGainsConfig();
    config.core_temp_time_constant_min = 1.0;

    CrewMemberConfig member = makeSensitiveCrew(1.0, 1.0, 1.0);
    member.baseline_spo2_percent = 98.0;
    member.baseline_core_temperature_c = 36.8;

    ActivityMetabolicProfile rest = makeLoadProfile(CrewActivity::Resting, 0.0);
    DerivedTelemetry telemetry{};

    CrewMemberState hot{};
    hot.spo2_percent = 98.0;
    hot.core_temperature_c = 36.8;
    model.updateVitalSigns(
        hot, member, rest, telemetry, 0.0, 0.0, 0.0, 0.0, config, 1.0, 40.0);

    CrewMemberState cold{};
    cold.spo2_percent = 98.0;
    cold.core_temperature_c = 36.8;
    model.updateVitalSigns(
        cold, member, rest, telemetry, 0.0, 0.0, 0.0, 0.0, config, 1.0, 30.0);

    // target_hot = 36.8 + 0.5*(40-36.8) = 38.4; blend 0.5 → 37.6
    REQUIRE(hot.core_temperature_c == Approx(37.6));
    // target_cold = 36.8 + 0.5*(30-36.8) = 33.4 → clamp 35.0; blend 0.5 → 35.9
    REQUIRE(cold.core_temperature_c == Approx(35.9));
    REQUIRE(hot.core_temperature_c > 36.8);
    REQUIRE(cold.core_temperature_c < 36.8);
    REQUIRE(hot.core_temperature_c < 38.4);
}

TEST_CASE("crew: performance declines with exposure and recovers when clear", "[crew]") {
    CrewPhysiologyModel model;
    VitalResponseConfig config{};
    config.cognitive_hypoxia_weight = 0.25;
    config.cognitive_co2_weight = 0.25;
    config.cognitive_thermal_weight = 0.25;
    config.cognitive_fatigue_weight = 0.25;
    config.physical_hypoxia_weight = 0.20;
    config.physical_co2_weight = 0.20;
    config.physical_thermal_weight = 0.20;
    config.physical_fatigue_weight = 0.20;

    ActivityMetabolicProfile rest = makeLoadProfile(CrewActivity::Resting, 0.0);
    CrewMemberState crew{};
    crew.hypoxia_exposure_index = 0.0;
    crew.co2_exposure_index = 0.0;
    crew.thermal_exposure_index = 0.0;
    crew.fatigue_index = 0.0;

    model.updatePerformance(crew, rest, config);
    REQUIRE(crew.cognitive_performance_factor == Approx(1.0));
    REQUIRE(crew.physical_performance_factor == Approx(1.0));

    crew.hypoxia_exposure_index = 1.0;
    model.updatePerformance(crew, rest, config);
    REQUIRE(crew.cognitive_performance_factor == Approx(0.75));
    REQUIRE(crew.physical_performance_factor == Approx(0.80));

    double impaired_cognitive = crew.cognitive_performance_factor;
    crew.hypoxia_exposure_index = 0.0;
    model.updatePerformance(crew, rest, config);
    REQUIRE(crew.cognitive_performance_factor > impaired_cognitive);
    REQUIRE(crew.cognitive_performance_factor == Approx(1.0));
}

TEST_CASE("crew: activity load and fatigue only reduce performance", "[crew]") {
    CrewPhysiologyModel model;
    VitalResponseConfig config{};
    config.cognitive_hypoxia_weight = 0.0;
    config.cognitive_co2_weight = 0.0;
    config.cognitive_thermal_weight = 0.0;
    config.cognitive_fatigue_weight = 0.5;
    config.physical_hypoxia_weight = 0.0;
    config.physical_co2_weight = 0.0;
    config.physical_thermal_weight = 0.0;
    config.physical_fatigue_weight = 0.5;

    ActivityMetabolicProfile idle = makeLoadProfile(CrewActivity::Resting, 0.0);
    ActivityMetabolicProfile work = makeLoadProfile(CrewActivity::HighWorkload, 0.8);

    CrewMemberState rested{};
    rested.fatigue_index = 0.0;
    model.updatePerformance(rested, idle, config);

    CrewMemberState loaded{};
    loaded.fatigue_index = 0.0;
    model.updatePerformance(loaded, work, config);

    REQUIRE(loaded.cognitive_performance_factor < rested.cognitive_performance_factor);
    REQUIRE(loaded.physical_performance_factor < rested.physical_performance_factor);
    REQUIRE(loaded.cognitive_performance_factor == Approx(0.6));
    REQUIRE(loaded.physical_performance_factor == Approx(0.6));

    CrewMemberState fatigued{};
    fatigued.fatigue_index = 0.4;
    model.updatePerformance(fatigued, idle, config);
    REQUIRE(fatigued.cognitive_performance_factor == Approx(0.8));
    REQUIRE(fatigued.physical_performance_factor == Approx(0.8));
}

TEST_CASE("crew: performance factors clamp to 0-1", "[crew][sec17]") {
    CrewPhysiologyModel model;
    VitalResponseConfig config{};
    config.cognitive_hypoxia_weight = 1.0;
    config.cognitive_co2_weight = 1.0;
    config.cognitive_thermal_weight = 1.0;
    config.cognitive_fatigue_weight = 1.0;
    config.physical_hypoxia_weight = 1.0;
    config.physical_co2_weight = 1.0;
    config.physical_thermal_weight = 1.0;
    config.physical_fatigue_weight = 1.0;

    ActivityMetabolicProfile work = makeLoadProfile(CrewActivity::HighWorkload, 1.0);
    CrewMemberState crew{};
    crew.hypoxia_exposure_index = 2.0;
    crew.co2_exposure_index = 2.0;
    crew.thermal_exposure_index = 2.0;
    crew.fatigue_index = 1.0;

    model.updatePerformance(crew, work, config);
    REQUIRE(crew.cognitive_performance_factor == Approx(0.0));
    REQUIRE(crew.physical_performance_factor == Approx(0.0));
}

namespace {

VitalResponseConfig makeAlarmConfig() {
    VitalResponseConfig config{};
    config.spo2_warning_percent = 94.0;
    config.spo2_critical_percent = 88.0;
    config.heart_rate_warning_bpm = 100.0;
    config.respiratory_rate_warning_bpm = 20.0;
    config.core_temp_low_c = 36.0;
    config.core_temp_high_c = 38.0;
    config.fatigue_warning_fraction = 0.6;
    config.performance_abort_fraction = 0.3;
    return config;
}

CrewMemberState makeHealthyCrew() {
    CrewMemberState crew{};
    crew.actvity = CrewActivity::NominalWork;
    crew.eva_status = EVAStatus::Idle;
    crew.spo2_percent = 98.0;
    crew.heart_rate_bpm = 70.0;
    crew.respiratory_rate_bpm = 14.0;
    crew.core_temperature_c = 36.8;
    crew.fatigue_index = 0.1;
    crew.hypoxia_exposure_index = 0.0;
    crew.co2_exposure_index = 0.0;
    crew.thermal_exposure_index = 0.0;
    crew.cognitive_performance_factor = 1.0;
    crew.physical_performance_factor = 1.0;
    crew.health_status = CrewHealthStatus::Nominal;
    return crew;
}

bool hasAlarm(const CrewMemberState& crew, CrewAlarmType type) {
    for (CrewAlarmType alarm : crew.active_alarms) {
        if (alarm == type) {
            return true;
        }
    }
    return false;
}

}

TEST_CASE("crew: health alarms fire for each configured threshold", "[crew]") {
    CrewPhysiologyModel model;
    VitalResponseConfig config = makeAlarmConfig();
    DerivedTelemetry telemetry{};
    telemetry.eva.eva_safe_return_margin_min = 100.0;
    vector<TimelineEvent> events;

    CrewMemberState hypoxia = makeHealthyCrew();
    hypoxia.spo2_percent = 93.0;
    model.updateHealthStatusAndAlarms(hypoxia, telemetry, config, events, 0);
    REQUIRE(hasAlarm(hypoxia, CrewAlarmType::Hypoxia));
    REQUIRE(hypoxia.health_status == CrewHealthStatus::Impaired);

    CrewMemberState critical_o2 = makeHealthyCrew();
    critical_o2.spo2_percent = 85.0;
    model.updateHealthStatusAndAlarms(critical_o2, telemetry, config, events, 0);
    REQUIRE(hasAlarm(critical_o2, CrewAlarmType::Hypoxia));
    REQUIRE(critical_o2.health_status == CrewHealthStatus::Critical);

    CrewMemberState co2 = makeHealthyCrew();
    co2.co2_exposure_index = 1.2;
    model.updateHealthStatusAndAlarms(co2, telemetry, config, events, 0);
    REQUIRE(hasAlarm(co2, CrewAlarmType::Hypercapnia));
    REQUIRE(co2.health_status == CrewHealthStatus::Critical);

    CrewMemberState hr = makeHealthyCrew();
    hr.heart_rate_bpm = 110.0;
    model.updateHealthStatusAndAlarms(hr, telemetry, config, events, 0);
    REQUIRE(hasAlarm(hr, CrewAlarmType::Tachycardia));
    REQUIRE(hr.health_status == CrewHealthStatus::ElevatedStress);

    CrewMemberState rr = makeHealthyCrew();
    rr.respiratory_rate_bpm = 22.0;
    model.updateHealthStatusAndAlarms(rr, telemetry, config, events, 0);
    REQUIRE(hasAlarm(rr, CrewAlarmType::Respiratory));
    REQUIRE(rr.health_status == CrewHealthStatus::ElevatedStress);

    CrewMemberState thermal = makeHealthyCrew();
    thermal.core_temperature_c = 38.5;
    model.updateHealthStatusAndAlarms(thermal, telemetry, config, events, 0);
    REQUIRE(hasAlarm(thermal, CrewAlarmType::Thermal));
    REQUIRE(thermal.health_status == CrewHealthStatus::Impaired);

    CrewMemberState fatigue = makeHealthyCrew();
    fatigue.fatigue_index = 0.7;
    model.updateHealthStatusAndAlarms(fatigue, telemetry, config, events, 0);
    REQUIRE(hasAlarm(fatigue, CrewAlarmType::Fatigue));
    REQUIRE(fatigue.health_status == CrewHealthStatus::Impaired);

    CrewMemberState abort = makeHealthyCrew();
    abort.cognitive_performance_factor = 0.2;
    model.updateHealthStatusAndAlarms(abort, telemetry, config, events, 0);
    REQUIRE(hasAlarm(abort, CrewAlarmType::Performance));
    REQUIRE(abort.health_status == CrewHealthStatus::Incapacitated);

    CrewMemberState eva = makeHealthyCrew();
    eva.eva_status = EVAStatus::Working;
    telemetry.eva.eva_safe_return_margin_min = -5.0;
    model.updateHealthStatusAndAlarms(eva, telemetry, config, events, 0);
    REQUIRE(hasAlarm(eva, CrewAlarmType::EVAReturn));
    REQUIRE(eva.health_status == CrewHealthStatus::Critical);
}

TEST_CASE("crew: clearing conditions removes non-latched alarms", "[crew]") {
    CrewPhysiologyModel model;
    VitalResponseConfig config = makeAlarmConfig();
    DerivedTelemetry telemetry{};
    telemetry.eva.eva_safe_return_margin_min = 100.0;
    vector<TimelineEvent> events;

    CrewMemberState crew = makeHealthyCrew();
    crew.spo2_percent = 92.0;
    crew.heart_rate_bpm = 105.0;
    model.updateHealthStatusAndAlarms(crew, telemetry, config, events, 0);
    REQUIRE(hasAlarm(crew, CrewAlarmType::Hypoxia));
    REQUIRE(hasAlarm(crew, CrewAlarmType::Tachycardia));
    REQUIRE(crew.health_status == CrewHealthStatus::Impaired);

    crew.spo2_percent = 98.0;
    crew.heart_rate_bpm = 70.0;
    model.updateHealthStatusAndAlarms(crew, telemetry, config, events, 0);
    REQUIRE(crew.active_alarms.empty());
    REQUIRE(crew.health_status == CrewHealthStatus::Nominal);
}

TEST_CASE("crew: nominal when all vitals are inside thresholds", "[crew]") {
    CrewPhysiologyModel model;
    VitalResponseConfig config = makeAlarmConfig();
    DerivedTelemetry telemetry{};
    telemetry.eva.eva_safe_return_margin_min = 100.0;
    vector<TimelineEvent> events;

    CrewMemberState crew = makeHealthyCrew();
    model.updateHealthStatusAndAlarms(crew, telemetry, config, events, 0);
    REQUIRE(crew.active_alarms.empty());
    REQUIRE(crew.health_status == CrewHealthStatus::Nominal);
}

TEST_CASE(
    "crew: health transition events occur once per status change",
    "[crew][sec17]") {
    CrewPhysiologyModel model;
    VitalResponseConfig config = makeAlarmConfig();
    DerivedTelemetry telemetry{};
    telemetry.eva.eva_safe_return_margin_min = 100.0;
    vector<TimelineEvent> events;

    CrewMemberState crew = makeHealthyCrew();
    crew.crew_id = "crew_01";

    // Nominal -> ElevatedStress
    crew.heart_rate_bpm = 110.0;
    model.updateHealthStatusAndAlarms(crew, telemetry, config, events, 1);
    REQUIRE(crew.health_status == CrewHealthStatus::ElevatedStress);
    REQUIRE(events.size() == 1);
    REQUIRE(events[0].event_type == "health_transition");
    REQUIRE(events[0].time_min == 1);

    // hold ElevatedStress: no new event
    model.updateHealthStatusAndAlarms(crew, telemetry, config, events, 2);
    REQUIRE(crew.health_status == CrewHealthStatus::ElevatedStress);
    REQUIRE(events.size() == 1);

    // ElevatedStress -> Impaired
    crew.spo2_percent = 92.0;
    model.updateHealthStatusAndAlarms(crew, telemetry, config, events, 3);
    REQUIRE(crew.health_status == CrewHealthStatus::Impaired);
    REQUIRE(events.size() == 2);
    REQUIRE(events[1].event_type == "health_transition");
    REQUIRE(events[1].time_min == 3);

    // hold Impaired
    model.updateHealthStatusAndAlarms(crew, telemetry, config, events, 4);
    REQUIRE(events.size() == 2);

    // Impaired -> Nominal
    crew.spo2_percent = 98.0;
    crew.heart_rate_bpm = 70.0;
    model.updateHealthStatusAndAlarms(crew, telemetry, config, events, 5);
    REQUIRE(crew.health_status == CrewHealthStatus::Nominal);
    REQUIRE(events.size() == 3);
    REQUIRE(events[2].event_type == "health_transition");

    // hold Nominal
    model.updateHealthStatusAndAlarms(crew, telemetry, config, events, 6);
    REQUIRE(events.size() == 3);
}

namespace {

vector<ParameterSource> buildPhysiologyParameterSources();

ScenarioConfig makeFullPhysiologyConfig() {
    ScenarioConfig config = makeSeverityConfig();

    ActivityMetabolicProfile sleep{};
    sleep.activity = CrewActivity::Sleep;
    sleep.oxygen_g_min = 0.35;
    sleep.co2_g_min = 0.40;
    sleep.heat_w = 75.0;
    sleep.activity_load = 0.1;

    ActivityMetabolicProfile resting{};
    resting.activity = CrewActivity::Resting;
    resting.oxygen_g_min = 0.50;
    resting.co2_g_min = 0.60;
    resting.heat_w = 100.0;
    resting.activity_load = 0.2;

    config.vital_response.activity_profiles = {sleep, resting};

    config.vital_response.hypoxia_accumulation_rate = 0.10;
    config.vital_response.co2_accumulation_rate = 0.08;
    config.vital_response.thermal_accumulation_rate = 0.06;
    config.vital_response.hypoxia_recovery_rate = 0.05;
    config.vital_response.co2_recovery_rate = 0.04;
    config.vital_response.thermal_recovery_rate = 0.03;

    config.vital_response.fatigue_work_rate = 0.05;
    config.vital_response.fatigue_eva_rate = 0.05;
    config.vital_response.fatigue_recovery_rate = 0.08;

    config.vital_response.hr_activity_gain = 40.0;
    config.vital_response.hr_hypoxia_gain = 30.0;
    config.vital_response.hr_co2_gain = 20.0;
    config.vital_response.hr_thermal_gain = 15.0;
    config.vital_response.hr_fatigue_gain = 25.0;
    config.vital_response.hr_min_bpm = 40.0;
    config.vital_response.hr_max_bpm = 180.0;

    config.vital_response.rr_activity_gain = 10.0;
    config.vital_response.rr_hypoxia_gain = 8.0;
    config.vital_response.rr_co2_gain = 6.0;
    config.vital_response.rr_thermal_gain = 4.0;
    config.vital_response.rr_min_bpm = 8.0;
    config.vital_response.rr_max_bpm = 40.0;

    config.vital_response.spo2_hypoxia_gain = 10.0;
    config.vital_response.spo2_pressure_gain = 5.0;
    config.vital_response.spo2_activity_gain = 2.0;
    config.vital_response.spo2_exposure_gain = 4.0;
    config.vital_response.spo2_min_percent = 70.0;
    config.vital_response.spo2_max_percent = 100.0;

    config.vital_response.core_temp_environment_gain = 0.0;
    config.vital_response.core_temp_activity_gain = 0.4;
    config.vital_response.core_temp_time_constant_min = 0.0;
    config.vital_response.core_temp_min_c = 35.0;
    config.vital_response.core_temp_max_c = 40.0;

    config.vital_response.cognitive_hypoxia_weight = 0.25;
    config.vital_response.cognitive_co2_weight = 0.25;
    config.vital_response.cognitive_thermal_weight = 0.25;
    config.vital_response.cognitive_fatigue_weight = 0.25;
    config.vital_response.physical_hypoxia_weight = 0.20;
    config.vital_response.physical_co2_weight = 0.20;
    config.vital_response.physical_thermal_weight = 0.20;
    config.vital_response.physical_fatigue_weight = 0.20;

    config.vital_response.spo2_warning_percent = 94.0;
    config.vital_response.spo2_critical_percent = 88.0;
    config.vital_response.heart_rate_warning_bpm = 100.0;
    config.vital_response.respiratory_rate_warning_bpm = 20.0;
    config.vital_response.core_temp_low_c = 36.0;
    config.vital_response.core_temp_high_c = 38.0;
    config.vital_response.fatigue_warning_fraction = 0.6;
    config.vital_response.performance_abort_fraction = 0.3;

    config.parameter_sources = buildPhysiologyParameterSources();
    return config;
}

vector<ParameterSource> buildPhysiologyParameterSources() {
    vector<ParameterSource> sources;

    auto add = [&](const string& name, SourceClassification classification,
                   const string& label, const string& note) {
        ParameterSource source{};
        source.parameter_name = name;
        source.classification = classification;
        source.source_label = label;
        source.note = note;
        sources.push_back(source);
    };

    // NASA standards used by environmental severity
    add("inspired_o2_warning_mmhg", SourceClassification::NASAStandard,
        "NASA inspired-O2 warning limit", "hypoxia severity safe threshold");
    add("inspired_o2_failure_mmhg", SourceClassification::NASAStandard,
        "NASA inspired-O2 failure limit", "hypoxia severity critical threshold");
    add("co2_one_hour_limit_mmhg", SourceClassification::NASAStandard,
        "NASA CO2 one-hour limit", "CO2 severity critical threshold");
    add("pressure_warning_low_kpa", SourceClassification::NASAStandard,
        "NASA cabin pressure warning", "pressure severity safe threshold");
    add("pressure_failure_low_kpa", SourceClassification::NASAStandard,
        "NASA cabin pressure failure", "pressure severity critical threshold");

    // NASA-reference metabolic baselines
    add("activity_metabolic_profiles", SourceClassification::NASAReference,
        "NASA metabolic design reference",
        "Sleep/Nominal/HighWorkload/EVA O2 CO2 heat rates");

    // ARES vital-response assumptions
    add("hypoxia_accumulation_rate", SourceClassification::ARESAssumption,
        "ARES exposure model", "hypoxia exposure accumulation");
    add("co2_accumulation_rate", SourceClassification::ARESAssumption,
        "ARES exposure model", "CO2 exposure accumulation");
    add("thermal_accumulation_rate", SourceClassification::ARESAssumption,
        "ARES exposure model", "thermal exposure accumulation");
    add("hypoxia_recovery_rate", SourceClassification::ARESAssumption,
        "ARES exposure model", "hypoxia exposure recovery");
    add("co2_recovery_rate", SourceClassification::ARESAssumption,
        "ARES exposure model", "CO2 exposure recovery");
    add("thermal_recovery_rate", SourceClassification::ARESAssumption,
        "ARES exposure model", "thermal exposure recovery");
    add("fatigue_work_rate", SourceClassification::ARESAssumption,
        "ARES fatigue model", "workload fatigue accumulation");
    add("fatigue_eva_rate", SourceClassification::ARESAssumption,
        "ARES fatigue model", "EVA fatigue accumulation");
    add("fatigue_recovery_rate", SourceClassification::ARESAssumption,
        "ARES fatigue model", "rest fatigue recovery");
    add("hr_activity_gain", SourceClassification::ARESAssumption,
        "ARES vital response", "heart-rate activity gain");
    add("hr_hypoxia_gain", SourceClassification::ARESAssumption,
        "ARES vital response", "heart-rate hypoxia gain");
    add("hr_co2_gain", SourceClassification::ARESAssumption,
        "ARES vital response", "heart-rate CO2 gain");
    add("hr_thermal_gain", SourceClassification::ARESAssumption,
        "ARES vital response", "heart-rate thermal gain");
    add("hr_fatigue_gain", SourceClassification::ARESAssumption,
        "ARES vital response", "heart-rate fatigue gain");
    add("rr_activity_gain", SourceClassification::ARESAssumption,
        "ARES vital response", "respiratory-rate activity gain");
    add("rr_hypoxia_gain", SourceClassification::ARESAssumption,
        "ARES vital response", "respiratory-rate hypoxia gain");
    add("rr_co2_gain", SourceClassification::ARESAssumption,
        "ARES vital response", "respiratory-rate CO2 gain");
    add("rr_thermal_gain", SourceClassification::ARESAssumption,
        "ARES vital response", "respiratory-rate thermal gain");
    add("spo2_hypoxia_gain", SourceClassification::ARESAssumption,
        "ARES vital response", "SpO2 hypoxia gain");
    add("spo2_pressure_gain", SourceClassification::ARESAssumption,
        "ARES vital response", "SpO2 pressure gain");
    add("spo2_activity_gain", SourceClassification::ARESAssumption,
        "ARES vital response", "SpO2 activity gain");
    add("spo2_exposure_gain", SourceClassification::ARESAssumption,
        "ARES vital response", "SpO2 cumulative-exposure gain");
    add("core_temp_environment_gain", SourceClassification::ARESAssumption,
        "ARES vital response", "core-temp cabin coupling");
    add("core_temp_activity_gain", SourceClassification::ARESAssumption,
        "ARES vital response", "core-temp activity heat");
    add("core_temp_time_constant_min", SourceClassification::ARESAssumption,
        "ARES vital response", "core-temp / SpO2 lag");
    add("cognitive_hypoxia_weight", SourceClassification::ARESAssumption,
        "ARES performance model", "cognitive hypoxia weight");
    add("cognitive_co2_weight", SourceClassification::ARESAssumption,
        "ARES performance model", "cognitive CO2 weight");
    add("cognitive_thermal_weight", SourceClassification::ARESAssumption,
        "ARES performance model", "cognitive thermal weight");
    add("cognitive_fatigue_weight", SourceClassification::ARESAssumption,
        "ARES performance model", "cognitive fatigue weight");
    add("physical_hypoxia_weight", SourceClassification::ARESAssumption,
        "ARES performance model", "physical hypoxia weight");
    add("physical_co2_weight", SourceClassification::ARESAssumption,
        "ARES performance model", "physical CO2 weight");
    add("physical_thermal_weight", SourceClassification::ARESAssumption,
        "ARES performance model", "physical thermal weight");
    add("physical_fatigue_weight", SourceClassification::ARESAssumption,
        "ARES performance model", "physical fatigue weight");
    add("oxygen_rationing_factor", SourceClassification::ARESAssumption,
        "ARES rationing policy", "hardcoded 0.75 metabolic scale under rationing");

    return sources;
}

CrewMemberConfig makePhysiologyMember() {
    CrewMemberConfig member = makeSensitiveCrew(1.0, 1.0, 1.0);
    member.baseline_heart_rate_bpm = 62.0;
    member.baseline_respiratory_rate_bpm = 12.0;
    member.baseline_spo2_percent = 98.0;
    member.baseline_core_temperature_c = 36.8;
    member.fitness_factor = 1.0;
    member.fatigue_recovery_factor = 1.0;
    member.initial_activity = CrewActivity::Resting;
    return member;
}

CrewMemberState makeBaselineCrewState(const CrewMemberConfig& member) {
    CrewMemberState crew{};
    crew.crew_id = member.crew_id;
    crew.actvity = CrewActivity::Resting;
    crew.eva_status = EVAStatus::Idle;
    crew.location_module = "hab_core";
    crew.heart_rate_bpm = member.baseline_heart_rate_bpm;
    crew.respiratory_rate_bpm = member.baseline_respiratory_rate_bpm;
    crew.spo2_percent = member.baseline_spo2_percent;
    crew.core_temperature_c = member.baseline_core_temperature_c;
    crew.hypoxia_exposure_index = 0.0;
    crew.co2_exposure_index = 0.0;
    crew.thermal_exposure_index = 0.0;
    crew.fatigue_index = 0.0;
    crew.cognitive_performance_factor = 1.0;
    crew.physical_performance_factor = 1.0;
    crew.oxygen_consumption_g_min = 0.50;
    crew.co2_production_g_min = 0.60;
    crew.heat_output_w = 100.0;
    crew.oxygen_rationing_active = false;
    crew.health_status = CrewHealthStatus::Nominal;
    return crew;
}

}

TEST_CASE(
    "crew: lower inspired O2 never improves hypoxia severity or SpO2",
    "[crew][sec17]") {
    CrewPhysiologyModel model;
    ScenarioConfig config = makeFullPhysiologyConfig();
    CrewMemberConfig member = makePhysiologyMember();
    config.crew_roster = {member};

    const double inspired_levels[] = {150.0, 120.0, 105.0, 90.0, 80.0};
    double prev_severity = -1.0;
    double prev_spo2 = 1e9;

    for (double inspired : inspired_levels) {
        double severity = model.calculateHypoxiaSeverity(
            makeEnvTelemetry(inspired, 80.0, 0.0), config, member);
        REQUIRE(severity >= prev_severity);
        prev_severity = severity;

        CrewMemberState crew = makeBaselineCrewState(member);
        DerivedTelemetry telemetry = makeEnvTelemetry(inspired, 80.0, 0.0);
        telemetry.eva.eva_safe_return_margin_min = 200.0;
        vector<TimelineEvent> events;
        model.updateCrewMember(
            crew, member, telemetry, config, 60.0, 22.0, events, 0);
        REQUIRE(crew.spo2_percent <= prev_spo2);
        prev_spo2 = crew.spo2_percent;
    }
}

TEST_CASE(
    "crew: higher CO2 never reduces CO2 severity",
    "[crew][sec17]") {
    CrewPhysiologyModel model;
    ScenarioConfig config = makeSeverityConfig();
    CrewMemberConfig crew = makeSensitiveCrew(1.0, 1.0, 1.0);

    const double co2_levels[] = {0.0, 2.0, 4.0, 6.0, 8.0, 10.0};
    double prev = -1.0;
    for (double co2 : co2_levels) {
        double severity = model.calculateCo2Severity(
            makeEnvTelemetry(150.0, 80.0, co2), config, crew);
        REQUIRE(severity >= prev);
        prev = severity;
    }
}

TEST_CASE(
    "crew: higher activity increases metabolic O2 CO2 and heat",
    "[crew][sec17]") {
    CrewPhysiologyModel model;
    VitalResponseConfig config{};

    ActivityMetabolicProfile sleep{};
    sleep.activity = CrewActivity::Sleep;
    sleep.oxygen_g_min = 0.35;
    sleep.co2_g_min = 0.40;
    sleep.heat_w = 75.0;
    sleep.activity_load = 0.1;

    ActivityMetabolicProfile nominal{};
    nominal.activity = CrewActivity::NominalWork;
    nominal.oxygen_g_min = 0.90;
    nominal.co2_g_min = 1.00;
    nominal.heat_w = 150.0;
    nominal.activity_load = 0.5;

    ActivityMetabolicProfile high{};
    high.activity = CrewActivity::HighWorkload;
    high.oxygen_g_min = 1.40;
    high.co2_g_min = 1.55;
    high.heat_w = 220.0;
    high.activity_load = 0.8;

    config.activity_profiles = {sleep, nominal, high};

    CrewMemberConfig member = makeSensitiveCrew(1.0, 1.0, 1.0);
    CrewMemberState state{};
    state.physical_performance_factor = 1.0;
    state.oxygen_rationing_active = false;

    model.updateMetabolicOutputs(state, member, sleep, config);
    const double o2_sleep = state.oxygen_consumption_g_min;
    const double co2_sleep = state.co2_production_g_min;
    const double heat_sleep = state.heat_output_w;

    model.updateMetabolicOutputs(state, member, nominal, config);
    const double o2_nominal = state.oxygen_consumption_g_min;
    const double co2_nominal = state.co2_production_g_min;
    const double heat_nominal = state.heat_output_w;

    model.updateMetabolicOutputs(state, member, high, config);
    REQUIRE(o2_sleep < o2_nominal);
    REQUIRE(o2_nominal < state.oxygen_consumption_g_min);
    REQUIRE(co2_sleep < co2_nominal);
    REQUIRE(co2_nominal < state.co2_production_g_min);
    REQUIRE(heat_sleep < heat_nominal);
    REQUIRE(heat_nominal < state.heat_output_w);
}

TEST_CASE(
    "crew: performance declines monotonically with graded hypoxia stress",
    "[crew][sec17]") {
    CrewPhysiologyModel model;
    VitalResponseConfig config{};
    config.cognitive_hypoxia_weight = 0.25;
    config.cognitive_co2_weight = 0.0;
    config.cognitive_thermal_weight = 0.0;
    config.cognitive_fatigue_weight = 0.0;
    config.physical_hypoxia_weight = 0.20;
    config.physical_co2_weight = 0.0;
    config.physical_thermal_weight = 0.0;
    config.physical_fatigue_weight = 0.0;

    ActivityMetabolicProfile rest = makeLoadProfile(CrewActivity::Resting, 0.0);
    const double exposures[] = {0.0, 0.25, 0.5, 0.75, 1.0};
    double prev_cog = 1.1;
    double prev_phys = 1.1;

    for (double exposure : exposures) {
        CrewMemberState crew{};
        crew.hypoxia_exposure_index = exposure;
        crew.co2_exposure_index = 0.0;
        crew.thermal_exposure_index = 0.0;
        crew.fatigue_index = 0.0;
        model.updatePerformance(crew, rest, config);

        REQUIRE(crew.cognitive_performance_factor >= 0.0);
        REQUIRE(crew.cognitive_performance_factor <= 1.0);
        REQUIRE(crew.physical_performance_factor >= 0.0);
        REQUIRE(crew.physical_performance_factor <= 1.0);
        REQUIRE(crew.cognitive_performance_factor <= prev_cog);
        REQUIRE(crew.physical_performance_factor <= prev_phys);
        prev_cog = crew.cognitive_performance_factor;
        prev_phys = crew.physical_performance_factor;
    }
}

TEST_CASE(
    "crew: same input produces identical vital telemetry (deterministic, no RNG seed)",
    "[crew][sec17]") {
    CrewPhysiologyModel model;
    ScenarioConfig config = makeFullPhysiologyConfig();
    CrewMemberConfig member = makePhysiologyMember();
    config.crew_roster = {member};

    DerivedTelemetry telemetry{};
    telemetry.atmosphere.inspired_oxygen_mmhg = 105.0;
    telemetry.atmosphere.cabin_pressure_kpa = 80.0;
    telemetry.atmosphere.co2_one_hour_avg_mmhg = 2.0;
    telemetry.eva.eva_safe_return_margin_min = 200.0;

    SimulationState a{};
    a.cabin_temperature_c = 22.0;
    a.crew = {makeBaselineCrewState(member)};
    SimulationState b = a;

    vector<TimelineEvent> events_a;
    vector<TimelineEvent> events_b;
    model.updateAllCrew(a, config, telemetry, 60.0, events_a);
    model.updateAllCrew(b, config, telemetry, 60.0, events_b);

    auto vitals_a = model.buildCrewVitalsTelemetry(a, config);
    auto vitals_b = model.buildCrewVitalsTelemetry(b, config);
    REQUIRE(vitals_a.size() == 1);
    REQUIRE(vitals_b.size() == 1);
    REQUIRE(vitals_a[0].heart_rate_bpm == Approx(vitals_b[0].heart_rate_bpm));
    REQUIRE(vitals_a[0].respiratory_rate_bpm ==
            Approx(vitals_b[0].respiratory_rate_bpm));
    REQUIRE(vitals_a[0].spo2_percent == Approx(vitals_b[0].spo2_percent));
    REQUIRE(vitals_a[0].core_temperature_c ==
            Approx(vitals_b[0].core_temperature_c));
    REQUIRE(vitals_a[0].cognitive_performance_percent ==
            Approx(vitals_b[0].cognitive_performance_percent));
    REQUIRE(vitals_a[0].physical_performance_percent ==
            Approx(vitals_b[0].physical_performance_percent));
}

TEST_CASE("crew: safe-step updateCrewMember stays near baseline", "[crew][sec17]") {
    CrewPhysiologyModel model;
    ScenarioConfig config = makeFullPhysiologyConfig();
    CrewMemberConfig member = makePhysiologyMember();
    CrewMemberState crew = makeBaselineCrewState(member);

    DerivedTelemetry telemetry{};
    telemetry.atmosphere.inspired_oxygen_mmhg = 150.0;
    telemetry.atmosphere.cabin_pressure_kpa = 80.0;
    telemetry.atmosphere.co2_one_hour_avg_mmhg = 0.0;
    telemetry.eva.eva_safe_return_margin_min = 200.0;

    vector<TimelineEvent> events;
    model.updateCrewMember(crew, member, telemetry, config, 60.0, 22.0, events, 0);

    REQUIRE(crew.heart_rate_bpm == Approx(70.0));
    REQUIRE(crew.respiratory_rate_bpm == Approx(14.0));
    REQUIRE(crew.spo2_percent == Approx(97.6));
    REQUIRE(crew.core_temperature_c == Approx(36.88));
    REQUIRE(crew.hypoxia_exposure_index == Approx(0.0));
    REQUIRE(crew.co2_exposure_index == Approx(0.0));
    REQUIRE(crew.thermal_exposure_index == Approx(0.0));
    REQUIRE(crew.oxygen_consumption_g_min == Approx(0.50));
    REQUIRE(crew.co2_production_g_min == Approx(0.60));
    REQUIRE(crew.heat_output_w == Approx(100.0));
    REQUIRE(crew.cognitive_performance_factor == Approx(0.95));
    REQUIRE(crew.physical_performance_factor == Approx(0.96));
    REQUIRE(crew.health_status == CrewHealthStatus::Nominal);
    REQUIRE(crew.active_alarms.empty());
}

TEST_CASE("crew: low-O2 updateCrewMember moves fields in expected directions", "[crew]") {
    CrewPhysiologyModel model;
    ScenarioConfig config = makeFullPhysiologyConfig();
    CrewMemberConfig member = makePhysiologyMember();
    CrewMemberState safe = makeBaselineCrewState(member);
    CrewMemberState hypoxic = makeBaselineCrewState(member);

    DerivedTelemetry safe_telemetry{};
    safe_telemetry.atmosphere.inspired_oxygen_mmhg = 150.0;
    safe_telemetry.atmosphere.cabin_pressure_kpa = 80.0;
    safe_telemetry.atmosphere.co2_one_hour_avg_mmhg = 0.0;
    safe_telemetry.eva.eva_safe_return_margin_min = 200.0;

    DerivedTelemetry low_o2 = safe_telemetry;
    low_o2.atmosphere.inspired_oxygen_mmhg = 90.0;

    vector<TimelineEvent> events;
    model.updateCrewMember(safe, member, safe_telemetry, config, 60.0, 22.0, events, 0);
    model.updateCrewMember(hypoxic, member, low_o2, config, 60.0, 22.0, events, 0);

    REQUIRE(hypoxic.hypoxia_exposure_index > safe.hypoxia_exposure_index);
    REQUIRE(hypoxic.heart_rate_bpm > safe.heart_rate_bpm);
    REQUIRE(hypoxic.respiratory_rate_bpm > safe.respiratory_rate_bpm);
    REQUIRE(hypoxic.spo2_percent < safe.spo2_percent);
    REQUIRE(hypoxic.cognitive_performance_factor < safe.cognitive_performance_factor);
    REQUIRE(hypoxic.physical_performance_factor < safe.physical_performance_factor);
    REQUIRE(hasAlarm(hypoxic, CrewAlarmType::Hypoxia));
    REQUIRE(hypoxic.health_status != CrewHealthStatus::Nominal);
}

TEST_CASE("crew: updateAllCrew differs by sensitivity and is reproducible", "[crew]") {
    CrewPhysiologyModel model;
    ScenarioConfig config = makeFullPhysiologyConfig();

    CrewMemberConfig hardy = makePhysiologyMember();
    hardy.crew_id = "crew_hardy";
    hardy.hypoxia_sensitivity = 0.5;
    hardy.fitness_factor = 2.0;

    CrewMemberConfig sensitive = makePhysiologyMember();
    sensitive.crew_id = "crew_sensitive";
    sensitive.hypoxia_sensitivity = 2.0;
    sensitive.fitness_factor = 1.0;

    config.crew_roster = {hardy, sensitive};

    SimulationState state{};
    state.cabin_temperature_c = 22.0;
    state.crew = {
        makeBaselineCrewState(hardy),
        makeBaselineCrewState(sensitive),
    };

    DerivedTelemetry telemetry{};
    telemetry.atmosphere.inspired_oxygen_mmhg = 105.0;
    telemetry.atmosphere.cabin_pressure_kpa = 80.0;
    telemetry.atmosphere.co2_one_hour_avg_mmhg = 0.0;
    telemetry.eva.eva_safe_return_margin_min = 200.0;

    vector<TimelineEvent> events;
    model.updateAllCrew(state, config, telemetry, 60.0, events);

    REQUIRE(state.crew[0].crew_id == "crew_hardy");
    REQUIRE(state.crew[1].crew_id == "crew_sensitive");
    REQUIRE(state.crew[1].spo2_percent < state.crew[0].spo2_percent);
    REQUIRE(state.crew[1].heart_rate_bpm > state.crew[0].heart_rate_bpm);
    REQUIRE(state.crew[1].hypoxia_exposure_index > state.crew[0].hypoxia_exposure_index);

    SimulationState again{};
    again.cabin_temperature_c = 22.0;
    again.crew = {
        makeBaselineCrewState(hardy),
        makeBaselineCrewState(sensitive),
    };
    vector<TimelineEvent> events2;
    model.updateAllCrew(again, config, telemetry, 60.0, events2);

    REQUIRE(again.crew[0].spo2_percent == Approx(state.crew[0].spo2_percent));
    REQUIRE(again.crew[1].spo2_percent == Approx(state.crew[1].spo2_percent));
    REQUIRE(again.crew[0].heart_rate_bpm == Approx(state.crew[0].heart_rate_bpm));
    REQUIRE(again.crew[1].heart_rate_bpm == Approx(state.crew[1].heart_rate_bpm));
    REQUIRE(again.crew[0].hypoxia_exposure_index ==
            Approx(state.crew[0].hypoxia_exposure_index));
    REQUIRE(again.crew[1].hypoxia_exposure_index ==
            Approx(state.crew[1].hypoxia_exposure_index));
}

TEST_CASE("crew: updateAllCrew rejects roster/state mismatch", "[crew]") {
    CrewPhysiologyModel model;
    ScenarioConfig config = makeFullPhysiologyConfig();
    CrewMemberConfig member = makePhysiologyMember();
    config.crew_roster = {member};

    SimulationState state{};
    state.cabin_temperature_c = 22.0;
    state.crew = {};

    DerivedTelemetry telemetry{};
    vector<TimelineEvent> events;
    REQUIRE_THROWS_AS(
        model.updateAllCrew(state, config, telemetry, 60.0, events), std::runtime_error);
}

TEST_CASE("crew: aggregateCrewLoads sums habitat crew and excludes active EVA", "[crew]") {
    CrewPhysiologyModel model;

    CrewMemberState habitat{};
    habitat.crew_id = "hab";
    habitat.eva_status = EVAStatus::Idle;
    habitat.oxygen_consumption_g_min = 0.50;
    habitat.co2_production_g_min = 0.60;
    habitat.heat_output_w = 100.0;

    CrewMemberState eva{};
    eva.crew_id = "eva";
    eva.eva_status = EVAStatus::Working;
    eva.oxygen_consumption_g_min = 1.80;
    eva.co2_production_g_min = 2.00;
    eva.heat_output_w = 300.0;

    CrewMemberState complete{};
    complete.crew_id = "done";
    complete.eva_status = EVAStatus::Complete;
    complete.oxygen_consumption_g_min = 0.50;
    complete.co2_production_g_min = 0.60;
    complete.heat_output_w = 100.0;

    CrewHabitatLoads loads =
        model.aggregateCrewLoads({habitat, eva, complete});

    REQUIRE(loads.oxygen_consumption_g_min == Approx(1.0));
    REQUIRE(loads.co2_production_g_min == Approx(1.2));
    REQUIRE(loads.heat_output_w == Approx(200.0));
}

TEST_CASE("crew: high-CO2 updateCrewMember moves fields in expected directions", "[crew]") {
    CrewPhysiologyModel model;
    ScenarioConfig config = makeFullPhysiologyConfig();
    CrewMemberConfig member = makePhysiologyMember();
    CrewMemberState safe = makeBaselineCrewState(member);
    CrewMemberState high_co2 = makeBaselineCrewState(member);

    DerivedTelemetry safe_telemetry{};
    safe_telemetry.atmosphere.inspired_oxygen_mmhg = 150.0;
    safe_telemetry.atmosphere.cabin_pressure_kpa = 80.0;
    safe_telemetry.atmosphere.co2_one_hour_avg_mmhg = 0.0;
    safe_telemetry.eva.eva_safe_return_margin_min = 200.0;

    DerivedTelemetry co2_telemetry = safe_telemetry;
    co2_telemetry.atmosphere.co2_one_hour_avg_mmhg = 8.0;

    vector<TimelineEvent> events;
    model.updateCrewMember(safe, member, safe_telemetry, config, 60.0, 22.0, events, 0);
    model.updateCrewMember(high_co2, member, co2_telemetry, config, 60.0, 22.0, events, 0);

    REQUIRE(high_co2.co2_exposure_index > safe.co2_exposure_index);
    REQUIRE(high_co2.heart_rate_bpm > safe.heart_rate_bpm);
    REQUIRE(high_co2.respiratory_rate_bpm > safe.respiratory_rate_bpm);
    REQUIRE(high_co2.cognitive_performance_factor < safe.cognitive_performance_factor);
    REQUIRE(high_co2.physical_performance_factor < safe.physical_performance_factor);
    REQUIRE(high_co2.health_status != CrewHealthStatus::Nominal);
}

TEST_CASE("crew: thermal-stress updateCrewMember moves fields in expected directions", "[crew]") {
    CrewPhysiologyModel model;
    ScenarioConfig config = makeFullPhysiologyConfig();
    config.vital_response.core_temp_environment_gain = 0.5;
    config.vital_response.core_temp_time_constant_min = 0.0;

    CrewMemberConfig member = makePhysiologyMember();
    CrewMemberState safe = makeBaselineCrewState(member);
    CrewMemberState hot = makeBaselineCrewState(member);

    DerivedTelemetry telemetry{};
    telemetry.atmosphere.inspired_oxygen_mmhg = 150.0;
    telemetry.atmosphere.cabin_pressure_kpa = 80.0;
    telemetry.atmosphere.co2_one_hour_avg_mmhg = 0.0;
    telemetry.eva.eva_safe_return_margin_min = 200.0;

    vector<TimelineEvent> events;
    model.updateCrewMember(safe, member, telemetry, config, 60.0, 22.0, events, 0);
    model.updateCrewMember(hot, member, telemetry, config, 60.0, 40.0, events, 0);

    REQUIRE(hot.thermal_exposure_index > safe.thermal_exposure_index);
    REQUIRE(hot.heart_rate_bpm > safe.heart_rate_bpm);
    REQUIRE(hot.respiratory_rate_bpm > safe.respiratory_rate_bpm);
    REQUIRE(hot.core_temperature_c > safe.core_temperature_c);
    REQUIRE(hot.cognitive_performance_factor < safe.cognitive_performance_factor);
    REQUIRE(hot.physical_performance_factor < safe.physical_performance_factor);
    REQUIRE(hasAlarm(hot, CrewAlarmType::Thermal));
    REQUIRE(hot.health_status != CrewHealthStatus::Nominal);
}

TEST_CASE("crew: habitat connection records one atomic TelemetrySample", "[crew]") {
    CrewPhysiologyModel physiology;
    ResourceModel resources;

    ScenarioConfig config = makeFullPhysiologyConfig();
    config.time_step_s = 60;
    config.habitat.effective_thermal_capacitance_kj_c = 500.0;
    config.atmosphere.scrubber_capacity_g_min = 0.0;
    config.solar.array_area_m2 = 100.0;
    config.solar.cell_efficiency = 0.30;
    config.solar.mars_sun_distance_au = 1.5;
    config.power.battery_capacity_kwh = 100.0;
    config.power.battery_reserve_percent = 20.0;
    config.power.charge_efficiency = 0.90;
    config.power.discharge_efficiency = 0.90;
    config.eva.maximum_duration_min = 360;
    config.eva.ingress_min = 30;
    config.eva.reserve_min = 30;
    config.communications.transmission_duration_min = 10;

    CrewMemberConfig member = makePhysiologyMember();
    member.crew_id = "crew_01";
    config.crew_roster = {member};

    SimulationState state{};
    state.time_min = 0;
    state.habitable_volume_m3 = 100.0;
    state.cabin_temperature_c = 22.0;
    state.oxygen_mass_kg = 20.0;
    state.inert_gas_mass_kg = 40.0;
    state.co2_mass_kg = 0.5;
    state.total_gas_leak_kg_hr = 0.0;
    state.leak_fault_factor = 1.0;
    state.scrubber_efficiency = 1.0;
    state.battery_energy_kwh = 50.0;
    state.solar_incidence_angle_deg = 0.0;
    state.atmospheric_transmission = 1.0;
    state.deposited_dust_factor = 1.0;
    state.solar_fault_factor = 1.0;
    state.essential_load_kw = 1.0;
    state.equipment_heat_w = 0.0;
    state.environmental_heat_w = 0.0;
    state.heater_heat_w = 0.0;
    state.tcs_rejection_capacity_w = 1000.0;
    state.crew = {makeBaselineCrewState(member)};
    state.crew[0].crew_id = "crew_01";

    const double dt_seconds = 60.0;
    MissionTelemetry mission{};
    mission.mission_status = MissionStatus::Nominal;

    // 1. pre-step habitat telemetry from current physical state
    DerivedTelemetry pre_step =
        resources.calculateDerivedTelemetry(state, config, {}, mission);

    // 2. physiology update once from pre-step environment
    vector<TimelineEvent> step_events;
    physiology.updateAllCrew(state, config, pre_step, dt_seconds, step_events);

    // 3. aggregate habitat-fed metabolic loads
    CrewHabitatLoads loads = physiology.aggregateCrewLoads(state.crew);

    const double o2_before = state.oxygen_mass_kg;
    const double co2_before = state.co2_mass_kg;

    // 4. pass totals into ResourceModel atmosphere / CO2 / thermal
    resources.updateAtmosphere(
        state, config, loads.oxygen_consumption_g_min, dt_seconds);
    resources.updateCarbonDioxide(
        state, config, loads.co2_production_g_min, dt_seconds);
    resources.updateThermalState(
        state, config, loads.heat_output_w, dt_seconds);

    // 5–6. post-step crew then habitat telemetry
    vector<CrewVitalsTelemetry> crew_vitals =
        physiology.buildCrewVitalsTelemetry(state, config);
    DerivedTelemetry post_step =
        resources.calculateDerivedTelemetry(state, config, crew_vitals, mission);

    // 7. one atomic TelemetrySample
    TelemetrySample sample{};
    sample.simulation_time_min = state.time_min;
    sample.telemetry = post_step;
    sample.events_this_step = {};
    sample.active_actions = {};
    sample.has_warning = false;
    sample.has_critical = false;
    for (const auto& vitals : sample.telemetry.crew_vitals) {
        if (vitals.health_status == CrewHealthStatus::ElevatedStress ||
            vitals.health_status == CrewHealthStatus::Impaired) {
            sample.has_warning = true;
        }
        if (vitals.health_status == CrewHealthStatus::Critical ||
            vitals.health_status == CrewHealthStatus::Incapacitated) {
            sample.has_critical = true;
        }
    }

    const double dt_minutes = dt_seconds / ares::constants::SECONDS_PER_MINUTE;
    const double expected_o2_kg =
        loads.oxygen_consumption_g_min * dt_minutes /
        ares::constants::GRAMS_PER_KILOGRAM;
    const double expected_co2_kg =
        loads.co2_production_g_min * dt_minutes /
        ares::constants::GRAMS_PER_KILOGRAM;

    REQUIRE(state.oxygen_mass_kg == Approx(o2_before - expected_o2_kg));
    REQUIRE(state.co2_mass_kg == Approx(co2_before + expected_co2_kg));
    REQUIRE(sample.telemetry.thermal.crew_heat_w == Approx(loads.heat_output_w));
    REQUIRE(sample.telemetry.crew_vitals.size() == 1);
    REQUIRE(sample.telemetry.crew_vitals[0].crew_id == "crew_01");
    REQUIRE(sample.simulation_time_min == 0);
    REQUIRE(sample.telemetry.crew_vitals[0].oxygen_consumption_g_min ==
            Approx(loads.oxygen_consumption_g_min));
}

TEST_CASE("crew: physiology parameter_sources cover vital-response coefficients", "[crew]") {
    ScenarioConfig config = makeFullPhysiologyConfig();
    REQUIRE_FALSE(config.parameter_sources.empty());

    auto find_source = [&](const string& name) -> const ParameterSource* {
        for (const auto& source : config.parameter_sources) {
            if (source.parameter_name == name) {
                return &source;
            }
        }
        return nullptr;
    };

    const ParameterSource* inspired =
        find_source("inspired_o2_warning_mmhg");
    REQUIRE(inspired != nullptr);
    REQUIRE(inspired->classification == SourceClassification::NASAStandard);

    const ParameterSource* metabolic =
        find_source("activity_metabolic_profiles");
    REQUIRE(metabolic != nullptr);
    REQUIRE(metabolic->classification == SourceClassification::NASAReference);

    const ParameterSource* hr_gain = find_source("hr_hypoxia_gain");
    REQUIRE(hr_gain != nullptr);
    REQUIRE(hr_gain->classification == SourceClassification::ARESAssumption);

    const ParameterSource* rationing = find_source("oxygen_rationing_factor");
    REQUIRE(rationing != nullptr);
    REQUIRE(rationing->classification == SourceClassification::ARESAssumption);

    const ParameterSource* co2_limit = find_source("co2_one_hour_limit_mmhg");
    REQUIRE(co2_limit != nullptr);
    REQUIRE(co2_limit->classification == SourceClassification::NASAStandard);

    int ares_count = 0;
    for (const auto& source : config.parameter_sources) {
        if (source.classification == SourceClassification::ARESAssumption) {
            ++ares_count;
        }
    }
    REQUIRE(ares_count >= 20);
}
