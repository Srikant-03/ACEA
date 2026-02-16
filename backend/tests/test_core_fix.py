
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from app.core.key_manager import KeyManager
from app.core.local_model import HybridModelClient

def test_key_manager_defaults():
    # Mock settings.api_keys_list
    with patch("app.core.config.Settings.api_keys_list", new_callable=PropertyMock) as mock_keys:
        mock_keys.return_value = ["key1", "key2"]
        # We need to ensure KeyManager imports settings from config
        # KeyManager logic: keys = settings.api_keys_list
        km = KeyManager()
        assert km.keys == ["key1", "key2"]

def test_key_manager_explicit():
    km = KeyManager(["custom_key"])
    assert km.keys == ["custom_key"]

def test_hybrid_client_injection():
    km = KeyManager(["k1"])
    client = HybridModelClient(km)
    assert client.km == km
    assert client.km.keys == ["k1"]

def test_hybrid_client_default():
    with patch("app.core.config.Settings.api_keys_list", new_callable=PropertyMock) as mock_keys:
        mock_keys.return_value = ["def_key"]
        client = HybridModelClient()
        assert client.km.keys == ["def_key"]
