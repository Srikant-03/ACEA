# ACEA Sentinel - Unified Model Client
# Cloud-first with local Ollama fallback.
# This module provides the agent-facing model interface.
# The class is named UnifiedModelClient to avoid collision with
# core/HybridModelClient.py (the Gemini API wrapper).
# A backward-compatible alias 'HybridModelClient' is exported at module level.

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
        except Exception:
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
            print(f"Ollama list_models error: {e}")
        return []
    
    async def generate(self, prompt: str, model: Optional[str] = None, json_mode: bool = False) -> str:
        """Generate text using local Ollama model."""
        model = model or self.current_model
        
        payload = {
            "model": model,
            "prompt": prompt,
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
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=300)
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
        """Chat completion using local Ollama model."""
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
            for avail in available:
                if preferred in avail or avail.startswith(preferred.split(":")[0]):
                    self.current_model = avail
                    return avail
        
        if available:
            self.current_model = available[0]
            return available[0]
        
        raise Exception("No models available in Ollama. Run: ollama pull qwen2.5-coder:14b")


class UnifiedModelClient:
    """
    Agent-facing model client.
    
    Wraps the core HybridModelClient (from HybridModelClient.py) for
    cloud Gemini calls with key rotation, and falls back to local Ollama
    when all API keys are exhausted.
    
    Returns plain str (not ModelResponse) for backward compatibility with
    all agent call sites.
    
    NOTE: Previously named 'HybridModelClient' which collided with
    core/HybridModelClient.py. Renamed to UnifiedModelClient for clarity.
    A module-level alias preserves backward compatibility for all imports.
    """
    
    def __init__(self, key_manager=None):
        self.ollama = OllamaClient()
        self.use_local = False
        self._ollama_available = None
        self._core_client = None
        self._key_manager = key_manager
    
    def _get_core_client(self):
        """Lazily initialize the core HybridModelClient to avoid circular imports."""
        if self._core_client is None:
            try:
                from app.core.HybridModelClient import HybridModelClient as CoreHybridModelClient
                from app.core.key_manager import KeyManager
                from app.core.config import settings

                km = self._key_manager or KeyManager(settings.api_keys_list)
                self._core_client = CoreHybridModelClient(km)
            except Exception as e:
                print(f"Warning: Core HybridModelClient init failed: {e}")
                self._core_client = None
        return self._core_client
    
    async def check_ollama(self) -> bool:
        """Check if Ollama is available (cached)."""
        if self._ollama_available is None:
            self._ollama_available = await self.ollama.is_available()
        return self._ollama_available
    
    # Keywords that indicate non-cacheable prompts (repair/debug context changes each time)
    _NO_CACHE_KEYWORDS = {"fix", "error", "debug", "repair", "rollback", "self-healing", "diagnos"}
    
    async def generate(self, prompt: str, json_mode: bool = False) -> str:
        """
        Generate text using best available model.
        
        Delegates to core HybridModelClient for Gemini cloud calls,
        falls back to Ollama on quota exhaustion.
        
        Enhancements:
        - G3/G15: Smart prompt caching (skips repair/debug prompts)
        - G17: MetricsCollector integration (latency, cache hits)
        
        Returns:
            str: Generated text (not ModelResponse, for agent compatibility)
        """
        import time as _time
        
        # --- G17: Metrics setup ---
        try:
            from app.core.metrics_collector import get_metrics_collector
            metrics = get_metrics_collector()
        except Exception:
            metrics = None
        
        start_ts = _time.time()
        
        # --- G3/G15: Check prompt cache ---
        is_cacheable = not any(kw in prompt.lower() for kw in self._NO_CACHE_KEYWORDS)
        model_name = "gemini-cloud"
        
        if is_cacheable:
            try:
                from app.core.cache import cache
                cached = await cache.get(prompt, model=model_name)
                if cached:
                    if metrics:
                        metrics.increment("cache_hits")
                        metrics.increment("llm_calls_total")
                    return cached
            except Exception:
                pass  # Cache miss or cache unavailable — proceed normally
        
        if metrics:
            metrics.increment("llm_calls_total")
            metrics.start_timer("_llm_call")
        
        # If in local mode and Ollama is available, use it directly
        if self.use_local:
            if await self.check_ollama():
                model_name = "ollama-local"
                result = await self.ollama.generate(prompt, json_mode=json_mode)
                self._post_generate(result, prompt, model_name, is_cacheable, metrics, start_ts)
                return result
            else:
                self.use_local = False  # Ollama not available, try cloud again
        
        # Try core client (cloud Gemini with key rotation)
        core = self._get_core_client()
        if core is not None:
            try:
                response = await core.generate(prompt, json_mode=json_mode)
                # Core returns ModelResponse; extract the text output
                result = response.output if hasattr(response, 'output') else str(response)
                self._post_generate(result, prompt, model_name, is_cacheable, metrics, start_ts)
                return result
            except RuntimeError as e:
                # All API keys exhausted — fall through to Ollama
                if "exhausted" in str(e).lower():
                    if metrics:
                        metrics.increment("llm_errors")
                else:
                    raise
            except Exception as e:
                error_str = str(e)
                if metrics:
                    metrics.increment("llm_errors")
                if "429" in error_str or "quota" in error_str.lower() or "RESOURCE_EXHAUSTED" in error_str:
                    print(f"⚠️ Core Client Quota Error: {error_str} - Falling back to Ollama") 
                    pass  # Fall through to Ollama
                else:
                    print(f"❌ Core Client Critical Error: {error_str}")
                    pass
        
        # Fallback: Ollama local inference
        if await self.check_ollama():
            self.use_local = True
            model_name = "ollama-local"
            try:
                await self.ollama.select_best_model()
            except Exception:
                pass
            result = await self.ollama.generate(prompt, json_mode=json_mode)
            self._post_generate(result, prompt, model_name, is_cacheable, metrics, start_ts)
            return result
        
        raise Exception(
            "All cloud API keys exhausted and Ollama not available. "
            "Either add more Gemini API keys to .env or start Ollama: ollama serve"
        )
    
    def _post_generate(self, result, prompt, model_name, is_cacheable, metrics, start_ts):
        """Post-generation: cache result + record metrics."""
        import time as _time
        latency_ms = (_time.time() - start_ts) * 1000
        
        # G3/G15: Cache deterministic responses
        if is_cacheable and result:
            try:
                from app.core.cache import cache
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(cache.set(prompt, model=model_name, response=result))
                else:
                    loop.run_until_complete(cache.set(prompt, model=model_name, response=result))
            except Exception:
                pass
        
        # G17: Record metrics
        if metrics:
            metrics.stop_timer("_llm_call")
            metrics.increment("total_tokens_estimated", len(result) // 4)
            metrics.record("last_model_used", model_name)
            metrics.record("last_latency_ms", round(latency_ms, 1))


# Backward-compatible alias: all agents import HybridModelClient from this module.
# This alias ensures existing imports work without modification.
HybridModelClient = UnifiedModelClient
