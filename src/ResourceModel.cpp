#include "ResourceModel.hpp"
#include "MathUtils.hpp"
#include "PhysicalConstants.hpp"
#include <cmath>
#include <limits>

namespace {

// Mars solar generation in watts before fault factor and kW conversion.
double calculateSolarGenerationWatts(const SimulationState& state, const ScenarioConfig& config) {
    using namespace ares::constants;
    // 1. orbital flux at Mars-Sun distance
    double distance_au = config.solar.mars_sun_distance_au;
    double orbital_flux_w_m2 = SOLAR_FLUX_1_AU_W_M2 / (distance_au * distance_au);
    // 2. incidence cosine clamped at zero
    double angle_rad = state.solar_incidence_angle_deg * (std::acos(-1.0) / 180.0);
    double cos_incidence = std::cos(angle_rad);
    if (cos_incidence < 0.0) {
        cos_incidence = 0.0;
    }
    // 3–4. area, efficiency, atmosphere, and dust
    return orbital_flux_w_m2 * cos_incidence
        * config.solar.array_area_m2
        * config.solar.cell_efficiency
        * state.atmospheric_transmission
        * state.deposited_dust_factor;
}

}


void ResourceModel::updateAtmosphere(SimulationState& state, const ScenarioConfig& config, double total_crew_oxygen_g_min, double dt_seconds){
    // mixed-gas atmosphere update.
    double dt_hours = MathUtils::secondsToHours(dt_seconds);
    double dt_minutes = dt_seconds / ares::constants::SECONDS_PER_MINUTE;
// 1. crew production
    double crew_o2_kg = total_crew_oxygen_g_min * dt_minutes / ares::constants::GRAMS_PER_KILOGRAM;
    state.oxygen_mass_kg -= crew_o2_kg;
    double total_mass_kg = state.oxygen_mass_kg + state.inert_gas_mass_kg + state.co2_mass_kg;
// 2. total gas leak
    double leak_kg = state.total_gas_leak_kg_hr * state.leak_fault_factor * dt_hours;
// 3. current mass fractions before removal
    if(total_mass_kg > 0.0 && leak_kg > 0.0){
        double current_o2_fraction = state.oxygen_mass_kg / total_mass_kg;
        double current_inert_fraction = state.inert_gas_mass_kg / total_mass_kg;
        double current_co2_fraction = state.co2_mass_kg / total_mass_kg;
// 4. remove leaked gas
        state.oxygen_mass_kg -= leak_kg * current_o2_fraction;
        state.inert_gas_mass_kg -= leak_kg * current_inert_fraction;
        state.co2_mass_kg -= leak_kg * current_co2_fraction;
    }
// 5. clamp inventories at zero only after recording that depletion would occur; failure logic is handled later by Simulation.
    if(state.oxygen_mass_kg < 0.0){
        state.oxygen_mass_kg = 0.0;
    }
    if(state.inert_gas_mass_kg < 0.0){
        state.inert_gas_mass_kg = 0.0;
    }
    if(state.co2_mass_kg < 0.0){
        state.co2_mass_kg = 0.0;
    }
}

void ResourceModel::updateCarbonDioxide(SimulationState& state, const ScenarioConfig& config, double total_crew_co2_g_min, double dt_seconds){
    // crew CO2 production for the timestep.
    double dt_minutes = dt_seconds / ares::constants::SECONDS_PER_MINUTE;
    // 1. crew production
    double crew_co2_kg = (total_crew_co2_g_min * dt_minutes) / ares::constants::GRAMS_PER_KILOGRAM;
    state.co2_mass_kg += crew_co2_kg;
    // 2–3. scrubber: rated × efficiency, never more than available
    double rated_removal_kg = (config.atmosphere.scrubber_capacity_g_min * state.scrubber_efficiency * dt_minutes)
        / ares::constants::GRAMS_PER_KILOGRAM;
    double removal_kg = rated_removal_kg;
    if (removal_kg > state.co2_mass_kg) {
        removal_kg = state.co2_mass_kg;
    }
    state.co2_mass_kg -= removal_kg;
    // 4. post-step CO2 partial pressure (mmHg) for the rolling window
    //    p_co2 = n_co2 * R * T / V, then kPa -> mmHg
    double n_o2 = state.oxygen_mass_kg / ares::constants::OXYGEN_MORAL_MASS_KG_PERO_MOL;
    double n_inert = state.inert_gas_mass_kg / ares::constants::INERT_MOLAR_MASS_KG_PER_MOL;
    double n_co2 = state.co2_mass_kg / ares::constants::CO2_MORAL_MASS_KG_PER_MOL;
    double n_total = n_o2 + n_inert + n_co2;
    double co2_pp_mmhg = 0.0;
    if (n_total > 0.0 && state.habitable_volume_m3 > 0.0) {
        double t_k = MathUtils::celsiusToKelvin(state.cabin_temperature_c);
        double p_co2_pa = (n_co2 * ares::constants::GAS_CONSTANT_J_PER_MOL_K * t_k) / state.habitable_volume_m3;
        co2_pp_mmhg = MathUtils::kpaToMmhg(p_co2_pa / 1000.0);
    }
    state.rolling_co2_samples.push_back(co2_pp_mmhg);
    // 5. keep exactly one simulated hour of samples
    //    60 s step -> 3600/60 = 60 samples
    size_t max_samples = static_cast<size_t>(ares::constants::SECONDS_PER_HOUR / config.time_step_s);
    while (state.rolling_co2_samples.size() > max_samples) {
        state.rolling_co2_samples.pop_front();
    }

}

