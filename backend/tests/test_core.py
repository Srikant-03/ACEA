# tests/test_core.py
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from app.core.persistence import AsyncRedisSaver

# We need to patch imports BEFORE importing KeyManager if we want to mock the Client class it uses
# But since we already imported it in previous test runs, we rely on patch
from app.core.key_manager import KeyManager
from app.core.HybridModelClient import HybridModelClient
from app.core.model_response import ModelResponse

# --- AsyncRedisSaver Tests ---
@pytest.mark.asyncio
async def test_redis_saver_set_get():
    mock_redis = AsyncMock()
    # Setup get return value (AsyncMock call returns a coroutine that resolves to this)
    mock_redis.get.return_value = '{"foo": "bar"}'
    
    with patch("app.core.persistence.redis.from_url", return_value=mock_redis) as mock_from_url:
        saver = AsyncRedisSaver("redis://localhost")
        
        # Test Set
        await saver.set("test_key", '{"foo": "bar"}')
        mock_redis.set.assert_called_with("test_key", '{"foo": "bar"}')
        
        # Test Get
        val = await saver.get("test_key")
        assert val == '{"foo": "bar"}'
        mock_redis.get.assert_called_with("test_key")

@pytest.mark.asyncio
async def test_redis_saver_missing_key():
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    
    with patch("app.core.persistence.redis.from_url", return_value=mock_redis):
        saver = AsyncRedisSaver("redis://localhost")
        with pytest.raises(KeyError):
            await saver.get("missing_key")

# --- KeyManager Tests ---
def test_key_manager_rotation():
    # Patch the Client class used in KeyManager
    with patch("app.core.key_manager.GeminiClient") as MockClient:
        keys = ["key1", "key2", "key3"]
        km = KeyManager(keys)
        
        # First call creates client with key1
        c1 = km.get_client()
        MockClient.assert_called_with(api_key="key1")
        
        km.rotate_key()
        c2 = km.get_client()
        MockClient.assert_called_with(api_key="key2")
        
        km.rotate_key()
        c3 = km.get_client()
        MockClient.assert_called_with(api_key="key3")
        
        km.rotate_key()
        c4 = km.get_client()
        MockClient.assert_called_with(api_key="key1") # Wrap around

def test_key_manager_exhaustion():
    with patch("app.core.key_manager.GeminiClient") as MockClient:
        keys = ["key1", "key2"]
        km = KeyManager(keys)
        
        # Mark key1 exhausted
        km.mark_exhausted("key1")
        
        # get_client should automatically skip key1 and use key2
        c = km.get_client()
        MockClient.assert_called_with(api_key="key2")
        
        # Mark key2 exhausted
        km.mark_exhausted("key2")
        
        # Now all exhausted
        with pytest.raises(RuntimeError, match="All API keys have been exhausted"):
            km.rotate_key()

# --- HybridModelClient Tests ---
@pytest.mark.asyncio
async def test_hybrid_client_success():
    km = MagicMock()
    mock_client = AsyncMock()
    # Setup mock response
    mock_response = MagicMock()
    mock_response.text = "Generated text"
    mock_response.thought_signature = "token123"
    
    # Setup client hierarchy for aio.models.generate_content
    # mock_client.aio returns an AsyncMock or MagicMock
    # We need to make sure the call chain works
    mock_aio = MagicMock()
    mock_models = MagicMock()
    mock_generate = AsyncMock(return_value=mock_response)
    
    mock_client.aio = mock_aio
    mock_aio.models = mock_models
    mock_models.generate_content = mock_generate
    
    km.get_client.return_value = mock_client
    
    client = HybridModelClient(km)
    resp = await client.generate("test prompt")
    
    assert resp.output == "Generated text"
    assert resp.thought_signature == "token123"

@pytest.mark.asyncio
async def test_hybrid_client_rotation_on_quota():
    # Mock KeyManager
    km = MagicMock()
    km.keys = ["k1", "k2"]
    km.index = 0
    
    # Client 1 raises Quota Error
    client1 = AsyncMock()
    client1.aio.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED")
    
    # Client 2 succeeds
    client2 = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.text = "Success"
    mock_resp.thought_signature = "sig"
    client2.aio.models.generate_content.return_value = mock_resp
    
    # Return different clients on subsequent calls
    km.get_client.side_effect = [client1, client2]
    
    client = HybridModelClient(km)
    resp = await client.generate("prompt")
    
    assert resp.output == "Success"
    
    # Verify we marked a key exhausted and rotated
    assert km.mark_exhausted.called
    assert km.rotate_key.called
