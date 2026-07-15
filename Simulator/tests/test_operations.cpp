#include <catch2/catch_test_macros.hpp>
#include <catch2/catch_approx.hpp>
#include <cmath>
#include "Enums.hpp"
#include "ResourceModel.hpp"
#include "ScenarioConfig.hpp"
#include "SimulationState.hpp"

using Catch::Approx;

namespace {

ScenarioConfig makeOpsConfig() {
    ScenarioConfig config{};
    config.eva.maximum_duration_min = 360;
    config.eva.ingress_min = 30;
    config.eva.reserve_min = 30;
    config.communications.transmission_duration_min = 10;
    config.communications.windows = {
        {100, 200},
        {300, 400},
    };
    return config;
}

SimulationState makeOpsState() {
    SimulationState state{};
    state.time_min = 0;
    state.eva_elapsed_min = 0;
    state.solar_repair_progress = 0.0;
    state.transmission_elapsed_min = 0;
    state.emergency_packet_sent = false;
    return state;
}

}

TEST_CASE("ops: EVA return margin matches configured time budget", "[ops][eva]") {
    ResourceModel model;
    ScenarioConfig config = makeOpsConfig();
    SimulationState state = makeOpsState();
    state.eva_elapsed_min = 36;
    state.solar_repair_progress = 0.25;

    CrewMemberState crew{};
    crew.crew_id = "crew_01";
    crew.eva_status = EVAStatus::Working;
    state.crew.push_back(crew);

    EVATelemetry telem = model.calculateEVATelemetry(state, config);

    REQUIRE(telem.eva_consumables_remaining_min == Approx(324.0));
    REQUIRE(telem.eva_safe_return_margin_min == Approx(264.0));
    REQUIRE(telem.repair_progress_percent == Approx(25.0));
    REQUIRE(telem.active_crew_id == "crew_01");
}

TEST_CASE("ops: comms window open is inclusive at open_min exclusive at close_min", "[ops][comms]") {
    ResourceModel model;
    ScenarioConfig config = makeOpsConfig();
    SimulationState state = makeOpsState();

    state.time_min = 100;
    CommunicationsTelemetry at_open = model.calculateCommunicationsTelemetry(state, config);
    REQUIRE(at_open.comms_window_open);

    state.time_min = 199;
    CommunicationsTelemetry before_close = model.calculateCommunicationsTelemetry(state, config);
    REQUIRE(before_close.comms_window_open);

    state.time_min = 200;
    CommunicationsTelemetry at_close = model.calculateCommunicationsTelemetry(state, config);
    REQUIRE_FALSE(at_close.comms_window_open);

    state.time_min = 99;
    CommunicationsTelemetry before_open = model.calculateCommunicationsTelemetry(state, config);
    REQUIRE_FALSE(before_open.comms_window_open);
}

TEST_CASE("ops: next comms window is soonest future opening or infinity", "[ops][comms]") {
    ResourceModel model;
    ScenarioConfig config = makeOpsConfig();
    SimulationState state = makeOpsState();

    state.time_min = 50;
    CommunicationsTelemetry before = model.calculateCommunicationsTelemetry(state, config);
    REQUIRE(before.next_comms_window_min == Approx(100.0));

    state.time_min = 150;
    CommunicationsTelemetry during = model.calculateCommunicationsTelemetry(state, config);
    REQUIRE(during.comms_window_open);
    REQUIRE(during.next_comms_window_min == Approx(300.0));

    state.time_min = 450;
    CommunicationsTelemetry after = model.calculateCommunicationsTelemetry(state, config);
    REQUIRE(std::isinf(after.next_comms_window_min));
}
