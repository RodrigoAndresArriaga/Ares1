#pragma once
#include <optional>
#include <string>
#include <vector>
#include "Enums.hpp"

using namespace std;


//planner action input and mutable execution-progress data here.

struct Action{
    ActionType type;
    string type_raw;
    int start_min;
    std::optional<double> percent;
    std::optional<string> module;
    std::optional<string> level;
    std::optional<int> duration_min;
    std::optional<double> hours;
    std::optional<string> crew_id;
    std::optional<string> eva_crew_id;
    vector<string> assigned_crew_ids;
    vector<string> target_crew_ids;
    vector<string> load_groups;
};

struct ActiveActionState{
    int action_index;
    ActionType type;
    ActionExecutionStatus status;
    std::optional<int> actual_start_min;
    int elapsed_min;
    double progress_fraction;
    std::optional<string> assigned_crew_id;
    std::optional<string> eva_crew_id;
    vector<string> assigned_crew_ids;
    string failure_reason;
};
