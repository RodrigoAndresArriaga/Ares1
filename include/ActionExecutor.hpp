#pragma once

#include <optional>
#include <string>
#include <vector>
#include "Plan.hpp"
#include "ScenarioConfig.hpp"
#include "SimulationState.hpp"
#include "TelemetrySample.hpp"

using namespace std;

// start-once scheduled recovery actions and long-running progress updates.

class ActionExecutor{
public:
    void applyScheduledActions(
        const Plan& plan, SimulationState& state, const ScenarioConfig& config,
        vector<TimelineEvent>& events);
    void updateActiveActions(
        SimulationState& state, const ScenarioConfig& config,
        vector<TimelineEvent>& events, double dt_seconds);

private:
    bool hasStartedAction(const SimulationState& state, int action_index) const;
    string resolveEvaCrewId(const Action& action) const;
    CrewMemberState* findCrew(SimulationState& state, const string& crew_id);
    const CrewMemberConfig* findCrewConfig(const ScenarioConfig& config, const string& crew_id) const;
    CrewActivity parseActivityLevel(const std::optional<string>& level) const;

    void startReducePowerLoad(
        const Action& action, int action_index, SimulationState& state,
        vector<TimelineEvent>& events);
    void startIsolateModule(
        const Action& action, int action_index, SimulationState& state,
        const ScenarioConfig& config, vector<TimelineEvent>& events);
    void startOxygenRationing(
        const Action& action, int action_index, SimulationState& state,
        vector<TimelineEvent>& events);
    void startRepairSolarArray(
        const Action& action, int action_index, SimulationState& state,
        const ScenarioConfig& config, vector<TimelineEvent>& events);
    void startDelayRoverUse(
        const Action& action, int action_index, SimulationState& state,
        vector<TimelineEvent>& events);
    void startSendEmergencyPacket(
        const Action& action, int action_index, SimulationState& state,
        const ScenarioConfig& config, vector<TimelineEvent>& events);

    ActiveActionState makeActive(
        int action_index, ActionType type, int start_min) const;
    void emitEvent(
        vector<TimelineEvent>& events, int time_min, const string& event_type,
        const string& message, ConstraintSeverity severity) const;
};
