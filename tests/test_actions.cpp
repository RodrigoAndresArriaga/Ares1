#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>
#include <cmath>
#include <string>
#include <vector>
#include "ActionExecutor.hpp"
#include "Enums.hpp"
#include "Plan.hpp"
#include "ResourceModel.hpp"
#include "ScenarioConfig.hpp"
#include "SimulationState.hpp"

using Catch::Approx;

namespace {

ScenarioConfig makeActionConfig(){
    ScenarioConfig config{};
    config.time_step_s = 60;
    config.habitat.initial_habitable_volume_m3 = 100.0;
    config.habitat.isolated_habitable_volume_m3 = 60.0;
    config.fault.isolation_leak_multiplier = 0.4;
    config.fault.solar_fault_factor = 0.3;
    config.fault.repaired_solar_fault_factor = 1.0;
    config.power.communications_load_kw = 0.1;
    config.eva.available = true;
    config.eva.preparation_min = 10;
    config.eva.egress_min = 10;
    config.eva.repair_work_min = 20;
    config.eva.ingress_min = 10;
    config.eva.reserve_min = 10;
    config.eva.maximum_duration_min = 360;
    config.eva.rover_required = true;
    config.eva.rover_minimum_reserve_percent = 20.0;
    config.communications.transmission_duration_min = 5;
    config.communications.transmission_power_kw = 0.5;
    config.communications.windows = {{100, 200}};

    CrewMemberConfig crew{};
    crew.crew_id = "crew_01";
    crew.display_name = "Commander";
    crew.eva_qualified = true;
    crew.initial_activity = CrewActivity::NominalWork;
    crew.initial_location_module = "core";
    crew.initial_eva_status = EVAStatus::Idle;
    crew.initial_oxygen_rationing_active = false;
    config.crew_roster.push_back(crew);

    CrewMemberConfig crew2 = crew;
    crew2.crew_id = "crew_02";
    crew2.display_name = "Specialist";
    crew2.eva_qualified = false;
    config.crew_roster.push_back(crew2);
    return config;
}

SimulationState makeActionState(const ScenarioConfig& config){
    SimulationState state{};
    state.time_min = 0;
    state.habitable_volume_m3 = config.habitat.initial_habitable_volume_m3;
    state.total_gas_leak_kg_hr = 2.0;
    state.leak_fault_factor = 1.0;
    state.discretionary_load_kw = 2.0;
    state.essential_load_kw = 1.5;
    state.thermal_control_load_kw = 1.0;
    state.equipment_heat_w = 400.0;
    state.tcs_rejection_capacity_w = 800.0;
    state.communications_load_kw = config.power.communications_load_kw;
    state.solar_fault_factor = config.fault.solar_fault_factor;
    state.solar_repair_progress = 0.0;
    state.eva_elapsed_min = 0;
    state.eva_work_elapsed_min = 0;
    state.eva_available = true;
    state.rover_available = true;
    state.rover_battery_percent = 100.0;
    state.rover_reserved_until_min = 0;
    state.module_isolated = false;
    state.emergency_packet_sent = false;
    state.transmission_elapsed_min = 0;

    CrewMemberState c1{};
    c1.crew_id = "crew_01";
    c1.location_module = "core";
    c1.actvity = CrewActivity::NominalWork;
    c1.eva_status = EVAStatus::Idle;
    c1.health_status = CrewHealthStatus::Nominal;
    c1.physical_performance_factor = 1.0;
    c1.oxygen_rationing_active = false;
    state.crew.push_back(c1);

    CrewMemberState c2 = c1;
    c2.crew_id = "crew_02";
    state.crew.push_back(c2);
    return state;
}

Plan makePlan(std::vector<Action> actions){
    Plan plan{};
    plan.plan_id = "test_plan";
    plan.actions = std::move(actions);
    return plan;
}

}

TEST_CASE("actions: reduce_power_load sheds discretionary and heat", "[actions][power]"){
    ActionExecutor exec;
    ScenarioConfig config = makeActionConfig();
    SimulationState state = makeActionState(config);
    std::vector<TimelineEvent> events;

    Action action{};
    action.type = ActionType::ReducePowerLoad;
    action.type_raw = "reduce_power_load";
    action.start_min = 0;
    action.percent = 50.0;
    action.load_groups = {"discretionary"};

    exec.applyScheduledActions(makePlan({action}), state, config, events);

    REQUIRE(state.discretionary_load_kw == Approx(1.0));
    REQUIRE(state.equipment_heat_w == Approx(200.0));
    REQUIRE(state.essential_load_kw == Approx(1.5));
    REQUIRE(state.active_actions.size() == 1);
    REQUIRE(state.active_actions[0].status == ActionExecutionStatus::Complete);
    REQUIRE(events.size() >= 1);
}

