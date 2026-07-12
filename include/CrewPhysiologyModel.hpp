#pragma once

#include <string>
#include <vector>
#include "CrewMember.hpp"
#include "DerivedTelemetry.hpp"
#include "ScenarioConfig.hpp"
#include "SimulationState.hpp"

using namespace std;

// crew-state initialization and frontend-ready vitals telemetry.

class CrewPhysiologyModel {
public:
    vector<CrewMemberState> initializeCrewStates(const ScenarioConfig& config) const;
    vector<CrewVitalsTelemetry> buildCrewVitalsTelemetry(
        const SimulationState& state, const ScenarioConfig& config) const;
    const CrewMemberConfig& findCrewConfig(
        const string& crew_id, const ScenarioConfig& config) const;

    const ActivityMetabolicProfile& findActivityProfile(
        CrewActivity activity, const VitalResponseConfig& vital_response) const;

    double calculateHypoxiaSeverity(
        const DerivedTelemetry& telemetry, const ScenarioConfig& config,
        const CrewMemberConfig& crew) const;
    double calculateCo2Severity(
        const DerivedTelemetry& telemetry, const ScenarioConfig& config,
        const CrewMemberConfig& crew) const;
    double calculatePressureSeverity(
        const DerivedTelemetry& telemetry, const ScenarioConfig& config,
        const CrewMemberConfig& crew) const;
    // cabin_temperature_c from SimulationState; not present on DerivedTelemetry
    double calculateThermalSeverity(
        const DerivedTelemetry& telemetry, const ScenarioConfig& config,
        const CrewMemberConfig& crew, double cabin_temperature_c) const;

    void updateExposureIndices(
        CrewMemberState& crew, double hypoxia_severity, double co2_severity,
        double thermal_severity, const VitalResponseConfig& config,
        double dt_minutes) const;
    void updateFatigue(
        CrewMemberState& crew, const CrewMemberConfig& member,
        const ActivityMetabolicProfile& profile, double hypoxia_severity,
        double co2_severity, double thermal_severity,
        const VitalResponseConfig& config, double dt_minutes) const;
    void updateMetabolicOutputs(
        CrewMemberState& crew, const CrewMemberConfig& member,
        const ActivityMetabolicProfile& profile,
        const VitalResponseConfig& config) const;
    void updateVitalSigns(
        CrewMemberState& crew, const CrewMemberConfig& member,
        const ActivityMetabolicProfile& profile, const DerivedTelemetry& telemetry,
        double hypoxia_severity, double co2_severity, double pressure_severity,
        double thermal_severity, const VitalResponseConfig& config,
        double dt_minutes, double cabin_temperature_c) const;
    void updatePerformance(
        CrewMemberState& crew, const ActivityMetabolicProfile& profile,
        const VitalResponseConfig& config) const;
    void updateHealthStatusAndAlarms(
        CrewMemberState& crew, const DerivedTelemetry& telemetry,
        const VitalResponseConfig& config) const;

    void updateCrewMember(
        CrewMemberState& crew, const CrewMemberConfig& member,
        const DerivedTelemetry& pre_step_telemetry, const ScenarioConfig& config,
        double dt_seconds, double cabin_temperature_c);
    void updateAllCrew(
        SimulationState& state, const ScenarioConfig& config,
        const DerivedTelemetry& pre_step_telemetry, double dt_seconds);
};
