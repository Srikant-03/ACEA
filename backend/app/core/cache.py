import hashlib
import json
from typing import Optional
from redis import asyncio as aioredis
import os

class AIResponseCache:
    """Cache AI responses to reduce API calls and costs."""
    
    def __init__(self):
        self.memory_cache = {}  # Simple in-memory cache
        self.redis = None  # Optional Redis for production
        
    async def init_redis(self):
        """Initialize Redis connection if URL is provided."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost")
        try:
            self.redis = await aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        except Exception:
            # Fall back to memory cache silently or log
            pass
    
    def _generate_key(self, prompt: str, model: str, **kwargs) -> str:
        """Generate cache key from prompt and parameters."""
        cache_data = {
            "prompt": prompt,
            "model": model,
            **kwargs
        }
        # Sort keys to ensure consistent hash
        cache_str = json.dumps(cache_data, sort_keys=True)
        return hashlib.sha256(cache_str.encode()).hexdigest()
    
    async def get(self, prompt: str, model: str, **kwargs) -> Optional[str]:
        """Get cached response if available."""
        key = self._generate_key(prompt, model, **kwargs)
        
        # Try Redis first (if initialized)
        if self.redis:
            try:
                cached = await self.redis.get(key)
                if cached:
                    return cached
            except Exception:
                pass
        
        # Fall back to memory
        return self.memory_cache.get(key)
    
    async def set(self, prompt: str, model: str, response: str, ttl: int = 3600, **kwargs):
        """Cache AI response."""
        key = self._generate_key(prompt, model, **kwargs)
        
        # Store in memory
        self.memory_cache[key] = response
        
        # Store in Redis with TTL
        if self.redis:
            try:
                await self.redis.setex(key, ttl, response)
            except Exception:
                pass

# Singleton instance
cache = AIResponseCache()
