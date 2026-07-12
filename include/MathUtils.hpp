#pragma once

//stateless numeric helpers for clamping, severity, and unit conversion.

class MathUtils{
public:
    static double clamp(double value, double minimum, double maximum);
    static double lowSideSeverity(double value, double safe_value, double critical_value);
    static double highSideSeverity(double value, double safe_value, double critical_value);
    static double percentToFraction(double percent);
    static double celsiusToKelvin(double temperature_c);
    static double kpaToMmhg(double pressure_kpa);
    static double secondsToHours(double seconds);
    static double minutesToHours(double minutes);
};
