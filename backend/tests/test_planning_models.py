# backend/tests/test_planning_models.py
import pytest
import json
from dataclasses import asdict
from app.agents.state import AgentState, ExecutionPlan, PlanStep, StepAction, RiskLevel

def test_plan_serialization():
    # Create steps
    step1 = PlanStep(
        id="s1",
        action=StepAction.CREATE,
        intent="Create file",
        target_files=["test.py"],
        dependencies=[],
        risk_level=RiskLevel.LOW,
        verification_method="Run tests"
    )
    
    step2 = PlanStep(
        id="s2",
        action=StepAction.MODIFY,
        intent="Update logic",
        target_files=["test.py"],
        dependencies=["s1"],
        risk_level=RiskLevel.MEDIUM,
        verification_method="Manual check"
    )
    
    # Create plan
    plan = ExecutionPlan(
        objective="Test Objective",
        strategy="Test Strategy",
        steps=[step1, step2],
        total_estimated_tokens=100,
        estimated_duration_minutes=5,
        risk_assessment="Low risk"
    )
    
    # Create state
    state = AgentState(
        agent_id="agent-1",
        execution_plan=plan
    )
    
    # Serialize
    json_str = state.json()
    assert "Test Objective" in json_str
    assert "s1" in json_str
    
    # Deserialize
    new_state = AgentState.parse_raw(json_str)
    
    assert new_state.execution_plan is not None
    assert new_state.execution_plan.objective == "Test Objective"
    assert len(new_state.execution_plan.steps) == 2
    assert isinstance(new_state.execution_plan.steps[0], PlanStep)
    assert new_state.execution_plan.steps[0].id == "s1"
    assert new_state.execution_plan.steps[1].dependencies == ["s1"]

def test_plan_logic():
    step1 = PlanStep(id="s1", action=StepAction.CREATE, intent="", target_files=[], dependencies=[], risk_level=RiskLevel.LOW, verification_method="")
    step2 = PlanStep(id="s2", action=StepAction.MODIFY, intent="", target_files=[], dependencies=["s1"], risk_level=RiskLevel.LOW, verification_method="")
    
    plan = ExecutionPlan(
        objective="Obj", strategy="Strat", steps=[step1, step2],
        total_estimated_tokens=0, estimated_duration_minutes=0, risk_assessment=""
    )
    
    # Init state: s1 pending, s2 pending (blocked by s1)
    next_step = plan.get_next_step()
    assert next_step.id == "s1"
    
    # Complete s1
    plan.mark_step_complete("s1")
    
    # Next should be s2
    next_step = plan.get_next_step()
    assert next_step.id == "s2"
    
    # Complete s2
    plan.mark_step_failed("s2", "Error")
    assert plan.steps[1].status == "failed"
