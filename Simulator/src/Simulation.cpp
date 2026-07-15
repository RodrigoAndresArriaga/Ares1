#include "Simulation.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

namespace {

bool isFinitePositive(double value){
    return std::isfinite(value) && value >= 0.0;
}

double minPositiveDeadline(double a, double b){
    double best = std::numeric_limits<double>::infinity();
    if(isFinitePositive(a)){
        best = a;
    }
    if(isFinitePositive(b) && b < best){
        best = b;
    }
    return best;
}

}

SimulationState Simulation::initializeState(const ScenarioConfig& config) const{
    SimulationState state{};
    state.time_min = 0;
    state.habitable_volume_m3 = config.habitat.initial_habitable_volume_m3;
    state.cabin_temperature_c = config.habitat.nominal_temperature_c;
    state.cabin_relative_humidity_percent = config.habitat.initial_relative_humidity_percent;

    state.oxygen_mass_kg = config.atmosphere.initial_oxygen_mass_kg;
    state.inert_gas_mass_kg = config.atmosphere.initial_inert_gas_mass_kg;
    state.co2_mass_kg = config.atmosphere.initial_co2_mass_kg;
    state.total_gas_leak_kg_hr = config.fault.total_gas_leak_kg_hr;
    state.leak_fault_factor = 1.0;
    state.scrubber_efficiency = config.atmosphere.initial_scrubber_efficiency;

    state.battery_energy_kwh = config.power.initial_battery_energy_kwh;
    state.solar_incidence_angle_deg = config.solar.initial_incidence_angle_deg;
    state.atmospheric_transmission = config.solar.initial_atmospheric_transmission;
    state.deposited_dust_factor = config.solar.initial_deposited_dust_factor;
    state.solar_fault_factor = config.fault.solar_fault_factor;
    state.essential_load_kw = config.power.essential_load_kw;
    state.discretionary_load_kw = config.power.discretionary_load_kw;
    state.thermal_control_load_kw = config.power.thermal_control_load_kw;
    state.eva_support_load_kw = config.power.eva_support_load_kw;
    state.communications_load_kw = config.power.communications_load_kw;

    state.equipment_heat_w = config.thermal.initial_equipment_heat_w;
    state.environmental_heat_w = config.thermal.initial_environmental_heat_w;
    state.heater_heat_w = config.thermal.initial_heater_heat_w;
    state.tcs_rejection_capacity_w = config.thermal.tcs_rejection_capacity_w;

    state.eva_available = config.eva.available;
    state.eva_elapsed_min = 0;
    state.eva_work_elapsed_min = 0;
    state.solar_repair_progress = 0.0;
    state.rover_battery_percent = 100.0;
    state.rover_available = true;
    state.rover_reserved_until_min = 0;

    state.module_isolated = false;
    state.isolated_module.clear();
    state.emergency_packet_sent = false;
    state.transmission_elapsed_min = 0;

    if(!config.fault.failure_type.empty()){
        state.active_faults.push_back(config.fault.failure_type);
    }
    state.crew = crew_model_.initializeCrewStates(config);
    state.rolling_co2_samples.clear();
    state.active_actions.clear();
    return state;
}

SimulationMetrics Simulation::initializeMetrics() const{
    SimulationMetrics metrics{};
    const double k_inf = std::numeric_limits<double>::infinity();
    metrics.minimum_inspired_o2_mmhg = k_inf;
    metrics.minimum_cabin_pressure_kpa = k_inf;
    metrics.maximum_co2_one_hour_avg_mmhg = 0.0;
    metrics.minimum_battery_soc_percent = k_inf;
    metrics.minimum_power_margin_kw = k_inf;
    metrics.minimum_temperature_margin_c = k_inf;
    metrics.minimum_eva_safe_return_margin_min = k_inf;
    metrics.minimum_crew_spo2_percent = k_inf;
    metrics.maximum_crew_fatigue_percent = 0.0;
    metrics.eva_completed = false;
    metrics.communications_sent = false;
    metrics.time_to_stabilization_hr = k_inf;
    return metrics;
}

