# backend/tests/test_autonomous_flow.py
import pytest
import shutil
import os
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import fastapi_app
from app.core.git_adapter import get_git_adapter
from unittest.mock import patch, MagicMock, AsyncMock

client = TestClient(fastapi_app)

# Test directories
TEST_REPO_DIR = Path("tmp_autonomous_test")

def _force_remove_readonly(func, path, exc_info):
    import stat
    if not os.access(path, os.W_OK):
        os.chmod(path, stat.S_IWRITE)
        func(path)
    else:
        raise

@pytest.fixture(autouse=True)
def setup_teardown():
    # Mock GitAdapter workspace to use test dir
    # We need to patch the __init__ or the property if it exists, but workspace_dir is set in __init__ associated with self.
    # Easiest way is to patch the default arg in __init__ or use a side_effect.
    # However, since we are testing endpoints that call get_git_adapter(), which is a singleton,
    # we should patch the singleton getter or reset the singleton.
    
    # 1. Reset singleton
    from app.core import git_adapter
    git_adapter._git_adapter = None
    
    # 2. Patch GitAdapter to use our test dir
    with patch("app.core.git_adapter.GitAdapter.__init__", return_value=None) as mock_init:
        # We need to manually set workspace_dir on the instance since we mocked init
        def side_effect(self, workspace_dir=None):
            self.workspace_dir = TEST_REPO_DIR
            self.repos = {}
            if TEST_REPO_DIR.exists():
                shutil.rmtree(TEST_REPO_DIR, onerror=_force_remove_readonly)
            TEST_REPO_DIR.mkdir()
            
        mock_init.side_effect = side_effect
        
        yield
        
        if TEST_REPO_DIR.exists():
            try:
                shutil.rmtree(TEST_REPO_DIR, onerror=_force_remove_readonly)
            except Exception:
                pass
        
        # Reset singleton again
        git_adapter._git_adapter = None


@pytest.mark.asyncio
@patch("app.agents.analyzer.AnalyzerAgent.analyze_codebase")
async def test_autonomous_execution_endpoint(mock_analyze):
    # Mock Analyzer
    mock_analyze.return_value = {
        "success": True,
        "tech_stack": {"languages": ["Python"]},
        "gemini_analysis": {"relevant_files": ["main.py"]}
    }
    
    # Needs a real repo URL or mocked clone. 
    # Let's mock the clone to avoid network dependency in unit test
    # Better to patch get_git_adapter to return a MagicMock
    mock_adapter = MagicMock()
    mock_adapter.clone_repository.return_value = (True, "Cloned", str(TEST_REPO_DIR / "job_test_123"))
    mock_adapter.create_feature_branch.return_value = (True, "Branched")
    
    with patch("app.core.git_adapter.get_git_adapter", return_value=mock_adapter):
        response = client.post("/api/autonomous/execute", json={
            "repo_url": "https://github.com/fake/repo.git",
            "objective": "Add new feature",
            "tech_stack": "Auto-detect"
        })
        
        if response.status_code != 200:
            print(f"Error response: {response.json()}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "job_id" in data
        assert data["status"] == "queued"
        assert data["objective"] == "Add new feature"
        
        # Verify calls
        mock_adapter.clone_repository.assert_called_once()
        mock_adapter.create_feature_branch.assert_called_once()
        mock_analyze.assert_called_once()

