# backend/tests/test_planner_integration.py
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.agents.state import AgentState, ExecutionPlan
from app.core.orchestrator import planner_node, builder

@pytest.mark.asyncio
async def test_planner_node_execution():
    # Setup state
    state = AgentState(
        project_id="test_project",
        user_prompt="Add auth",
        repo_path="/tmp/test_repo",
        tech_stack="Python"
    )
    
    # Mock PlannerAgent
    mock_plan = ExecutionPlan(
        objective="Add auth",
        strategy="Test",
        steps=[],
        total_estimated_tokens=0,
        estimated_duration_minutes=0,
        risk_assessment="Low"
    )
    
    with patch("app.agents.planner.get_planner_agent") as mock_get_planner:
        mock_agent = MagicMock()
        mock_agent.create_plan = AsyncMock(return_value=mock_plan)
        mock_get_planner.return_value = mock_agent
        
        # Mock SocketManager to avoid connection errors
        with patch("app.core.socket_manager.SocketManager.emit", new_callable=AsyncMock) as mock_emit:
            # Mock save_state (it's in orchestrator module scope)
            with patch("app.core.orchestrator.save_state", new_callable=AsyncMock):
                
                result = await planner_node(state)
                
                assert result["current_status"] == "plan_generated"
                assert state.execution_plan == mock_plan
                mock_agent.create_plan.assert_called_once()
                
                # Verify emission
                mock_emit.assert_any_call("plan_generated", {
                    "plan": mock_plan.to_dict(),
                    "steps": 0,
                    "estimated_duration": 0
                })

@pytest.mark.asyncio
async def test_planner_node_skipped():
    # State without repo_path
    state = AgentState(
        project_id="test_project_new",
        user_prompt="Create new app",
        repo_path=None
    )
    
    with patch("app.core.socket_manager.SocketManager"):
        result = await planner_node(state)
        assert result["current_status"] == "planning_skipped"

def test_graph_structure():
    # Verify graph compilation works and edges are correct
    # We can't easily inspect the compiled graph structure cleanly without internal access,
    # but we can try to compile it (which happens at import time mostly)
    # or check the builder.
    
    nodes = builder.nodes.keys()
    assert "planner" in nodes
    assert "architect" in nodes
    assert "virtuoso" in nodes
