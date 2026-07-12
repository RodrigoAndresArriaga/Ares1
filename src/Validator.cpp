#include "Validator.hpp"

#include <unordered_set>

void Validator::addError(
    ValidationResult& result, const string& code, const string& message,
    ConstraintSeverity severity, std::optional<int> action_index) const{
    ValidationMessage msg{};
    msg.code = code;
    msg.message = message;
    msg.severity = severity;
    msg.action_index = action_index;
    if(severity == ConstraintSeverity::Warning){
        result.warnings.push_back(msg);
    }else{
        result.errors.push_back(msg);
        result.valid = false;
    }
}

bool Validator::crewIdExists(const ScenarioConfig& config, const string& crew_id) const{
    return findCrew(config, crew_id) != nullptr;
}

const CrewMemberConfig* Validator::findCrew(
    const ScenarioConfig& config, const string& crew_id) const{
    for(const auto& member : config.crew_roster){
        if(member.crew_id == crew_id){
            return &member;
        }
    }
    return nullptr;
}

bool Validator::activityProfileExists(
    const ScenarioConfig& config, CrewActivity activity) const{
    for(const auto& profile : config.vital_response.activity_profiles){
        if(profile.activity == activity){
            return true;
        }
    }
    return false;
}

bool Validator::isCommsWindowOpen(const ScenarioConfig& config, int time_min) const{
    for(const auto& window : config.communications.windows){
        if(time_min >= window.open_min && time_min < window.close_min){
            return true;
        }
    }
    return false;
}

