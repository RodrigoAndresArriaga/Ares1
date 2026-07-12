cmake_minimum_required(VERSION 3.16)

project(ARES1SimCore LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

include(FetchContent)

# Prefer extraction-time timestamps for URL downloads (CMake 3.24+)
if(POLICY CMP0135)
    cmake_policy(SET CMP0135 NEW)
endif()

FetchContent_Declare(
    nlohmann_json
    URL https://github.com/nlohmann/json/releases/download/v3.11.3/json.tar.xz
    URL_HASH SHA256=d6c65aca6b1ed68e7a182f4757257b107ae403032760ed6ef121c9d55e81757d
)
FetchContent_MakeAvailable(nlohmann_json)

FetchContent_Declare(
    Catch2
    URL https://github.com/catchorg/Catch2/archive/refs/tags/v3.7.1.tar.gz
    URL_HASH SHA256=c991b247a1a0d7bb9c39aa35faf0fe9e19764213f28ffba3109388e62ee0269c
)
FetchContent_MakeAvailable(Catch2)

add_executable(sim_core
    src/main.cpp
    src/ResourceModel.cpp
    src/CrewPhysiologyModel.cpp
    src/ActionExecutor.cpp
    src/Validator.cpp
    src/Simulation.cpp
    src/JsonIO.cpp
    src/MathUtils.cpp
)

target_include_directories(sim_core PRIVATE include)
target_link_libraries(sim_core PRIVATE nlohmann_json::nlohmann_json)

enable_testing()
add_subdirectory(tests)
