#pragma once

//all ARES enum classes here.

enum class MissionStatus {
    Nominal,
    Warning,
    Critical,
    Stabilized,
    Failure,
    Rejected
};

enum class OutcomeStatus{
    Stabilized,
    Failure,
    Rejected
};

enum class ActionType {
    ReducePowerLoad,
    IsolateModule, 
    OxygenRationing,
    RepairSolarArray,
    DelayRoverUse,
    SendEmergencyPacket,
    Unknown
};

enum class ActionExecutionStatus{
    Pending,
    Active,
    Complete,
    Failed,
    Aborted
};

enum class CrewActivity{
    Sleep, 
    Resting, 
    NominalWork,
    HighWorkload, 
    EVAPrep, 
    EVATransit, 
    EVAWork, 
    Recovery, 
    Incapacitated
};

enum class CrewHealthStatus{
    Nominal,
    ElevatedStress,
    Impaired,
    Critical,
    Incapacitated
};

enum class CrewAlarmType{
    Hypoxia,
    Hypercapnia,
    Pressure,
    Tachycardia,
    Respiratory,
    Thermal,
    Fatigue,
    Performance,
    EVAReturn
};

enum class EVAStatus{
    Idle,
    Preparing,
    Egress,
    Working,
    Ingress,
    Complete,
    Aborted
};

enum class ConstraintSeverity{
    Info,
    Warning,
    Critical,
    Failure
};

enum class SourceClassification{
    NASAStandard,
    NASAReference,
    DerivedPhysics,
    ARESAssumption
};