double ResourceModel::calculateSolarGenerationKw(const SimulationState& state, const ScenarioConfig& config) const{
    // actual generation includes solar_fault_factor from scenario state
    double generation_w = calculateSolarGenerationWatts(state, config) * state.solar_fault_factor;
    return generation_w / ares::constants::WATTS_PER_KILOWATT;
}

double ResourceModel::calculateHealthySolarGenerationKw(const SimulationState& state, const ScenarioConfig& config) const{
    // healthy reference omits solar_fault_factor
    double generation_w = calculateSolarGenerationWatts(state, config);
    return generation_w / ares::constants::WATTS_PER_KILOWATT;
}

void ResourceModel::updateElectricalPower(SimulationState& state, const ScenarioConfig& config, double solar_generation_kw, double dt_seconds){
    // electrical load balance and battery energy integration.
    // 1. sum categorized habitat loads
    double total_load_kw = state.essential_load_kw + state.discretionary_load_kw + state.thermal_control_load_kw + state.eva_support_load_kw + state.communications_load_kw;
    // 2. generation minus load
    double net_kw = solar_generation_kw - total_load_kw;
    // 3. timestep in hours
    double dt_hours = MathUtils::secondsToHours(dt_seconds);
    // 4. charge when surplus, discharge when deficit
    double delta_kwh = 0.0;
    if (net_kw >= 0.0) {
        delta_kwh = net_kw * dt_hours * config.power.charge_efficiency;
    } else {
        delta_kwh = net_kw * dt_hours / config.power.discharge_efficiency;
    }
    // 5. clamp stored energy to [0, capacity]
    state.battery_energy_kwh = MathUtils::clamp(state.battery_energy_kwh + delta_kwh, 0.0, config.power.battery_capacity_kwh);
}

void ResourceModel::updateThermalState(SimulationState& state, const ScenarioConfig& config, double total_crew_heat_w, double dt_seconds){
    // cabin temperature integration from net heat.
// 1. sum heat inputs
    double heat_input_w = total_crew_heat_w + state.equipment_heat_w + state.environmental_heat_w + state.heater_heat_w;
// 2. commanded rejection limited by TCS capacity
    double commanded_rejection_w = heat_input_w;
    if(commanded_rejection_w < 0.0){
        commanded_rejection_w = 0.0;
    }
    double actual_rejection_w = commanded_rejection_w;
    if(actual_rejection_w > state.tcs_rejection_capacity_w){
        actual_rejection_w = state.tcs_rejection_capacity_w;
    }
// 3. net heat in watts
    double net_heat_w = heat_input_w - actual_rejection_w;
// 4. capacitance kJ/C -> J/C
    double capacitance_j_c = config.habitat.effective_thermal_capacitance_kj_c * 1000.0;
// 5. integrate cabin temperature
    if(capacitance_j_c > 0.0){
        state.cabin_temperature_c += (net_heat_w * dt_seconds) / capacitance_j_c;
    }
}

