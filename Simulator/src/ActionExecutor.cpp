#include "ActionExecutor.hpp"
#include "ResourceModel.hpp"
#include <cctype>

namespace {

string toLower(string value){
    for(char& c : value){
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    }
    return value;
}

bool isProtectedLoadGroup(const string& group){
    string g = toLower(group);
    return g == "essential" || g == "life_support" || g == "life-support" || g == "protected";
}

}

ActiveActionState ActionExecutor::makeActive(
    int action_index, ActionType type, int start_min) const{
    ActiveActionState active{};
    active.action_index = action_index;
    active.type = type;
    active.status = ActionExecutionStatus::Active;
    active.actual_start_min = start_min;
    active.elapsed_min = 0;
    active.progress_fraction = 0.0;
    return active;
}

void ActionExecutor::emitEvent(
    vector<TimelineEvent>& events, int time_min, const string& event_type,
    const string& message, ConstraintSeverity severity) const{
    TimelineEvent ev{};
    ev.time_min = time_min;
    ev.event_type = event_type;
    ev.message = message;
    ev.severity = severity;
    events.push_back(ev);
}

bool ActionExecutor::hasStartedAction(const SimulationState& state, int action_index) const{
    for(const auto& active : state.active_actions){
        if(active.action_index == action_index){
            return true;
        }
    }
    return false;
}

string ActionExecutor::resolveEvaCrewId(const Action& action) const{
    if(action.eva_crew_id.has_value() && !action.eva_crew_id->empty()){
        return *action.eva_crew_id;
    }
    if(!action.assigned_crew_ids.empty()){
        return action.assigned_crew_ids.front();
    }
    if(action.crew_id.has_value()){
        return *action.crew_id;
    }
    return "";
}

CrewMemberState* ActionExecutor::findCrew(SimulationState& state, const string& crew_id){
    for(auto& crew : state.crew){
        if(crew.crew_id == crew_id){
            return &crew;
        }
    }
    return nullptr;
}

const CrewMemberConfig* ActionExecutor::findCrewConfig(
    const ScenarioConfig& config, const string& crew_id) const{
    for(const auto& member : config.crew_roster){
        if(member.crew_id == crew_id){
            return &member;
        }
    }
    return nullptr;
}

CrewActivity ActionExecutor::parseActivityLevel(const std::optional<string>& level) const{
    if(!level.has_value()){
        return CrewActivity::Resting;
    }
    string value = toLower(*level);
    if(value == "sleep"){
        return CrewActivity::Sleep;
    }
    if(value == "rest" || value == "resting"){
        return CrewActivity::Resting;
    }
    if(value == "nominal" || value == "nominal_work" || value == "nominalwork"){
        return CrewActivity::NominalWork;
    }
    if(value == "high" || value == "high_workload" || value == "highworkload"){
        return CrewActivity::HighWorkload;
    }
    if(value == "recovery"){
        return CrewActivity::Recovery;
    }
    return CrewActivity::Resting;
}

void ActionExecutor::applyScheduledActions(
    const Plan& plan, SimulationState& state, const ScenarioConfig& config,
    vector<TimelineEvent>& events){
    for(size_t i = 0; i < plan.actions.size(); ++i){
        const Action& action = plan.actions[i];
        int action_index = static_cast<int>(i);
        if(action.start_min != state.time_min){
            continue;
        }
        if(hasStartedAction(state, action_index)){
            continue;
        }

        switch(action.type){
        case ActionType::ReducePowerLoad:
            startReducePowerLoad(action, action_index, state, events);
            break;
        case ActionType::IsolateModule:
            startIsolateModule(action, action_index, state, config, events);
            break;
        case ActionType::OxygenRationing:
            startOxygenRationing(action, action_index, state, events);
            break;
        case ActionType::RepairSolarArray:
            startRepairSolarArray(action, action_index, state, config, events);
            break;
        case ActionType::DelayRoverUse:
            startDelayRoverUse(action, action_index, state, events);
            break;
        case ActionType::SendEmergencyPacket:
            startSendEmergencyPacket(action, action_index, state, config, events);
            break;
        case ActionType::Unknown:
        default:{
            ActiveActionState active = makeActive(action_index, action.type, state.time_min);
            active.status = ActionExecutionStatus::Failed;
            active.failure_reason = "unknown action type";
            state.active_actions.push_back(active);
            emitEvent(events, state.time_min, "action_failed",
                "unknown action type rejected at start", ConstraintSeverity::Failure);
            break;
        }
        }
    }
}

