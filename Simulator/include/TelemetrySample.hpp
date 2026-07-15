#pragma once
#include <string>
#include <vector>
#include "Action.hpp"
#include "DerivedTelemetry.hpp"
#include "Enums.hpp"

using namespace std;

//timeline-event and atomic telemetry-snapshot data here.

struct TimelineEvent{
    int time_min;
    string event_type;
    string message;
    ConstraintSeverity severity;
};

struct TelemetrySample{
    int simulation_time_min;
    DerivedTelemetry telemetry;
    vector<TimelineEvent> events_this_step;
    vector<ActiveActionState> active_actions;
    bool has_warning;
    bool has_critical;
};
