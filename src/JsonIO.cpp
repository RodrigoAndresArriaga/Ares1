#include "JsonIO.hpp"

#include <cmath>
#include <fstream>
#include <initializer_list>
#include <sstream>
#include <unordered_set>

#include <nlohmann/json.hpp>

using json = nlohmann::json;

namespace {

// set error and return false
bool fail(string& error, const string& message){
    error = message;
    return false;
}

string pathJoin(const string& base, const string& key){
    if(base.empty()){
        return key;
    }
    return base + "." + key;
}

string pathIndex(const string& base, size_t index){
    return base + "[" + std::to_string(index) + "]";
}

bool rejectUnknownKeys(
    const json& obj,
    std::initializer_list<const char*> allowed,
    const string& path,
    string& error){
    unordered_set<string> allow;
    for(const char* key : allowed){
        allow.insert(key);
    }
    for(auto it = obj.begin(); it != obj.end(); ++it){
        if(allow.find(it.key()) == allow.end()){
            return fail(error, "unknown key at " + pathJoin(path, it.key()));
        }
    }
    return true;
}

bool requireKeys(
    const json& obj,
    std::initializer_list<const char*> required,
    const string& path,
    string& error){
    for(const char* key : required){
        if(!obj.contains(key)){
            return fail(error, "missing key at " + pathJoin(path, key));
        }
    }
    return true;
}

bool requireObject(const json& value, const string& path, string& error){
    if(!value.is_object()){
        return fail(error, "expected object at " + path);
    }
    return true;
}

bool requireArray(const json& value, const string& path, string& error){
    if(!value.is_array()){
        return fail(error, "expected array at " + path);
    }
    return true;
}

bool readString(const json& obj, const string& key, const string& path, string& out, string& error){
    const string key_path = pathJoin(path, key);
    if(!obj.contains(key)){
        return fail(error, "missing key at " + key_path);
    }
    if(!obj.at(key).is_string()){
        return fail(error, "expected string at " + key_path);
    }
    out = obj.at(key).get<string>();
    return true;
}

bool readBool(const json& obj, const string& key, const string& path, bool& out, string& error){
    const string key_path = pathJoin(path, key);
    if(!obj.contains(key)){
        return fail(error, "missing key at " + key_path);
    }
    if(!obj.at(key).is_boolean()){
        return fail(error, "expected bool at " + key_path);
    }
    out = obj.at(key).get<bool>();
    return true;
}

bool readInt(const json& obj, const string& key, const string& path, int& out, string& error){
    const string key_path = pathJoin(path, key);
    if(!obj.contains(key)){
        return fail(error, "missing key at " + key_path);
    }
    const json& value = obj.at(key);
    if(!value.is_number_integer()){
        return fail(error, "expected integer at " + key_path);
    }
    out = value.get<int>();
    return true;
}

bool readDouble(const json& obj, const string& key, const string& path, double& out, string& error){
    const string key_path = pathJoin(path, key);
    if(!obj.contains(key)){
        return fail(error, "missing key at " + key_path);
    }
    const json& value = obj.at(key);
    if(!value.is_number()){
        return fail(error, "expected number at " + key_path);
    }
    out = value.get<double>();
    if(!std::isfinite(out)){
        return fail(error, "non-finite number at " + key_path);
    }
    return true;
}

bool readStringArray(
    const json& obj, const string& key, const string& path, vector<string>& out, string& error){
    const string key_path = pathJoin(path, key);
    if(!obj.contains(key)){
        return fail(error, "missing key at " + key_path);
    }
    if(!requireArray(obj.at(key), key_path, error)){
        return false;
    }
    out.clear();
    size_t index = 0;
    for(const json& item : obj.at(key)){
        if(!item.is_string()){
            return fail(error, "expected string at " + pathIndex(key_path, index));
        }
        out.push_back(item.get<string>());
        ++index;
    }
    return true;
}

bool parseCrewActivity(const string& text, CrewActivity& out, const string& path, string& error){
    if(text == "SLEEP"){ out = CrewActivity::Sleep; return true; }
    if(text == "RESTING"){ out = CrewActivity::Resting; return true; }
    if(text == "NOMINAL_WORK"){ out = CrewActivity::NominalWork; return true; }
    if(text == "HIGH_WORKLOAD"){ out = CrewActivity::HighWorkload; return true; }
    if(text == "EVA_PREP"){ out = CrewActivity::EVAPrep; return true; }
    if(text == "EVA_TRANSIT"){ out = CrewActivity::EVATransit; return true; }
    if(text == "EVA_WORK"){ out = CrewActivity::EVAWork; return true; }
    if(text == "RECOVERY"){ out = CrewActivity::Recovery; return true; }
    if(text == "INCAPACITATED"){ out = CrewActivity::Incapacitated; return true; }
    return fail(error, "unknown CrewActivity at " + path + ": " + text);
}

bool parseEVAStatus(const string& text, EVAStatus& out, const string& path, string& error){
    if(text == "IDLE"){ out = EVAStatus::Idle; return true; }
    if(text == "PREPARING"){ out = EVAStatus::Preparing; return true; }
    if(text == "EGRESS"){ out = EVAStatus::Egress; return true; }
    if(text == "WORKING"){ out = EVAStatus::Working; return true; }
    if(text == "INGRESS"){ out = EVAStatus::Ingress; return true; }
    if(text == "COMPLETE"){ out = EVAStatus::Complete; return true; }
    if(text == "ABORTED"){ out = EVAStatus::Aborted; return true; }
    return fail(error, "unknown EVAStatus at " + path + ": " + text);
}

bool parseSourceClassification(
    const string& text, SourceClassification& out, const string& path, string& error){
    if(text == "NASA_STANDARD"){ out = SourceClassification::NASAStandard; return true; }
    if(text == "NASA_REFERENCE"){ out = SourceClassification::NASAReference; return true; }
    if(text == "DERIVED_PHYSICS"){ out = SourceClassification::DerivedPhysics; return true; }
    if(text == "ARES_ASSUMPTION"){ out = SourceClassification::ARESAssumption; return true; }
    return fail(error, "unknown SourceClassification at " + path + ": " + text);
}

bool parseActionType(const string& text, ActionType& out, const string& path, string& error){
    if(text == "reduce_power_load"){ out = ActionType::ReducePowerLoad; return true; }
    if(text == "isolate_module"){ out = ActionType::IsolateModule; return true; }
    if(text == "oxygen_rationing"){ out = ActionType::OxygenRationing; return true; }
    if(text == "repair_solar_array"){ out = ActionType::RepairSolarArray; return true; }
    if(text == "delay_rover_use"){ out = ActionType::DelayRoverUse; return true; }
    if(text == "send_emergency_packet"){ out = ActionType::SendEmergencyPacket; return true; }
    return fail(error, "unknown action type at " + path + ": " + text);
}

string toString(MissionStatus value){
    switch(value){
        case MissionStatus::Nominal: return "NOMINAL";
        case MissionStatus::Warning: return "WARNING";
        case MissionStatus::Critical: return "CRITICAL";
        case MissionStatus::Stabilized: return "STABILIZED";
        case MissionStatus::Failure: return "FAILURE";
        case MissionStatus::Rejected: return "REJECTED";
    }
    return "NOMINAL";
}

string toString(OutcomeStatus value){
    switch(value){
        case OutcomeStatus::Stabilized: return "STABILIZED";
        case OutcomeStatus::Failure: return "FAILURE";
        case OutcomeStatus::Rejected: return "REJECTED";
    }
    return "FAILURE";
}

string toString(CrewActivity value){
    switch(value){
        case CrewActivity::Sleep: return "SLEEP";
        case CrewActivity::Resting: return "RESTING";
        case CrewActivity::NominalWork: return "NOMINAL_WORK";
        case CrewActivity::HighWorkload: return "HIGH_WORKLOAD";
        case CrewActivity::EVAPrep: return "EVA_PREP";
        case CrewActivity::EVATransit: return "EVA_TRANSIT";
        case CrewActivity::EVAWork: return "EVA_WORK";
        case CrewActivity::Recovery: return "RECOVERY";
        case CrewActivity::Incapacitated: return "INCAPACITATED";
    }
    return "NOMINAL_WORK";
}

string toString(CrewHealthStatus value){
    switch(value){
        case CrewHealthStatus::Nominal: return "NOMINAL";
        case CrewHealthStatus::ElevatedStress: return "ELEVATED_STRESS";
        case CrewHealthStatus::Impaired: return "IMPAIRED";
        case CrewHealthStatus::Critical: return "CRITICAL";
        case CrewHealthStatus::Incapacitated: return "INCAPACITATED";
    }
    return "NOMINAL";
}

string toString(CrewAlarmType value){
    switch(value){
        case CrewAlarmType::Hypoxia: return "HYPOXIA";
        case CrewAlarmType::Hypercapnia: return "HYPERCAPNIA";
        case CrewAlarmType::Pressure: return "PRESSURE";
        case CrewAlarmType::Tachycardia: return "TACHYCARDIA";
        case CrewAlarmType::Respiratory: return "RESPIRATORY";
        case CrewAlarmType::Thermal: return "THERMAL";
        case CrewAlarmType::Fatigue: return "FATIGUE";
        case CrewAlarmType::Performance: return "PERFORMANCE";
        case CrewAlarmType::EVAReturn: return "EVA_RETURN";
    }
    return "HYPOXIA";
}

string toString(ActionType value){
    switch(value){
        case ActionType::ReducePowerLoad: return "reduce_power_load";
        case ActionType::IsolateModule: return "isolate_module";
        case ActionType::OxygenRationing: return "oxygen_rationing";
        case ActionType::RepairSolarArray: return "repair_solar_array";
        case ActionType::DelayRoverUse: return "delay_rover_use";
        case ActionType::SendEmergencyPacket: return "send_emergency_packet";
        case ActionType::Unknown: return "unknown";
    }
    return "unknown";
}

string toString(ActionExecutionStatus value){
    switch(value){
        case ActionExecutionStatus::Pending: return "PENDING";
        case ActionExecutionStatus::Active: return "ACTIVE";
        case ActionExecutionStatus::Complete: return "COMPLETE";
        case ActionExecutionStatus::Failed: return "FAILED";
        case ActionExecutionStatus::Aborted: return "ABORTED";
    }
    return "PENDING";
}

string toString(ConstraintSeverity value){
    switch(value){
        case ConstraintSeverity::Info: return "INFO";
        case ConstraintSeverity::Warning: return "WARNING";
        case ConstraintSeverity::Critical: return "CRITICAL";
        case ConstraintSeverity::Failure: return "FAILURE";
    }
    return "INFO";
}

bool parseParameterSource(const json& obj, const string& path, ParameterSource& out, string& error){
    if(!requireObject(obj, path, error)){
        return false;
    }
    if(!rejectUnknownKeys(obj, {"parameter_name", "classification", "source_label", "note"}, path, error)){
        return false;
    }
    if(!requireKeys(obj, {"parameter_name", "classification", "source_label", "note"}, path, error)){
        return false;
    }
    string classification;
    if(!readString(obj, "parameter_name", path, out.parameter_name, error) ||
       !readString(obj, "classification", path, classification, error) ||
       !readString(obj, "source_label", path, out.source_label, error) ||
       !readString(obj, "note", path, out.note, error)){
        return false;
    }
    return parseSourceClassification(classification, out.classification, pathJoin(path, "classification"), error);
}

bool parseCommunicationWindow(
    const json& obj, const string& path, CommunicationWindow& out, string& error){
    if(!requireObject(obj, path, error)){
        return false;
    }
    if(!rejectUnknownKeys(obj, {"open_min", "close_min"}, path, error)){
        return false;
    }
    if(!requireKeys(obj, {"open_min", "close_min"}, path, error)){
        return false;
    }
    return readInt(obj, "open_min", path, out.open_min, error) &&
           readInt(obj, "close_min", path, out.close_min, error);
}

bool parseActivityProfile(
    const json& obj, const string& path, ActivityMetabolicProfile& out, string& error){
    if(!requireObject(obj, path, error)){
        return false;
    }
    if(!rejectUnknownKeys(
           obj, {"activity", "oxygen_g_min", "co2_g_min", "heat_w", "activity_load"}, path, error)){
        return false;
    }
    if(!requireKeys(
           obj, {"activity", "oxygen_g_min", "co2_g_min", "heat_w", "activity_load"}, path, error)){
        return false;
    }
    string activity;
    if(!readString(obj, "activity", path, activity, error) ||
       !readDouble(obj, "oxygen_g_min", path, out.oxygen_g_min, error) ||
       !readDouble(obj, "co2_g_min", path, out.co2_g_min, error) ||
       !readDouble(obj, "heat_w", path, out.heat_w, error) ||
       !readDouble(obj, "activity_load", path, out.activity_load, error)){
        return false;
    }
    return parseCrewActivity(activity, out.activity, pathJoin(path, "activity"), error);
}

bool parseHabitat(const json& obj, const string& path, HabitatConfig& out, string& error){
    if(!requireObject(obj, path, error)){
        return false;
    }
    if(!rejectUnknownKeys(
           obj,
           {"initial_habitable_volume_m3", "isolated_habitable_volume_m3", "nominal_temperature_c",
            "initial_relative_humidity_percent", "effective_thermal_capacitance_kj_c"},
           path,
           error)){
        return false;
    }
    if(!requireKeys(
           obj,
           {"initial_habitable_volume_m3", "isolated_habitable_volume_m3", "nominal_temperature_c",
            "initial_relative_humidity_percent", "effective_thermal_capacitance_kj_c"},
           path,
           error)){
        return false;
    }
    return readDouble(obj, "initial_habitable_volume_m3", path, out.initial_habitable_volume_m3, error) &&
           readDouble(obj, "isolated_habitable_volume_m3", path, out.isolated_habitable_volume_m3, error) &&
           readDouble(obj, "nominal_temperature_c", path, out.nominal_temperature_c, error) &&
           readDouble(obj, "initial_relative_humidity_percent", path, out.initial_relative_humidity_percent, error) &&
           readDouble(obj, "effective_thermal_capacitance_kj_c", path, out.effective_thermal_capacitance_kj_c, error);
}

bool parseAtmosphere(const json& obj, const string& path, AtmosphereConfig& out, string& error){
    if(!requireObject(obj, path, error)){
        return false;
    }
    const std::initializer_list<const char*> keys = {
        "initial_oxygen_mass_kg", "initial_inert_gas_mass_kg", "initial_co2_mass_kg",
        "scrubber_capacity_g_min", "initial_scrubber_efficiency",
        "pressure_warning_low_kpa", "pressure_failure_low_kpa", "pressure_high_limit_kpa",
        "inspired_o2_nominal_mmhg", "inspired_o2_warning_mmhg", "inspired_o2_failure_mmhg",
        "co2_one_hour_limit_mmhg", "minimum_inert_fraction"};
    if(!rejectUnknownKeys(obj, keys, path, error) || !requireKeys(obj, keys, path, error)){
        return false;
    }
    return readDouble(obj, "initial_oxygen_mass_kg", path, out.initial_oxygen_mass_kg, error) &&
           readDouble(obj, "initial_inert_gas_mass_kg", path, out.initial_inert_gas_mass_kg, error) &&
           readDouble(obj, "initial_co2_mass_kg", path, out.initial_co2_mass_kg, error) &&
           readDouble(obj, "scrubber_capacity_g_min", path, out.scrubber_capacity_g_min, error) &&
           readDouble(obj, "initial_scrubber_efficiency", path, out.initial_scrubber_efficiency, error) &&
           readDouble(obj, "pressure_warning_low_kpa", path, out.pressure_warning_low_kpa, error) &&
           readDouble(obj, "pressure_failure_low_kpa", path, out.pressure_failure_low_kpa, error) &&
           readDouble(obj, "pressure_high_limit_kpa", path, out.pressure_high_limit_kpa, error) &&
           readDouble(obj, "inspired_o2_nominal_mmhg", path, out.inspired_o2_nominal_mmhg, error) &&
           readDouble(obj, "inspired_o2_warning_mmhg", path, out.inspired_o2_warning_mmhg, error) &&
           readDouble(obj, "inspired_o2_failure_mmhg", path, out.inspired_o2_failure_mmhg, error) &&
           readDouble(obj, "co2_one_hour_limit_mmhg", path, out.co2_one_hour_limit_mmhg, error) &&
           readDouble(obj, "minimum_inert_fraction", path, out.minimum_inert_fraction, error);
}

bool parsePower(const json& obj, const string& path, PowerConfig& out, string& error){
    if(!requireObject(obj, path, error)){
        return false;
    }
    const std::initializer_list<const char*> keys = {
        "initial_battery_energy_kwh", "battery_capacity_kwh", "battery_reserve_percent",
        "charge_efficiency", "discharge_efficiency", "essential_load_kw", "discretionary_load_kw",
        "thermal_control_load_kw", "eva_support_load_kw", "communications_load_kw"};
    if(!rejectUnknownKeys(obj, keys, path, error) || !requireKeys(obj, keys, path, error)){
        return false;
    }
    return readDouble(obj, "initial_battery_energy_kwh", path, out.initial_battery_energy_kwh, error) &&
           readDouble(obj, "battery_capacity_kwh", path, out.battery_capacity_kwh, error) &&
           readDouble(obj, "battery_reserve_percent", path, out.battery_reserve_percent, error) &&
           readDouble(obj, "charge_efficiency", path, out.charge_efficiency, error) &&
           readDouble(obj, "discharge_efficiency", path, out.discharge_efficiency, error) &&
           readDouble(obj, "essential_load_kw", path, out.essential_load_kw, error) &&
           readDouble(obj, "discretionary_load_kw", path, out.discretionary_load_kw, error) &&
           readDouble(obj, "thermal_control_load_kw", path, out.thermal_control_load_kw, error) &&
           readDouble(obj, "eva_support_load_kw", path, out.eva_support_load_kw, error) &&
           readDouble(obj, "communications_load_kw", path, out.communications_load_kw, error);
}

bool parseSolar(const json& obj, const string& path, SolarConfig& out, string& error){
    if(!requireObject(obj, path, error)){
        return false;
    }
    const std::initializer_list<const char*> keys = {
        "array_area_m2", "cell_efficiency", "mars_sun_distance_au", "initial_incidence_angle_deg",
        "initial_atmospheric_transmission", "initial_deposited_dust_factor"};
    if(!rejectUnknownKeys(obj, keys, path, error) || !requireKeys(obj, keys, path, error)){
        return false;
    }
    return readDouble(obj, "array_area_m2", path, out.array_area_m2, error) &&
           readDouble(obj, "cell_efficiency", path, out.cell_efficiency, error) &&
           readDouble(obj, "mars_sun_distance_au", path, out.mars_sun_distance_au, error) &&
           readDouble(obj, "initial_incidence_angle_deg", path, out.initial_incidence_angle_deg, error) &&
           readDouble(obj, "initial_atmospheric_transmission", path, out.initial_atmospheric_transmission, error) &&
           readDouble(obj, "initial_deposited_dust_factor", path, out.initial_deposited_dust_factor, error);
}

bool parseThermal(const json& obj, const string& path, ThermalConfig& out, string& error){
    if(!requireObject(obj, path, error)){
        return false;
    }
    const std::initializer_list<const char*> keys = {
        "initial_equipment_heat_w", "initial_environmental_heat_w", "initial_heater_heat_w",
        "tcs_rejection_capacity_w", "comfort_low_c", "comfort_high_c", "critical_low_c",
        "critical_high_c", "humidity_low_percent", "humidity_high_percent"};
    if(!rejectUnknownKeys(obj, keys, path, error) || !requireKeys(obj, keys, path, error)){
        return false;
    }
    return readDouble(obj, "initial_equipment_heat_w", path, out.initial_equipment_heat_w, error) &&
           readDouble(obj, "initial_environmental_heat_w", path, out.initial_environmental_heat_w, error) &&
           readDouble(obj, "initial_heater_heat_w", path, out.initial_heater_heat_w, error) &&
           readDouble(obj, "tcs_rejection_capacity_w", path, out.tcs_rejection_capacity_w, error) &&
           readDouble(obj, "comfort_low_c", path, out.comfort_low_c, error) &&
           readDouble(obj, "comfort_high_c", path, out.comfort_high_c, error) &&
           readDouble(obj, "critical_low_c", path, out.critical_low_c, error) &&
           readDouble(obj, "critical_high_c", path, out.critical_high_c, error) &&
           readDouble(obj, "humidity_low_percent", path, out.humidity_low_percent, error) &&
           readDouble(obj, "humidity_high_percent", path, out.humidity_high_percent, error);
}

bool parseEVA(const json& obj, const string& path, EVAConfig& out, string& error){
    if(!requireObject(obj, path, error)){
        return false;
    }
    const std::initializer_list<const char*> keys = {
        "available", "preparation_min", "egress_min", "repair_work_min", "ingress_min",
        "reserve_min", "maximum_duration_min", "rover_required", "rover_minimum_reserve_percent"};
    if(!rejectUnknownKeys(obj, keys, path, error) || !requireKeys(obj, keys, path, error)){
        return false;
    }
    return readBool(obj, "available", path, out.available, error) &&
           readInt(obj, "preparation_min", path, out.preparation_min, error) &&
           readInt(obj, "egress_min", path, out.egress_min, error) &&
           readInt(obj, "repair_work_min", path, out.repair_work_min, error) &&
           readInt(obj, "ingress_min", path, out.ingress_min, error) &&
           readInt(obj, "reserve_min", path, out.reserve_min, error) &&
           readInt(obj, "maximum_duration_min", path, out.maximum_duration_min, error) &&
           readBool(obj, "rover_required", path, out.rover_required, error) &&
           readDouble(obj, "rover_minimum_reserve_percent", path, out.rover_minimum_reserve_percent, error);
}

bool parseCommunications(
    const json& obj, const string& path, CommunicationsConfig& out, string& error){
    if(!requireObject(obj, path, error)){
        return false;
    }
    if(!rejectUnknownKeys(
           obj, {"windows", "transmission_duration_min", "transmission_power_kw"}, path, error)){
        return false;
    }
    if(!requireKeys(
           obj, {"windows", "transmission_duration_min", "transmission_power_kw"}, path, error)){
        return false;
    }
    if(!requireArray(obj.at("windows"), pathJoin(path, "windows"), error)){
        return false;
    }
    out.windows.clear();
    size_t index = 0;
    for(const json& item : obj.at("windows")){
        CommunicationWindow window{};
        if(!parseCommunicationWindow(item, pathIndex(pathJoin(path, "windows"), index), window, error)){
            return false;
        }
        out.windows.push_back(window);
        ++index;
    }
    return readInt(obj, "transmission_duration_min", path, out.transmission_duration_min, error) &&
           readDouble(obj, "transmission_power_kw", path, out.transmission_power_kw, error);
}

bool parseFault(const json& obj, const string& path, FaultConfig& out, string& error){
    if(!requireObject(obj, path, error)){
        return false;
    }
    const std::initializer_list<const char*> keys = {
        "failure_type", "leak_module", "total_gas_leak_kg_hr", "isolation_leak_multiplier",
        "solar_fault_factor", "repaired_solar_fault_factor", "stabilized_leak_kg_hr"};
    if(!rejectUnknownKeys(obj, keys, path, error) || !requireKeys(obj, keys, path, error)){
        return false;
    }
    return readString(obj, "failure_type", path, out.failure_type, error) &&
           readString(obj, "leak_module", path, out.leak_module, error) &&
           readDouble(obj, "total_gas_leak_kg_hr", path, out.total_gas_leak_kg_hr, error) &&
           readDouble(obj, "isolation_leak_multiplier", path, out.isolation_leak_multiplier, error) &&
           readDouble(obj, "solar_fault_factor", path, out.solar_fault_factor, error) &&
           readDouble(obj, "repaired_solar_fault_factor", path, out.repaired_solar_fault_factor, error) &&
           readDouble(obj, "stabilized_leak_kg_hr", path, out.stabilized_leak_kg_hr, error);
}

bool parseVitalResponse(const json& obj, const string& path, VitalResponseConfig& out, string& error){
    if(!requireObject(obj, path, error)){
        return false;
    }
    const std::initializer_list<const char*> keys = {
        "activity_profiles",
        "hypoxia_accumulation_rate", "co2_accumulation_rate", "thermal_accumulation_rate",
        "hypoxia_recovery_rate", "co2_recovery_rate", "thermal_recovery_rate",
        "fatigue_work_rate", "fatigue_eva_rate", "fatigue_recovery_rate",
        "hr_activity_gain", "hr_hypoxia_gain", "hr_co2_gain", "hr_thermal_gain", "hr_fatigue_gain",
        "hr_min_bpm", "hr_max_bpm",
        "rr_activity_gain", "rr_hypoxia_gain", "rr_co2_gain", "rr_thermal_gain",
        "rr_min_bpm", "rr_max_bpm",
        "spo2_hypoxia_gain", "spo2_pressure_gain", "spo2_activity_gain", "spo2_exposure_gain",
        "spo2_min_percent", "spo2_max_percent",
        "core_temp_environment_gain", "core_temp_activity_gain", "core_temp_time_constant_min",
        "core_temp_min_c", "core_temp_max_c",
        "cognitive_hypoxia_weight", "cognitive_co2_weight", "cognitive_thermal_weight",
        "cognitive_fatigue_weight",
        "physical_hypoxia_weight", "physical_co2_weight", "physical_thermal_weight",
        "physical_fatigue_weight",
        "spo2_warning_percent", "spo2_critical_percent", "heart_rate_warning_bpm",
        "respiratory_rate_warning_bpm", "core_temp_low_c", "core_temp_high_c",
        "fatigue_warning_fraction", "performance_abort_fraction"};
    if(!rejectUnknownKeys(obj, keys, path, error) || !requireKeys(obj, keys, path, error)){
        return false;
    }
    if(!requireArray(obj.at("activity_profiles"), pathJoin(path, "activity_profiles"), error)){
        return false;
    }
    out.activity_profiles.clear();
    size_t index = 0;
    for(const json& item : obj.at("activity_profiles")){
        ActivityMetabolicProfile profile{};
        if(!parseActivityProfile(
               item, pathIndex(pathJoin(path, "activity_profiles"), index), profile, error)){
            return false;
        }
        out.activity_profiles.push_back(profile);
        ++index;
    }
    return readDouble(obj, "hypoxia_accumulation_rate", path, out.hypoxia_accumulation_rate, error) &&
           readDouble(obj, "co2_accumulation_rate", path, out.co2_accumulation_rate, error) &&
           readDouble(obj, "thermal_accumulation_rate", path, out.thermal_accumulation_rate, error) &&
           readDouble(obj, "hypoxia_recovery_rate", path, out.hypoxia_recovery_rate, error) &&
           readDouble(obj, "co2_recovery_rate", path, out.co2_recovery_rate, error) &&
           readDouble(obj, "thermal_recovery_rate", path, out.thermal_recovery_rate, error) &&
           readDouble(obj, "fatigue_work_rate", path, out.fatigue_work_rate, error) &&
           readDouble(obj, "fatigue_eva_rate", path, out.fatigue_eva_rate, error) &&
           readDouble(obj, "fatigue_recovery_rate", path, out.fatigue_recovery_rate, error) &&
           readDouble(obj, "hr_activity_gain", path, out.hr_activity_gain, error) &&
           readDouble(obj, "hr_hypoxia_gain", path, out.hr_hypoxia_gain, error) &&
           readDouble(obj, "hr_co2_gain", path, out.hr_co2_gain, error) &&
           readDouble(obj, "hr_thermal_gain", path, out.hr_thermal_gain, error) &&
           readDouble(obj, "hr_fatigue_gain", path, out.hr_fatigue_gain, error) &&
           readDouble(obj, "hr_min_bpm", path, out.hr_min_bpm, error) &&
           readDouble(obj, "hr_max_bpm", path, out.hr_max_bpm, error) &&
           readDouble(obj, "rr_activity_gain", path, out.rr_activity_gain, error) &&
           readDouble(obj, "rr_hypoxia_gain", path, out.rr_hypoxia_gain, error) &&
           readDouble(obj, "rr_co2_gain", path, out.rr_co2_gain, error) &&
           readDouble(obj, "rr_thermal_gain", path, out.rr_thermal_gain, error) &&
           readDouble(obj, "rr_min_bpm", path, out.rr_min_bpm, error) &&
           readDouble(obj, "rr_max_bpm", path, out.rr_max_bpm, error) &&
           readDouble(obj, "spo2_hypoxia_gain", path, out.spo2_hypoxia_gain, error) &&
           readDouble(obj, "spo2_pressure_gain", path, out.spo2_pressure_gain, error) &&
           readDouble(obj, "spo2_activity_gain", path, out.spo2_activity_gain, error) &&
           readDouble(obj, "spo2_exposure_gain", path, out.spo2_exposure_gain, error) &&
           readDouble(obj, "spo2_min_percent", path, out.spo2_min_percent, error) &&
           readDouble(obj, "spo2_max_percent", path, out.spo2_max_percent, error) &&
           readDouble(obj, "core_temp_environment_gain", path, out.core_temp_environment_gain, error) &&
           readDouble(obj, "core_temp_activity_gain", path, out.core_temp_activity_gain, error) &&
           readDouble(obj, "core_temp_time_constant_min", path, out.core_temp_time_constant_min, error) &&
           readDouble(obj, "core_temp_min_c", path, out.core_temp_min_c, error) &&
           readDouble(obj, "core_temp_max_c", path, out.core_temp_max_c, error) &&
           readDouble(obj, "cognitive_hypoxia_weight", path, out.cognitive_hypoxia_weight, error) &&
           readDouble(obj, "cognitive_co2_weight", path, out.cognitive_co2_weight, error) &&
           readDouble(obj, "cognitive_thermal_weight", path, out.cognitive_thermal_weight, error) &&
           readDouble(obj, "cognitive_fatigue_weight", path, out.cognitive_fatigue_weight, error) &&
           readDouble(obj, "physical_hypoxia_weight", path, out.physical_hypoxia_weight, error) &&
           readDouble(obj, "physical_co2_weight", path, out.physical_co2_weight, error) &&
           readDouble(obj, "physical_thermal_weight", path, out.physical_thermal_weight, error) &&
           readDouble(obj, "physical_fatigue_weight", path, out.physical_fatigue_weight, error) &&
           readDouble(obj, "spo2_warning_percent", path, out.spo2_warning_percent, error) &&
           readDouble(obj, "spo2_critical_percent", path, out.spo2_critical_percent, error) &&
           readDouble(obj, "heart_rate_warning_bpm", path, out.heart_rate_warning_bpm, error) &&
           readDouble(obj, "respiratory_rate_warning_bpm", path, out.respiratory_rate_warning_bpm, error) &&
           readDouble(obj, "core_temp_low_c", path, out.core_temp_low_c, error) &&
           readDouble(obj, "core_temp_high_c", path, out.core_temp_high_c, error) &&
           readDouble(obj, "fatigue_warning_fraction", path, out.fatigue_warning_fraction, error) &&
           readDouble(obj, "performance_abort_fraction", path, out.performance_abort_fraction, error);
}

bool parseCrewMember(const json& obj, const string& path, CrewMemberConfig& out, string& error){
    if(!requireObject(obj, path, error)){
        return false;
    }
    const std::initializer_list<const char*> keys = {
        "crew_id", "display_name", "assigned_role", "body_mass_kg",
        "baseline_heart_rate_bpm", "baseline_respiratory_rate_bpm", "baseline_spo2_percent",
        "baseline_core_temperature_c", "fitness_factor", "hypoxia_sensitivity", "co2_sensitivity",
        "thermal_sensitivity", "fatigue_recovery_factor", "eva_qualified",
        "initial_activity", "initial_location_module", "initial_eva_status",
        "initial_oxygen_rationing_active"};
    if(!rejectUnknownKeys(obj, keys, path, error) || !requireKeys(obj, keys, path, error)){
        return false;
    }
    string activity;
    string eva_status;
    if(!readString(obj, "crew_id", path, out.crew_id, error) ||
       !readString(obj, "display_name", path, out.display_name, error) ||
       !readString(obj, "assigned_role", path, out.assigned_role, error) ||
       !readDouble(obj, "body_mass_kg", path, out.body_mass_kg, error) ||
       !readDouble(obj, "baseline_heart_rate_bpm", path, out.baseline_heart_rate_bpm, error) ||
       !readDouble(obj, "baseline_respiratory_rate_bpm", path, out.baseline_respiratory_rate_bpm, error) ||
       !readDouble(obj, "baseline_spo2_percent", path, out.baseline_spo2_percent, error) ||
       !readDouble(obj, "baseline_core_temperature_c", path, out.baseline_core_temperature_c, error) ||
       !readDouble(obj, "fitness_factor", path, out.fitness_factor, error) ||
       !readDouble(obj, "hypoxia_sensitivity", path, out.hypoxia_sensitivity, error) ||
       !readDouble(obj, "co2_sensitivity", path, out.co2_sensitivity, error) ||
       !readDouble(obj, "thermal_sensitivity", path, out.thermal_sensitivity, error) ||
       !readDouble(obj, "fatigue_recovery_factor", path, out.fatigue_recovery_factor, error) ||
       !readBool(obj, "eva_qualified", path, out.eva_qualified, error) ||
       !readString(obj, "initial_activity", path, activity, error) ||
       !readString(obj, "initial_location_module", path, out.initial_location_module, error) ||
       !readString(obj, "initial_eva_status", path, eva_status, error) ||
       !readBool(obj, "initial_oxygen_rationing_active", path, out.initial_oxygen_rationing_active, error)){
        return false;
    }
    return parseCrewActivity(activity, out.initial_activity, pathJoin(path, "initial_activity"), error) &&
           parseEVAStatus(eva_status, out.initial_eva_status, pathJoin(path, "initial_eva_status"), error);
}

bool parseOptionalDouble(
    const json& obj, const string& key, const string& path, std::optional<double>& out, string& error){
    if(!obj.contains(key) || obj.at(key).is_null()){
        out = std::nullopt;
        return true;
    }
    double value = 0.0;
    if(!readDouble(obj, key, path, value, error)){
        return false;
    }
    out = value;
    return true;
}

bool parseOptionalInt(
    const json& obj, const string& key, const string& path, std::optional<int>& out, string& error){
    if(!obj.contains(key) || obj.at(key).is_null()){
        out = std::nullopt;
        return true;
    }
    int value = 0;
    if(!readInt(obj, key, path, value, error)){
        return false;
    }
    out = value;
    return true;
}

bool parseOptionalString(
    const json& obj, const string& key, const string& path, std::optional<string>& out, string& error){
    if(!obj.contains(key) || obj.at(key).is_null()){
        out = std::nullopt;
        return true;
    }
    string value;
    if(!readString(obj, key, path, value, error)){
        return false;
    }
    out = value;
    return true;
}

bool parseStringArrayOptional(
    const json& obj, const string& key, const string& path, vector<string>& out, string& error){
    if(!obj.contains(key)){
        out.clear();
        return true;
    }
    return readStringArray(obj, key, path, out, error);
}

bool parseAction(const json& obj, const string& path, Action& out, string& error){
    if(!requireObject(obj, path, error)){
        return false;
    }
    if(!rejectUnknownKeys(
           obj,
           {"type", "start_min", "percent", "module", "level", "duration_min", "hours", "crew_id",
            "eva_crew_id", "assigned_crew_ids", "target_crew_ids", "load_groups"},
           path,
           error)){
        return false;
    }
    if(!requireKeys(obj, {"type", "start_min"}, path, error)){
        return false;
    }
    string type_text;
    if(!readString(obj, "type", path, type_text, error) ||
       !readInt(obj, "start_min", path, out.start_min, error)){
        return false;
    }
    out.type_raw = type_text;
    if(!parseActionType(type_text, out.type, pathJoin(path, "type"), error)){
        return false;
    }
    if(!parseOptionalDouble(obj, "percent", path, out.percent, error) ||
       !parseOptionalString(obj, "module", path, out.module, error) ||
       !parseOptionalString(obj, "level", path, out.level, error) ||
       !parseOptionalInt(obj, "duration_min", path, out.duration_min, error) ||
       !parseOptionalDouble(obj, "hours", path, out.hours, error) ||
       !parseOptionalString(obj, "crew_id", path, out.crew_id, error) ||
       !parseOptionalString(obj, "eva_crew_id", path, out.eva_crew_id, error) ||
       !parseStringArrayOptional(obj, "assigned_crew_ids", path, out.assigned_crew_ids, error) ||
       !parseStringArrayOptional(obj, "target_crew_ids", path, out.target_crew_ids, error) ||
       !parseStringArrayOptional(obj, "load_groups", path, out.load_groups, error)){
        return false;
    }
    return true;
}

bool parseScenarioJson(const json& root, ScenarioConfig& out, string& error){
    if(!requireObject(root, "", error)){
        return false;
    }
    const std::initializer_list<const char*> keys = {
        "scenario_id", "name", "time_step_s", "maximum_duration_min", "stabilization_hold_min",
        "habitat", "atmosphere", "power", "solar", "thermal", "eva", "communications", "fault",
        "vital_response", "crew_roster", "parameter_sources"};
    if(!rejectUnknownKeys(root, keys, "", error) || !requireKeys(root, keys, "", error)){
        return false;
    }
    if(!readString(root, "scenario_id", "", out.scenario_id, error) ||
       !readString(root, "name", "", out.name, error) ||
       !readInt(root, "time_step_s", "", out.time_step_s, error) ||
       !readInt(root, "maximum_duration_min", "", out.maximum_duration_min, error) ||
       !readInt(root, "stabilization_hold_min", "", out.stabilization_hold_min, error) ||
       !parseHabitat(root.at("habitat"), "habitat", out.habitat, error) ||
       !parseAtmosphere(root.at("atmosphere"), "atmosphere", out.atmosphere, error) ||
       !parsePower(root.at("power"), "power", out.power, error) ||
       !parseSolar(root.at("solar"), "solar", out.solar, error) ||
       !parseThermal(root.at("thermal"), "thermal", out.thermal, error) ||
       !parseEVA(root.at("eva"), "eva", out.eva, error) ||
       !parseCommunications(root.at("communications"), "communications", out.communications, error) ||
       !parseFault(root.at("fault"), "fault", out.fault, error) ||
       !parseVitalResponse(root.at("vital_response"), "vital_response", out.vital_response, error)){
        return false;
    }
    if(!requireArray(root.at("crew_roster"), "crew_roster", error)){
        return false;
    }
    out.crew_roster.clear();
    size_t crew_index = 0;
    for(const json& item : root.at("crew_roster")){
        CrewMemberConfig crew{};
        if(!parseCrewMember(item, pathIndex("crew_roster", crew_index), crew, error)){
            return false;
        }
        out.crew_roster.push_back(crew);
        ++crew_index;
    }
    if(!requireArray(root.at("parameter_sources"), "parameter_sources", error)){
        return false;
    }
    out.parameter_sources.clear();
    size_t source_index = 0;
    for(const json& item : root.at("parameter_sources")){
        ParameterSource source{};
        if(!parseParameterSource(item, pathIndex("parameter_sources", source_index), source, error)){
            return false;
        }
        out.parameter_sources.push_back(source);
        ++source_index;
    }
    return true;
}

bool parsePlanJson(const json& root, Plan& out, string& error){
    if(!requireObject(root, "", error)){
        return false;
    }
    const std::initializer_list<const char*> keys = {
        "plan_id", "summary", "actions", "rationale", "expected_risk", "constraints_checked"};
    if(!rejectUnknownKeys(root, keys, "", error) || !requireKeys(root, keys, "", error)){
        return false;
    }
    if(!readString(root, "plan_id", "", out.plan_id, error) ||
       !readString(root, "summary", "", out.summary, error) ||
       !readString(root, "rationale", "", out.rationale, error) ||
       !readString(root, "expected_risk", "", out.expected_risk, error) ||
       !readStringArray(root, "constraints_checked", "", out.constraints_checked, error)){
        return false;
    }
    if(!requireArray(root.at("actions"), "actions", error)){
        return false;
    }
    out.actions.clear();
    size_t index = 0;
    for(const json& item : root.at("actions")){
        Action action{};
        if(!parseAction(item, pathIndex("actions", index), action, error)){
            return false;
        }
        out.actions.push_back(action);
        ++index;
    }
    return true;
}

json finiteOrZero(double value){
    if(!std::isfinite(value)){
        return 0.0;
    }
    return value;
}

json serializeOptionalInt(const std::optional<int>& value){
    if(!value.has_value()){
        return nullptr;
    }
    return *value;
}

json serializeOptionalString(const std::optional<string>& value){
    if(!value.has_value()){
        return nullptr;
    }
    return *value;
}

json serializeEvent(const TimelineEvent& event){
    json out = json::object();
    out["time_min"] = event.time_min;
    out["event_type"] = event.event_type;
    out["message"] = event.message;
    out["severity"] = toString(event.severity);
    return out;
}

json serializeActiveAction(const ActiveActionState& action){
    json out = json::object();
    out["action_index"] = action.action_index;
    out["type"] = toString(action.type);
    out["status"] = toString(action.status);
    out["actual_start_min"] = serializeOptionalInt(action.actual_start_min);
    out["elapsed_min"] = action.elapsed_min;
    out["progress_fraction"] = finiteOrZero(action.progress_fraction);
    out["assigned_crew_id"] = serializeOptionalString(action.assigned_crew_id);
    out["eva_crew_id"] = serializeOptionalString(action.eva_crew_id);
    out["assigned_crew_ids"] = action.assigned_crew_ids;
    out["failure_reason"] = action.failure_reason;
    return out;
}

json serializeCrew(const CrewVitalsTelemetry& crew){
    json alarms = json::array();
    for(CrewAlarmType alarm : crew.active_alarms){
        alarms.push_back(toString(alarm));
    }
    json out = json::object();
    out["crew_id"] = crew.crew_id;
    out["display_name"] = crew.display_name;
    out["activity"] = toString(crew.activity);
    out["heart_rate_bpm"] = finiteOrZero(crew.heart_rate_bpm);
    out["respiratory_rate_bpm"] = finiteOrZero(crew.respiratory_rate_bpm);
    out["spo2_percent"] = finiteOrZero(crew.spo2_percent);
    out["core_temperature_c"] = finiteOrZero(crew.core_temperature_c);
    out["fatigue_percent"] = finiteOrZero(crew.fatigue_percent);
    out["cognitive_performance_percent"] = finiteOrZero(crew.cognitive_performance_percent);
    out["physical_performance_percent"] = finiteOrZero(crew.physical_performance_percent);
    out["health_status"] = toString(crew.health_status);
    out["alarms"] = alarms;
    return out;
}

json serializeHabitat(const DerivedTelemetry& telemetry){
    json out = json::object();
    out["cabin_pressure_kpa"] = finiteOrZero(telemetry.atmosphere.cabin_pressure_kpa);
    out["inspired_oxygen_mmhg"] = finiteOrZero(telemetry.atmosphere.inspired_oxygen_mmhg);
    out["co2_one_hour_avg_mmhg"] = finiteOrZero(telemetry.atmosphere.co2_one_hour_avg_mmhg);
    out["oxygen_hours_remaining"] = finiteOrZero(telemetry.atmosphere.oxygen_hours_remaining);
    out["battery_soc_percent"] = finiteOrZero(telemetry.power.battery_soc_percent);
    out["solar_generation_percent"] = finiteOrZero(telemetry.power.solar_generation_percent);
    out["power_margin_kw"] = finiteOrZero(telemetry.power.power_margin_kw);
    out["cabin_temperature_c"] = finiteOrZero(telemetry.thermal.cabin_temperature_c);
    out["temperature_margin_c"] = finiteOrZero(telemetry.thermal.temperature_margin_c);
    out["eva_safe_return_margin_min"] = finiteOrZero(telemetry.eva.eva_safe_return_margin_min);
    out["mission_status"] = toString(telemetry.mission.mission_status);
    return out;
}

json serializeSample(const TelemetrySample& sample){
    json crew = json::array();
    for(const CrewVitalsTelemetry& member : sample.telemetry.crew_vitals){
        crew.push_back(serializeCrew(member));
    }
    json events = json::array();
    for(const TimelineEvent& event : sample.events_this_step){
        events.push_back(serializeEvent(event));
    }
    json active_actions = json::array();
    for(const ActiveActionState& action : sample.active_actions){
        active_actions.push_back(serializeActiveAction(action));
    }
    json out = json::object();
    out["simulation_time_min"] = sample.simulation_time_min;
    out["habitat"] = serializeHabitat(sample.telemetry);
    out["crew"] = crew;
    out["events"] = events;
    out["active_actions"] = active_actions;
    out["has_warning"] = sample.has_warning;
    out["has_critical"] = sample.has_critical;
    return out;
}

json serializeMetrics(const SimulationMetrics& metrics){
    json out = json::object();
    out["minimum_inspired_o2_mmhg"] = finiteOrZero(metrics.minimum_inspired_o2_mmhg);
    out["minimum_cabin_pressure_kpa"] = finiteOrZero(metrics.minimum_cabin_pressure_kpa);
    out["maximum_co2_one_hour_avg_mmhg"] = finiteOrZero(metrics.maximum_co2_one_hour_avg_mmhg);
    out["minimum_battery_soc_percent"] = finiteOrZero(metrics.minimum_battery_soc_percent);
    out["minimum_power_margin_kw"] = finiteOrZero(metrics.minimum_power_margin_kw);
    out["minimum_temperature_margin_c"] = finiteOrZero(metrics.minimum_temperature_margin_c);
    out["minimum_eva_safe_return_margin_min"] = finiteOrZero(metrics.minimum_eva_safe_return_margin_min);
    out["minimum_crew_spo2_percent"] = finiteOrZero(metrics.minimum_crew_spo2_percent);
    out["maximum_crew_fatigue_percent"] = finiteOrZero(metrics.maximum_crew_fatigue_percent);
    out["eva_completed"] = metrics.eva_completed;
    out["communications_sent"] = metrics.communications_sent;
    out["time_to_stabilization_hr"] = finiteOrZero(metrics.time_to_stabilization_hr);
    return out;
}

json serializeResult(const SimulationResult& result){
    json timeline = json::array();
    for(const TimelineEvent& event : result.timeline){
        timeline.push_back(serializeEvent(event));
    }
    json telemetry_history = json::array();
    for(const TelemetrySample& sample : result.telemetry_history){
        telemetry_history.push_back(serializeSample(sample));
    }
    json out = json::object();
    out["scenario_id"] = result.scenario_id;
    out["plan_id"] = result.plan_id;
    out["outcome"] = toString(result.outcome);
    out["valid_plan"] = result.valid_plan;
    out["metrics"] = serializeMetrics(result.metrics);
    out["timeline"] = timeline;
    out["telemetry_history"] = telemetry_history;
    out["failure_reasons"] = result.failure_reasons;
    return out;
}

bool readFileText(const string& path, string& text, string& error){
    std::ifstream input(path);
    if(!input){
        return fail(error, "failed to open file: " + path);
    }
    std::ostringstream buffer;
    buffer << input.rdbuf();
    text = buffer.str();
    return true;
}

bool parseJsonText(const string& json_text, json& out, string& error){
    try{
        out = json::parse(json_text);
    }catch(const json::exception& ex){
        return fail(error, string("JSON parse error: ") + ex.what());
    }
    return true;
}

}

