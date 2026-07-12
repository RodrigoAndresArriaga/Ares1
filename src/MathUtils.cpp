#include "MathUtils.hpp"
#include "PhysicalConstants.hpp"

//1. Implement clamp without hiding invalid min/max ordering.
//2. For low-side severity, returns 0 at or above safe, 1 at or below critical, and linearly interpolates between.
//3. For high-side severity, returns 0 at or below safe, and 1 at or above critical.
//4. Clamps only the normalized severity result, not the physical state being checked.

double MathUtils::clamp(double value, double minimum, double maximum){
    //clamp logic.
if (value < minimum) {
    return minimum;
}
if (value > maximum) {
    return maximum;
}
return value;
}

double MathUtils::lowSideSeverity(double value, double safe_value, double critical_value){
    // low-side severity logic.
    double severity = (safe_value - value) / (safe_value - critical_value);
    return clamp(severity, 0.0, 1.0);
}

double MathUtils::highSideSeverity(double value, double safe_value, double critical_value){
    // high-side severity logic.
    double severity = (value - safe_value) / (critical_value - safe_value);
    return clamp(severity, 0.0, 1.0);
}

double MathUtils::percentToFraction(double percent){
    // percent-to-fraction conversion.
    return percent / 100.0;
}

double MathUtils::celsiusToKelvin(double temperature_c){
    // Celsius-to-Kelvin conversion.
    return temperature_c + ares::constants::CELSIUS_TO_KELVIN;
}

double MathUtils::kpaToMmhg(double pressure_kpa){
    // kPa-to-mmHg conversion.
    return pressure_kpa * ares::constants::KPA_TO_MMHG;
}

double MathUtils::secondsToHours(double seconds){
    // seconds-to-hours conversion.
    return seconds / ares::constants::SECONDS_PER_HOUR; 
}

double MathUtils::minutesToHours(double minutes){
    // minutes-to-hours conversion.
    return minutes / ares::constants::MINUTES_PER_HOUR;
}
