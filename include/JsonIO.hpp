#pragma once

#include <string>
#include "Plan.hpp"
#include "ScenarioConfig.hpp"
#include "SimulationResult.hpp"

using namespace std;

// strict scenario/plan load and deterministic result serialization

bool loadScenario(const string& path, ScenarioConfig& out, string& error);
bool loadScenarioFromString(const string& json_text, ScenarioConfig& out, string& error);

bool loadPlan(const string& path, Plan& out, string& error);
bool loadPlanFromString(const string& json_text, Plan& out, string& error);

bool writeResult(const string& path, const SimulationResult& result, string& error);
bool writeResultToString(const SimulationResult& result, string& out, string& error);
