#include "CrewPhysiologyModel.hpp"
#include "MathUtils.hpp"
#include "PhysicalConstants.hpp"

#include <algorithm>
#include <stdexcept>

vector<CrewMemberState> CrewPhysiologyModel::initializeCrewStates(
    const ScenarioConfig& config) const {
    vector<CrewMemberState> states;
    states.reserve(config.crew_roster.size());

    for (const auto& member : config.crew_roster) {
        const ActivityMetabolicProfile& profile =
            findActivityProfile(member.initial_activity, config.vital_response);

        CrewMemberState state{};
        state.crew_id = member.crew_id;
        state.location_module = member.initial_location_module;
        state.actvity = member.initial_activity;
        state.eva_status = member.initial_eva_status;
        state.oxygen_rationing_active = member.initial_oxygen_rationing_active;

        state.heart_rate_bpm = member.baseline_heart_rate_bpm;
        state.respiratory_rate_bpm = member.baseline_respiratory_rate_bpm;
        state.spo2_percent = member.baseline_spo2_percent;
        state.core_temperature_c = member.baseline_core_temperature_c;

        state.hypoxia_exposure_index = 0.0;
        state.co2_exposure_index = 0.0;
        state.thermal_exposure_index = 0.0;
        state.fatigue_index = 0.0;

        state.cognitive_performance_factor = 1.0;
        state.physical_performance_factor = 1.0;

        state.oxygen_consumption_g_min = profile.oxygen_g_min;
        state.co2_production_g_min = profile.co2_g_min;
        state.heat_output_w = profile.heat_w;

        state.health_status = CrewHealthStatus::Nominal;
        state.active_alarms.clear();

        states.push_back(state);
    }

    return states;
}

const CrewMemberConfig& CrewPhysiologyModel::findCrewConfig(
    const string& crew_id, const ScenarioConfig& config) const {
    for (const auto& member : config.crew_roster) {
        if (member.crew_id == crew_id) {
            return member;
        }
    }
    throw std::runtime_error("crew_id not found in roster: " + crew_id);
}

vector<CrewVitalsTelemetry> CrewPhysiologyModel::buildCrewVitalsTelemetry(
    const SimulationState& state, const ScenarioConfig& config) const {
    vector<CrewVitalsTelemetry> out;
    out.reserve(state.crew.size());

    for (const auto& member : state.crew) {
        const CrewMemberConfig& member_config = findCrewConfig(member.crew_id, config);

        CrewVitalsTelemetry telemetry{};
        telemetry.crew_id = member.crew_id;
        telemetry.display_name = member_config.display_name;
        telemetry.assigned_role = member_config.assigned_role;
        telemetry.location_module = member.location_module;
        telemetry.activity = member.actvity;
        telemetry.eva_status = member.eva_status;

        telemetry.heart_rate_bpm = member.heart_rate_bpm;
        telemetry.respiratory_rate_bpm = member.respiratory_rate_bpm;
        telemetry.spo2_percent = member.spo2_percent;
        telemetry.core_temperature_c = member.core_temperature_c;

        telemetry.oxygen_consumption_g_min = member.oxygen_consumption_g_min;
        telemetry.co2_production_g_min = member.co2_production_g_min;
        telemetry.heat_output_w = member.heat_output_w;

        telemetry.fatigue_percent = member.fatigue_index * 100.0;
        telemetry.hypoxia_exposure = member.hypoxia_exposure_index;
        telemetry.co2_exposure = member.co2_exposure_index;
        telemetry.thermal_exposure = member.thermal_exposure_index;
        telemetry.cognitive_performance_percent = member.cognitive_performance_factor * 100.0;
        telemetry.physical_performance_percent = member.physical_performance_factor * 100.0;

        telemetry.health_status = member.health_status;
        telemetry.active_alarms = member.active_alarms;

        out.push_back(telemetry);
    }

    return out;
}

// resolve exactly one activity metabolic profile from scenario config
const ActivityMetabolicProfile& CrewPhysiologyModel::findActivityProfile(
    CrewActivity activity, const VitalResponseConfig& vital_response) const {
    const ActivityMetabolicProfile* match = nullptr;

    for (const auto& profile : vital_response.activity_profiles) {
        if (profile.activity != activity) {
            continue;
        }
        if (match != nullptr) {
            throw std::runtime_error("duplicate activity metabolic profile");
        }
        match = &profile;
    }

    if (match == nullptr) {
        throw std::runtime_error("missing activity metabolic profile");
    }

    return *match;
}

