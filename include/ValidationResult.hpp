#pragma once
#include <optional>
#include <string>
#include <vector>
#include "Enums.hpp"

using namespace std;

//reusable validation messages for schema/static and dynamic validation here.

struct ValidationMessage{
    string code;
    string message;
    ConstraintSeverity severity;
    std::optional<int> action_index;
    std::optional<int> simulation_time_min;
};

struct ValidationResult{
    bool valid;
    vector<ValidationMessage> errors;
    vector<ValidationMessage> warnings;
};
