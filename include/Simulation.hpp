#pragma once

#include "ActionExecutor.hpp"
#include "CrewPhysiologyModel.hpp"
#include "Plan.hpp"
#include "ResourceModel.hpp"
#include "ScenarioConfig.hpp"
#include "SimulationResult.hpp"
#include "SimulationState.hpp"
#include "Validator.hpp"

using namespace std;

// owns scenario state and mission authority for baseline/plan runs

struct MissionEvaluation{
    bool terminate;
    OutcomeStatus outcome;
};

class Simulation{
public:
    SimulationResult runBaseline(const ScenarioConfig& config);
    SimulationResult runWithPlan(const ScenarioConfig& config, const Plan& plan);

    MissionEvaluation evaluateMissionState(
        SimulationState& state,
        const ScenarioConfig& config,
        DerivedTelemetry& telemetry,
        MissionTelemetry& mission,
        vector<TimelineEvent>& events,
        double dt_minutes);

    void updateExtremaAndMetrics(
        SimulationMetrics& metrics,
        const DerivedTelemetry& telemetry,
        const SimulationState& state) const;

private:
    SimulationState initializeState(const ScenarioConfig& config) const;
    SimulationMetrics initializeMetrics() const;
    MissionTelemetry initializeMission() const;

    SimulationResult makeRejectedResult(
        const ScenarioConfig& config,
        const string& plan_id,
        const ValidationResult& validation) const;

    SimulationResult runInternal(
        const ScenarioConfig& config,
        const Plan* plan);

    DerivedTelemetry buildTelemetry(
        const SimulationState& state,
        const ScenarioConfig& config,
        const MissionTelemetry& mission) const;

    void applyCrewAbortRules(
        SimulationState& state,
        const DerivedTelemetry& telemetry,
        vector<TimelineEvent>& events) const;

    bool isOutsideEva(EVAStatus status) const;
    bool stabilizationConditionsMet(
        const SimulationState& state,
        const ScenarioConfig& config,
        const DerivedTelemetry& telemetry) const;
    double remainingRepairHours(
        const SimulationState& state,
        const ScenarioConfig& config) const;
    double minimumResourceDeadlineHours(const DerivedTelemetry& telemetry) const;

    Validator validator_;
    ActionExecutor action_executor_;
    CrewPhysiologyModel crew_model_;
    ResourceModel resource_model_;
};