// normalize inspired-O2 shortfall
// safe: inspired_o2_warning_mmhg; critical: inspired_o2_failure_mmhg
double CrewPhysiologyModel::calculateHypoxiaSeverity(
    const DerivedTelemetry& telemetry, const ScenarioConfig& config,
    const CrewMemberConfig& crew) const {
    double severity = MathUtils::lowSideSeverity(
        telemetry.atmosphere.inspired_oxygen_mmhg,
        config.atmosphere.inspired_o2_warning_mmhg,
        config.atmosphere.inspired_o2_failure_mmhg);
    return MathUtils::clamp(severity * crew.hypoxia_sensitivity, 0.0, 1.0);
}

// normalize rolling CO2 excess
// safe: 0.0 mmHg baseline; critical: co2_one_hour_limit_mmhg
double CrewPhysiologyModel::calculateCo2Severity(
    const DerivedTelemetry& telemetry, const ScenarioConfig& config,
    const CrewMemberConfig& crew) const {
    double severity = MathUtils::highSideSeverity(
        telemetry.atmosphere.co2_one_hour_avg_mmhg,
        0.0,
        config.atmosphere.co2_one_hour_limit_mmhg);
    return MathUtils::clamp(severity * crew.co2_sensitivity, 0.0, 1.0);
}

// normalize cabin-pressure shortfall
// safe: pressure_warning_low_kpa; critical: pressure_failure_low_kpa
double CrewPhysiologyModel::calculatePressureSeverity(
    const DerivedTelemetry& telemetry, const ScenarioConfig& config,
    const CrewMemberConfig& crew) const {
    (void)crew;
    return MathUtils::lowSideSeverity(
        telemetry.atmosphere.cabin_pressure_kpa,
        config.atmosphere.pressure_warning_low_kpa,
        config.atmosphere.pressure_failure_low_kpa);
}

// normalize hot/cold cabin stress; max of both sides
// cold safe/critical: comfort_low_c / critical_low_c
// hot safe/critical: comfort_high_c / critical_high_c
double CrewPhysiologyModel::calculateThermalSeverity(
    const DerivedTelemetry& telemetry, const ScenarioConfig& config,
    const CrewMemberConfig& crew, double cabin_temperature_c) const {
    (void)telemetry;
    double cold_severity = MathUtils::lowSideSeverity(
        cabin_temperature_c,
        config.thermal.comfort_low_c,
        config.thermal.critical_low_c);
    double hot_severity = MathUtils::highSideSeverity(
        cabin_temperature_c,
        config.thermal.comfort_high_c,
        config.thermal.critical_high_c);
    double severity = (std::max)(cold_severity, hot_severity);
    return MathUtils::clamp(severity * crew.thermal_sensitivity, 0.0, 1.0);
}

// add exposure memory and recovery; no upper clamp in data contract
void CrewPhysiologyModel::updateExposureIndices(
    CrewMemberState& crew, double hypoxia_severity, double co2_severity,
    double thermal_severity, const VitalResponseConfig& config,
    double dt_minutes) const {
    crew.hypoxia_exposure_index +=
        hypoxia_severity * config.hypoxia_accumulation_rate * dt_minutes;
    if (hypoxia_severity < 1.0) {
        crew.hypoxia_exposure_index -=
            config.hypoxia_recovery_rate * (1.0 - hypoxia_severity) * dt_minutes;
    }
    if (crew.hypoxia_exposure_index < 0.0) {
        crew.hypoxia_exposure_index = 0.0;
    }

    crew.co2_exposure_index +=
        co2_severity * config.co2_accumulation_rate * dt_minutes;
    if (co2_severity < 1.0) {
        crew.co2_exposure_index -=
            config.co2_recovery_rate * (1.0 - co2_severity) * dt_minutes;
    }
    if (crew.co2_exposure_index < 0.0) {
        crew.co2_exposure_index = 0.0;
    }

    crew.thermal_exposure_index +=
        thermal_severity * config.thermal_accumulation_rate * dt_minutes;
    if (thermal_severity < 1.0) {
        crew.thermal_exposure_index -=
            config.thermal_recovery_rate * (1.0 - thermal_severity) * dt_minutes;
    }
    if (crew.thermal_exposure_index < 0.0) {
        crew.thermal_exposure_index = 0.0;
    }
}