TEST_CASE("actions: reduce_power_load refuses essential life support", "[actions][power]"){
    ActionExecutor exec;
    ScenarioConfig config = makeActionConfig();
    SimulationState state = makeActionState(config);
    std::vector<TimelineEvent> events;

    Action action{};
    action.type = ActionType::ReducePowerLoad;
    action.start_min = 0;
    action.percent = 50.0;
    action.load_groups = {"essential"};

    exec.applyScheduledActions(makePlan({action}), state, config, events);

    REQUIRE(state.essential_load_kw == Approx(1.5));
    REQUIRE(state.active_actions[0].status == ActionExecutionStatus::Failed);
    REQUIRE_FALSE(state.active_actions[0].failure_reason.empty());
}

TEST_CASE("actions: TCS shed reduces rejection capacity", "[actions][power][thermal]"){
    ActionExecutor exec;
    ScenarioConfig config = makeActionConfig();
    SimulationState state = makeActionState(config);
    std::vector<TimelineEvent> events;

    Action action{};
    action.type = ActionType::ReducePowerLoad;
    action.start_min = 0;
    action.percent = 50.0;
    action.load_groups = {"thermal_control"};

    exec.applyScheduledActions(makePlan({action}), state, config, events);

    REQUIRE(state.thermal_control_load_kw == Approx(0.5));
    REQUIRE(state.tcs_rejection_capacity_w == Approx(400.0));
    REQUIRE(state.active_actions[0].status == ActionExecutionStatus::Complete);
}

TEST_CASE("actions: isolate_module fails when crew trapped", "[actions][isolate]"){
    ActionExecutor exec;
    ScenarioConfig config = makeActionConfig();
    SimulationState state = makeActionState(config);
    state.crew[0].location_module = "lab";
    std::vector<TimelineEvent> events;

    Action action{};
    action.type = ActionType::IsolateModule;
    action.start_min = 0;
    action.module = "lab";

    exec.applyScheduledActions(makePlan({action}), state, config, events);

    REQUIRE(state.active_actions[0].status == ActionExecutionStatus::Failed);
    REQUIRE(state.module_isolated == false);
    REQUIRE(state.habitable_volume_m3 == Approx(100.0));
}

TEST_CASE("actions: isolate_module reduces volume and multiplies leak", "[actions][isolate]"){
    ActionExecutor exec;
    ScenarioConfig config = makeActionConfig();
    SimulationState state = makeActionState(config);
    std::vector<TimelineEvent> events;

    Action action{};
    action.type = ActionType::IsolateModule;
    action.start_min = 0;
    action.module = "lab";

    exec.applyScheduledActions(makePlan({action}), state, config, events);

    REQUIRE(state.active_actions[0].status == ActionExecutionStatus::Complete);
    REQUIRE(state.module_isolated);
    REQUIRE(state.isolated_module == "lab");
    REQUIRE(state.habitable_volume_m3 == Approx(60.0));
    REQUIRE(state.leak_fault_factor == Approx(0.4));
    REQUIRE(state.total_gas_leak_kg_hr == Approx(2.0));
}

TEST_CASE("actions: oxygen_rationing sets flag and activity without adding O2", "[actions][rationing]"){
    ActionExecutor exec;
    ScenarioConfig config = makeActionConfig();
    SimulationState state = makeActionState(config);
    state.oxygen_mass_kg = 50.0;
    std::vector<TimelineEvent> events;

    Action action{};
    action.type = ActionType::OxygenRationing;
    action.start_min = 0;
    action.level = "rest";
    action.target_crew_ids = {"crew_01"};

    exec.applyScheduledActions(makePlan({action}), state, config, events);

    REQUIRE(state.crew[0].oxygen_rationing_active);
    REQUIRE(state.crew[0].actvity == CrewActivity::Resting);
    REQUIRE_FALSE(state.crew[1].oxygen_rationing_active);
    REQUIRE(state.oxygen_mass_kg == Approx(50.0));
    REQUIRE(state.active_actions[0].status == ActionExecutionStatus::Complete);
}

TEST_CASE("actions: start-once does not reapply same action index", "[actions]"){
    ActionExecutor exec;
    ScenarioConfig config = makeActionConfig();
    SimulationState state = makeActionState(config);
    std::vector<TimelineEvent> events;

    Action action{};
    action.type = ActionType::OxygenRationing;
    action.start_min = 0;
    action.level = "sleep";

    Plan plan = makePlan({action});
    exec.applyScheduledActions(plan, state, config, events);
    REQUIRE(state.active_actions.size() == 1);

    exec.applyScheduledActions(plan, state, config, events);
    REQUIRE(state.active_actions.size() == 1);
}

