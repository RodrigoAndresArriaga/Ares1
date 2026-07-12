#pragma once
#include <string>
#include <vector>
#include "CrewMember.hpp"
#include "Enums.hpp"

using namespace std;

//immutable scenario and subsystem configuration data here.

struct ParameterSource{
    string parameter_name;
    SourceClassification classification;
    string source_label;
    string note;
};

struct CommunicationWindow{
    int open_min;
    int close_min;
};

struct ActivityMetabolicProfile{
    CrewActivity activity;
    double oxygen_g_min;
    double co2_g_min;
    double heat_w;
    double activity_load;
};

struct HabitatConfig{
    double initial_habitable_volume_m3;
    double isolated_habitable_volume_m3;
    double nominal_temperature_c;
    double initial_relative_humidity_percent;
    double effective_thermal_capacitance_kj_c;
};

struct AtmosphereConfig{
    //Initial inventory
    double initial_oxygen_mass_kg;
    double initial_inert_gas_mass_kg;
    double initial_co2_mass_kg;

    //Scrubber
    double scrubber_capacity_g_min;
    double initial_scrubber_efficiency;

    //Pressure checks
    double pressure_warning_low_kpa;
    double pressure_failure_low_kpa;
    double pressure_high_limit_kpa;

    //Inspired oxygen checks
    double inspired_o2_nominal_mmhg;
    double inspired_o2_warning_mmhg;
    double inspired_o2_failure_mmhg;

    //CO2 check
    double co2_one_hour_limit_mmhg;

    //Composition
    double minimum_inert_fraction;
};

struct PowerConfig{
    double initial_battery_energy_kwh;
    double battery_capacity_kwh;
    double battery_reserve_percent;
    double charge_efficiency;
    double discharge_efficiency;
    double essential_load_kw;
    double discretionary_load_kw;
    double thermal_control_load_kw;
    double eva_support_load_kw;
    double communications_load_kw;
};

struct SolarConfig{
    double array_area_m2;
    double cell_efficiency;
    double mars_sun_distance_au;
    double initial_incidence_angle_deg;
    double initial_atmospheric_transmission;
    double initial_deposited_dust_factor;
};

struct ThermalConfig{
    double initial_equipment_heat_w;
    double initial_environmental_heat_w;
    double initial_heater_heat_w;
    double tcs_rejection_capacity_w;
    double comfort_low_c;
    double comfort_high_c;
    double critical_low_c;
    double critical_high_c;
    double humidity_low_percent;
    double humidity_high_percent;
};

struct EVAConfig{
    bool available;
    int preparation_min;
    int egress_min;
    int repair_work_min;
    int ingress_min;
    int reserve_min;
    int maximum_duration_min;
    bool rover_required;
    double rover_minimum_reserve_percent;
};

struct CommunicationsConfig{
    vector<CommunicationWindow> windows;
    int transmission_duration_min;
    double transmission_power_kw;
};

struct FaultConfig{
    string failure_type;
    string leak_module;
    double total_gas_leak_kg_hr;
    double isolation_leak_multiplier;
    double solar_fault_factor;
    double repaired_solar_fault_factor;
};

struct VitalResponseConfig{
    //Activity profiles
    vector<ActivityMetabolicProfile> activity_profiles;

    //Exposure accumulation
    double hypoxia_accumulation_rate;
    double co2_accumulation_rate;
    double thermal_accumulation_rate;

    //Exposure recovery
    double hypoxia_recovery_rate;
    double co2_recovery_rate;
    double thermal_recovery_rate;

    //Fatigue
    double fatigue_work_rate;
    double fatigue_eva_rate;
    double fatigue_recovery_rate;

    //Heart-rate response
    double hr_activity_gain;
    double hr_hypoxia_gain;
    double hr_co2_gain;
    double hr_thermal_gain;
    double hr_fatigue_gain;
    double hr_min_bpm;
    double hr_max_bpm;

    //Respiratory-rate response
    double rr_activity_gain;
    double rr_hypoxia_gain;
    double rr_co2_gain;
    double rr_thermal_gain;
    double rr_min_bpm;
    double rr_max_bpm;

    //SpO2 response
    double spo2_hypoxia_gain;
    double spo2_pressure_gain;
    double spo2_activity_gain;
    double spo2_exposure_gain;
    double spo2_min_percent;
    double spo2_max_percent;

    //Core-temperature response
    double core_temp_environment_gain;
    double core_temp_activity_gain;
    double core_temp_time_constant_min;
    double core_temp_min_c;
    double core_temp_max_c;

    //Cognitive performance weights
    double cognitive_hypoxia_weight;
    double cognitive_co2_weight;
    double cognitive_thermal_weight;
    double cognitive_fatigue_weight;

    //Physical performance weights
    double physical_hypoxia_weight;
    double physical_co2_weight;
    double physical_thermal_weight;
    double physical_fatigue_weight;

    //Alarm thresholds
    double spo2_warning_percent;
    double spo2_critical_percent;
    double heart_rate_warning_bpm;
    double respiratory_rate_warning_bpm;
    double core_temp_low_c;
    double core_temp_high_c;
    double fatigue_warning_fraction;
    double performance_abort_fraction;
};

struct ScenarioConfig{
    //Metadata
    string scenario_id;
    string name;

    //Simulation timing
    int time_step_s;
    int maximum_duration_min;
    int stabilization_hold_min;

    //Configuration groups
    HabitatConfig habitat;
    AtmosphereConfig atmosphere;
    PowerConfig power;
    SolarConfig solar;
    ThermalConfig thermal;
    EVAConfig eva;
    CommunicationsConfig communications;
    FaultConfig fault;
    VitalResponseConfig vital_response;

    //Crew
    vector<CrewMemberConfig> crew_roster;

    //Source metadata
    vector<ParameterSource> parameter_sources;
};