MissionTelemetry Simulation::initializeMission() const{
    MissionTelemetry mission{};
    mission.mission_status = MissionStatus::Nominal;
    mission.stabilization_elapsed_min = 0.0;
    return mission;
}

SimulationResult Simulation::makeRejectedResult(
    const ScenarioConfig& config,
    const string& plan_id,
    const ValidationResult& validation) const{
    SimulationResult result{};
    result.scenario_id = config.scenario_id;
    result.plan_id = plan_id;
    result.outcome = OutcomeStatus::Rejected;
    result.valid_plan = false;
    result.metrics = initializeMetrics();
    for(const auto& error : validation.errors){
        result.failure_reasons.push_back(error.code + ": " + error.message);
    }
    return result;
}

bool Simulation::isOutsideEva(EVAStatus status) const{
    return status == EVAStatus::Preparing ||
           status == EVAStatus::Egress ||
           status == EVAStatus::Working ||
           status == EVAStatus::Ingress;
}

DerivedTelemetry Simulation::buildTelemetry(
    const SimulationState& state,
    const ScenarioConfig& config,
    const MissionTelemetry& mission) const{
    vector<CrewVitalsTelemetry> crew_vitals =
        crew_model_.buildCrewVitalsTelemetry(state, config);
    return resource_model_.calculateDerivedTelemetry(state, config, crew_vitals, mission);
}

void Simulation::applyCrewAbortRules(
    SimulationState& state,
    const DerivedTelemetry& telemetry,
    vector<TimelineEvent>& events) const{
    for(auto& crew : state.crew){
        if(!isOutsideEva(crew.eva_status)){
            continue;
        }
        if(crew.health_status == CrewHealthStatus::Critical &&
           (crew.eva_status == EVAStatus::Preparing ||
            crew.eva_status == EVAStatus::Egress ||
            crew.eva_status == EVAStatus::Working)){
            crew.eva_status = EVAStatus::Ingress;
            crew.actvity = CrewActivity::EVATransit;
            state.eva_work_elapsed_min = 0;
            TimelineEvent ev{};
            ev.time_min = state.time_min;
            ev.event_type = "eva_ingress";
            ev.message = "critical EVA vitals; aborting to ingress";
            ev.severity = ConstraintSeverity::Warning;
            events.push_back(ev);
        }
    }
    (void)telemetry;
}

double Simulation::remainingRepairHours(
    const SimulationState& state,
    const ScenarioConfig& config) const{
    const CrewMemberState* active = nullptr;
    for(const auto& crew : state.crew){
        if(isOutsideEva(crew.eva_status) || crew.eva_status == EVAStatus::Working){
            active = &crew;
            break;
        }
    }

    double performance = 1.0;
    if(active != nullptr && active->physical_performance_factor > 0.0){
        performance = active->physical_performance_factor;
    }

    double remaining_min = 0.0;
    if(active == nullptr){
        remaining_min = static_cast<double>(
            config.eva.preparation_min + config.eva.egress_min +
            config.eva.repair_work_min + config.eva.ingress_min);
    }else if(active->eva_status == EVAStatus::Preparing){
        remaining_min = static_cast<double>(
            std::max(0, config.eva.preparation_min - state.eva_elapsed_min) +
            config.eva.egress_min + config.eva.repair_work_min + config.eva.ingress_min);
    }else if(active->eva_status == EVAStatus::Egress){
        int egress_done_at = config.eva.preparation_min + config.eva.egress_min;
        remaining_min = static_cast<double>(
            std::max(0, egress_done_at - state.eva_elapsed_min) +
            config.eva.repair_work_min + config.eva.ingress_min);
    }else if(active->eva_status == EVAStatus::Working){
        double work_left_frac = std::max(0.0, 1.0 - state.solar_repair_progress);
        double work_left_min =
            (performance > 0.0)
                ? (work_left_frac * static_cast<double>(config.eva.repair_work_min) / performance)
                : std::numeric_limits<double>::infinity();
        remaining_min = work_left_min + static_cast<double>(config.eva.ingress_min);
    }else if(active->eva_status == EVAStatus::Ingress){
        remaining_min = static_cast<double>(
            std::max(0, config.eva.ingress_min - state.eva_work_elapsed_min));
    }

    return remaining_min / 60.0;
}

