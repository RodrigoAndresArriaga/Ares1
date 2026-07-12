#pragma once

//deterministic run extrema and final-run metrics here.

struct SimulationMetrics{
    double minimum_inspired_o2_mmhg;
    double minimum_cabin_pressure_kpa;
    double maximum_co2_one_hour_avg_mmhg;
    double minimum_battery_soc_percent;
    double minimum_power_margin_kw;
    double minimum_temperature_margin_c;
    double minimum_eva_safe_return_margin_min;
    double minimum_crew_spo2_percent;
    double maximum_crew_fatigue_percent;
    bool eva_completed;
    bool communications_sent;
    double time_to_stabilization_hr;
};
