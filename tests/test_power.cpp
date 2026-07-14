#include <catch2/catch_test_macros.hpp>
#include <catch2/catch_approx.hpp>
#include <cmath>
#include "ResourceModel.hpp"
#include "ScenarioConfig.hpp"
#include "SimulationState.hpp"

using Catch::Approx;

namespace {

ScenarioConfig makeSolarConfig() {
    ScenarioConfig config{};
    config.solar.array_area_m2 = 100.0;
    config.solar.cell_efficiency = 0.30;
    config.solar.mars_sun_distance_au = 1.5;
    return config;
}

SimulationState makeSolarState() {
    SimulationState state{};
    state.solar_incidence_angle_deg = 0.0;
    state.atmospheric_transmission = 1.0;
    state.deposited_dust_factor = 1.0;
    state.solar_fault_factor = 1.0;
    return state;
}

}

TEST_CASE("power: ninety degree incidence produces zero solar generation", "[power][solar][sec17]") {
    ResourceModel model;
    ScenarioConfig config = makeSolarConfig();
    SimulationState state = makeSolarState();
    state.solar_incidence_angle_deg = 90.0;

    REQUIRE(model.calculateSolarGenerationKw(state, config) == Approx(0.0).margin(1e-12));
    REQUIRE(model.calculateHealthySolarGenerationKw(state, config) == Approx(0.0).margin(1e-12));
}

TEST_CASE("power: incidence greater than 90 degrees produces zero solar generation", "[power][solar]") {
    ResourceModel model;
    ScenarioConfig config = makeSolarConfig();
    SimulationState state = makeSolarState();
    state.solar_incidence_angle_deg = 120.0;

    REQUIRE(model.calculateSolarGenerationKw(state, config) == Approx(0.0));
    REQUIRE(model.calculateHealthySolarGenerationKw(state, config) == Approx(0.0));
}

TEST_CASE("power: solar fault factor scales actual generation relative to healthy", "[power][solar][sec17]") {
    ResourceModel model;
    ScenarioConfig config = makeSolarConfig();
    SimulationState state = makeSolarState();
    state.solar_fault_factor = 0.55;

    double healthy_kw = model.calculateHealthySolarGenerationKw(state, config);
    double actual_kw = model.calculateSolarGenerationKw(state, config);

    REQUIRE(healthy_kw > 0.0);
    REQUIRE(actual_kw == Approx(healthy_kw * state.solar_fault_factor));
}

namespace {

ScenarioConfig makePowerConfig() {
    ScenarioConfig config{};
    config.power.battery_capacity_kwh = 100.0;
    config.power.charge_efficiency = 0.90;
    config.power.discharge_efficiency = 0.90;
    return config;
}

SimulationState makePowerState() {
    SimulationState state{};
    state.battery_energy_kwh = 50.0;
    state.essential_load_kw = 0.0;
    state.discretionary_load_kw = 0.0;
    state.thermal_control_load_kw = 0.0;
    state.eva_support_load_kw = 0.0;
    state.communications_load_kw = 0.0;
    return state;
}

}

TEST_CASE("power: one hour at 1 kW deficit applies discharge efficiency", "[power][battery][sec17]") {
    ResourceModel model;
    ScenarioConfig config = makePowerConfig();
    SimulationState state = makePowerState();
    state.essential_load_kw = 1.0;

    model.updateElectricalPower(state, config, 0.0, 3600.0);

    REQUIRE(state.battery_energy_kwh == Approx(50.0 - (1.0 / config.power.discharge_efficiency)));
}

TEST_CASE("power: one hour at 1 kW surplus applies charge efficiency", "[power][battery]") {
    ResourceModel model;
    ScenarioConfig config = makePowerConfig();
    SimulationState state = makePowerState();

    model.updateElectricalPower(state, config, 1.0, 3600.0);

    REQUIRE(state.battery_energy_kwh == Approx(50.0 + (1.0 * config.power.charge_efficiency)));
}