double Simulation::minimumResourceDeadlineHours(const DerivedTelemetry& telemetry) const{
    double deadline = minPositiveDeadline(
        telemetry.atmosphere.oxygen_hours_remaining,
        telemetry.atmosphere.time_to_pressure_limit_hr);
    deadline = minPositiveDeadline(deadline, telemetry.atmosphere.time_to_co2_limit_hr);
    deadline = minPositiveDeadline(deadline, telemetry.power.battery_hours_to_reserve);
    return deadline;
}

bool Simulation::stabilizationConditionsMet(
    const SimulationState& state,
    const ScenarioConfig& config,
    const DerivedTelemetry& telemetry) const{
    double effective_leak = state.total_gas_leak_kg_hr * state.leak_fault_factor;
    if(effective_leak > config.fault.stabilized_leak_kg_hr){
        return false;
    }

    const AtmosphereTelemetry& atm = telemetry.atmosphere;
    if(atm.inspired_oxygen_mmhg <= config.atmosphere.inspired_o2_failure_mmhg){
        return false;
    }
    if(atm.cabin_pressure_kpa <= config.atmosphere.pressure_failure_low_kpa){
        return false;
    }
    if(atm.co2_one_hour_avg_mmhg >= config.atmosphere.co2_one_hour_limit_mmhg){
        return false;
    }
    if(telemetry.power.battery_soc_percent <= config.power.battery_reserve_percent){
        return false;
    }
    if(state.cabin_temperature_c <= config.thermal.critical_low_c ||
       state.cabin_temperature_c >= config.thermal.critical_high_c){
        return false;
    }

    bool power_ok =
        telemetry.power.power_margin_kw >= 0.0 ||
        state.solar_fault_factor >= config.fault.repaired_solar_fault_factor;
    if(!power_ok){
        return false;
    }

    for(const auto& crew : state.crew){
        if(isOutsideEva(crew.eva_status) &&
           telemetry.eva.eva_safe_return_margin_min < 0.0 &&
           crew.eva_status != EVAStatus::Ingress){
            return false;
        }
        if(crew.health_status == CrewHealthStatus::Critical ||
           crew.health_status == CrewHealthStatus::Incapacitated){
            return false;
        }
    }

    return true;
}

