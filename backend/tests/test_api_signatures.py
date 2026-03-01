
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.agents.state import ThoughtSignature
from unittest.mock import patch, AsyncMock

@pytest.mark.asyncio
async def test_get_signatures_endpoint():
    """Verify /signatures/{project_id} endpoint."""
    
    mock_checkpoint = {
        "thought_signatures": [
            {
                "signature_id": "sig_1",
                "agent": "ARCHITECT",
                "timestamp": "2023-01-01",
                "intent": "Test",
                "rationale": "Test rationale",
                "confidence": 0.9,
                "alternatives_considered": [],
                "context_used": [],
                "predicted_outcome": "",
                "token_usage": 100,
                "model_used": "gpt-4"
            }
        ]
    }
    
    # Mock get_checkpoint_manager
    with patch('app.core.persistence.get_checkpoint_manager') as MockGet:
        mock_manager = AsyncMock()
        mock_manager.load_checkpoint.return_value = mock_checkpoint
        MockGet.return_value = mock_manager
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/signatures/test_project_id")
            
        assert response.status_code == 200
        data = response.json()
        assert data["project_id"] == "test_project_id"
        assert len(data["signatures"]) == 1
        assert data["signatures"][0]["intent"] == "Test"

@pytest.mark.asyncio
async def test_get_signature_detail_endpoint():
    """Verify /signatures/{project_id}/{signature_id} endpoint."""
    
    mock_checkpoint = {
        "thought_signatures": [
            {
                "signature_id": "sig_1",
                "agent": "ARCHITECT",
                "timestamp": "2023-01-01",
                "intent": "Test",
                "rationale": "Test rationale",
                "confidence": 0.9,
                "alternatives_considered": [],
                "context_used": [],
                "predicted_outcome": "",
                "token_usage": 100,
                "model_used": "gpt-4"
            }
        ]
    }
    
    with patch('app.core.persistence.get_checkpoint_manager') as MockGet:
        mock_manager = AsyncMock()
        mock_manager.load_checkpoint.return_value = mock_checkpoint
        MockGet.return_value = mock_manager
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/signatures/test_project_id/sig_1")
            
        assert response.status_code == 200
        data = response.json()
        assert data["signature_id"] == "sig_1"
        assert data["intent"] == "Test"

@pytest.mark.asyncio
async def test_get_signature_not_found():
    """Verify 404 for missing signature."""
    
    mock_checkpoint = {
        "thought_signatures": []
    }
    
    with patch('app.core.persistence.get_checkpoint_manager') as MockGet:
        mock_manager = AsyncMock()
        mock_manager.load_checkpoint.return_value = mock_checkpoint
        MockGet.return_value = mock_manager
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/signatures/test_project_id/missing_sig")
            
        assert response.status_code == 404
