
from google import genai
from app.core.config import settings
import random

class KeyManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(KeyManager, cls).__new__(cls)
            cls._instance.keys = settings.api_keys_list
            cls._instance.current_index = 0
            cls._instance.client = None
        return cls._instance

    def get_current_key(self):
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
