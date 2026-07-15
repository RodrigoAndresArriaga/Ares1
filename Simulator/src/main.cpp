#include <iostream>
#include <string>

#include "JsonIO.hpp"
#include "Plan.hpp"
#include "ScenarioConfig.hpp"
#include "Simulation.hpp"
#include "SimulationResult.hpp"

using namespace std;

int main(int argc, char* argv[]){
    string scenario_path;
    string plan_path;
    string output_path;

    for(int i = 1; i < argc; ++i){
        string arg = argv[i];
        if(arg == "--scenario"){
            if(i + 1 >= argc){
                cerr << "missing value for --scenario\n";
                return 1;
            }
            scenario_path = argv[++i];
        }else if(arg == "--plan"){
            if(i + 1 >= argc){
                cerr << "missing value for --plan\n";
                return 1;
            }
            plan_path = argv[++i];
        }else if(arg == "--output"){
            if(i + 1 >= argc){
                cerr << "missing value for --output\n";
                return 1;
            }
            output_path = argv[++i];
        }else{
            cerr << "unknown argument: " << arg << "\n";
            return 1;
        }
    }

    if(scenario_path.empty() || output_path.empty()){
        cerr << "usage: sim_core --scenario <path> [--plan <path>] --output <path>\n";
        return 1;
    }

    ScenarioConfig scenario{};
    string error;
    if(!loadScenario(scenario_path, scenario, error)){
        cerr << error << "\n";
        return 1;
    }

    Simulation simulation;
    SimulationResult result{};
    if(plan_path.empty()){
        result = simulation.runBaseline(scenario);
    }else{
        Plan plan{};
        if(!loadPlan(plan_path, plan, error)){
            cerr << error << "\n";
            return 1;
        }
        result = simulation.runWithPlan(scenario, plan);
    }

    if(!writeResult(output_path, result, error)){
        cerr << error << "\n";
        return 1;
    }

    return 0;
}