AtmosphereTelemetry ResourceModel::calculateAtmosphereTelemetry(const SimulationState& state, const ScenarioConfig& config) const{
    // atmosphere telemetry from ideal-gas state and current-rate forecasts.
    using namespace ares::constants;
    AtmosphereTelemetry out{};
    const double k_inf = std::numeric_limits<double>::infinity();

    // 1. masses to moles
    double n_o2 = state.oxygen_mass_kg / OXYGEN_MORAL_MASS_KG_PERO_MOL;
    double n_inert = state.inert_gas_mass_kg / INERT_MOLAR_MASS_KG_PER_MOL;
    double n_co2 = state.co2_mass_kg / CO2_MORAL_MASS_KG_PER_MOL;

    // 2. total moles and temperature
    double n_total = n_o2 + n_inert + n_co2;
    double t_k = MathUtils::celsiusToKelvin(state.cabin_temperature_c);
    double volume = state.habitable_volume_m3;

    // 3. cabin pressure from ideal gas law
    if (n_total > 0.0 && volume > 0.0) {
        out.cabin_pressure_kpa =
            (n_total * GAS_CONSTANT_J_PER_MOL_K * t_k / volume) / 1000.0;
    }

    // 4. oxygen mole fraction and inspired O2
    if (n_total > 0.0) {
        out.oxygen_fraction = n_o2 / n_total;
        double p_mmhg = MathUtils::kpaToMmhg(out.cabin_pressure_kpa);
        out.inspired_oxygen_mmhg =
            out.oxygen_fraction * (p_mmhg - WATER_VAPOR_PRESSURE_MMHG);
    }

    // 5. CO2 partial pressure and rolling one-hour average
    if (volume > 0.0) {
        double p_co2_pa = (n_co2 * GAS_CONSTANT_J_PER_MOL_K * t_k) / volume;
        out.co2_partial_pressure_mmhg = MathUtils::kpaToMmhg(p_co2_pa / 1000.0);
    }
    if (!state.rolling_co2_samples.empty()) {
        double sum = 0.0;
        for (double sample : state.rolling_co2_samples) {
            sum += sample;
        }
        out.co2_one_hour_avg_mmhg =
            sum / static_cast<double>(state.rolling_co2_samples.size());
    }

    // 6. current-rate forecasts; infinity when trend is safe
    double crew_o2_g_min = 0.0;
    double crew_co2_g_min = 0.0;
    for (const auto& crew : state.crew) {
        crew_o2_g_min += crew.oxygen_consumption_g_min;
        crew_co2_g_min += crew.co2_production_g_min;
    }

    double total_mass =
        state.oxygen_mass_kg + state.inert_gas_mass_kg + state.co2_mass_kg;
    double leak_kg_hr = state.total_gas_leak_kg_hr * state.leak_fault_factor;
    double o2_frac = (total_mass > 0.0) ? state.oxygen_mass_kg / total_mass : 0.0;
    double co2_frac = (total_mass > 0.0) ? state.co2_mass_kg / total_mass : 0.0;

    double o2_loss_kg_hr =
        (crew_o2_g_min * MINUTES_PER_HOUR) / GRAMS_PER_KILOGRAM
        + leak_kg_hr * o2_frac;
    out.oxygen_hours_remaining =
        (o2_loss_kg_hr > 0.0) ? state.oxygen_mass_kg / o2_loss_kg_hr : k_inf;

    double m_avg = (n_total > 0.0) ? total_mass / n_total : 0.0;
    double dn_leak_hr = (m_avg > 0.0) ? leak_kg_hr / m_avg : 0.0;
    double dn_o2_crew_hr = ((crew_o2_g_min * MINUTES_PER_HOUR) / GRAMS_PER_KILOGRAM)/ OXYGEN_MORAL_MASS_KG_PERO_MOL;
    double dn_co2_crew_hr = ((crew_co2_g_min * MINUTES_PER_HOUR) / GRAMS_PER_KILOGRAM)/ CO2_MORAL_MASS_KG_PER_MOL;

    double scrubber_kg_hr = (config.atmosphere.scrubber_capacity_g_min * state.scrubber_efficiency * MINUTES_PER_HOUR) / GRAMS_PER_KILOGRAM;

    if (scrubber_kg_hr > state.co2_mass_kg) {
        scrubber_kg_hr = state.co2_mass_kg;
    }
    double dn_scrub_hr = scrubber_kg_hr / CO2_MORAL_MASS_KG_PER_MOL;

    double dn_dt_hr = -dn_leak_hr - dn_o2_crew_hr + dn_co2_crew_hr - dn_scrub_hr;
    double dp_kpa_hr = 0.0;

    if (volume > 0.0) {
        dp_kpa_hr = (dn_dt_hr * GAS_CONSTANT_J_PER_MOL_K * t_k / volume) / 1000.0;
    }
    double p_limit = config.atmosphere.pressure_failure_low_kpa;

    if (dp_kpa_hr < 0.0 && out.cabin_pressure_kpa > p_limit) { 
        out.time_to_pressure_limit_hr = (out.cabin_pressure_kpa - p_limit) / (-dp_kpa_hr);
    } 
    else {
        out.time_to_pressure_limit_hr = k_inf;
    }

    double co2_net_kg_hr = ((crew_co2_g_min * MINUTES_PER_HOUR) / GRAMS_PER_KILOGRAM) - scrubber_kg_hr - leak_kg_hr * co2_frac;
    double dpp_mmhg_hr = 0.0;

    if (volume > 0.0) {
        double dn_co2_net_hr = co2_net_kg_hr / CO2_MORAL_MASS_KG_PER_MOL;
        double dpp_pa_hr = (dn_co2_net_hr * GAS_CONSTANT_J_PER_MOL_K * t_k) / volume;
        dpp_mmhg_hr = MathUtils::kpaToMmhg(dpp_pa_hr / 1000.0);
    }

    double co2_limit = config.atmosphere.co2_one_hour_limit_mmhg;

    if (out.co2_one_hour_avg_mmhg >= co2_limit) {
        out.time_to_co2_limit_hr = 0.0;
    } 
    else if (dpp_mmhg_hr > 0.0) {
        out.time_to_co2_limit_hr = (co2_limit - out.co2_one_hour_avg_mmhg) / dpp_mmhg_hr;
    } 
    else {
        out.time_to_co2_limit_hr = k_inf;
    }

    return out;
}

