#pragma once
using namespace std;

#include<string>
#include<vector>
#include "Enums.hpp"

//crew configuration, mutable crew state, and crew telemetry data here.

struct CrewMemberConfig{
    string crew_id;
    string display_name;
    string assigned_role;
    double body_mass_kg;
    double baseline_heart_rate_bpm;
    double baseline_respiratory_rate_bpm;
    double baseline_spo2_percent;
    double baseline_core_temperature_c;
    double fitness_factor;
    double hypoxia_sensitivity;
    double co2_sensitivity;
    double thermal_sensitivity;
    double fatigue_recovery_factor;
    bool eva_qualified;

    //Initial operational state
    CrewActivity initial_activity;
    string initial_location_module;
    EVAStatus initial_eva_status;
    bool initial_oxygen_rationing_active;
};

struct CrewMemberState{
    string crew_id;
    string location_module;
    double heart_rate_bpm;
    double respiratory_rate_bpm;
    double spo2_percent;
    double core_temperature_c;
    double hypoxia_exposure_index;
    double co2_exposure_index;
    double thermal_exposure_index;
    double fatigue_index;
    double cognitive_performance_factor;
    double physical_performance_factor;
    double oxygen_consumption_g_min;
    double co2_production_g_min;
    double heat_output_w;
    bool oxygen_rationing_active;
    CrewActivity actvity;
    EVAStatus eva_status;
    CrewHealthStatus health_status;
    vector<CrewAlarmType> active_alarms;
};

struct CrewVitalsTelemetry{
    //Identity and context
    string crew_id;
    string display_name;
    string assigned_role;
    string location_module;
    CrewActivity activity;
    EVAStatus eva_status;

    //vitals
    double heart_rate_bpm;
    double respiratory_rate_bpm;
    double spo2_percent;
    double core_temperature_c;

    //metabolism
    double oxygen_consumption_g_min;
    double co2_production_g_min;
    double heat_output_w;

    //exposure and performance output
    double fatigue_percent;
    double hypoxia_exposure;
    double co2_exposure;
    double thermal_exposure;
    double cognitive_performance_percent;
    double physical_performance_percent;


    //Health status
    CrewHealthStatus health_status;
    vector<CrewAlarmType> active_alarms;
};