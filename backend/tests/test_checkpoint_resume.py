# backend/tests/test_checkpoint_resume.py
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.core.persistence import CheckpointManager
from app.agents.state import AgentState

@pytest.fixture
def mock_agent_state():
    return AgentState(
        project_id="job_test_123",
        user_prompt="Test Prompt",
        repo_path="/tmp/test_repo",
        current_step_id="step_2",
        messages=["Message 1", "Message 2"]
    )

@pytest.mark.asyncio
async def test_checkpoint_save_load_filesystem(mock_agent_state):
    """Test saving and loading checkpoint using filesystem fallback."""
    manager = CheckpointManager(redis_url=None) # Force filesystem
    
    # Save
    state_dict = mock_agent_state.to_dict() if hasattr(mock_agent_state, "to_dict") else mock_agent_state.__dict__
    # Dataclass to dict
    from dataclasses import asdict
    state_dict = asdict(mock_agent_state)
    
    job_id = "job_fs_test"
    success = await manager.save_checkpoint(job_id, state_dict, step_id="step_2")
    assert success
    
    # Load
    loaded_state = await manager.load_checkpoint(job_id)
    assert loaded_state is not None
    assert loaded_state["project_id"] == "job_test_123"
    assert loaded_state["_checkpoint_meta"]["step_id"] == "step_2"
    
    # Cleanup
    await manager.delete_checkpoint(job_id)
    assert not (manager.checkpoint_dir / f"{job_id}.json").exists()

@pytest.mark.asyncio
async def test_orchestrator_resume_logic():
    """Test resume_from_checkpoint logic in orchestrator."""
    from app.core.orchestrator import resume_from_checkpoint
    
    job_id = "job_orch_test"
    mock_data = {
        "project_id": job_id,
        "user_prompt": "Resume Me",
        "messages": [],
        "tech_stack": "Python",
        "_checkpoint_meta": {"step_id": "step_1"}
    }
    
    # Mock load_checkpoint
    with patch("app.core.persistence.CheckpointManager.load_checkpoint", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = mock_data
        
        state = await resume_from_checkpoint(job_id)
        
        assert state is not None
        assert state.project_id == job_id
        assert state.user_prompt == "Resume Me"
        mock_load.assert_called_once_with(job_id)

@pytest.mark.asyncio
async def test_list_checkpoints():
    manager = CheckpointManager(redis_url=None)
    
    # Create dummy checkpoint
    job_id = "job_list_test"
    state = {"project_id": job_id, "_checkpoint_meta": {"saved_at": "2023-01-01"}}
    await manager.save_checkpoint(job_id, state)
    
    checkpoints = await manager.list_checkpoints()
    found = any(c["job_id"] == job_id for c in checkpoints)
    assert found
    
    await manager.delete_checkpoint(job_id)