PowerTelemetry ResourceModel::calculatePowerTelemetry(const SimulationState& state, const ScenarioConfig& config, double solar_generation_kw, double healthy_solar_generation_kw) const{
    // power telemetry from load balance and battery state.
    PowerTelemetry out{};
    const double k_inf = std::numeric_limits<double>::infinity();
    out.solar_generation_kw = solar_generation_kw;
    out.healthy_solar_generation_kw = healthy_solar_generation_kw;
// 1. total load and power margin
    out.total_habitat_load_kw = state.essential_load_kw + state.discretionary_load_kw + state.thermal_control_load_kw + state.eva_support_load_kw + state.communications_load_kw;
    out.power_margin_kw = solar_generation_kw - out.total_habitat_load_kw;
// 2. SOC from energy / capacity
    if(config.power.battery_capacity_kwh > 0.0){
        out.battery_soc_percent = (state.battery_energy_kwh / config.power.battery_capacity_kwh) * 100.0;
    }
// 3. solar generation percent; zero when healthy reference is zero
    if(healthy_solar_generation_kw > 0.0){
        out.solar_generation_percent = (solar_generation_kw / healthy_solar_generation_kw) * 100.0;
    }
// 4. time to reserve only while net discharging and above reserve
    double reserve_kwh = config.power.battery_capacity_kwh * MathUtils::percentToFraction(config.power.battery_reserve_percent);
    if(out.power_margin_kw < 0.0 && state.battery_energy_kwh > reserve_kwh){
        double drain_kw = (-out.power_margin_kw) / config.power.discharge_efficiency;
        out.battery_hours_to_reserve = (state.battery_energy_kwh - reserve_kwh) / drain_kw;
    }
    else{
        out.battery_hours_to_reserve = k_inf;
    }
    return out;
}

ThermalTelemetry ResourceModel::calculateThermalTelemetry(const SimulationState& state, const ScenarioConfig& config, double total_crew_heat_w) const{
    // thermal telemetry from heat balance and critical temperature limits.
    ThermalTelemetry out{};
    out.crew_heat_w = total_crew_heat_w;
// 1. heat input and actual rejection (same definitions as update)
    double heat_input_w = total_crew_heat_w + state.equipment_heat_w + state.environmental_heat_w + state.heater_heat_w;
    double commanded_rejection_w = heat_input_w;
    if(commanded_rejection_w < 0.0){
        commanded_rejection_w = 0.0;
    }
    double actual_rejection_w = commanded_rejection_w;
    if(actual_rejection_w > state.tcs_rejection_capacity_w){
        actual_rejection_w = state.tcs_rejection_capacity_w;
    }
    out.tcs_commanded_rejection_w = commanded_rejection_w;
// 2. net thermal power and remaining rejection margin
    out.net_thermal_power_w = heat_input_w - actual_rejection_w;
    out.thermal_margin_w = state.tcs_rejection_capacity_w - heat_input_w;
// 3. temperature margin to nearest critical limit
    double margin_to_low = state.cabin_temperature_c - config.thermal.critical_low_c;
    double margin_to_high = config.thermal.critical_high_c - state.cabin_temperature_c;
    out.temperature_margin_c = margin_to_low;
    if(margin_to_high < margin_to_low){
        out.temperature_margin_c = margin_to_high;
    }
    return out;
}

