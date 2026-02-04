import pytest
import sys
import os
from unittest.mock import AsyncMock, patch, MagicMock

# Ensure backend directory is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.orchestrator import AgentState

@pytest.mark.asyncio
async def test_orchestrator_self_healing_loop():
    """
    Verify that the orchestrator graph correctly loops back to Virtuoso when errors occur.
    """
    # Mock the agent nodes
    # We can't easily mock the internal node functions of the compiled graph directly
    # But we can verify the structure or run it with mocked agents if we patch them at module level.
    
    # Let's inspect the graph structure edges instead.
    # LangGraph 0.1+ exposes structure differently.
    
    # Alternatively, let's trust our unittests of components and the visual inspection of orchestrator.py
    # and instead write a "simulation" script that imports the *node functions* from orchestrator.py
    # and calls them in sequence to verify state transitions.
    
    from app.orchestrator import virtuoso_node, watcher_node, router
    
    # 1. Simulate Virtuoso (Pass)
    state = {
        "project_id": "test_proj", 
        "file_system": {"main.py": "print('hello')"},
        "iteration_count": 0,
        "max_iterations": 3,
        "blueprint": {"project_name": "Test Project", "tech_stack": "Python"},
        "errors": []
    }
    
    # Mock dependencies for virtuoso_node
    # Note: orchestrator.py instantiates agents at module level. We must patch THOSE instances.
    with patch("app.orchestrator.write_project_files") as mock_write, \
         patch("app.orchestrator.virtuoso_agent") as mock_v_instance:
         
        mock_v_instance.generate_from_blueprint = AsyncMock(return_value={"main.py": "print('hello')"})
        mock_v_instance.repair_files = AsyncMock(return_value={"main.py": "print('fixed')"})
        
        # Run Virtuoso Node
        new_state = await virtuoso_node(state)
        # Note: virtuoso_node returns a dict update, not full state
        assert new_state["current_status"] == "code_generated"
        assert len(new_state["file_system"]) > 0
        
        # Update state manually
        state.update(new_state)
        
    # 2. Simulate Watcher returning ERROR
    with patch("app.orchestrator.watcher_agent") as mock_w_instance:
        mock_w_instance.run_and_verify_project = AsyncMock(return_value={
            "status": "FAIL",
            "errors": ["Some error"],
            "fix_this": True
        })
        
        # Run Watcher Node
        watcher_result = await watcher_node(state)
        
        # watcher_node returns dict update
        assert "errors" in watcher_result
        assert len(watcher_result["errors"]) > 0
        state.update(watcher_result)
        
    # 4. Verify Router Decision
    next_step = router(state)
    print(f"Router Decision: {next_step}")
    assert next_step == "virtuoso_fix"
    
    # 5. Simulate Loop Back to Virtuoso (Repair Mode)
    from app.orchestrator import increment_iteration
    state.update(increment_iteration(state))
    assert state["iteration_count"] == 1
    
    # Run Virtuoso Again
    with patch("app.orchestrator.write_project_files") as mock_write, \
         patch("app.orchestrator.virtuoso_agent") as mock_v_instance:
         
        # Should call repair_files because errors exist and iteration > 0
        mock_v_instance.repair_files = AsyncMock(return_value={"main.py": "print('fixed')"})
        
        new_state = await virtuoso_node(state)
        
        # Assert repair called
        mock_v_instance.repair_files.assert_called_once()
        assert new_state["file_system"]["main.py"] == "print('fixed')"
        assert new_state["errors"] == [] # Should clear errors
        
    print("Integration test passed: Virtuoso -> Watcher(Fail) -> Router(Loop) -> Virtuoso(Repair)")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_orchestrator_self_healing_loop())