void ActionExecutor::startReducePowerLoad(
    const Action& action, int action_index, SimulationState& state,
    vector<TimelineEvent>& events){
    ActiveActionState active = makeActive(action_index, ActionType::ReducePowerLoad, state.time_min);

    if(!action.percent.has_value() || *action.percent < 0.0 || *action.percent > 100.0){
        active.status = ActionExecutionStatus::Failed;
        active.failure_reason = "reduce_power_load requires percent in [0, 100]";
        state.active_actions.push_back(active);
        emitEvent(events, state.time_min, "action_failed", active.failure_reason, ConstraintSeverity::Failure);
        return;
    }
    if(action.load_groups.empty()){
        active.status = ActionExecutionStatus::Failed;
        active.failure_reason = "reduce_power_load requires load_groups";
        state.active_actions.push_back(active);
        emitEvent(events, state.time_min, "action_failed", active.failure_reason, ConstraintSeverity::Failure);
        return;
    }

    double fraction = *action.percent / 100.0;
    bool shed_any = false;
    for(const string& group : action.load_groups){
        if(isProtectedLoadGroup(group)){
            active.status = ActionExecutionStatus::Failed;
            active.failure_reason = "cannot shed protected life-support load group: " + group;
            state.active_actions.push_back(active);
            emitEvent(events, state.time_min, "action_failed", active.failure_reason, ConstraintSeverity::Failure);
            return;
        }
        string g = toLower(group);
        if(g == "discretionary"){
            double before = state.discretionary_load_kw;
            state.discretionary_load_kw *= (1.0 - fraction);
            if(before > 0.0){
                state.equipment_heat_w *= (state.discretionary_load_kw / before);
            }
            shed_any = true;
        }else if(g == "thermal_control" || g == "tcs"){
            state.thermal_control_load_kw *= (1.0 - fraction);
            state.tcs_rejection_capacity_w *= (1.0 - fraction);
            shed_any = true;
        }else if(g == "communications" || g == "comms"){
            state.communications_load_kw *= (1.0 - fraction);
            shed_any = true;
        }else if(g == "eva_support" || g == "eva"){
            state.eva_support_load_kw *= (1.0 - fraction);
            shed_any = true;
        }else{
            active.status = ActionExecutionStatus::Failed;
            active.failure_reason = "unknown or protected load group: " + group;
            state.active_actions.push_back(active);
            emitEvent(events, state.time_min, "action_failed", active.failure_reason, ConstraintSeverity::Failure);
            return;
        }
    }

    if(!shed_any){
        active.status = ActionExecutionStatus::Failed;
        active.failure_reason = "no discretionary load groups were reduced";
        state.active_actions.push_back(active);
        emitEvent(events, state.time_min, "action_failed", active.failure_reason, ConstraintSeverity::Failure);
        return;
    }

    active.status = ActionExecutionStatus::Complete;
    active.progress_fraction = 1.0;
    state.active_actions.push_back(active);
    emitEvent(events, state.time_min, "action_started",
        "reduce_power_load applied", ConstraintSeverity::Info);
    emitEvent(events, state.time_min, "action_complete",
        "reduce_power_load complete", ConstraintSeverity::Info);
}