// accumulate workload/stress fatigue and recover at rest
void CrewPhysiologyModel::updateFatigue(
    CrewMemberState& crew, const CrewMemberConfig& member,
    const ActivityMetabolicProfile& profile, double hypoxia_severity,
    double co2_severity, double thermal_severity,
    const VitalResponseConfig& config, double dt_minutes) const {
    // workload from activity metabolic load
    double accumulate =
        profile.activity_load * config.fatigue_work_rate * dt_minutes;

    // EVA-specific fatigue only in active phases
    const bool active_eva =
        crew.eva_status == EVAStatus::Preparing ||
        crew.eva_status == EVAStatus::Egress ||
        crew.eva_status == EVAStatus::Working ||
        crew.eva_status == EVAStatus::Ingress;
    if (active_eva) {
        accumulate += config.fatigue_eva_rate * dt_minutes;
    }

    // mean environmental severity contribution
    double env_severity =
        (hypoxia_severity + co2_severity + thermal_severity) / 3.0;
    accumulate += env_severity * config.fatigue_work_rate * dt_minutes;

    // higher fitness slows fatigue accumulation
    accumulate /= member.fitness_factor;

    double recover = 0.0;
    if (crew.actvity == CrewActivity::Sleep ||
        crew.actvity == CrewActivity::Resting ||
        crew.actvity == CrewActivity::Recovery) {
        recover = config.fatigue_recovery_rate * dt_minutes;
        recover *= member.fatigue_recovery_factor;
    }

    crew.fatigue_index =
        MathUtils::clamp(crew.fatigue_index + accumulate - recover, 0.0, 1.0);
}

// set O2, CO2, and heat from activity profile with shared modifiers
void CrewPhysiologyModel::updateMetabolicOutputs(
    CrewMemberState& crew, const CrewMemberConfig& member,
    const ActivityMetabolicProfile& profile,
    const VitalResponseConfig& config) const {
    (void)member;

    // shared scale: current physical performance modifier
    double scale = crew.physical_performance_factor;

    // ARES rationing reduction; floor comes from Sleep profile in config
    constexpr double k_rationing_factor = 0.75;
    if (crew.oxygen_rationing_active) {
        scale *= k_rationing_factor;
    }

    double oxygen_g_min = profile.oxygen_g_min * scale;
    double co2_g_min = profile.co2_g_min * scale;
    double heat_w = profile.heat_w * scale;

    if (crew.oxygen_rationing_active) {
        const ActivityMetabolicProfile& floor =
            findActivityProfile(CrewActivity::Sleep, config);
        if (oxygen_g_min < floor.oxygen_g_min) {
            oxygen_g_min = floor.oxygen_g_min;
        }
        if (co2_g_min < floor.co2_g_min) {
            co2_g_min = floor.co2_g_min;
        }
        if (heat_w < floor.heat_w) {
            heat_w = floor.heat_w;
        }
    }

    crew.oxygen_consumption_g_min = oxygen_g_min;
    crew.co2_production_g_min = co2_g_min;
    crew.heat_output_w = heat_w;
}

// update HR, RR, SpO2, and core temperature
void CrewPhysiologyModel::updateVitalSigns(
    CrewMemberState& crew, const CrewMemberConfig& member,
    const ActivityMetabolicProfile& profile, const DerivedTelemetry& telemetry,
    double hypoxia_severity, double co2_severity, double pressure_severity,
    double thermal_severity, const VitalResponseConfig& config,
    double dt_minutes, double cabin_temperature_c) const {
    (void)telemetry;

    // target HR from baseline plus additive response components
    double target_hr =
        member.baseline_heart_rate_bpm +
        config.hr_activity_gain * profile.activity_load +
        config.hr_hypoxia_gain * hypoxia_severity +
        config.hr_co2_gain * co2_severity +
        config.hr_thermal_gain * thermal_severity +
        config.hr_fatigue_gain * crew.fatigue_index;

    // target RR from baseline plus additive response components
    double target_rr =
        member.baseline_respiratory_rate_bpm +
        config.rr_activity_gain * profile.activity_load +
        config.rr_hypoxia_gain * hypoxia_severity +
        config.rr_co2_gain * co2_severity +
        config.rr_thermal_gain * thermal_severity;

    // instantaneous response; no HR/RR time-constant field in config
    crew.heart_rate_bpm =
        MathUtils::clamp(target_hr, config.hr_min_bpm, config.hr_max_bpm);
    crew.respiratory_rate_bpm =
        MathUtils::clamp(target_rr, config.rr_min_bpm, config.rr_max_bpm);

    // SpO2 target: baseline minus hypoxia/pressure/activity/exposure terms
    double target_spo2 =
        member.baseline_spo2_percent -
        config.spo2_hypoxia_gain * hypoxia_severity * member.hypoxia_sensitivity -
        config.spo2_pressure_gain * pressure_severity -
        config.spo2_activity_gain * profile.activity_load -
        config.spo2_exposure_gain * crew.hypoxia_exposure_index;
    target_spo2 = MathUtils::clamp(
        target_spo2, config.spo2_min_percent, config.spo2_max_percent);

    // core-temp target: baseline plus cabin offset and activity heat
    double target_core =
        member.baseline_core_temperature_c +
        config.core_temp_environment_gain *
            (cabin_temperature_c - member.baseline_core_temperature_c) +
        config.core_temp_activity_gain * profile.activity_load;
    target_core = MathUtils::clamp(
        target_core, config.core_temp_min_c, config.core_temp_max_c);

    // first-order lag using configured vital time constant
    double tau = config.core_temp_time_constant_min;
    double blend = 1.0;
    if (tau > 0.0) {
        blend = dt_minutes / (tau + dt_minutes);
    }

    crew.spo2_percent =
        crew.spo2_percent + blend * (target_spo2 - crew.spo2_percent);
    crew.spo2_percent = MathUtils::clamp(
        crew.spo2_percent, config.spo2_min_percent, config.spo2_max_percent);

    crew.core_temperature_c =
        crew.core_temperature_c + blend * (target_core - crew.core_temperature_c);
    crew.core_temperature_c = MathUtils::clamp(
        crew.core_temperature_c, config.core_temp_min_c, config.core_temp_max_c);
}

