# ACEA Sentinel - Local Model Client (Ollama)
# Provides local AI inference when cloud APIs are unavailable

import aiohttp
import json
from typing import Optional, Dict, Any

class OllamaClient:
    """
    Client for Ollama local model server.
    Provides the same interface as Gemini for seamless fallback.
    """
    
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        # Best models for 12GB VRAM, ordered by preference
        self.models = [
            "qwen2.5-coder:7b",      # Best coding quality
            "qwen2.5-coder:3b",       # Faster fallback
            "codellama:13b",          # Alternative
            "deepseek-coder:6.7b-instruct-q4_K_M",  # If available
        ]
        self.current_model = self.models[0]
    
    async def is_available(self) -> bool:
        """Check if Ollama server is running."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/tags", timeout=aiohttp.ClientTimeout(total=2)) as resp:
                    return resp.status == 200
        except Exception as e:
            # Silent check, just return False
            return False
    
    async def list_models(self) -> list:
        """List available models in Ollama."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/tags") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            # We can't use SocketManager here easily as it might be circular or too noisy
            # But we should at least print to stderr or return empty
            print(f"Ollama list_models error: {e}")
        return []
    
    async def generate(self, prompt: str, model: Optional[str] = None, json_mode: bool = False) -> str:
        """
        Generate text using local Ollama model.
        
        Args:
            prompt: The prompt to send
            model: Model name (defaults to best available)
            json_mode: If True, request JSON output format
        
        Returns:
            Generated text
        """
        model = model or self.current_model
        
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 4096,  # Max tokens
            }
        }
        
        if json_mode:
            payload["format"] = "json"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=300)  # 5 min for long generations
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("response", "")
                    else:
                        error = await resp.text()
                        raise Exception(f"Ollama error: {error}")
        except aiohttp.ClientError as e:
            raise Exception(f"Ollama connection error: {str(e)}")
    
    async def chat(self, messages: list, model: Optional[str] = None, json_mode: bool = False) -> str:
        """
        Chat completion using local Ollama model.
        Compatible with OpenAI chat format.
        
        Args:
            messages: List of {"role": "user"|"assistant"|"system", "content": "..."}
            model: Model name
            json_mode: If True, request JSON output
        
        Returns:
            Assistant's response text
        """
        model = model or self.current_model
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 4096,
            }
        }
        
        if json_mode:
            payload["format"] = "json"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=300)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("message", {}).get("content", "")
                    else:
                        error = await resp.text()
                        raise Exception(f"Ollama error: {error}")
        except aiohttp.ClientError as e:
            raise Exception(f"Ollama connection error: {str(e)}")
    
    async def select_best_model(self) -> str:
        """Select the best available model from Ollama."""
        available = await self.list_models()
        
        for preferred in self.models:
            # Check exact match or partial match
            for avail in available:
                if preferred in avail or avail.startswith(preferred.split(":")[0]):
                    self.current_model = avail
                    return avail
        
        # Fallback to first available
        if available:
            self.current_model = available[0]
            return available[0]
        
        raise Exception("No models available in Ollama. Run: ollama pull qwen2.5-coder:14b")


class HybridModelClient:
    """
    Hybrid client that tries cloud APIs first, falls back to local.
    """
    
    def __init__(self):
        from app.core.key_manager import KeyManager
        self.km = KeyManager()
        self.ollama = OllamaClient()
        self.use_local = False  # Track if we're in local mode
        self._ollama_available = None  # Cache availability check
    
    async def check_ollama(self) -> bool:
        """Check if Ollama is available (cached)."""
        if self._ollama_available is None:
            self._ollama_available = await self.ollama.is_available()
        return self._ollama_available
    
    async def generate(self, prompt: str, json_mode: bool = False) -> str:
        """
        Generate text using best available model.
        Tries Gemini first, falls back to Ollama on quota errors.
        """
        from app.core.socket_manager import SocketManager
        sm = SocketManager()
        
        # If we're in local mode and Ollama is available, use it directly
        if self.use_local:
            if await self.check_ollama():
                await sm.emit("agent_log", {"agent_name": "SYSTEM", "message": "🏠 Using local model (Ollama)..."})
                return await self.ollama.generate(prompt, json_mode=json_mode)
            else:
                self.use_local = False  # Ollama not available, try cloud again
        
        # Try Gemini first
        try:
            client = self.km.get_client()
            config = {"response_mime_type": "application/json"} if json_mode else {}
            
            response = await client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=config
            )
            return response.text
            
        except Exception as e:
            error_str = str(e)
            
            # Check for quota errors
            if "429" in error_str or "quota" in error_str.lower() or "RESOURCE_EXHAUSTED" in error_str:
                await sm.emit("agent_log", {"agent_name": "SYSTEM", "message": "⚠️ API quota exhausted. Switching to local model..."})
                
                # Try Ollama fallback
                if await self.check_ollama():
                    self.use_local = True
                    await sm.emit("agent_log", {"agent_name": "SYSTEM", "message": f"🏠 Using Ollama: {self.ollama.current_model}"})
                    
                    # Select best available model
                    try:
                        model = await self.ollama.select_best_model()
                        await sm.emit("agent_log", {"agent_name": "SYSTEM", "message": f"Selected model: {model}"})
                    except Exception as e:
                        await sm.emit("agent_log", {"agent_name": "SYSTEM", "message": f"⚠️ Local model select error: {e}"})
                    
                    return await self.ollama.generate(prompt, json_mode=json_mode)
                else:
                    await sm.emit("agent_log", {"agent_name": "SYSTEM", "message": "❌ Ollama not running. Start with: ollama serve"})
                    raise Exception("API quota exhausted and Ollama not available. Run: ollama serve")
            
            # Other errors - re-raise
            raise
