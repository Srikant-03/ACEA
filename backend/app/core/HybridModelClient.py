# app/core/HybridModelClient.py
import asyncio
import base64
import logging
import time
from google.genai import Client as GeminiClient, errors as genai_exceptions
from app.core.key_manager import KeyManager
from app.core.model_response import ModelResponse

logger = logging.getLogger(__name__)

# Transient error patterns that should trigger retry with backoff
_TRANSIENT_PATTERNS = [
    "RESOURCE_EXHAUSTED",
    "UNAVAILABLE",
    "INTERNAL",
    "DEADLINE_EXCEEDED",
    "503",
    "500",
    "ConnectionError",
    "ConnectionReset",
    "TimeoutError",
    "ServerDisconnectedError",
]

def _is_transient(exc: Exception) -> bool:
    """Check if an exception is transient (worth retrying)."""
    err_str = str(exc)
    status_code = getattr(exc, 'status_code', 0)
    if status_code in (429, 500, 502, 503, 504):
        return True
    return any(p in err_str for p in _TRANSIENT_PATTERNS)

def _is_quota_error(exc: Exception) -> bool:
    """Check if this is specifically a quota/rate-limit error."""
    return "RESOURCE_EXHAUSTED" in str(exc) or getattr(exc, 'status_code', 0) == 429


class HybridModelClient:
    def __init__(self, key_manager: KeyManager):
        self.key_manager = key_manager

    async def generate(self, prompt: str, json_mode: bool = False, **kwargs) -> ModelResponse:
        """
        Send prompt to Gemini, auto-rotating keys on rate-limit errors.
        Includes exponential backoff for transient failures.
        Returns ModelResponse(output: str, thought_signature: str).
        """
        keys = self.key_manager.keys or []
        max_retries = max(len(keys) + 2, 5)
        base_delay = 1.0  # seconds
        max_delay = 30.0  # cap backoff at 30s

        # Build config for JSON mode if requested
        if json_mode:
            from google.genai import types
            kwargs.setdefault('config', types.GenerateContentConfig(
                response_mime_type="application/json"
            ))

        last_error = None
        for attempt in range(max_retries):
            client = self.key_manager.get_client()
            try:
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt,
                        **kwargs
                    ),
                    timeout=120  # 2-minute hard timeout per request
                )
                
                text_out = response.text
                thought_sig = getattr(response, 'thought_signature', "")
                
                return ModelResponse(output=text_out, thought_signature=thought_sig)

            except asyncio.TimeoutError:
                last_error = TimeoutError(f"Gemini API timed out after 120s (attempt {attempt + 1}/{max_retries})")
                logger.warning(f"HybridModelClient: Timeout on attempt {attempt + 1}/{max_retries}")
                # Backoff and retry
                delay = min(base_delay * (2 ** attempt), max_delay)
                await asyncio.sleep(delay)
                continue
                
            except Exception as e:
                last_error = e
                
                if _is_quota_error(e):
                    # Rotate API key and retry immediately
                    exhausted_key = self.key_manager.keys[self.key_manager.index]
                    self.key_manager.mark_exhausted(exhausted_key)
                    try:
                        self.key_manager.rotate_key()
                        logger.info(f"HybridModelClient: Key rotated after quota error (attempt {attempt + 1})")
                        continue  # retry with next key, no delay
                    except RuntimeError:
                        raise RuntimeError("All Gemini API keys exhausted; generation failed.")
                
                elif _is_transient(e):
                    # Exponential backoff for transient errors
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    logger.warning(
                        f"HybridModelClient: Transient error on attempt {attempt + 1}/{max_retries}: "
                        f"{str(e)[:80]}. Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)
                    continue
                    
                else:
                    # Non-transient error — fail fast
                    raise

        raise RuntimeError(
            f"Failed to generate after {max_retries} attempts. Last error: {last_error}"
        )

    async def generate_with_image(
        self, 
        prompt: str, 
        image_base64: str, 
        image_mime_type: str = "image/png",
        **kwargs
    ) -> str:
        """
        Send prompt with image to Gemini Vision for visual analysis.
        Includes exponential backoff for transient failures.
        
        Args:
            prompt: Text prompt describing what to analyze
            image_base64: Base64 encoded image data
            image_mime_type: MIME type of the image
            
        Returns:
            String response from the model
        """
        max_retries = max(len(self.key_manager.keys) + 2, 5)
        base_delay = 1.0
        max_delay = 30.0

        last_error = None
        for attempt in range(max_retries):
            client = self.key_manager.get_client()
            try:
                # Build multimodal content with image and text
                contents = [
                    {
                        "parts": [
                            {
                                "inline_data": {
                                    "mime_type": image_mime_type,
                                    "data": image_base64
                                }
                            },
                            {
                                "text": prompt
                            }
                        ]
                    }
                ]
                
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model='gemini-2.0-flash-exp',
                        contents=contents,
                        **kwargs
                    ),
                    timeout=120
                )
                
                return response.text

            except asyncio.TimeoutError:
                last_error = TimeoutError(f"Vision API timed out (attempt {attempt + 1}/{max_retries})")
                logger.warning(f"HybridModelClient: Vision timeout on attempt {attempt + 1}/{max_retries}")
                delay = min(base_delay * (2 ** attempt), max_delay)
                await asyncio.sleep(delay)
                continue

            except Exception as e:
                last_error = e
                
                if _is_quota_error(e):
                    exhausted_key = self.key_manager.keys[self.key_manager.index]
                    self.key_manager.mark_exhausted(exhausted_key)
                    try:
                        self.key_manager.rotate_key()
                        logger.info(f"HybridModelClient: Vision key rotated (attempt {attempt + 1})")
                        continue
                    except RuntimeError:
                        raise RuntimeError("All Gemini API keys exhausted; vision generation failed.")
                
                elif _is_transient(e):
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    logger.warning(
                        f"HybridModelClient: Vision transient error on attempt {attempt + 1}/{max_retries}: "
                        f"{str(e)[:80]}. Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)
                    continue
                    
                else:
                    raise
        
        raise RuntimeError(
            f"Failed to generate vision response after {max_retries} attempts. Last error: {last_error}"
        )
