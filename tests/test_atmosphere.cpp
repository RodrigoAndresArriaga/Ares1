#include <catch2/catch_test_macros.hpp>
#include <catch2/catch_approx.hpp>
#include <cmath>
#include "Enums.hpp"
#include "PhysicalConstants.hpp"
#include "ResourceModel.hpp"
#include "ScenarioConfig.hpp"
#include "SimulationState.hpp"

using Catch::Approx;

namespace {

ScenarioConfig makeDerivedConfig() {
    ScenarioConfig config{};
    config.time_step_s = 60;
    config.habitat.effective_thermal_capacitance_kj_c = 500.0;
    config.solar.array_area_m2 = 100.0;
    config.solar.cell_efficiency = 0.30;
    config.solar.mars_sun_distance_au = 1.5;
    config.power.battery_capacity_kwh = 100.0;
    config.power.battery_reserve_percent = 20.0;
    config.power.charge_efficiency = 0.90;
    config.power.discharge_efficiency = 0.90;
    config.thermal.critical_low_c = 10.0;
    config.thermal.critical_high_c = 35.0;
    config.eva.maximum_duration_min = 360;
    config.eva.ingress_min = 30;
    config.eva.reserve_min = 30;
    config.communications.transmission_duration_min = 10;
    config.communications.windows = {{100, 200}};
    config.atmosphere.pressure_failure_low_kpa = 50.0;
    config.atmosphere.co2_one_hour_limit_mmhg = 8.0;
    config.atmosphere.scrubber_capacity_g_min = 5.0;
    return config;
}

SimulationState makeDerivedState() {
    SimulationState state{};
    state.time_min = 120;
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
    state.solar_fault_factor = 0.55;
    state.essential_load_kw = 1.0;
    state.equipment_heat_w = 200.0;
    state.tcs_rejection_capacity_w = 1000.0;
    state.eva_elapsed_min = 36;
    state.solar_repair_progress = 0.25;
    state.emergency_packet_sent = false;
    state.transmission_elapsed_min = 0;
    return state;
}

SimulationState makeAtmosphereState() {
    SimulationState state{};
    state.habitable_volume_m3 = 100.0;
    state.cabin_temperature_c = 22.0;
    state.oxygen_mass_kg = 20.0;
    state.inert_gas_mass_kg = 40.0;
    state.co2_mass_kg = 0.5;
    state.total_gas_leak_kg_hr = 0.0;
    state.leak_fault_factor = 1.0;
    state.scrubber_efficiency = 1.0;
    return state;
}

}

TEST_CASE("atmosphere: derived telemetry is coherent and idempotent", "[atmosphere][derived]") {
    ResourceModel model;
    ScenarioConfig config = makeDerivedConfig();
    SimulationState state = makeDerivedState();

    CrewVitalsTelemetry crew{};
    crew.crew_id = "crew_01";
    crew.heat_output_w = 100.0;
    vector<CrewVitalsTelemetry> crew_vitals = {crew};

    MissionTelemetry mission{};
    mission.mission_status = MissionStatus::Warning;
    mission.stabilization_elapsed_min = 15.0;
    mission.warnings = {"low_power_margin"};
    mission.violated_constraints = {};

    DerivedTelemetry first = model.calculateDerivedTelemetry(state, config, crew_vitals, mission);
    DerivedTelemetry second = model.calculateDerivedTelemetry(state, config, crew_vitals, mission);

    REQUIRE(first.atmosphere.cabin_pressure_kpa > 0.0);
    REQUIRE(first.power.solar_generation_kw > 0.0);
    REQUIRE(first.power.solar_generation_percent == Approx(55.0));
    REQUIRE(first.thermal.crew_heat_w == Approx(100.0));
    REQUIRE(first.eva.eva_safe_return_margin_min == Approx(264.0));
    REQUIRE(first.communications.comms_window_open);
    REQUIRE(first.crew_vitals.size() == 1);
    REQUIRE(first.crew_vitals[0].crew_id == "crew_01");
    REQUIRE(first.mission.mission_status == MissionStatus::Warning);
    REQUIRE(first.mission.stabilization_elapsed_min == Approx(15.0));
    REQUIRE(first.mission.warnings.size() == 1);

    REQUIRE(second.atmosphere.cabin_pressure_kpa == Approx(first.atmosphere.cabin_pressure_kpa));
    REQUIRE(second.power.solar_generation_kw == Approx(first.power.solar_generation_kw));
    REQUIRE(second.power.battery_soc_percent == Approx(first.power.battery_soc_percent));
    REQUIRE(second.thermal.net_thermal_power_w == Approx(first.thermal.net_thermal_power_w));
    REQUIRE(second.thermal.temperature_margin_c == Approx(first.thermal.temperature_margin_c));
    REQUIRE(second.eva.repair_progress_percent == Approx(first.eva.repair_progress_percent));
    REQUIRE(second.communications.next_comms_window_min == Approx(first.communications.next_comms_window_min));
    REQUIRE(second.mission.stabilization_elapsed_min == Approx(first.mission.stabilization_elapsed_min));
}