MissionEvaluation Simulation::evaluateMissionState(
    SimulationState& state,
    const ScenarioConfig& config,
    DerivedTelemetry& telemetry,
    MissionTelemetry& mission,
    vector<TimelineEvent>& events,
    double dt_minutes){
    MissionEvaluation evaluation{};
    evaluation.terminate = false;
    evaluation.outcome = OutcomeStatus::Failure;

    applyCrewAbortRules(state, telemetry, events);

    mission.warnings.clear();
    mission.violated_constraints.clear();

    vector<string> failure_reasons;

    const AtmosphereTelemetry& atm = telemetry.atmosphere;
    if(atm.inspired_oxygen_mmhg <= config.atmosphere.inspired_o2_failure_mmhg){
        failure_reasons.push_back("inspired_o2_hard_limit");
    }
    if(atm.cabin_pressure_kpa <= config.atmosphere.pressure_failure_low_kpa){
        failure_reasons.push_back("pressure_hard_limit");
    }
    if(atm.co2_one_hour_avg_mmhg >= config.atmosphere.co2_one_hour_limit_mmhg){
        failure_reasons.push_back("co2_hard_limit");
    }
    if(state.battery_energy_kwh <= 0.0 ||
       telemetry.power.battery_soc_percent <= config.power.battery_reserve_percent){
        failure_reasons.push_back("battery_failure_reserve");
    }
    if(state.cabin_temperature_c <= config.thermal.critical_low_c ||
       state.cabin_temperature_c >= config.thermal.critical_high_c){
        failure_reasons.push_back("cabin_temperature_critical");
    }

    bool any_incapacitated_on_eva = false;
    int incapacitated_count = 0;
    for(const auto& crew : state.crew){
        if(crew.health_status == CrewHealthStatus::Incapacitated){
            ++incapacitated_count;
            if(isOutsideEva(crew.eva_status)){
                any_incapacitated_on_eva = true;
                failure_reasons.push_back("eva_crew_incapacitated:" + crew.crew_id);
            }
        }
        if(crew.eva_status == EVAStatus::Preparing ||
           crew.eva_status == EVAStatus::Egress ||
           crew.eva_status == EVAStatus::Working){
            if(telemetry.eva.eva_safe_return_margin_min < 0.0){
                failure_reasons.push_back("eva_safe_return_negative");
            }
        }
    }
    if(!state.crew.empty() && incapacitated_count == static_cast<int>(state.crew.size())){
        failure_reasons.push_back("all_crew_incapacitated");
    }
    (void)any_incapacitated_on_eva;

    bool solar_faulted =
        state.solar_fault_factor < config.fault.repaired_solar_fault_factor;
    bool repair_incomplete = state.solar_repair_progress < 1.0;
    if(solar_faulted && repair_incomplete){
        double repair_hours = remainingRepairHours(state, config);
        double resource_deadline = minimumResourceDeadlineHours(telemetry);
        if(std::isfinite(repair_hours) && std::isfinite(resource_deadline) &&
           repair_hours > resource_deadline){
            failure_reasons.push_back("critical_repair_impossible");
        }
    }

    if(!failure_reasons.empty()){
        mission.mission_status = MissionStatus::Failure;
        mission.stabilization_elapsed_min = 0.0;
        mission.violated_constraints = failure_reasons;
        evaluation.terminate = true;
        evaluation.outcome = OutcomeStatus::Failure;
        TimelineEvent ev{};
        ev.time_min = state.time_min;
        ev.event_type = "mission_failure";
        ev.message = failure_reasons.front();
        ev.severity = ConstraintSeverity::Failure;
        events.push_back(ev);
        telemetry.mission = mission;
        return evaluation;
    }

    // soft warnings
    if(atm.inspired_oxygen_mmhg <= config.atmosphere.inspired_o2_warning_mmhg){
        mission.warnings.push_back("inspired_o2_warning");
    }
    if(atm.cabin_pressure_kpa <= config.atmosphere.pressure_warning_low_kpa){
        mission.warnings.push_back("pressure_warning");
    }
    if(atm.co2_one_hour_avg_mmhg >= config.atmosphere.co2_one_hour_limit_mmhg * 0.8){
        mission.warnings.push_back("co2_elevated");
    }
    if(telemetry.power.battery_soc_percent <= config.power.battery_reserve_percent + 10.0){
        mission.warnings.push_back("battery_low");
    }
    if(state.cabin_temperature_c <= config.thermal.comfort_low_c ||
       state.cabin_temperature_c >= config.thermal.comfort_high_c){
        mission.warnings.push_back("thermal_comfort");
    }
    for(const auto& crew : state.crew){
        if(!crew.active_alarms.empty()){
            mission.warnings.push_back("crew_alarm:" + crew.crew_id);
        }
        if(crew.health_status == CrewHealthStatus::Impaired ||
           crew.health_status == CrewHealthStatus::Critical){
            mission.warnings.push_back("crew_impaired:" + crew.crew_id);
        }
    }

    bool has_critical_crew = false;
    for(const auto& crew : state.crew){
        if(crew.health_status == CrewHealthStatus::Critical){
            has_critical_crew = true;
            break;
        }
    }

    if(stabilizationConditionsMet(state, config, telemetry)){
        mission.stabilization_elapsed_min += dt_minutes;
        if(mission.stabilization_elapsed_min >= static_cast<double>(config.stabilization_hold_min)){
            mission.mission_status = MissionStatus::Stabilized;
            evaluation.terminate = true;
            evaluation.outcome = OutcomeStatus::Stabilized;
            TimelineEvent ev{};
            ev.time_min = state.time_min;
            ev.event_type = "mission_stabilized";
            ev.message = "stabilization hold complete";
            ev.severity = ConstraintSeverity::Info;
            events.push_back(ev);
            telemetry.mission = mission;
            return evaluation;
        }
        mission.mission_status = has_critical_crew
            ? MissionStatus::Critical
            : (!mission.warnings.empty() ? MissionStatus::Warning : MissionStatus::Nominal);
    }else{
        mission.stabilization_elapsed_min = 0.0;
        if(has_critical_crew){
            mission.mission_status = MissionStatus::Critical;
        }else if(!mission.warnings.empty()){
            mission.mission_status = MissionStatus::Warning;
        }else{
            mission.mission_status = MissionStatus::Nominal;
        }
    }

    telemetry.mission = mission;
    return evaluation;
}

