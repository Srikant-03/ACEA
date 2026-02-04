import pytest
import sys
import os
from unittest.mock import AsyncMock, patch

# Ensure backend directory is in path
sys.path.insert(0, os.getcwd())

from app.agents.virtuoso import VirtuosoAgent

@pytest.mark.asyncio
async def test_repair_files_structured():
    # Mock dependencies - Patch where they are defined, since they are imported locally
    with patch("app.core.local_model.HybridModelClient") as MockClient, \
         patch("app.core.socket_manager.SocketManager") as MockSM:
         
        # Setup Mocks
        mock_client_instance = MockClient.return_value
        mock_client_instance.generate = AsyncMock(return_value="FIXED CODE CONTENT")
        
        mock_sm_instance = MockSM.return_value
        mock_sm_instance.emit = AsyncMock()

        agent = VirtuosoAgent()
        
        existing_files = {
            "frontend/app/page.tsx": "ORIGINAL BROKEN CODE"
        }
        
        # Structured fix from TesterAgent
        errors = [
            {
                "file": "frontend/app/page.tsx",
                "change": "Fix syntax error"
            }
        ]
        
        # Run repair
        result = await agent.repair_files(existing_files, errors)
        
        # Verify result
        assert result["frontend/app/page.tsx"] == "FIXED CODE CONTENT"
        
        # Verify prompt contained instruction
        call_args = mock_client_instance.generate.call_args[0][0]
        assert "TARGET: frontend/app/page.tsx" in call_args
        assert "INSTRUCTION: Fix syntax error" in call_args

@pytest.mark.asyncio
async def test_repair_files_legacy_string():
    # Mock dependencies
    with patch("app.core.local_model.HybridModelClient") as MockClient, \
         patch("app.core.socket_manager.SocketManager") as MockSM:
         
        # Setup Mocks
        mock_client_instance = MockClient.return_value
        mock_client_instance.generate = AsyncMock(return_value="FIXED LEGACY CODE")
        
        mock_sm_instance = MockSM.return_value
        mock_sm_instance.emit = AsyncMock()

        agent = VirtuosoAgent()
        
        existing_files = {
            "frontend/app/page.tsx": "ORIGINAL BROKEN CODE"
        }
        
        # Legacy string error
        errors = ["FILE: frontend/app/page.tsx - Fix legacy error"]
        
        # Run repair
        result = await agent.repair_files(existing_files, errors)
        
        # Verify result
        assert result["frontend/app/page.tsx"] == "FIXED LEGACY CODE"