TEST_CASE("actions: delay_rover_use reserves then releases rover", "[actions][rover]"){
    ActionExecutor exec;
    ScenarioConfig config = makeActionConfig();
    SimulationState state = makeActionState(config);
    std::vector<TimelineEvent> events;

    Action action{};
    action.type = ActionType::DelayRoverUse;
    action.start_min = 0;
    action.hours = 1.0;

    exec.applyScheduledActions(makePlan({action}), state, config, events);
    REQUIRE_FALSE(state.rover_available);
    REQUIRE(state.rover_reserved_until_min == 60);
    REQUIRE(state.active_actions[0].status == ActionExecutionStatus::Active);

    state.time_min = 60;
    exec.updateActiveActions(state, config, events, 60.0);
    REQUIRE(state.rover_available);
    REQUIRE(state.rover_reserved_until_min == 0);
    REQUIRE(state.active_actions[0].status == ActionExecutionStatus::Complete);
}

TEST_CASE("actions: repair blocked while rover reserved", "[actions][rover][repair]"){
    ActionExecutor exec;
    ScenarioConfig config = makeActionConfig();
    SimulationState state = makeActionState(config);
    std::vector<TimelineEvent> events;

    Action delay{};
    delay.type = ActionType::DelayRoverUse;
    delay.start_min = 0;
    delay.duration_min = 30;

    Action repair{};
    repair.type = ActionType::RepairSolarArray;
    repair.start_min = 0;
    repair.eva_crew_id = "crew_01";

    exec.applyScheduledActions(makePlan({delay, repair}), state, config, events);

    REQUIRE(state.active_actions.size() == 2);
    REQUIRE(state.active_actions[0].status == ActionExecutionStatus::Active);
    REQUIRE(state.active_actions[1].status == ActionExecutionStatus::Failed);
    REQUIRE(state.crew[0].eva_status == EVAStatus::Idle);
}

TEST_CASE("actions: unqualified crew cannot start repair", "[actions][repair]"){
    ActionExecutor exec;
    ScenarioConfig config = makeActionConfig();
    SimulationState state = makeActionState(config);
    std::vector<TimelineEvent> events;

    Action repair{};
    repair.type = ActionType::RepairSolarArray;
    repair.start_min = 0;
    repair.eva_crew_id = "crew_02";

    exec.applyScheduledActions(makePlan({repair}), state, config, events);
    REQUIRE(state.active_actions[0].status == ActionExecutionStatus::Failed);
    REQUIRE(state.crew[1].eva_status == EVAStatus::Idle);
}

TEST_CASE("actions: packet outside window fails", "[actions][comms]"){
    ActionExecutor exec;
    ScenarioConfig config = makeActionConfig();
    SimulationState state = makeActionState(config);
    state.time_min = 50;
    std::vector<TimelineEvent> events;

    Action packet{};
    packet.type = ActionType::SendEmergencyPacket;
    packet.start_min = 50;

    exec.applyScheduledActions(makePlan({packet}), state, config, events);
    REQUIRE(state.active_actions[0].status == ActionExecutionStatus::Failed);
    REQUIRE_FALSE(state.emergency_packet_sent);
}

TEST_CASE("actions: packet in window completes after duration", "[actions][comms]"){
    ActionExecutor exec;
    ScenarioConfig config = makeActionConfig();
    SimulationState state = makeActionState(config);
    state.time_min = 100;
    double o2_before = 40.0;
    state.oxygen_mass_kg = o2_before;
    std::vector<TimelineEvent> events;

    Action packet{};
    packet.type = ActionType::SendEmergencyPacket;
    packet.start_min = 100;

    exec.applyScheduledActions(makePlan({packet}), state, config, events);
    REQUIRE(state.active_actions[0].status == ActionExecutionStatus::Active);
    REQUIRE(state.communications_load_kw == Approx(0.5));

    for(int i = 0; i < 5; ++i){
        state.time_min = 100 + i + 1;
        exec.updateActiveActions(state, config, events, 60.0);
    }

    REQUIRE(state.emergency_packet_sent);
    REQUIRE(state.active_actions[0].status == ActionExecutionStatus::Complete);
    REQUIRE(state.oxygen_mass_kg == Approx(o2_before));
    REQUIRE(state.communications_load_kw == Approx(config.power.communications_load_kw));
}