bool loadScenarioFromString(const string& json_text, ScenarioConfig& out, string& error){
    json root;
    if(!parseJsonText(json_text, root, error)){
        return false;
    }
    ScenarioConfig parsed{};
    if(!parseScenarioJson(root, parsed, error)){
        return false;
    }
    out = parsed;
    return true;
}

bool loadScenario(const string& path, ScenarioConfig& out, string& error){
    string text;
    if(!readFileText(path, text, error)){
        return false;
    }
    return loadScenarioFromString(text, out, error);
}

bool loadPlanFromString(const string& json_text, Plan& out, string& error){
    json root;
    if(!parseJsonText(json_text, root, error)){
        return false;
    }
    Plan parsed{};
    if(!parsePlanJson(root, parsed, error)){
        return false;
    }
    out = parsed;
    return true;
}

bool loadPlan(const string& path, Plan& out, string& error){
    string text;
    if(!readFileText(path, text, error)){
        return false;
    }
    return loadPlanFromString(text, out, error);
}

bool writeResultToString(const SimulationResult& result, string& out, string& error){
    try{
        const json document = serializeResult(result);
        out = document.dump(2);
    }catch(const json::exception& ex){
        return fail(error, string("JSON serialize error: ") + ex.what());
    }
    return true;
}

bool writeResult(const string& path, const SimulationResult& result, string& error){
    string text;
    if(!writeResultToString(result, text, error)){
        return false;
    }
    std::ofstream output(path);
    if(!output){
        return fail(error, "failed to open output file: " + path);
    }
    output << text;
    if(!output){
        return fail(error, "failed to write output file: " + path);
    }
    return true;
}
