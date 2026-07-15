#pragma once

#include <vector>
#include "CrewMember.hpp"
#include "DerivedTelemetry.hpp"
#include "ScenarioConfig.hpp"
#include "SimulationState.hpp"
#include "TelemetrySample.hpp"

using namespace std;

//stateless physical-resource updates and derived habitat telemetry.

class ResourceModel{
public:
    void updateAtmosphere(SimulationState& state, const ScenarioConfig& config, double total_crew_oxygen_g_min, double dt_seconds);
    void updateCarbonDioxide(SimulationState& state, const ScenarioConfig& config, double total_crew_co2_g_min, double dt_seconds);
    double calculateSolarGenerationKw(const SimulationState& state, const ScenarioConfig& config) const;
    double calculateHealthySolarGenerationKw(const SimulationState& state, const ScenarioConfig& config) const;
    void updateElectricalPower(SimulationState& state, const ScenarioConfig& config, double solar_generation_kw, double dt_seconds);
    void updateThermalState(SimulationState& state, const ScenarioConfig& config, double total_crew_heat_w, double dt_seconds);
    void updateEVAAndRepair(SimulationState& state, const ScenarioConfig& config, vector<TimelineEvent>& events, double dt_seconds);
    AtmosphereTelemetry calculateAtmosphereTelemetry(const SimulationState& state, const ScenarioConfig& config) const;
    PowerTelemetry calculatePowerTelemetry(const SimulationState& state, const ScenarioConfig& config, double solar_generation_kw, double healthy_solar_generation_kw) const;
    ThermalTelemetry calculateThermalTelemetry(const SimulationState& state, const ScenarioConfig& config, double total_crew_heat_w) const;
    EVATelemetry calculateEVATelemetry(const SimulationState& state, const ScenarioConfig& config) const;
    CommunicationsTelemetry calculateCommunicationsTelemetry(const SimulationState& state, const ScenarioConfig& config) const;
    DerivedTelemetry calculateDerivedTelemetry(const SimulationState& state, const ScenarioConfig& config, const vector<CrewVitalsTelemetry>& crew_vitals, const MissionTelemetry& mission_telemetry) const;
};