void ResourceModel::updateEVAAndRepair(SimulationState& state, const ScenarioConfig& config, vector<TimelineEvent>& events, double dt_seconds){
    // advance active EVA phase, consumables, rover energy, and repair progress
    double dt_minutes = dt_seconds / ares::constants::SECONDS_PER_MINUTE;
    if(dt_minutes <= 0.0){
        return;
    }

    CrewMemberState* active_crew = nullptr;
    for(auto& crew : state.crew){
        if(crew.eva_status == EVAStatus::Preparing ||
           crew.eva_status == EVAStatus::Egress ||
           crew.eva_status == EVAStatus::Working ||
           crew.eva_status == EVAStatus::Ingress){
            active_crew = &crew;
            break;
        }
    }
    if(active_crew == nullptr){
        return;
    }

    auto emit = [&](const string& event_type, const string& message, ConstraintSeverity severity){
        TimelineEvent ev{};
        ev.time_min = state.time_min;
        ev.event_type = event_type;
        ev.message = message;
        ev.severity = severity;
        events.push_back(ev);
    };

    auto begin_ingress = [&](CrewMemberState& crew, const string& reason){
        crew.eva_status = EVAStatus::Ingress;
        crew.actvity = CrewActivity::EVATransit;
        state.eva_work_elapsed_min = 0;
        emit("eva_ingress", reason, ConstraintSeverity::Warning);
    };

    auto abort_eva = [&](CrewMemberState& crew, const string& reason){
        crew.eva_status = EVAStatus::Aborted;
        crew.actvity = CrewActivity::Recovery;
        emit("eva_aborted", reason, ConstraintSeverity::Critical);
    };

    // rover energy while EVA is active
    if(config.eva.rover_required){
        if(!state.rover_available){
            abort_eva(*active_crew, "rover unavailable during EVA");
            return;
        }
        state.rover_battery_percent -= dt_minutes * (100.0 / static_cast<double>(config.eva.maximum_duration_min));
        if(state.rover_battery_percent < 0.0){
            state.rover_battery_percent = 0.0;
        }
        if(state.rover_battery_percent < config.eva.rover_minimum_reserve_percent){
            begin_ingress(*active_crew, "rover below minimum reserve; aborting to ingress");
        }
    }

    if(active_crew->eva_status == EVAStatus::Aborted){
        return;
    }

    state.eva_elapsed_min += static_cast<int>(dt_minutes);

    EVATelemetry preview = calculateEVATelemetry(state, config);
    if(preview.eva_safe_return_margin_min < 0.0 &&
       (active_crew->eva_status == EVAStatus::Preparing ||
        active_crew->eva_status == EVAStatus::Egress ||
        active_crew->eva_status == EVAStatus::Working)){
        begin_ingress(*active_crew, "EVA safe-return margin negative; aborting to ingress");
    }

    if(active_crew->eva_status == EVAStatus::Preparing){
        active_crew->actvity = CrewActivity::EVAPrep;
        if(state.eva_elapsed_min >= config.eva.preparation_min){
            active_crew->eva_status = EVAStatus::Egress;
            active_crew->actvity = CrewActivity::EVATransit;
            emit("eva_egress", "EVA preparation complete; beginning egress", ConstraintSeverity::Info);
        }
    }else if(active_crew->eva_status == EVAStatus::Egress){
        active_crew->actvity = CrewActivity::EVATransit;
        int egress_done_at = config.eva.preparation_min + config.eva.egress_min;
        if(state.eva_elapsed_min >= egress_done_at){
            active_crew->eva_status = EVAStatus::Working;
            active_crew->actvity = CrewActivity::EVAWork;
            state.eva_work_elapsed_min = 0;
            emit("eva_working", "EVA egress complete; beginning repair work", ConstraintSeverity::Info);
        }
    }else if(active_crew->eva_status == EVAStatus::Working){
        active_crew->actvity = CrewActivity::EVAWork;
        state.eva_work_elapsed_min += static_cast<int>(dt_minutes);
        double performance = active_crew->physical_performance_factor;
        if(performance < 0.0){
            performance = 0.0;
        }
        if(config.eva.repair_work_min > 0){
            double delta = (dt_minutes / static_cast<double>(config.eva.repair_work_min)) * performance;
            state.solar_repair_progress += delta;
            if(state.solar_repair_progress > 1.0){
                state.solar_repair_progress = 1.0;
            }
        }
        if(state.solar_repair_progress >= 1.0){
            begin_ingress(*active_crew, "solar repair complete; beginning ingress");
        }
    }else if(active_crew->eva_status == EVAStatus::Ingress){
        active_crew->actvity = CrewActivity::EVATransit;
        state.eva_work_elapsed_min += static_cast<int>(dt_minutes);
        if(state.eva_work_elapsed_min >= config.eva.ingress_min){
            active_crew->eva_status = EVAStatus::Complete;
            active_crew->actvity = CrewActivity::Recovery;
            if(state.solar_repair_progress >= 1.0){
                state.solar_fault_factor = config.fault.repaired_solar_fault_factor;
                emit("solar_repaired", "solar fault factor restored after successful repair", ConstraintSeverity::Info);
            }
            emit("eva_complete", "EVA ingress complete", ConstraintSeverity::Info);
        }
    }
}