ValidationResult Validator::validateScenario(const ScenarioConfig& config) const{
    ValidationResult result{};
    result.valid = true;

    if(config.scenario_id.empty()){
        addError(result, "scenario_id_missing", "scenario_id is required", ConstraintSeverity::Failure);
    }
    if(config.time_step_s <= 0){
        addError(result, "time_step_invalid", "time_step_s must be positive", ConstraintSeverity::Failure);
    }
    if(config.maximum_duration_min <= 0){
        addError(result, "duration_invalid", "maximum_duration_min must be positive", ConstraintSeverity::Failure);
    }
    if(config.stabilization_hold_min < 0){
        addError(result, "hold_invalid", "stabilization_hold_min must be non-negative", ConstraintSeverity::Failure);
    }

    if(config.habitat.initial_habitable_volume_m3 <= 0.0){
        addError(result, "volume_invalid", "initial_habitable_volume_m3 must be positive", ConstraintSeverity::Failure);
    }
    if(config.habitat.isolated_habitable_volume_m3 <= 0.0){
        addError(result, "isolated_volume_invalid", "isolated_habitable_volume_m3 must be positive", ConstraintSeverity::Failure);
    }
    if(config.habitat.isolated_habitable_volume_m3 > config.habitat.initial_habitable_volume_m3){
        addError(result, "isolated_volume_too_large",
            "isolated_habitable_volume_m3 cannot exceed initial_habitable_volume_m3",
            ConstraintSeverity::Failure);
    }
    if(config.habitat.effective_thermal_capacitance_kj_c <= 0.0){
        addError(result, "thermal_cap_invalid",
            "effective_thermal_capacitance_kj_c must be positive", ConstraintSeverity::Failure);
    }

    const AtmosphereConfig& atm = config.atmosphere;
    if(atm.initial_oxygen_mass_kg < 0.0 || atm.initial_inert_gas_mass_kg < 0.0 || atm.initial_co2_mass_kg < 0.0){
        addError(result, "gas_mass_invalid", "initial gas masses must be non-negative", ConstraintSeverity::Failure);
    }
    if(atm.scrubber_capacity_g_min < 0.0){
        addError(result, "scrubber_invalid", "scrubber_capacity_g_min must be non-negative", ConstraintSeverity::Failure);
    }
    if(atm.pressure_failure_low_kpa <= 0.0){
        addError(result, "pressure_failure_invalid", "pressure_failure_low_kpa must be positive", ConstraintSeverity::Failure);
    }
    if(atm.pressure_warning_low_kpa < atm.pressure_failure_low_kpa){
        addError(result, "pressure_threshold_order",
            "pressure_warning_low_kpa must be >= pressure_failure_low_kpa", ConstraintSeverity::Failure);
    }
    if(atm.pressure_high_limit_kpa <= atm.pressure_warning_low_kpa){
        addError(result, "pressure_high_invalid",
            "pressure_high_limit_kpa must exceed pressure_warning_low_kpa", ConstraintSeverity::Failure);
    }
    if(atm.inspired_o2_failure_mmhg <= 0.0){
        addError(result, "o2_failure_invalid", "inspired_o2_failure_mmhg must be positive", ConstraintSeverity::Failure);
    }
    if(atm.inspired_o2_warning_mmhg < atm.inspired_o2_failure_mmhg){
        addError(result, "o2_threshold_order",
            "inspired_o2_warning_mmhg must be >= inspired_o2_failure_mmhg", ConstraintSeverity::Failure);
    }
    if(atm.inspired_o2_nominal_mmhg < atm.inspired_o2_warning_mmhg){
        addError(result, "o2_nominal_order",
            "inspired_o2_nominal_mmhg must be >= inspired_o2_warning_mmhg", ConstraintSeverity::Failure);
    }
    if(atm.co2_one_hour_limit_mmhg <= 0.0){
        addError(result, "co2_limit_invalid", "co2_one_hour_limit_mmhg must be positive", ConstraintSeverity::Failure);
    }

    const PowerConfig& power = config.power;
    if(power.battery_capacity_kwh <= 0.0){
        addError(result, "battery_capacity_invalid", "battery_capacity_kwh must be positive", ConstraintSeverity::Failure);
    }
    if(power.initial_battery_energy_kwh < 0.0 || power.initial_battery_energy_kwh > power.battery_capacity_kwh){
        addError(result, "battery_energy_invalid",
            "initial_battery_energy_kwh must be in [0, battery_capacity_kwh]", ConstraintSeverity::Failure);
    }
    if(power.battery_reserve_percent < 0.0 || power.battery_reserve_percent > 100.0){
        addError(result, "battery_reserve_invalid",
            "battery_reserve_percent must be in [0, 100]", ConstraintSeverity::Failure);
    }
    if(power.charge_efficiency <= 0.0 || power.charge_efficiency > 1.0 ||
       power.discharge_efficiency <= 0.0 || power.discharge_efficiency > 1.0){
        addError(result, "battery_efficiency_invalid",
            "charge/discharge efficiency must be in (0, 1]", ConstraintSeverity::Failure);
    }

    if(config.solar.array_area_m2 <= 0.0 || config.solar.cell_efficiency <= 0.0){
        addError(result, "solar_invalid", "solar array_area_m2 and cell_efficiency must be positive", ConstraintSeverity::Failure);
    }

    const ThermalConfig& thermal = config.thermal;
    if(thermal.critical_low_c >= thermal.critical_high_c){
        addError(result, "thermal_critical_order",
            "critical_low_c must be < critical_high_c", ConstraintSeverity::Failure);
    }
    if(thermal.comfort_low_c >= thermal.comfort_high_c){
        addError(result, "thermal_comfort_order",
            "comfort_low_c must be < comfort_high_c", ConstraintSeverity::Failure);
    }
    if(thermal.comfort_low_c < thermal.critical_low_c || thermal.comfort_high_c > thermal.critical_high_c){
        addError(result, "thermal_comfort_bounds",
            "comfort band must lie within critical temperature limits", ConstraintSeverity::Failure);
    }

    const EVAConfig& eva = config.eva;
    if(eva.maximum_duration_min <= 0){
        addError(result, "eva_max_duration_invalid", "eva.maximum_duration_min must be positive", ConstraintSeverity::Failure);
    }
    int eva_phase_sum = eva.preparation_min + eva.egress_min + eva.repair_work_min + eva.ingress_min + eva.reserve_min;
    if(eva_phase_sum > eva.maximum_duration_min){
        addError(result, "eva_phases_exceed_max",
            "EVA prep+egress+work+ingress+reserve exceeds maximum_duration_min", ConstraintSeverity::Failure);
    }
    if(eva.preparation_min < 0 || eva.egress_min < 0 || eva.repair_work_min < 0 ||
       eva.ingress_min < 0 || eva.reserve_min < 0){
        addError(result, "eva_phase_negative", "EVA phase durations must be non-negative", ConstraintSeverity::Failure);
    }

    if(config.communications.transmission_duration_min <= 0){
        addError(result, "comms_duration_invalid",
            "transmission_duration_min must be positive", ConstraintSeverity::Failure);
    }
    for(size_t i = 0; i < config.communications.windows.size(); ++i){
        const CommunicationWindow& window = config.communications.windows[i];
        if(window.close_min <= window.open_min){
            addError(result, "comms_window_invalid",
                "communication window close_min must exceed open_min", ConstraintSeverity::Failure);
        }
        for(size_t j = i + 1; j < config.communications.windows.size(); ++j){
            const CommunicationWindow& other = config.communications.windows[j];
            bool overlap = window.open_min < other.close_min && other.open_min < window.close_min;
            if(overlap){
                addError(result, "comms_window_overlap",
                    "communication windows must not overlap", ConstraintSeverity::Failure);
            }
        }
    }

    if(config.fault.total_gas_leak_kg_hr < 0.0){
        addError(result, "leak_rate_invalid", "total_gas_leak_kg_hr must be non-negative", ConstraintSeverity::Failure);
    }
    if(config.fault.isolation_leak_multiplier < 0.0 || config.fault.isolation_leak_multiplier > 1.0){
        addError(result, "isolation_multiplier_invalid",
            "isolation_leak_multiplier must be in [0, 1]", ConstraintSeverity::Failure);
    }
    if(config.fault.solar_fault_factor < 0.0 || config.fault.repaired_solar_fault_factor < 0.0){
        addError(result, "solar_fault_invalid", "solar fault factors must be non-negative", ConstraintSeverity::Failure);
    }
    if(config.fault.stabilized_leak_kg_hr < 0.0){
        addError(result, "stabilized_leak_invalid",
            "stabilized_leak_kg_hr must be non-negative", ConstraintSeverity::Failure);
    }

    const VitalResponseConfig& vital = config.vital_response;
    if(vital.spo2_critical_percent > vital.spo2_warning_percent){
        addError(result, "spo2_threshold_order",
            "spo2_critical_percent must be <= spo2_warning_percent", ConstraintSeverity::Failure);
    }
    if(vital.performance_abort_fraction < 0.0 || vital.performance_abort_fraction > 1.0){
        addError(result, "performance_abort_invalid",
            "performance_abort_fraction must be in [0, 1]", ConstraintSeverity::Failure);
    }
    if(vital.activity_profiles.empty()){
        addError(result, "activity_profiles_missing",
            "vital_response.activity_profiles must not be empty", ConstraintSeverity::Failure);
    }

    unordered_set<string> seen_ids;
    for(const auto& member : config.crew_roster){
        if(member.crew_id.empty()){
            addError(result, "crew_id_empty", "crew_id must not be empty", ConstraintSeverity::Failure);
            continue;
        }
        if(!seen_ids.insert(member.crew_id).second){
            addError(result, "crew_id_duplicate",
                "duplicate crew_id: " + member.crew_id, ConstraintSeverity::Failure);
        }
        if(member.body_mass_kg <= 0.0){
            addError(result, "crew_mass_invalid",
                "body_mass_kg must be positive for " + member.crew_id, ConstraintSeverity::Failure);
        }
        if(member.fitness_factor <= 0.0 ||
           member.hypoxia_sensitivity <= 0.0 ||
           member.co2_sensitivity <= 0.0 ||
           member.thermal_sensitivity <= 0.0 ||
           member.fatigue_recovery_factor <= 0.0){
            addError(result, "crew_sensitivity_invalid",
                "crew sensitivity/fitness factors must be positive for " + member.crew_id,
                ConstraintSeverity::Failure);
        }
        if(!activityProfileExists(config, member.initial_activity)){
            addError(result, "crew_activity_profile_missing",
                "no activity profile for initial activity of " + member.crew_id,
                ConstraintSeverity::Failure);
        }
    }
    if(config.crew_roster.empty()){
        addError(result, "crew_roster_empty", "crew_roster must not be empty", ConstraintSeverity::Failure);
    }

    return result;
}