void Simulation::updateExtremaAndMetrics(
    SimulationMetrics& metrics,
    const DerivedTelemetry& telemetry,
    const SimulationState& state) const{
    metrics.minimum_inspired_o2_mmhg =
        std::min(metrics.minimum_inspired_o2_mmhg, telemetry.atmosphere.inspired_oxygen_mmhg);
    metrics.minimum_cabin_pressure_kpa =
        std::min(metrics.minimum_cabin_pressure_kpa, telemetry.atmosphere.cabin_pressure_kpa);
    metrics.maximum_co2_one_hour_avg_mmhg =
        std::max(metrics.maximum_co2_one_hour_avg_mmhg, telemetry.atmosphere.co2_one_hour_avg_mmhg);
    metrics.minimum_battery_soc_percent =
        std::min(metrics.minimum_battery_soc_percent, telemetry.power.battery_soc_percent);
    metrics.minimum_power_margin_kw =
        std::min(metrics.minimum_power_margin_kw, telemetry.power.power_margin_kw);
    metrics.minimum_temperature_margin_c =
        std::min(metrics.minimum_temperature_margin_c, telemetry.thermal.temperature_margin_c);
    metrics.minimum_eva_safe_return_margin_min =
        std::min(metrics.minimum_eva_safe_return_margin_min, telemetry.eva.eva_safe_return_margin_min);

    for(const auto& crew : telemetry.crew_vitals){
        metrics.minimum_crew_spo2_percent =
            std::min(metrics.minimum_crew_spo2_percent, crew.spo2_percent);
        metrics.maximum_crew_fatigue_percent =
            std::max(metrics.maximum_crew_fatigue_percent, crew.fatigue_percent);
    }

    for(const auto& crew : state.crew){
        if(crew.eva_status == EVAStatus::Complete){
            metrics.eva_completed = true;
        }
    }
    if(state.emergency_packet_sent){
        metrics.communications_sent = true;
    }
}

SimulationResult Simulation::runBaseline(const ScenarioConfig& config){
    return runInternal(config, nullptr);
}

SimulationResult Simulation::runWithPlan(const ScenarioConfig& config, const Plan& plan){
    return runInternal(config, &plan);
}

