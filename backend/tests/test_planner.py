# backend/tests/test_planner.py
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.agents.planner import PlannerAgent, get_planner_agent
from app.agents.state import StepAction, RiskLevel

@pytest.mark.asyncio
async def test_create_plan_success():
    # Mock context
    context = {
        "repo_analysis": {
            "tech_stack": {"languages": ["Python"]},
            "key_files": ["main.py"]
        }
    }
    
    # Mock LLM response
    mock_json_response = """
    {
        "strategy": "Test Strategy",
        "risk_assessment": "Low",
        "total_estimated_tokens": 100,
        "estimated_duration_minutes": 5,
        "steps": [
            {
                "id": "s1",
                "action": "create",
                "intent": "Create something",
                "target_files": ["new.py"],
                "dependencies": [],
                "risk_level": "low",
                "verification_method": "Check file"
            }
        ]
    }
    """
    
    with patch("app.core.HybridModelClient.HybridModelClient") as MockClient:
        with patch("app.core.key_manager.KeyManager"):
            with patch("app.core.thought_signature.capture_signature", new_callable=AsyncMock, return_value=None):
                mock_instance = MockClient.return_value
                mock_instance.generate = AsyncMock(return_value=mock_json_response)
                
                agent = PlannerAgent()
                result = await agent.create_plan("Test Objective", context)
                
                # create_plan returns (plan, signature) tuple
                plan, signature = result
                
                assert plan.objective == "Test Objective"
                assert plan.strategy == "Test Strategy"
                assert len(plan.steps) == 1
                assert plan.steps[0].id == "s1"
                assert plan.steps[0].action == StepAction.CREATE
                assert plan.steps[0].risk_level == RiskLevel.LOW

@pytest.mark.asyncio
async def test_create_plan_fallback():
    # Force exception to trigger fallback
    with patch("app.core.HybridModelClient.HybridModelClient", side_effect=Exception("API Error")):
        with patch("app.core.key_manager.KeyManager"):
            agent = PlannerAgent()
            result = await agent.create_plan("Fallback Test", {})
            
            # Fallback returns ExecutionPlan directly (not tuple)
            plan = result if not isinstance(result, tuple) else result[0]
            
            assert "Fallback" in plan.strategy
            assert len(plan.steps) == 2
            assert plan.steps[0].intent == "Generate code based on objective"

def test_singleton():
    agent1 = get_planner_agent()
    agent2 = get_planner_agent()
    assert agent1 is agent2