// update cognitive and physical performance from weighted impairments
void CrewPhysiologyModel::updatePerformance(
    CrewMemberState& crew, const ActivityMetabolicProfile& profile,
    const VitalResponseConfig& config) const {
    // clamp exposure when converting to performance (may exceed 1 while accumulating)
    double hypoxia_exp = MathUtils::clamp(crew.hypoxia_exposure_index, 0.0, 1.0);
    double co2_exp = MathUtils::clamp(crew.co2_exposure_index, 0.0, 1.0);
    double thermal_exp = MathUtils::clamp(crew.thermal_exposure_index, 0.0, 1.0);
    double fatigue = MathUtils::clamp(crew.fatigue_index, 0.0, 1.0);
    double activity_load = MathUtils::clamp(profile.activity_load, 0.0, 1.0);

    // cognitive impairment from exposure, fatigue, and activity load
    double cognitive_impairment =
        config.cognitive_hypoxia_weight * hypoxia_exp +
        config.cognitive_co2_weight * co2_exp +
        config.cognitive_thermal_weight * thermal_exp +
        config.cognitive_fatigue_weight * fatigue +
        config.cognitive_fatigue_weight * activity_load;

    // physical impairment from exposure, fatigue, and activity load
    double physical_impairment =
        config.physical_hypoxia_weight * hypoxia_exp +
        config.physical_co2_weight * co2_exp +
        config.physical_thermal_weight * thermal_exp +
        config.physical_fatigue_weight * fatigue +
        config.physical_fatigue_weight * activity_load;

    crew.cognitive_performance_factor =
        MathUtils::clamp(1.0 - cognitive_impairment, 0.0, 1.0);
    crew.physical_performance_factor =
        MathUtils::clamp(1.0 - physical_impairment, 0.0, 1.0);
}

