#pragma once
#include <deque>
#include <string>
#include <vector>
#include "Action.hpp"
#include "CrewMember.hpp"

using namespace std;

//all mutable physical and operational simulation state here.

struct SimulationState{
    //Clock and habitat
    int time_min;
    double habitable_volume_m3;
    double cabin_temperature_c;
    double cabin_relative_humidity_percent;

    //Atmosphere
    double oxygen_mass_kg;
    double inert_gas_mass_kg;
    double co2_mass_kg;
    double total_gas_leak_kg_hr;
    double leak_fault_factor;
    double scrubber_efficiency;

    //Solar and electrical power
    double battery_energy_kwh;
    double solar_incidence_angle_deg;
    double atmospheric_transmission;
    double deposited_dust_factor;
    double solar_fault_factor;
    double essential_load_kw;
    double discretionary_load_kw;
    double thermal_control_load_kw;
    double eva_support_load_kw;
    double communications_load_kw;

    //Thermal
    double equipment_heat_w;
    double environmental_heat_w;
    double heater_heat_w;
    double tcs_rejection_capacity_w;

    //EVA and rover
    bool eva_available;
    int eva_elapsed_min;
    int eva_work_elapsed_min;
    double solar_repair_progress;
    double rover_battery_percent;
    bool rover_available;
    int rover_reserved_until_min;

    //Module isolation
    bool module_isolated;
    string isolated_module;

    //Communications
    bool emergency_packet_sent;
    int transmission_elapsed_min;

    //Collections
    vector<string> active_faults;
    vector<CrewMemberState> crew;
    deque<double> rolling_co2_samples;
    vector<ActiveActionState> active_actions;
};
