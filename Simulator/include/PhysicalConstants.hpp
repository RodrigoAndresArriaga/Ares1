#pragma once

//universal physical and unit-conversion constants here.

namespace ares::constants{

    inline constexpr double GAS_CONSTANT_J_PER_MOL_K = 8.314462618; //Universal gas constant
    inline constexpr double OXYGEN_MORAL_MASS_KG_PERO_MOL = 0.031998; //O2 molar mass
    inline constexpr double INERT_MOLAR_MASS_KG_PER_MOL = 0.0280134; //N2-equivelent molar mass
    inline constexpr double CO2_MORAL_MASS_KG_PER_MOL = 0.04401; //CO2 molar mass
    inline constexpr double CELSIUS_TO_KELVIN = 273.15; //Celsius to kelvin offset
    inline constexpr double KPA_TO_MMHG = 7.50062; //pressure conversion
    inline constexpr double WATER_VAPOR_PRESSURE_MMHG = 47.0; //Respiratory water-vapor reference
    inline constexpr double SOLAR_FLUX_1_AU_W_M2 = 1361.0; //Solar Flux at 1 AU
    inline constexpr double SECONDS_PER_MINUTE = 60.0;
    inline constexpr double MINUTES_PER_HOUR = 60.0;
    inline constexpr double SECONDS_PER_HOUR = 3600.0;
    inline constexpr double GRAMS_PER_KILOGRAM = 1000.0;
    inline constexpr double WATTS_PER_KILOWATT = 1000.0;
}