SimulationResult Simulation::runInternal(
    const ScenarioConfig& config,
    const Plan* plan){
    ValidationResult scenario_validation = validator_.validateScenario(config);
    if(!scenario_validation.valid){
        return makeRejectedResult(config, plan ? plan->plan_id : "", scenario_validation);
    }

    Plan empty_plan{};
    empty_plan.plan_id = "";
    const Plan& active_plan = plan ? *plan : empty_plan;

    if(plan != nullptr){
        ValidationResult plan_validation = validator_.validatePlan(active_plan, config);
        if(!plan_validation.valid){
            return makeRejectedResult(config, active_plan.plan_id, plan_validation);
        }
    }

    SimulationState state = initializeState(config);
    SimulationMetrics metrics = initializeMetrics();
    MissionTelemetry mission = initializeMission();
    vector<TimelineEvent> timeline;
    vector<TelemetrySample> history;

    SimulationResult result{};
    result.scenario_id = config.scenario_id;
    result.plan_id = active_plan.plan_id;
    result.valid_plan = true;
    result.outcome = OutcomeStatus::Failure;

    const double dt_seconds = static_cast<double>(config.time_step_s);
    const double dt_minutes = dt_seconds / 60.0;
    const int step_min = std::max(1, config.time_step_s / 60);

    while(true){
        vector<TimelineEvent> step_events;

        // 1. scheduled actions
        if(plan != nullptr){
            action_executor_.applyScheduledActions(active_plan, state, config, step_events);
        }

        // 2-3. pre-step telemetry from current physical state
        DerivedTelemetry pre_step = buildTelemetry(state, config, mission);

        // 4-5. physiology and habitat loads
        crew_model_.updateAllCrew(state, config, pre_step, dt_seconds, step_events);
        CrewHabitatLoads loads = crew_model_.aggregateCrewLoads(state.crew);

        // 6-11. resource updates
        resource_model_.updateAtmosphere(state, config, loads.oxygen_consumption_g_min, dt_seconds);
        resource_model_.updateCarbonDioxide(state, config, loads.co2_production_g_min, dt_seconds);
        double solar_kw = resource_model_.calculateSolarGenerationKw(state, config);
        resource_model_.updateElectricalPower(state, config, solar_kw, dt_seconds);
        resource_model_.updateThermalState(state, config, loads.heat_output_w, dt_seconds);
        resource_model_.updateEVAAndRepair(state, config, step_events, dt_seconds);

        if(plan != nullptr){
            action_executor_.updateActiveActions(state, config, step_events, dt_seconds);
        }

        // 12. post-step telemetry
        DerivedTelemetry post_step = buildTelemetry(state, config, mission);

        // 13. mission evaluation
        MissionEvaluation evaluation = evaluateMissionState(
            state, config, post_step, mission, step_events, dt_minutes);

        updateExtremaAndMetrics(metrics, post_step, state);
        if(evaluation.terminate && evaluation.outcome == OutcomeStatus::Stabilized){
            metrics.time_to_stabilization_hr =
                static_cast<double>(state.time_min) / 60.0;
        }

        TelemetrySample sample{};
        sample.simulation_time_min = state.time_min;
        sample.telemetry = post_step;
        sample.events_this_step = step_events;
        sample.active_actions = state.active_actions;
        sample.has_warning = post_step.mission.mission_status == MissionStatus::Warning;
        sample.has_critical =
            post_step.mission.mission_status == MissionStatus::Critical ||
            post_step.mission.mission_status == MissionStatus::Failure;
        history.push_back(sample);
        timeline.insert(timeline.end(), step_events.begin(), step_events.end());

        if(evaluation.terminate){
            result.outcome = evaluation.outcome;
            if(evaluation.outcome == OutcomeStatus::Failure){
                result.failure_reasons = post_step.mission.violated_constraints;
            }
            break;
        }

        if(state.time_min >= config.maximum_duration_min){
            result.outcome = OutcomeStatus::Failure;
            result.failure_reasons.push_back("maximum_duration_exceeded");
            break;
        }

        // 14. advance clock
        state.time_min += step_min;
    }

    result.metrics = metrics;
    result.timeline = std::move(timeline);
    result.telemetry_history = std::move(history);
    return result;
}
