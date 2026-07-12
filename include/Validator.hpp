#pragma once

#include "Plan.hpp"
#include "ScenarioConfig.hpp"
#include "ValidationResult.hpp"

using namespace std;

// static and plan validation before any physical run
class Validator{
public:
    ValidationResult validateScenario(const ScenarioConfig& config) const;
    ValidationResult validatePlan(const Plan& plan, const ScenarioConfig& config) const;

private:
    void addError(
        ValidationResult& result, const string& code, const string& message,
        ConstraintSeverity severity,
        std::optional<int> action_index = std::nullopt) const;
    bool crewIdExists(const ScenarioConfig& config, const string& crew_id) const;
    const CrewMemberConfig* findCrew(
        const ScenarioConfig& config, const string& crew_id) const;
    bool activityProfileExists(
        const ScenarioConfig& config, CrewActivity activity) const;
    bool isCommsWindowOpen(const ScenarioConfig& config, int time_min) const;
};
