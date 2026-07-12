add_executable(sim_core_tests
    test_math_utils.cpp
    test_atmosphere.cpp
    test_power.cpp
    test_thermal.cpp
    test_operations.cpp
    test_crew_physiology.cpp
    test_actions.cpp
    test_validator.cpp
    test_simulation.cpp
    ${CMAKE_SOURCE_DIR}/src/ResourceModel.cpp
    ${CMAKE_SOURCE_DIR}/src/CrewPhysiologyModel.cpp
    ${CMAKE_SOURCE_DIR}/src/ActionExecutor.cpp
    ${CMAKE_SOURCE_DIR}/src/Validator.cpp
    ${CMAKE_SOURCE_DIR}/src/Simulation.cpp
    ${CMAKE_SOURCE_DIR}/src/MathUtils.cpp
)

target_include_directories(sim_core_tests PRIVATE ${CMAKE_SOURCE_DIR}/include)
target_link_libraries(sim_core_tests PRIVATE Catch2::Catch2WithMain)

include(Catch)
catch_discover_tests(sim_core_tests DISCOVERY_MODE PRE_TEST)