TEST_CASE(
    "atmosphere: ideal-gas pressure matches hand calculation",
    "[atmosphere][sec17]") {
    using namespace ares::constants;
    ResourceModel model;
    ScenarioConfig config = makeDerivedConfig();
    SimulationState state = makeAtmosphereState();

    const double n_o2 = state.oxygen_mass_kg / OXYGEN_MORAL_MASS_KG_PERO_MOL;
    const double n_inert = state.inert_gas_mass_kg / INERT_MOLAR_MASS_KG_PER_MOL;
    const double n_co2 = state.co2_mass_kg / CO2_MORAL_MASS_KG_PER_MOL;
    const double n_total = n_o2 + n_inert + n_co2;
    const double t_k = state.cabin_temperature_c + CELSIUS_TO_KELVIN;
    const double expected_kpa =
        (n_total * GAS_CONSTANT_J_PER_MOL_K * t_k / state.habitable_volume_m3) /
        1000.0;

    AtmosphereTelemetry telem = model.calculateAtmosphereTelemetry(state, config);
    REQUIRE(telem.cabin_pressure_kpa == Approx(expected_kpa));
}

TEST_CASE(
    "atmosphere: no leak and no crew load preserve gas inventory",
    "[atmosphere][sec17]") {
    ResourceModel model;
    ScenarioConfig config = makeDerivedConfig();
    config.atmosphere.scrubber_capacity_g_min = 0.0;
    SimulationState state = makeAtmosphereState();
    state.scrubber_efficiency = 0.0;
    state.total_gas_leak_kg_hr = 0.0;

    const double o2 = state.oxygen_mass_kg;
    const double inert = state.inert_gas_mass_kg;
    const double co2 = state.co2_mass_kg;

    model.updateAtmosphere(state, config, 0.0, 3600.0);
    model.updateCarbonDioxide(state, config, 0.0, 3600.0);

    REQUIRE(state.oxygen_mass_kg == Approx(o2));
    REQUIRE(state.inert_gas_mass_kg == Approx(inert));
    REQUIRE(state.co2_mass_kg == Approx(co2));
}

TEST_CASE(
    "atmosphere: mixed-gas leak removes constituents proportionally",
    "[atmosphere][sec17]") {
    ResourceModel model;
    ScenarioConfig config = makeDerivedConfig();
    SimulationState state = makeAtmosphereState();
    state.total_gas_leak_kg_hr = 6.05;
    state.leak_fault_factor = 1.0;

    model.updateAtmosphere(state, config, 0.0, 3600.0);

    REQUIRE(state.oxygen_mass_kg == Approx(18.0));
    REQUIRE(state.inert_gas_mass_kg == Approx(36.0));
    REQUIRE(state.co2_mass_kg == Approx(0.45));
}

TEST_CASE(
    "atmosphere: CO2 removal cannot exceed available CO2",
    "[atmosphere][sec17]") {
    ResourceModel model;
    ScenarioConfig config = makeDerivedConfig();
    config.atmosphere.scrubber_capacity_g_min = 5.0;
    SimulationState state = makeAtmosphereState();
    state.co2_mass_kg = 0.001;
    state.scrubber_efficiency = 1.0;

    model.updateCarbonDioxide(state, config, 0.0, 60.0);

    REQUIRE(state.co2_mass_kg == Approx(0.0));
    REQUIRE(state.co2_mass_kg >= 0.0);
}

TEST_CASE(
    "atmosphere: one-hour CO2 average uses the correct window",
    "[atmosphere][sec17]") {
    ResourceModel model;
    ScenarioConfig config = makeDerivedConfig();
    config.time_step_s = 60;
    config.atmosphere.scrubber_capacity_g_min = 0.0;
    SimulationState state = makeAtmosphereState();
    state.scrubber_efficiency = 0.0;
    state.co2_mass_kg = 0.1;

    // 61 steps: window holds max 60 samples; first sample is dropped
    for (int i = 0; i < 61; ++i) {
        state.co2_mass_kg = 0.1 + 0.01 * static_cast<double>(i);
        model.updateCarbonDioxide(state, config, 0.0, 60.0);
    }

    REQUIRE(state.rolling_co2_samples.size() == 60);

    double sum = 0.0;
    for (double sample : state.rolling_co2_samples) {
        sum += sample;
    }
    const double expected_avg = sum / 60.0;
    AtmosphereTelemetry telem = model.calculateAtmosphereTelemetry(state, config);
    REQUIRE(telem.co2_one_hour_avg_mmhg == Approx(expected_avg));
}
