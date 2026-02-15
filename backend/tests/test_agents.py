# tests/test_agents.py
import pytest
import sys
import os
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from app.agents.state import AgentState, Issue

# Fix path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import from ACTUAL files
from app.agents.watcher import WatcherAgent # Was BrowserAgent/VibeAgent
from app.agents.testing_agent import TestingAgent # Was TestingAgent
from app.agents.sentinel import SentinelAgent # Was SentinelAgent

# --- WatcherAgent Tests (Browser + Visual) ---
@pytest.mark.asyncio
async def test_watcher_agent_verify_page():
    # Setup state if needed, but WatcherAgent directly takes url
    # However, orchestrator calls run_and_verify_project
    
    agent = WatcherAgent()
    
    # Patch where it is imported from
    with patch("playwright.async_api.async_playwright") as mock_pw_func:
        # Mock Playwright
        mock_context_mgr = MagicMock()
        mock_p = MagicMock()
        mock_context_mgr.__aenter__.return_value = mock_p
        mock_pw_func.return_value = mock_context_mgr
        
        mock_browser = AsyncMock()
        mock_p.chromium.launch.side_effect = AsyncMock(return_value=mock_browser)
        
        mock_context = AsyncMock()
        mock_browser.new_context.return_value = mock_context
        
        mock_page = AsyncMock()
        mock_context.new_page.return_value = mock_page
        
        # Mock response for goto
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_page.goto.return_value = mock_response
        
        # Test verify_page directly
        with patch.object(agent, "analyze_visuals", return_value=[]) as mock_analyze:
             result = await agent.verify_page("http://localhost:3000")
             
             # Debug failure if any
             if result["status"] != "PASS":
                 print(f"WatcherAgent Errors: {result.get('errors')}")
             
             assert result["status"] == "PASS"
             mock_page.goto.assert_called()
             mock_page.screenshot.assert_called()
             mock_analyze.assert_called() # Check if Vibe check was called

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

# --- SentinelAgent Tests ---
@pytest.mark.asyncio
async def test_sentinel_agent_batch_audit():
    agent = SentinelAgent()
    files = {"main.py": "print('hello')"}
    
    # Mock SecurityScanner
    mock_scanner = MagicMock()
    mock_scanner.bandit_available = True
    mock_scanner.semgrep_available = True
    mock_scanner.npm_available = True
    
    # Patch where it is defined, because sentinel imports it inside a method
    with patch("app.services.security_scanner.get_scanner", return_value=mock_scanner):
         # Mock scan_python_file to return issue
         mock_scanner.scan_python_file = AsyncMock(return_value=[
             {"severity": "HIGH", "description": "Hardcoded password", "fix_suggestion": "Remove it", "line": 1}
         ])
         
         report = await agent.batch_audit(files)
         
         assert report["status"] == "BLOCKED"
         assert len(report["vulnerabilities"]) == 1
         assert report["vulnerabilities"][0]["description"] == "Hardcoded password"
