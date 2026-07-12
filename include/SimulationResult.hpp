#pragma once
#include <string>
#include <vector>
#include "Enums.hpp"
#include "SimulationMetrics.hpp"
#include "TelemetrySample.hpp"

using namespace std;

//deterministic simulator output container here.

struct SimulationResult{
    string scenario_id;
    string plan_id;
    OutcomeStatus outcome;
    bool valid_plan;
    SimulationMetrics metrics;
    vector<TimelineEvent> timeline;
    vector<TelemetrySample> telemetry_history;
    vector<string> failure_reasons;
};