void ActionExecutor::startIsolateModule(
    const Action& action, int action_index, SimulationState& state,
    const ScenarioConfig& config, vector<TimelineEvent>& events){
    ActiveActionState active = makeActive(action_index, ActionType::IsolateModule, state.time_min);

    if(!action.module.has_value() || action.module->empty()){
        active.status = ActionExecutionStatus::Failed;
        active.failure_reason = "isolate_module requires module";
        state.active_actions.push_back(active);
        emitEvent(events, state.time_min, "action_failed", active.failure_reason, ConstraintSeverity::Failure);
        return;
    }

    const string& module = *action.module;
    for(const auto& crew : state.crew){
        if(crew.location_module == module){
            active.status = ActionExecutionStatus::Failed;
            active.failure_reason = "crew would remain trapped in isolated module: " + crew.crew_id;
            state.active_actions.push_back(active);
            emitEvent(events, state.time_min, "action_failed", active.failure_reason, ConstraintSeverity::Failure);
            return;
        }
    }

    state.module_isolated = true;
    state.isolated_module = module;
    state.habitable_volume_m3 = config.habitat.isolated_habitable_volume_m3;
    state.leak_fault_factor *= config.fault.isolation_leak_multiplier;

    active.status = ActionExecutionStatus::Complete;
    active.progress_fraction = 1.0;
    state.active_actions.push_back(active);
    emitEvent(events, state.time_min, "action_started",
        "isolate_module applied to " + module, ConstraintSeverity::Info);
    emitEvent(events, state.time_min, "action_complete",
        "isolate_module complete; leak continues at reduced factor", ConstraintSeverity::Info);
}

void ActionExecutor::startOxygenRationing(
    const Action& action, int action_index, SimulationState& state,
    vector<TimelineEvent>& events){
    ActiveActionState active = makeActive(action_index, ActionType::OxygenRationing, state.time_min);
    CrewActivity activity = parseActivityLevel(action.level);

    vector<string> targets = action.target_crew_ids;
    if(targets.empty()){
        for(const auto& crew : state.crew){
            targets.push_back(crew.crew_id);
        }
    }

    for(const string& crew_id : targets){
        CrewMemberState* crew = findCrew(state, crew_id);
        if(crew == nullptr){
            active.status = ActionExecutionStatus::Failed;
            active.failure_reason = "oxygen_rationing target crew not found: " + crew_id;
            state.active_actions.push_back(active);
            emitEvent(events, state.time_min, "action_failed", active.failure_reason, ConstraintSeverity::Failure);
            return;
        }
        crew->oxygen_rationing_active = true;
        if(crew->eva_status == EVAStatus::Idle ||
           crew->eva_status == EVAStatus::Complete ||
           crew->eva_status == EVAStatus::Aborted){
            crew->actvity = activity;
        }
    }

    active.status = ActionExecutionStatus::Complete;
    active.progress_fraction = 1.0;
    active.assigned_crew_ids = targets;
    state.active_actions.push_back(active);
    emitEvent(events, state.time_min, "action_started",
        "oxygen_rationing applied", ConstraintSeverity::Info);
    emitEvent(events, state.time_min, "action_complete",
        "oxygen_rationing complete; future metabolic loads reduced", ConstraintSeverity::Info);
}

