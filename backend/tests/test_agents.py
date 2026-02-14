# tests/test_agents.py
import pytest
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from unittest.mock import AsyncMock, patch, MagicMock
from app.agents.state import AgentState, Issue
from app.agents.browser_agent import BrowserAgent
from app.agents.vibe_agent import VibeAgent
from app.agents.sentinel_agent import SentinelAgent
from app.agents.testing_agent import TestingAgent

# --- BrowserAgent Tests ---
@pytest.mark.asyncio
async def test_browser_agent_run():
    state = AgentState(
        agent_id="test_agent", 
        project_id="test_proj"
    )
    # Mock preview_url on state (using setattr for dataclass/monkeypatch)
    setattr(state, "preview_url", "http://localhost:3000")
    
    with patch("app.agents.browser_agent.async_playwright") as mock_pw_func:
        # async_playwright() returns a context manager
        mock_context_mgr = MagicMock() # The manager itself isn't async, its __aenter__ is
        
        # The object yielded by context manager (p)
        mock_p = MagicMock()
        
        # __aenter__ is async, returns p
        # We need an AsyncMock for __aenter__? Or explicit future?
        # Standard way is to make __aenter__ return a coroutine or be an AsyncMock
        mock_context_mgr.__aenter__.return_value = mock_p
        
        # async_playwright() -> returns mock_context_mgr
        mock_pw_func.return_value = mock_context_mgr
        
        # p.chromium.launch() is async -> returns browser
        mock_browser = AsyncMock()
        mock_p.chromium.launch.side_effect = AsyncMock(return_value=mock_browser)
        # Using side_effect to ensure it's treated as awaitable if simple return_value validation fails
        mock_p.chromium.launch.return_value = mock_browser # simple way usually works with AsyncMock parent
        
        mock_context = AsyncMock()
        mock_browser.new_context.return_value = mock_context
        
        mock_page = AsyncMock()
        mock_context.new_page.return_value = mock_page
        
        agent = BrowserAgent()
        new_state = await agent.run(state)
        
        # Verify navigation
        mock_page.goto.assert_called_with("http://localhost:3000", timeout=60000)
        
        # Verify screenshot
        mock_page.screenshot.assert_called()
        
        # Verify state update
        assert len(new_state.screenshot_paths) > 0
        assert "BrowserAgent finished." in new_state.messages

# --- VibeAgent Tests ---
@pytest.mark.asyncio
async def test_vibe_agent_analyze():
    state = AgentState(agent_id="vibe", project_id="p1")
    
    with patch("app.agents.vibe_agent.requests.post") as mock_post:
        # Mock successful response
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "issues": [
                {"file": "index.html", "issue": "Misaligned button", "fix": "Add margin"}
            ]
        }
        mock_post.return_value = mock_resp
        
        # Mock Image.open to avoid file errors
        with patch("app.agents.vibe_agent.Image.open"):
            # Mock os.path.exists
            with patch("app.agents.vibe_agent.os.path.exists", return_value=True):
                 agent = VibeAgent()
                 issues = await agent.analyze("shot.png", "logs", state)
                 
                 assert len(issues) == 1
                 assert issues[0].issue == "Misaligned button"
                 assert len(state.issues) == 1

# --- SentinelAgent Tests ---
@pytest.mark.asyncio
async def test_sentinel_agent_run():
    state = AgentState(agent_id="sentinel", project_id="p1")
    
    with patch("app.agents.sentinel_agent.subprocess.run") as mock_run:
        # Mock Bandit output
        mock_res_bandit = MagicMock()
        mock_res_bandit.stdout = '{"results": [{"filename": "main.py", "issue_text": "Hardcoded password", "test_id": "B101"}]}'
        mock_res_bandit.returncode = 1 
        
        # Mock Semgrep output
        mock_res_semgrep = MagicMock()
        mock_res_semgrep.stdout = '{"results": []}'
        
        # Mock npm audit output
        mock_res_npm = MagicMock()
        mock_res_npm.stdout = '{"vulnerabilities": {}}'
        
        mock_run.side_effect = [mock_res_bandit, mock_res_semgrep, mock_res_npm]
        
        agent = SentinelAgent()
        new_state = await agent.run(state)
        
        assert len(new_state.issues) == 1
        assert new_state.issues[0].file == "main.py"
        assert new_state.issues[0].issue == "Hardcoded password"

# --- TestingAgent Tests ---
@pytest.mark.asyncio
async def test_testing_agent_run():
    state = AgentState(agent_id="tester", project_id="p1")
    
    with patch("app.agents.testing_agent.subprocess.run") as mock_run:
        # Mock pytest failure
        mock_pytest = MagicMock()
        mock_pytest.returncode = 1
        mock_pytest.stderr = "AssertionError: 1 != 2"
        
        # Mock vitest success
        mock_vitest = MagicMock()
        mock_vitest.returncode = 0
        
        mock_run.side_effect = [mock_pytest, mock_vitest]
        
        agent = TestingAgent()
        new_state = await agent.run(state)
        
        # Should have 1 issue from pytest
        assert len(new_state.issues) == 1
        assert new_state.issues[0].file == "PyTest"
        assert "Unit tests failed" in new_state.issues[0].issue
