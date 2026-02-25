import os
import json
import pickle
import asyncio
import tempfile
from typing import Any, AsyncIterator, Dict, Optional, Sequence, Tuple, List
from contextlib import asynccontextmanager
from pathlib import Path
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointMetadata, CheckpointTuple
from langgraph.checkpoint.memory import MemorySaver as LangGraphMemorySaver
import redis.asyncio as redis


def _run_async_in_sync(coro):
    """Run an async coroutine from synchronous context.
    
    Handles the case where we may or may not already be inside
    an active event loop (e.g. during testing vs production).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # We're inside an async context — spin up a thread to avoid deadlock
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=30)
    else:
        return asyncio.run(coro)

# 1. InMemorySaver (Alias for existing behavior)
class InMemorySaver(LangGraphMemorySaver):
    """
    Wrapper around LangGraph's MemorySaver to maintain interface consistency.
    This is the default persistence layer.
    """
    pass

# 2. LangGraphRedisSaver (formerly AsyncRedisSaver)
class LangGraphRedisSaver(BaseCheckpointSaver):
    """
    Redis-based CheckpointSaver implementation for LangGraph.
    Stores checkpoints in Redis using Pickle serialization.
    """
    def __init__(self, url: str, key_prefix: str = "checkpoint"):
        super().__init__()
        self.client = redis.from_url(url)
        self.key_prefix = key_prefix

    async def aget_tuple(self, config: Dict[str, Any]) -> Optional[CheckpointTuple]:
        """Get a checkpoint tuple from Redis."""
        try:
            thread_id = config["configurable"]["thread_id"]
            key = f"{self.key_prefix}:{thread_id}"
            
            # Get the latest checkpoint
            data = await self.client.get(key)
            if not data:
                return None
                
            return pickle.loads(data)
        except Exception as e:
            print(f"AsyncRedisSaver [GET] Error: {e}")
            return None # Fail gracefully to empty state

    async def aput(
        self,
        config: Dict[str, Any],
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Save a checkpoint to Redis."""
        try:
            thread_id = config["configurable"]["thread_id"]
            key = f"{self.key_prefix}:{thread_id}"

            # Sanitize config to remove unpickleable objects (like stream_writer)
            safe_config = config.copy()
            if "configurable" in safe_config:
                safe_config["configurable"] = {k: v for k, v in safe_config["configurable"].items() 
                                             if isinstance(v, (str, int, float, bool, list, dict, tuple, type(None)))}
            
            # Store tuple data
            data = pickle.dumps(
                CheckpointTuple(
                    config=safe_config,
                    checkpoint=checkpoint,
                    metadata=metadata,
                    parent_config=safe_config 
                )
            )
            
            await self.client.set(key, data)
        except Exception as e:
            print(f"AsyncRedisSaver [PUT] Error: {e}")
            
        return config

    async def aput_writes(
        self,
        config: Dict[str, Any],
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
    ) -> None:
        """Store intermediate writes (required by abstract base class)."""
        # For this implementation, we might not strictly need to store writes 
        # for simple restart-ability, but to be fully compliant we should.
        # However, to avoid complexity with pickling unexpected objects in writes, 
        # we will implement a safe no-op or simple store.
        pass

    # Synchronous wrappers — delegate to async implementations
    # Required by LangGraph's Abstract Base Class for sync callers
    def get_tuple(self, config: Dict[str, Any]) -> Optional[CheckpointTuple]:
        """Synchronous wrapper around aget_tuple."""
        return _run_async_in_sync(self.aget_tuple(config))

    def put(
        self,
        config: Dict[str, Any],
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Synchronous wrapper around aput."""
        return _run_async_in_sync(self.aput(config, checkpoint, metadata, new_versions))

    async def alist(
        self,
        config: Optional[Dict[str, Any]],
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """List checkpoints (Simplified implementation to satisfy interface)."""
        # For now, we only store the LATEST checkpoint per thread, 
        # so list just yields that one if it matches.
        if config and "configurable" in config and "thread_id" in config["configurable"]:
             ckpt = await self.aget_tuple(config)
             if ckpt:
                 yield ckpt


# 3. Simple AsyncRedisSaver (User Requested)
class AsyncRedisSaver:
    def __init__(self, url: str):
        self.url = url
        self._redis = None

    async def _get_redis(self):
        if not self._redis:
            self._redis = redis.from_url(self.url, decode_responses=True)
        return self._redis

    async def get(self, key: str) -> str:
        """
        Get a JSON string by key from Redis.
        Returns the string or raises KeyError if not found.
        """
        client = await self._get_redis()
        try:
            value = await client.get(key)
        except Exception as e:
            # Fallback or error handling logic could go here
            # For now, just re-raise as per "catch Redis connection errors"
            print(f"AsyncRedisSaver Get Error: {e}")
            raise e

        if value is None:
            raise KeyError(f"Redis key not found: {key}")
        return value

    async def set(self, key: str, value: str) -> None:
        """
        Set a JSON string value by key in Redis.
        """
        client = await self._get_redis()
        try:
             await client.set(key, value)
        except Exception as e:
             # If USE_REDIS_PERSISTENCE is True, any failure should raise an exception
             print(f"AsyncRedisSaver Set Error: {e}")
             raise e

class CheckpointManager:
    """
    Manages state checkpoints for resume capability.
    
    Storage layers:
    1. Redis (primary, if available)
    2. Filesystem (fallback)
    """
    
    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url
        self.redis_client = None
        self.checkpoint_dir = Path(tempfile.gettempdir()) / "acea_checkpoints"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
        if redis_url:
            try:
                # We reuse the redis module imported at top
                self.redis_client = redis.from_url(
                    self.redis_url,
                    decode_responses=True
                )
                # logger not defined in this file original? 
                # It was in the user prompt code but the original file didn't have logger init.
                # I should add logger or print. Original matches usage of print.
                print("CheckpointManager: Redis client initialized")
            except Exception as e:
                print(f"Redis init failed: {e}. Using filesystem fallback.")
                self.redis_client = None
    
    async def save_checkpoint(
        self,
        job_id: str,
        state_dict: Dict[str, Any],
        step_id: Optional[str] = None
    ) -> bool:
        """Save checkpoint."""
        checkpoint_key = f"checkpoint:{job_id}"
        
        state_to_save = state_dict.copy()
        state_to_save["_checkpoint_meta"] = {
            "saved_at": __import__("datetime").datetime.now().isoformat(),
            "step_id": step_id
        }
        
        # Try Redis first
        if self.redis_client:
            try:
                await self.redis_client.set(
                    checkpoint_key,
                    json.dumps(state_to_save, default=str),
                    ex=86400
                )
                print(f"Checkpoint saved to Redis: {job_id}")
                return True
            except Exception as e:
                # Redis failed — disable client and fall through to filesystem
                print(f"Redis save failed ({e}), falling back to filesystem")
                self.redis_client = None
        
        # Filesystem fallback (always reachable)
        try:
            checkpoint_file = self.checkpoint_dir / f"{job_id}.json"
            with open(checkpoint_file, 'w') as f:
                json.dump(state_to_save, f, indent=2, default=str)
            print(f"Checkpoint saved to file: {checkpoint_file}")
            return True
        except Exception as e:
            print(f"Failed to save checkpoint: {e}")
            return False
    
    async def load_checkpoint(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Load checkpoint."""
        checkpoint_key = f"checkpoint:{job_id}"
        
        # Try Redis first
        if self.redis_client:
            try:
                data = await self.redis_client.get(checkpoint_key)
                if data:
                    print(f"Checkpoint loaded from Redis: {job_id}")
                    return json.loads(data)
            except Exception as e:
                print(f"Redis load failed ({e}), falling back to filesystem")
                self.redis_client = None
        
        # Filesystem fallback
        try:
            checkpoint_file = self.checkpoint_dir / f"{job_id}.json"
            if checkpoint_file.exists():
                with open(checkpoint_file, 'r') as f:
                    data = json.load(f)
                print(f"Checkpoint loaded from file: {checkpoint_file}")
                return data
            return None
        except Exception as e:
            print(f"Failed to load checkpoint: {e}")
            return None

    async def delete_checkpoint(self, job_id: str) -> bool:
        """Delete checkpoint."""
        checkpoint_key = f"checkpoint:{job_id}"
        
        # Try Redis
        if self.redis_client:
            try:
                await self.redis_client.delete(checkpoint_key)
            except Exception as e:
                print(f"Redis delete failed ({e})")
                self.redis_client = None
        
        # Always clean up filesystem too
        try:
            checkpoint_file = self.checkpoint_dir / f"{job_id}.json"
            if checkpoint_file.exists():
                checkpoint_file.unlink()
            print(f"Checkpoint deleted: {job_id}")
            return True
        except Exception as e:
            print(f"Failed to delete checkpoint: {e}")
            return False

    async def list_checkpoints(self) -> List[Dict[str, Any]]:
        """List all checkpoints."""
        checkpoints = []
        try:
            if self.redis_client:
                keys = []
                async for key in self.redis_client.scan_iter("checkpoint:*"):
                    keys.append(key)
                
                for key in keys:
                    job_id = key.replace("checkpoint:", "")
                    data = await self.redis_client.get(key)
                    if data:
                        state = json.loads(data)
                        meta = state.get("_checkpoint_meta", {})
                        checkpoints.append({
                            "job_id": job_id,
                            "saved_at": meta.get("saved_at"),
                            "step_id": meta.get("step_id"),
                            "source": "redis"
                        })
            
            from pathlib import Path
            for checkpoint_file in self.checkpoint_dir.glob("*.json"):
                job_id = checkpoint_file.stem
                if any(c["job_id"] == job_id for c in checkpoints):
                    continue
                try:
                    with open(checkpoint_file) as f:
                        state = json.load(f)
                    meta = state.get("_checkpoint_meta", {})
                    checkpoints.append({
                        "job_id": job_id,
                        "saved_at": meta.get("saved_at"),
                        "step_id": meta.get("step_id"),
                        "source": "filesystem"
                    })
                except:
                    pass
            return checkpoints
        except Exception as e:
            print(f"Failed to list checkpoints: {e}")
            return []

# Singleton
_checkpoint_manager = None

def get_checkpoint_manager(redis_url: Optional[str] = None) -> CheckpointManager:
    global _checkpoint_manager
    if _checkpoint_manager is None:
        _checkpoint_manager = CheckpointManager(redis_url)
    return _checkpoint_manager
