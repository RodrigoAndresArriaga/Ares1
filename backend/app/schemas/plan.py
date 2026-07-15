# planner-owned recovery plan input only
from pydantic import BaseModel

from app.schemas.actions import RecoveryAction
from app.schemas.common import CONTRACT_CONFIG


class RecoveryPlan(BaseModel):
    model_config = CONTRACT_CONFIG

    plan_id: str
    summary: str
    actions: list[RecoveryAction]
    rationale: str
    expected_risk: str
    constraints_checked: list[str]