// apply transparent health/alarm thresholds; rebuild alarms each step
void CrewPhysiologyModel::updateHealthStatusAndAlarms(
    CrewMemberState& crew, const DerivedTelemetry& telemetry,
    const VitalResponseConfig& config) const {
    crew.active_alarms.clear();

    if (crew.spo2_percent <= config.spo2_warning_percent ||
        crew.hypoxia_exposure_index >= 1.0) {
        crew.active_alarms.push_back(CrewAlarmType::Hypoxia);
    }
    if (crew.co2_exposure_index >= 1.0) {
        crew.active_alarms.push_back(CrewAlarmType::Hypercapnia);
    }
    if (crew.heart_rate_bpm >= config.heart_rate_warning_bpm) {
        crew.active_alarms.push_back(CrewAlarmType::Tachycardia);
    }
    if (crew.respiratory_rate_bpm >= config.respiratory_rate_warning_bpm) {
        crew.active_alarms.push_back(CrewAlarmType::Respiratory);
    }
    if (crew.core_temperature_c < config.core_temp_low_c ||
        crew.core_temperature_c > config.core_temp_high_c) {
        crew.active_alarms.push_back(CrewAlarmType::Thermal);
    }
    if (crew.fatigue_index >= config.fatigue_warning_fraction) {
        crew.active_alarms.push_back(CrewAlarmType::Fatigue);
    }
    if (crew.cognitive_performance_factor <= config.performance_abort_fraction ||
        crew.physical_performance_factor <= config.performance_abort_fraction) {
        crew.active_alarms.push_back(CrewAlarmType::Performance);
    }

    const bool active_eva =
        crew.eva_status == EVAStatus::Preparing ||
        crew.eva_status == EVAStatus::Egress ||
        crew.eva_status == EVAStatus::Working ||
        crew.eva_status == EVAStatus::Ingress;
    if (active_eva && telemetry.eva.eva_safe_return_margin_min < 0.0) {
        crew.active_alarms.push_back(CrewAlarmType::EVAReturn);
    }

    // ordered health status: worst matching rule wins
    const double min_performance =
        (crew.cognitive_performance_factor < crew.physical_performance_factor)
            ? crew.cognitive_performance_factor
            : crew.physical_performance_factor;

    if (crew.actvity == CrewActivity::Incapacitated ||
        min_performance <= config.performance_abort_fraction) {
        crew.health_status = CrewHealthStatus::Incapacitated;
    } else if (crew.spo2_percent <= config.spo2_critical_percent ||
               crew.co2_exposure_index >= 1.0 ||
               (active_eva && telemetry.eva.eva_safe_return_margin_min < 0.0)) {
        crew.health_status = CrewHealthStatus::Critical;
    } else if (crew.spo2_percent <= config.spo2_warning_percent ||
               crew.fatigue_index >= config.fatigue_warning_fraction ||
               crew.core_temperature_c < config.core_temp_low_c ||
               crew.core_temperature_c > config.core_temp_high_c) {
        crew.health_status = CrewHealthStatus::Impaired;
    } else if (crew.heart_rate_bpm >= config.heart_rate_warning_bpm ||
               crew.respiratory_rate_bpm >= config.respiratory_rate_warning_bpm ||
               crew.hypoxia_exposure_index > 0.0 ||
               crew.co2_exposure_index > 0.0 ||
               crew.thermal_exposure_index > 0.0 ||
               !crew.active_alarms.empty()) {
        crew.health_status = CrewHealthStatus::ElevatedStress;
    } else {
        crew.health_status = CrewHealthStatus::Nominal;
    }
}

// ordered physiology update for one crewmember
void CrewPhysiologyModel::updateCrewMember(
    CrewMemberState& crew, const CrewMemberConfig& member,
    const DerivedTelemetry& pre_step_telemetry, const ScenarioConfig& config,
    double dt_seconds, double cabin_temperature_c) {
    double dt_minutes = dt_seconds / ares::constants::SECONDS_PER_MINUTE;

    const ActivityMetabolicProfile& profile =
        findActivityProfile(crew.actvity, config.vital_response);

    double hypoxia_severity =
        calculateHypoxiaSeverity(pre_step_telemetry, config, member);
    double co2_severity =
        calculateCo2Severity(pre_step_telemetry, config, member);
    double pressure_severity =
        calculatePressureSeverity(pre_step_telemetry, config, member);
    double thermal_severity = calculateThermalSeverity(
        pre_step_telemetry, config, member, cabin_temperature_c);

    updateExposureIndices(
        crew, hypoxia_severity, co2_severity, thermal_severity,
        config.vital_response, dt_minutes);
    updateFatigue(
        crew, member, profile, hypoxia_severity, co2_severity, thermal_severity,
        config.vital_response, dt_minutes);
    updateMetabolicOutputs(crew, member, profile, config.vital_response);
    updateVitalSigns(
        crew, member, profile, pre_step_telemetry, hypoxia_severity, co2_severity,
        pressure_severity, thermal_severity, config.vital_response, dt_minutes,
        cabin_temperature_c);
    updatePerformance(crew, profile, config.vital_response);
    updateHealthStatusAndAlarms(crew, pre_step_telemetry, config.vital_response);
}

// one deterministic physiology step for the full roster
void CrewPhysiologyModel::updateAllCrew(
    SimulationState& state, const ScenarioConfig& config,
    const DerivedTelemetry& pre_step_telemetry, double dt_seconds) {
    if (state.crew.size() != config.crew_roster.size()) {
        throw std::runtime_error("crew state/roster size mismatch");
    }

    for (const auto& member : config.crew_roster) {
        CrewMemberState* matched = nullptr;
        for (auto& crew : state.crew) {
            if (crew.crew_id == member.crew_id) {
                matched = &crew;
                break;
            }
        }
        if (matched == nullptr) {
            throw std::runtime_error(
                "crew_id not found in state: " + member.crew_id);
        }

        updateCrewMember(
            *matched, member, pre_step_telemetry, config, dt_seconds,
            state.cabin_temperature_c);
    }
}
