# ACEA Sentinel - API Key Manager with Usage Tracking

from google import genai
from app.core.config import settings
from datetime import datetime
from typing import Dict, List


class KeyManager:
    """
    Manages API keys with:
    - Round-robin rotation
    - Usage tracking per key
    - Health monitoring
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(KeyManager, cls).__new__(cls)
            cls._instance.keys = settings.api_keys_list
            cls._instance.current_index = 0
            cls._instance.client = None
            
            # Usage tracking per key
            cls._instance.key_stats = [
                {
                    'calls_made': 0,
                    'calls_remaining': 1500,  # Estimate for free tier
                    'last_used': None,
                    'errors': 0,
                    'last_error': None
                }
                for _ in settings.api_keys_list
            ]
            cls._instance.total_calls = 0
            
        return cls._instance

    def get_current_key(self) -> str:
        if not self.keys:
            raise ValueError("No API Keys configured in .env")
        return self.keys[self.current_index]

    def get_client(self) -> genai.Client:
        """Returns the active genai Client."""
        if self.client is None:
            self.client = genai.Client(api_key=self.get_current_key())
        return self.client

    def rotate_key(self):
        """Switches to the next key and refreshes the client."""
        prev = self.current_index
        self.current_index = (self.current_index + 1) % len(self.keys)
        print(f"KeyManager: Rotated Key from ...{self.keys[prev][-4:]} to ...{self.keys[self.current_index][-4:]}")
        # Re-init client with new key
        self.client = genai.Client(api_key=self.get_current_key())
        return self.client

    def track_usage(self, success: bool = True, error_msg: str = None):
        """Track API call usage for current key."""
        idx = self.current_index
        self.key_stats[idx]['calls_made'] += 1
        self.key_stats[idx]['calls_remaining'] -= 1
        self.key_stats[idx]['last_used'] = datetime.now().isoformat()
        self.total_calls += 1
        
        if not success:
            self.key_stats[idx]['errors'] += 1
            self.key_stats[idx]['last_error'] = error_msg

    def get_status(self) -> Dict:
        """Get health status of all API keys."""
        active_count = sum(
            1 for stats in self.key_stats if stats['calls_remaining'] > 0
        )
        
        return {
            'keys': [
                {
                    'key_id': f"key_{i+1}",
                    'masked': f"...{self.keys[i][-4:]}" if i < len(self.keys) else "N/A",
                    'status': 'active' if stats['calls_remaining'] > 0 else 'exhausted',
                    'calls_made': stats['calls_made'],
                    'calls_remaining': stats['calls_remaining'],
                    'last_used': stats['last_used'],
                    'errors': stats['errors']
                }
                for i, stats in enumerate(self.key_stats)
            ],
            'total_calls': self.total_calls,
            'active_keys': active_count,
            'exhausted_keys': len(self.keys) - active_count,
            'current_key_index': self.current_index
        }

    def reset_daily_quota(self):
        """Reset daily quotas (call at midnight)."""
        for stats in self.key_stats:
            stats['calls_remaining'] = 1500
            stats['errors'] = 0