void ActionExecutor::startRepairSolarArray(
    const Action& action, int action_index, SimulationState& state,
    const ScenarioConfig& config, vector<TimelineEvent>& events){
    ActiveActionState active = makeActive(action_index, ActionType::RepairSolarArray, state.time_min);
    string crew_id = resolveEvaCrewId(action);

    if(crew_id.empty()){
        active.status = ActionExecutionStatus::Failed;
        active.failure_reason = "repair_solar_array requires eva_crew_id or assigned_crew_ids";
        state.active_actions.push_back(active);
        emitEvent(events, state.time_min, "action_failed", active.failure_reason, ConstraintSeverity::Failure);
        return;
    }

    CrewMemberState* crew = findCrew(state, crew_id);
    const CrewMemberConfig* member = findCrewConfig(config, crew_id);
    if(crew == nullptr || member == nullptr){
        active.status = ActionExecutionStatus::Failed;
        active.failure_reason = "repair_solar_array crew not found: " + crew_id;
        state.active_actions.push_back(active);
        emitEvent(events, state.time_min, "action_failed", active.failure_reason, ConstraintSeverity::Failure);
        return;
    }
    if(!member->eva_qualified){
        active.status = ActionExecutionStatus::Failed;
        active.failure_reason = "crew is not EVA qualified: " + crew_id;
        state.active_actions.push_back(active);
        emitEvent(events, state.time_min, "action_failed", active.failure_reason, ConstraintSeverity::Failure);
        return;
    }
    if(crew->eva_status != EVAStatus::Idle &&
       crew->eva_status != EVAStatus::Complete &&
       crew->eva_status != EVAStatus::Aborted){
        active.status = ActionExecutionStatus::Failed;
        active.failure_reason = "crew already on EVA: " + crew_id;
        state.active_actions.push_back(active);
        emitEvent(events, state.time_min, "action_failed", active.failure_reason, ConstraintSeverity::Failure);
        return;
    }
    if(crew->health_status == CrewHealthStatus::Incapacitated ||
       crew->health_status == CrewHealthStatus::Critical ||
       crew->health_status == CrewHealthStatus::Impaired){
        active.status = ActionExecutionStatus::Failed;
        active.failure_reason = "crew health prevents EVA: " + crew_id;
        state.active_actions.push_back(active);
        emitEvent(events, state.time_min, "action_failed", active.failure_reason, ConstraintSeverity::Failure);
        return;
    }
    if(config.eva.rover_required){
        if(!state.rover_available ||
           (state.rover_reserved_until_min > 0 && state.time_min < state.rover_reserved_until_min)){
            active.status = ActionExecutionStatus::Failed;
            active.failure_reason = "rover unavailable or reserved for repair_solar_array";
            state.active_actions.push_back(active);
            emitEvent(events, state.time_min, "action_failed", active.failure_reason, ConstraintSeverity::Failure);
            return;
        }
        if(state.rover_battery_percent < config.eva.rover_minimum_reserve_percent){
            active.status = ActionExecutionStatus::Failed;
            active.failure_reason = "rover battery below minimum reserve";
            state.active_actions.push_back(active);
            emitEvent(events, state.time_min, "action_failed", active.failure_reason, ConstraintSeverity::Failure);
            return;
        }
    }

    crew->eva_status = EVAStatus::Preparing;
    crew->actvity = CrewActivity::EVAPrep;
    state.eva_available = true;
    state.eva_elapsed_min = 0;
    state.eva_work_elapsed_min = 0;
    state.solar_repair_progress = 0.0;

    active.status = ActionExecutionStatus::Active;
    active.assigned_crew_id = crew_id;
    active.eva_crew_id = crew_id;
    active.assigned_crew_ids = action.assigned_crew_ids;
    if(active.assigned_crew_ids.empty()){
        active.assigned_crew_ids.push_back(crew_id);
    }
    state.active_actions.push_back(active);
    emitEvent(events, state.time_min, "action_started",
        "repair_solar_array started; EVA preparation begins for " + crew_id,
        ConstraintSeverity::Info);
}

void ActionExecutor::startDelayRoverUse(
    const Action& action, int action_index, SimulationState& state,
    vector<TimelineEvent>& events){
    ActiveActionState active = makeActive(action_index, ActionType::DelayRoverUse, state.time_min);

    int delay_min = 0;
    if(action.hours.has_value()){
        delay_min = static_cast<int>(*action.hours * 60.0);
    }else if(action.duration_min.has_value()){
        delay_min = *action.duration_min;
    }else{
        active.status = ActionExecutionStatus::Failed;
        active.failure_reason = "delay_rover_use requires hours or duration_min";
        state.active_actions.push_back(active);
        emitEvent(events, state.time_min, "action_failed", active.failure_reason, ConstraintSeverity::Failure);
        return;
    }
    if(delay_min <= 0){
        active.status = ActionExecutionStatus::Failed;
        active.failure_reason = "delay_rover_use duration must be positive";
        state.active_actions.push_back(active);
        emitEvent(events, state.time_min, "action_failed", active.failure_reason, ConstraintSeverity::Failure);
        return;
    }

    state.rover_available = false;
    state.rover_reserved_until_min = state.time_min + delay_min;
    active.status = ActionExecutionStatus::Active;
    state.active_actions.push_back(active);
    emitEvent(events, state.time_min, "action_started",
        "delay_rover_use reserved rover until t=" + std::to_string(state.rover_reserved_until_min),
        ConstraintSeverity::Info);
}

