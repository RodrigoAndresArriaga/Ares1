#include <catch2/catch_test_macros.hpp>
#include <catch2/catch_approx.hpp>
#include "ResourceModel.hpp"
#include "ScenarioConfig.hpp"
#include "SimulationState.hpp"

using Catch::Approx;

namespace {

ScenarioConfig makeThermalConfig() {
    ScenarioConfig config{};
    config.habitat.effective_thermal_capacitance_kj_c = 500.0;
    return config;
}

SimulationState makeThermalState() {
    SimulationState state{};
    state.cabin_temperature_c = 22.0;
    state.equipment_heat_w = 0.0;
    state.environmental_heat_w = 0.0;
    state.heater_heat_w = 0.0;
    state.tcs_rejection_capacity_w = 1000.0;
    return state;
}

}

TEST_CASE("thermal: zero net heat leaves temperature unchanged", "[thermal]") {
    ResourceModel model;
    ScenarioConfig config = makeThermalConfig();
    SimulationState state = makeThermalState();
    state.equipment_heat_w = 400.0;
    state.tcs_rejection_capacity_w = 1000.0;

    model.updateThermalState(state, config, 100.0, 60.0);

    REQUIRE(state.cabin_temperature_c == Approx(22.0));
}

TEST_CASE("thermal: positive net heat increases temperature by expected amount", "[thermal]") {
    ResourceModel model;
    ScenarioConfig config = makeThermalConfig();
    SimulationState state = makeThermalState();
    // heat_in = 800, capacity = 500 -> net = 300 W
    // C = 500 kJ/C = 500000 J/C; dt = 60 s
    // dT = 300 * 60 / 500000 = 0.036 C
    state.equipment_heat_w = 800.0;
    state.tcs_rejection_capacity_w = 500.0;

    model.updateThermalState(state, config, 0.0, 60.0);

    REQUIRE(state.cabin_temperature_c == Approx(22.036));
}

TEST_CASE("thermal: capacity-limited rejection produces expected overload margin", "[thermal]") {
    ResourceModel model;
    ScenarioConfig config = makeThermalConfig();
    SimulationState state = makeThermalState();
    double crew_heat_w = 200.0;
    state.equipment_heat_w = 300.0;
    state.environmental_heat_w = 100.0;
    state.heater_heat_w = 50.0;
    state.tcs_rejection_capacity_w = 400.0;
    double heat_input_w = crew_heat_w + state.equipment_heat_w + state.environmental_heat_w + state.heater_heat_w;
    double net_heat_w = heat_input_w - state.tcs_rejection_capacity_w;
    double thermal_margin_w = state.tcs_rejection_capacity_w - heat_input_w;
    double dt_seconds = 60.0;
    double expected_dT = (net_heat_w * dt_seconds) / (config.habitat.effective_thermal_capacitance_kj_c * 1000.0);

    model.updateThermalState(state, config, crew_heat_w, dt_seconds);

    REQUIRE(thermal_margin_w == Approx(-250.0));
    REQUIRE(net_heat_w == Approx(250.0));
    REQUIRE(state.cabin_temperature_c == Approx(22.0 + expected_dT));
}

TEST_CASE("thermal: telemetry matches update heat balance fixture", "[thermal]") {
    ResourceModel model;
    ScenarioConfig config = makeThermalConfig();
    config.thermal.critical_low_c = 10.0;
    config.thermal.critical_high_c = 35.0;
    SimulationState state = makeThermalState();
    double crew_heat_w = 200.0;
    state.equipment_heat_w = 300.0;
    state.environmental_heat_w = 100.0;
    state.heater_heat_w = 50.0;
    state.tcs_rejection_capacity_w = 400.0;

    ThermalTelemetry telem = model.calculateThermalTelemetry(state, config, crew_heat_w);

    REQUIRE(telem.crew_heat_w == Approx(200.0));
    REQUIRE(telem.tcs_commanded_rejection_w == Approx(650.0));
    REQUIRE(telem.net_thermal_power_w == Approx(250.0));
    REQUIRE(telem.thermal_margin_w == Approx(-250.0));
    REQUIRE(telem.cabin_temperature_c == Approx(22.0));
}

TEST_CASE("thermal: temperature margin negative only when critical limit crossed", "[thermal]") {
    ResourceModel model;
    ScenarioConfig config = makeThermalConfig();
    config.thermal.critical_low_c = 10.0;
    config.thermal.critical_high_c = 35.0;
    SimulationState state = makeThermalState();

    state.cabin_temperature_c = 22.0;
    ThermalTelemetry inside = model.calculateThermalTelemetry(state, config, 0.0);
    REQUIRE(inside.temperature_margin_c == Approx(12.0));
    REQUIRE(inside.temperature_margin_c > 0.0);

    state.cabin_temperature_c = 36.0;
    ThermalTelemetry above = model.calculateThermalTelemetry(state, config, 0.0);
    REQUIRE(above.temperature_margin_c == Approx(-1.0));

    state.cabin_temperature_c = 8.0;
    ThermalTelemetry below = model.calculateThermalTelemetry(state, config, 0.0);
    REQUIRE(below.temperature_margin_c == Approx(-2.0));
}
