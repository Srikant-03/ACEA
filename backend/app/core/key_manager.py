# app/core/key_manager.py
from typing import List, Optional, Set
from google.genai import Client as GeminiClient
import os

class KeyManager:
    def __init__(self, keys: Optional[List[str]] = None):
        if keys is None:
            from app.core.config import settings
            keys = settings.api_keys_list
            
        if not keys:
             # Fallback to env or empty list, but orchestrator should provide them.
             print("Warning: KeyManager initialized with no keys.")
             
        self.keys = keys
        self.index = 0
        self.exhausted: Set[str] = set()
        # list of 30+ Gemini API keys
        # current key index
        # optionally track exhausted keys

    def get_client(self) -> GeminiClient:
        """Return a GeminiClient authenticated with the current key."""
        if not self.keys:
            raise RuntimeError("No API keys available in KeyManager.")
        
        # Check if all keys are exhausted
        if len(self.exhausted) >= len(self.keys):
             raise RuntimeError("All API keys have been exhausted.")

        key = self.keys[self.index]
        
        # If current key is exhausted, try to rotate immediately
        if key in self.exhausted:
            self.rotate_key()
            key = self.keys[self.index]

        client = GeminiClient(api_key=key)
        return client

    def rotate_key(self) -> None:
        """Advance index to the next non-exhausted key (wrap-around)."""
        if not self.keys:
            raise RuntimeError("No keys to rotate.")
        
        # Cycle until finding a non-exhausted key
        n = len(self.keys)
        # Try n times to find a usable key
        start_index = self.index
        for _ in range(n):
            self.index = (self.index + 1) % n
            if self.keys[self.index] not in self.exhausted:
                return
        
        # If loop completes without return, all keys are exhausted
        raise RuntimeError("All API keys have been exhausted.")

    def mark_exhausted(self, key: str) -> None:
        """Mark a key as exhausted (e.g. after a quota error)."""
        self.exhausted.add(key)
