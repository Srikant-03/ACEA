import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.preview_browser_test_service import PreviewBrowserTestService

@pytest.fixture
def service():
    return PreviewBrowserTestService()

@pytest.mark.asyncio
async def test_run_test_resolution_failure(service):
    """Test that it reports error if URL cannot be resolved."""
    with patch.object(service, '_resolve_preview_url', return_value=None) as mock_resolve, \
         patch('app.core.socket_manager.SocketManager') as MockSM:
        
        mock_sm_instance = MockSM.return_value
        mock_sm_instance.emit = AsyncMock()
        
        result = await service.run_test("test-project-id", "quick")
        
        assert result["overall_status"] == "ERROR"
        assert "No active preview found" in result["error"]
        
        # Check start event and error event were emitted
        assert mock_sm_instance.emit.call_count >= 2

@pytest.mark.asyncio
async def test_run_test_success(service):
    """Test successful execution flow."""
    mock_report = {
        "overall_status": "PASS",
        "scores": {"overall": 95},
        "tests": {
            "interactive": {"issues": []},
            "accessibility": {"issues": []}
        }
    }
    
    with patch.object(service, '_resolve_preview_url', return_value="http://localhost:3000") as mock_resolve, \
         patch('app.agents.browser_validation_agent.BrowserValidationAgent.comprehensive_validate', new_callable=AsyncMock) as mock_validate, \
         patch('app.core.socket_manager.SocketManager') as MockSM:
        
        mock_validate.return_value = mock_report
        mock_sm_instance = MockSM.return_value
        mock_sm_instance.emit = AsyncMock()
        
        result = await service.run_test("test-project-id", "standard")
        
        assert result["overall_status"] == "PASS"
        assert result["url"] == "http://localhost:3000"
        assert result["scores"]["overall"] == 95
        assert result["categories"]["accessibility"] == []
        
        mock_validate.assert_called_once()
        # Should emit: starting, resolved, validating, complete
        assert mock_sm_instance.emit.call_count >= 4

@pytest.mark.asyncio
async def test_resolve_preview_url_e2b(service):
    """Test URL resolution via E2B service."""
    with patch('app.services.e2b_vscode_service.get_e2b_vscode_service') as mock_get_e2b:
        mock_e2b = mock_get_e2b.return_value
        mock_e2b.get_sandbox.return_value = {"preview_url": "https://e2b-preview.com"}
        
        url = await service._resolve_preview_url("proj-123")
        assert url == "https://e2b-preview.com"

@pytest.mark.asyncio
async def test_resolve_preview_url_proxy_fallback(service):
    """Test URL resolution via PreviewProxyService fallback."""
    with patch('app.services.e2b_vscode_service.get_e2b_vscode_service') as mock_get_e2b, \
         patch('app.services.preview_proxy_service.get_preview_proxy_service') as mock_get_proxy:
        
        # E2B fails or returns nothing
        mock_e2b = mock_get_e2b.return_value
        mock_e2b.get_sandbox.return_value = None
        
        # Proxy has session
        mock_proxy = mock_get_proxy.return_value
        mock_proxy.sessions = {"sess_1": {"project_id": "proj-123", "preview_url": "http://proxy-url.com"}}
        
        url = await service._resolve_preview_url("proj-123")
        assert url == "http://proxy-url.com"