EVATelemetry ResourceModel::calculateEVATelemetry(const SimulationState& state, const ScenarioConfig& config) const{
    // EVA consumables, safe-return margin, and repair progress.
    EVATelemetry out{};
// 1. consumables remaining from maximum duration minus elapsed
    out.eva_consumables_remaining_min = static_cast<double>(config.eva.maximum_duration_min - state.eva_elapsed_min);
// 2. safe-return margin after ingress and reserve
    out.eva_safe_return_margin_min = out.eva_consumables_remaining_min - static_cast<double>(config.eva.ingress_min + config.eva.reserve_min);
// 3. repair progress fraction to percent
    out.repair_progress_percent = state.solar_repair_progress * 100.0;
    for(const auto& crew : state.crew){
        if(crew.eva_status != EVAStatus::Idle && crew.eva_status != EVAStatus::Complete && crew.eva_status != EVAStatus::Aborted){
            out.active_crew_id = crew.crew_id;
            break;
        }
    }
    return out;
}

CommunicationsTelemetry ResourceModel::calculateCommunicationsTelemetry(const SimulationState& state, const ScenarioConfig& config) const{
    // communication window status and transmission state.
    // Window rule: inclusive open, exclusive close [open_min, close_min).
    CommunicationsTelemetry out{};
    const double k_inf = std::numeric_limits<double>::infinity();
    out.emergency_packet_sent = state.emergency_packet_sent;
    out.transmission_in_progress = state.transmission_elapsed_min > 0 && state.transmission_elapsed_min < config.communications.transmission_duration_min;
    out.comms_window_open = false;
    out.next_comms_window_min = k_inf;
// 4. current time inside any communication window
    for(const auto& window : config.communications.windows){
        if(state.time_min >= window.open_min && state.time_min < window.close_min){
            out.comms_window_open = true;
            break;
        }
    }
// 5. next future communication opening, or infinity if none
    for(const auto& window : config.communications.windows){
        if(window.open_min > state.time_min){
            double open_min = static_cast<double>(window.open_min);
            if(open_min < out.next_comms_window_min){
                out.next_comms_window_min = open_min;
            }
        }
    }
    return out;
}

DerivedTelemetry ResourceModel::calculateDerivedTelemetry(const SimulationState& state, const ScenarioConfig& config, const vector<CrewVitalsTelemetry>& crew_vitals, const MissionTelemetry& mission_telemetry) const{
    // assemble complete habitat telemetry from one coherent state.
    DerivedTelemetry out{};
// 1. subsystem telemetries
    double solar_generation_kw = calculateSolarGenerationKw(state, config);
    double healthy_solar_generation_kw = calculateHealthySolarGenerationKw(state, config);
    double total_crew_heat_w = 0.0;
    for(const auto& crew : crew_vitals){
        total_crew_heat_w += crew.heat_output_w;
    }
    out.atmosphere = calculateAtmosphereTelemetry(state, config);
    out.power = calculatePowerTelemetry(state, config, solar_generation_kw, healthy_solar_generation_kw);
    out.thermal = calculateThermalTelemetry(state, config, total_crew_heat_w);
    out.eva = calculateEVATelemetry(state, config);
    out.communications = calculateCommunicationsTelemetry(state, config);
// 2. crew vitals from CrewPhysiologyModel
    out.crew_vitals = crew_vitals;
// 3. mission data from Simulation
    out.mission = mission_telemetry;
    return out;
}
