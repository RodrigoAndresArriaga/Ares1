#pragma once
#include <string>
#include <vector>
#include "CrewMember.hpp"
#include "Enums.hpp"

using namespace std;

//values derived from ScenarioConfig and SimulationState here.

struct AtmosphereTelemetry{
    double cabin_pressure_kpa;
    double oxygen_fraction;
    double inspired_oxygen_mmhg;
    double co2_partial_pressure_mmhg;
    double co2_one_hour_avg_mmhg;
    double oxygen_hours_remaining;
    double time_to_pressure_limit_hr;
    double time_to_co2_limit_hr;
};

struct PowerTelemetry{
    double solar_generation_kw;
    double healthy_solar_generation_kw;
    double solar_generation_percent;
    double total_habitat_load_kw;
    double power_margin_kw;
    double battery_soc_percent;
    double battery_hours_to_reserve;
};

struct ThermalTelemetry{
    double crew_heat_w;
    double tcs_commanded_rejection_w;
    double net_thermal_power_w;
    double thermal_margin_w;
    double temperature_margin_c;
};

struct EVATelemetry{
    double eva_consumables_remaining_min;
    double eva_safe_return_margin_min;
    double repair_progress_percent;
    string active_crew_id;
};

struct CommunicationsTelemetry{
    bool comms_window_open;
    double next_comms_window_min;
    bool transmission_in_progress;
    bool emergency_packet_sent;
};

struct MissionTelemetry{
    MissionStatus mission_status;
    double stabilization_elapsed_min;
    vector<string> violated_constraints;
    vector<string> warnings;
};

struct DerivedTelemetry{
    AtmosphereTelemetry atmosphere;
    PowerTelemetry power;
    ThermalTelemetry thermal;
    EVATelemetry eva;
    CommunicationsTelemetry communications;
    MissionTelemetry mission;
    vector<CrewVitalsTelemetry> crew_vitals;
};