TEST_CASE("actions: repair EVA advances phases and restores solar only on complete", "[actions][repair][eva]"){
    ActionExecutor exec;
    ResourceModel resources;
    ScenarioConfig config = makeActionConfig();
    SimulationState state = makeActionState(config);
    state.time_min = 0;
    std::vector<TimelineEvent> events;

    Action repair{};
    repair.type = ActionType::RepairSolarArray;
    repair.start_min = 0;
    repair.eva_crew_id = "crew_01";

    exec.applyScheduledActions(makePlan({repair}), state, config, events);
    REQUIRE(state.crew[0].eva_status == EVAStatus::Preparing);
    REQUIRE(state.solar_fault_factor == Approx(0.3));
    REQUIRE(state.solar_repair_progress == Approx(0.0));

    // preparation 10 min
    for(int t = 0; t < 10; ++t){
        resources.updateEVAAndRepair(state, config, events, 60.0);
        state.time_min += 1;
        exec.updateActiveActions(state, config, events, 60.0);
    }
    REQUIRE(state.crew[0].eva_status == EVAStatus::Egress);
    REQUIRE(state.solar_repair_progress == Approx(0.0));
    REQUIRE(state.solar_fault_factor == Approx(0.3));

    // egress 10 min
    for(int t = 0; t < 10; ++t){
        resources.updateEVAAndRepair(state, config, events, 60.0);
        state.time_min += 1;
        exec.updateActiveActions(state, config, events, 60.0);
    }
    REQUIRE(state.crew[0].eva_status == EVAStatus::Working);
    REQUIRE(state.solar_repair_progress == Approx(0.0));

    // work 20 min at performance 1.0
    for(int t = 0; t < 20; ++t){
        resources.updateEVAAndRepair(state, config, events, 60.0);
        state.time_min += 1;
        exec.updateActiveActions(state, config, events, 60.0);
    }
    REQUIRE(state.solar_repair_progress == Approx(1.0));
    REQUIRE(state.crew[0].eva_status == EVAStatus::Ingress);
    REQUIRE(state.solar_fault_factor == Approx(0.3));

    // ingress 10 min
    for(int t = 0; t < 10; ++t){
        resources.updateEVAAndRepair(state, config, events, 60.0);
        state.time_min += 1;
        exec.updateActiveActions(state, config, events, 60.0);
    }
    REQUIRE(state.crew[0].eva_status == EVAStatus::Complete);
    REQUIRE(state.solar_fault_factor == Approx(1.0));
    REQUIRE(state.active_actions[0].status == ActionExecutionStatus::Complete);
}

TEST_CASE("actions: repair progress slower with lower physical performance", "[actions][repair]"){
    ResourceModel resources;
    ScenarioConfig config = makeActionConfig();
    SimulationState state = makeActionState(config);
    std::vector<TimelineEvent> events;

    state.crew[0].eva_status = EVAStatus::Working;
    state.crew[0].actvity = CrewActivity::EVAWork;
    state.crew[0].physical_performance_factor = 0.5;
    state.eva_elapsed_min = config.eva.preparation_min + config.eva.egress_min;
    state.eva_work_elapsed_min = 0;
    state.solar_repair_progress = 0.0;

    resources.updateEVAAndRepair(state, config, events, 60.0);
    REQUIRE(state.solar_repair_progress == Approx(0.5 / 20.0));

    SimulationState state_full = makeActionState(config);
    state_full.crew[0].eva_status = EVAStatus::Working;
    state_full.crew[0].physical_performance_factor = 1.0;
    state_full.eva_elapsed_min = config.eva.preparation_min + config.eva.egress_min;
    std::vector<TimelineEvent> events2;
    resources.updateEVAAndRepair(state_full, config, events2, 60.0);
    REQUIRE(state_full.solar_repair_progress == Approx(1.0 / 20.0));
    REQUIRE(state.solar_repair_progress < state_full.solar_repair_progress);
}

TEST_CASE("actions: no repair progress during preparation", "[actions][repair][eva]"){
    ResourceModel resources;
    ScenarioConfig config = makeActionConfig();
    SimulationState state = makeActionState(config);
    std::vector<TimelineEvent> events;

    state.crew[0].eva_status = EVAStatus::Preparing;
    state.crew[0].physical_performance_factor = 1.0;
    state.eva_elapsed_min = 0;
    state.solar_repair_progress = 0.0;

    resources.updateEVAAndRepair(state, config, events, 60.0);
    REQUIRE(state.solar_repair_progress == Approx(0.0));
    REQUIRE(state.crew[0].eva_status == EVAStatus::Preparing);
}

TEST_CASE("actions: ActiveActionState persists progress not planner Action", "[actions]"){
    ActionExecutor exec;
    ScenarioConfig config = makeActionConfig();
    SimulationState state = makeActionState(config);
    std::vector<TimelineEvent> events;

    Action action{};
    action.type = ActionType::DelayRoverUse;
    action.start_min = 0;
    action.hours = 2.0;
    Plan plan = makePlan({action});

    exec.applyScheduledActions(plan, state, config, events);
    REQUIRE(plan.actions[0].hours == Approx(2.0));
    REQUIRE(state.active_actions[0].type == ActionType::DelayRoverUse);
    REQUIRE(state.active_actions[0].status == ActionExecutionStatus::Active);
    REQUIRE(state.active_actions[0].actual_start_min.has_value());
}