void ActionExecutor::startSendEmergencyPacket(
    const Action& action, int action_index, SimulationState& state,
    const ScenarioConfig& config, vector<TimelineEvent>& events){
    ActiveActionState active = makeActive(action_index, ActionType::SendEmergencyPacket, state.time_min);
    ResourceModel resources;

    if(state.emergency_packet_sent){
        active.status = ActionExecutionStatus::Failed;
        active.failure_reason = "emergency packet already sent";
        state.active_actions.push_back(active);
        emitEvent(events, state.time_min, "action_failed", active.failure_reason, ConstraintSeverity::Failure);
        return;
    }

    CommunicationsTelemetry comms = resources.calculateCommunicationsTelemetry(state, config);
    if(!comms.comms_window_open){
        active.status = ActionExecutionStatus::Failed;
        active.failure_reason = "send_emergency_packet requires an open communications window";
        state.active_actions.push_back(active);
        emitEvent(events, state.time_min, "action_failed", active.failure_reason, ConstraintSeverity::Failure);
        return;
    }

    state.transmission_elapsed_min = 0;
    state.communications_load_kw = config.communications.transmission_power_kw;
    active.status = ActionExecutionStatus::Active;
    state.active_actions.push_back(active);
    emitEvent(events, state.time_min, "action_started",
        "send_emergency_packet transmission started", ConstraintSeverity::Info);
}

void ActionExecutor::updateActiveActions(
    SimulationState& state, const ScenarioConfig& config,
    vector<TimelineEvent>& events, double dt_seconds){
    double dt_minutes = dt_seconds / 60.0;
    int dt_min_i = static_cast<int>(dt_minutes);

    for(auto& active : state.active_actions){
        if(active.status != ActionExecutionStatus::Active){
            continue;
        }
        active.elapsed_min += dt_min_i;

        if(active.type == ActionType::DelayRoverUse){
            if(state.time_min >= state.rover_reserved_until_min){
                state.rover_available = true;
                state.rover_reserved_until_min = 0;
                active.status = ActionExecutionStatus::Complete;
                active.progress_fraction = 1.0;
                emitEvent(events, state.time_min, "action_complete",
                    "delay_rover_use complete; rover available", ConstraintSeverity::Info);
            }else if(state.rover_reserved_until_min > active.actual_start_min.value_or(0)){
                int total = state.rover_reserved_until_min - active.actual_start_min.value_or(0);
                int done = state.time_min - active.actual_start_min.value_or(0);
                active.progress_fraction = total > 0
                    ? static_cast<double>(done) / static_cast<double>(total)
                    : 1.0;
            }
        }else if(active.type == ActionType::SendEmergencyPacket){
            state.transmission_elapsed_min += dt_min_i;
            int duration = config.communications.transmission_duration_min;
            if(duration <= 0){
                duration = 1;
            }
            active.progress_fraction =
                static_cast<double>(state.transmission_elapsed_min) / static_cast<double>(duration);
            if(active.progress_fraction > 1.0){
                active.progress_fraction = 1.0;
            }
            if(state.transmission_elapsed_min >= duration){
                state.emergency_packet_sent = true;
                state.communications_load_kw = config.power.communications_load_kw;
                active.status = ActionExecutionStatus::Complete;
                active.progress_fraction = 1.0;
                emitEvent(events, state.time_min, "action_complete",
                    "send_emergency_packet complete", ConstraintSeverity::Info);
            }
        }else if(active.type == ActionType::RepairSolarArray){
            active.progress_fraction = state.solar_repair_progress;
            string crew_id;
            if(active.eva_crew_id.has_value()){
                crew_id = *active.eva_crew_id;
            }else if(active.assigned_crew_id.has_value()){
                crew_id = *active.assigned_crew_id;
            }
            CrewMemberState* crew = crew_id.empty() ? nullptr : findCrew(state, crew_id);
            if(crew != nullptr){
                if(crew->eva_status == EVAStatus::Complete && state.solar_repair_progress >= 1.0){
                    active.status = ActionExecutionStatus::Complete;
                    active.progress_fraction = 1.0;
                    emitEvent(events, state.time_min, "action_complete",
                        "repair_solar_array complete", ConstraintSeverity::Info);
                }else if(crew->eva_status == EVAStatus::Aborted){
                    active.status = ActionExecutionStatus::Aborted;
                    active.failure_reason = "EVA aborted before repair completion";
                    emitEvent(events, state.time_min, "action_aborted",
                        active.failure_reason, ConstraintSeverity::Critical);
                }
            }
        }
    }
}