TEST_CASE("power: battery energy cannot go below zero", "[power][battery]") {
    ResourceModel model;
    ScenarioConfig config = makePowerConfig();
    SimulationState state = makePowerState();
    state.battery_energy_kwh = 0.5;
    state.essential_load_kw = 10.0;

    model.updateElectricalPower(state, config, 0.0, 3600.0);

    REQUIRE(state.battery_energy_kwh == Approx(0.0));
}

TEST_CASE("power: battery energy cannot exceed capacity", "[power][battery]") {
    ResourceModel model;
    ScenarioConfig config = makePowerConfig();
    SimulationState state = makePowerState();
    state.battery_energy_kwh = 99.0;

    model.updateElectricalPower(state, config, 20.0, 3600.0);

    REQUIRE(state.battery_energy_kwh == Approx(config.power.battery_capacity_kwh));
}

TEST_CASE("power: SOC is energy divided by capacity", "[power][telemetry][sec17]") {
    ResourceModel model;
    ScenarioConfig config = makePowerConfig();
    config.power.battery_reserve_percent = 20.0;
    config.power.discharge_efficiency = 0.90;
    SimulationState state = makePowerState();
    state.battery_energy_kwh = 32.0;
    state.essential_load_kw = 2.0;

    PowerTelemetry telem = model.calculatePowerTelemetry(state, config, 0.5, 1.0);

    REQUIRE(telem.battery_soc_percent == Approx(32.0));
}

TEST_CASE("power: power margin is generation minus total load", "[power][telemetry]") {
    ResourceModel model;
    ScenarioConfig config = makePowerConfig();
    config.power.battery_reserve_percent = 20.0;
    config.power.discharge_efficiency = 0.90;
    SimulationState state = makePowerState();
    state.essential_load_kw = 1.0;
    state.discretionary_load_kw = 0.5;
    state.thermal_control_load_kw = 0.3;
    state.eva_support_load_kw = 0.2;
    state.communications_load_kw = 0.1;

    PowerTelemetry telem = model.calculatePowerTelemetry(state, config, 0.8, 1.0);

    REQUIRE(telem.total_habitat_load_kw == Approx(2.1));
    REQUIRE(telem.power_margin_kw == Approx(-1.3));
}

TEST_CASE("power: solar generation percent handles healthy and zero healthy", "[power][telemetry]") {
    ResourceModel model;
    ScenarioConfig config = makePowerConfig();
    config.power.battery_reserve_percent = 20.0;
    config.power.discharge_efficiency = 0.90;
    SimulationState state = makePowerState();

    PowerTelemetry telem = model.calculatePowerTelemetry(state, config, 0.55, 1.0);
    REQUIRE(telem.solar_generation_percent == Approx(55.0));

    PowerTelemetry zero_healthy = model.calculatePowerTelemetry(state, config, 0.0, 0.0);
    REQUIRE(zero_healthy.solar_generation_percent == Approx(0.0));
}

TEST_CASE("power: battery hours to reserve only while discharging above reserve", "[power][telemetry]") {
    ResourceModel model;
    ScenarioConfig config = makePowerConfig();
    config.power.battery_capacity_kwh = 100.0;
    config.power.battery_reserve_percent = 20.0;
    config.power.discharge_efficiency = 0.90;
    SimulationState state = makePowerState();
    state.battery_energy_kwh = 50.0;
    state.essential_load_kw = 2.0;

    // net = 0 - 2 = -2 kW; drain = 2 / 0.9; above reserve = 50 - 20 = 30
    PowerTelemetry discharging = model.calculatePowerTelemetry(state, config, 0.0, 1.0);
    REQUIRE(discharging.battery_hours_to_reserve == Approx(30.0 / (2.0 / 0.90)));

    // charging / surplus -> infinity
    PowerTelemetry charging = model.calculatePowerTelemetry(state, config, 5.0, 1.0);
    REQUIRE(std::isinf(charging.battery_hours_to_reserve));

    // at or below reserve -> infinity
    state.battery_energy_kwh = 20.0;
    PowerTelemetry at_reserve = model.calculatePowerTelemetry(state, config, 0.0, 1.0);
    REQUIRE(std::isinf(at_reserve.battery_hours_to_reserve));
}