ValidationResult Validator::validatePlan(const Plan& plan, const ScenarioConfig& config) const{
    ValidationResult result{};
    result.valid = true;

    if(plan.plan_id.empty()){
        addError(result, "plan_id_missing", "plan_id is required", ConstraintSeverity::Failure);
    }

    for(size_t i = 0; i < plan.actions.size(); ++i){
        const Action& action = plan.actions[i];
        int index = static_cast<int>(i);

        if(action.type == ActionType::Unknown){
            addError(result, "unknown_action",
                "unknown action type: " + action.type_raw, ConstraintSeverity::Failure, index);
            continue;
        }
        if(action.start_min < 0){
            addError(result, "action_start_negative",
                "action start_min must be non-negative", ConstraintSeverity::Failure, index);
        }
        if(action.start_min > config.maximum_duration_min){
            addError(result, "action_start_past_end",
                "action start_min exceeds maximum_duration_min", ConstraintSeverity::Failure, index);
        }

        switch(action.type){
        case ActionType::ReducePowerLoad:
            if(!action.percent.has_value() || *action.percent < 0.0 || *action.percent > 100.0){
                addError(result, "reduce_power_percent",
                    "reduce_power_load requires percent in [0, 100]", ConstraintSeverity::Failure, index);
            }
            if(action.load_groups.empty()){
                addError(result, "reduce_power_groups",
                    "reduce_power_load requires load_groups", ConstraintSeverity::Failure, index);
            }
            break;

        case ActionType::IsolateModule:
            if(!action.module.has_value() || action.module->empty()){
                addError(result, "isolate_module_missing",
                    "isolate_module requires module", ConstraintSeverity::Failure, index);
            }
            break;

        case ActionType::OxygenRationing:
            if(!action.level.has_value() || action.level->empty()){
                addError(result, "rationing_level_missing",
                    "oxygen_rationing requires level", ConstraintSeverity::Failure, index);
            }
            for(const string& crew_id : action.target_crew_ids){
                if(!crewIdExists(config, crew_id)){
                    addError(result, "rationing_crew_unknown",
                        "oxygen_rationing target crew not found: " + crew_id,
                        ConstraintSeverity::Failure, index);
                }
            }
            break;

        case ActionType::RepairSolarArray:{
            string crew_id;
            if(action.eva_crew_id.has_value() && !action.eva_crew_id->empty()){
                crew_id = *action.eva_crew_id;
            }else if(action.crew_id.has_value() && !action.crew_id->empty()){
                crew_id = *action.crew_id;
            }else if(!action.assigned_crew_ids.empty()){
                crew_id = action.assigned_crew_ids.front();
            }
            if(crew_id.empty()){
                addError(result, "repair_crew_missing",
                    "repair_solar_array requires eva_crew_id or assigned_crew_ids",
                    ConstraintSeverity::Failure, index);
                break;
            }
            const CrewMemberConfig* member = findCrew(config, crew_id);
            if(member == nullptr){
                addError(result, "repair_crew_unknown",
                    "repair_solar_array crew not found: " + crew_id,
                    ConstraintSeverity::Failure, index);
            }else if(!member->eva_qualified){
                addError(result, "repair_crew_unqualified",
                    "crew is not EVA qualified: " + crew_id,
                    ConstraintSeverity::Failure, index);
            }
            if(!config.eva.available){
                addError(result, "eva_unavailable",
                    "EVA is not available in this scenario", ConstraintSeverity::Failure, index);
            }
            break;
        }

        case ActionType::DelayRoverUse:
            if(!action.hours.has_value() || *action.hours <= 0.0){
                addError(result, "delay_rover_hours",
                    "delay_rover_use requires positive hours", ConstraintSeverity::Failure, index);
            }
            break;

        case ActionType::SendEmergencyPacket:
            if(config.communications.windows.empty()){
                addError(result, "comms_windows_missing",
                    "send_emergency_packet requires communication windows",
                    ConstraintSeverity::Failure, index);
            }else if(!isCommsWindowOpen(config, action.start_min)){
                addError(result, "comms_window_closed",
                    "send_emergency_packet start is outside an open communication window",
                    ConstraintSeverity::Failure, index);
            }
            break;

        case ActionType::Unknown:
            break;
        }
    }

    // static rover conflict: repair during a delay_rover_use reservation window
    for(size_t i = 0; i < plan.actions.size(); ++i){
        const Action& action = plan.actions[i];
        if(action.type != ActionType::RepairSolarArray || !config.eva.rover_required){
            continue;
        }
        for(size_t j = 0; j < plan.actions.size(); ++j){
            const Action& delay = plan.actions[j];
            if(delay.type != ActionType::DelayRoverUse || !delay.hours.has_value()){
                continue;
            }
            int delay_end = delay.start_min + static_cast<int>(*delay.hours * 60.0);
            if(action.start_min >= delay.start_min && action.start_min < delay_end){
                addError(result, "rover_reserved",
                    "repair_solar_array starts while rover is reserved by delay_rover_use",
                    ConstraintSeverity::Failure, static_cast<int>(i));
            }
        }
    }

    return result;
}
