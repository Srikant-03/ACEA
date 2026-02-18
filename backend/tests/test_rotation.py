
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.core.local_model import HybridModelClient
from app.core.key_manager import KeyManager

@pytest.mark.asyncio
async def test_hybrid_client_key_rotation():
    # Setup KeyManager with 2 keys
    km = KeyManager(["key1", "key2"])
    client = HybridModelClient(km)
    
    # Mock SocketManager to avoid errors
    with patch("app.core.socket_manager.SocketManager") as mock_sm_cls:
        mock_sm = mock_sm_cls.return_value
        mock_sm.emit = AsyncMock()
        
        # Mock Gemini Client
        with patch("app.core.key_manager.GeminiClient") as mock_gemini:
            mock_client_instance = mock_gemini.return_value
            mock_aio = mock_client_instance.aio.models.generate_content
            
            # First call fails, Second succeeds
            async def side_effect(*args, **kwargs):
                if mock_aio.call_count == 1:
                    raise Exception("429 RESOURCE_EXHAUSTED")
                return MagicMock(text="Success")
            
            mock_aio.side_effect = side_effect
            
            response = await client.generate("test prompt")
            
            # Assertions
            assert response == "Success"
            params = mock_aio.call_args_list
            assert len(params) == 2 # Called twice
            assert "key1" in km.exhausted
            assert km.keys[km.index] == "key2"

@pytest.mark.asyncio
async def test_hybrid_client_exhaustion_fallback():
    # Setup KeyManager with 1 key
    km = KeyManager(["key1"])
    client = HybridModelClient(km)
    
    with patch("app.core.socket_manager.SocketManager") as mock_sm_cls:
        mock_sm = mock_sm_cls.return_value
        mock_sm.emit = AsyncMock()
        
        with patch("app.core.key_manager.GeminiClient") as mock_gemini:
            mock_client_instance = mock_gemini.return_value
            mock_client_instance.aio.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED")
            
            # Mock Ollama availability
            client.ollama.is_available = AsyncMock(return_value=True)
            client.ollama.select_best_model = AsyncMock(return_value="llama3")
            client.ollama.generate = AsyncMock(return_value="Ollama Response")
            
            response = await client.generate("test prompt")
            
            assert response == "Ollama Response"
            assert client.use_local is True
