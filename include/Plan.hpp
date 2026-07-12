#pragma once
using namespace std;

#include <string>
#include <vector>
#include "Action.hpp"

//recovery plan supplied by the planner here.

struct Plan{
    string plan_id;
    string summary;
    vector<Action> actions;
    string rationale;
    string expected_risk;
    vector<string> constraints_checked;
};
