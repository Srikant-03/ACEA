# app/core/HybridModelClient.py
import asyncio
import base64
from google.genai import Client as GeminiClient, errors as genai_exceptions
from app.core.key_manager import KeyManager
from app.core.model_response import ModelResponse

class HybridModelClient:
    def __init__(self, key_manager: KeyManager):
        self.key_manager = key_manager

    async def generate(self, prompt: str, **kwargs) -> ModelResponse:
        """
        Send prompt to Gemini, auto-rotating keys on rate-limit errors.
        Returns ModelResponse(output: str, thought_signature: str).
        """
        attempts = 0
        max_retries = len(self.key_manager.keys) + 1 # Try all keys at least once if needed

        while attempts < max_retries:
            client = self.key_manager.get_client()
            try:
                response = await client.aio.models.generate_content(model='gemini-2.0-flash-exp', contents=prompt, **kwargs)
                
                text_out = response.text
                thought_sig = getattr(response, 'thought_signature', "")
                
                return ModelResponse(output=text_out, thought_signature=thought_sig)

            except Exception as e:
                is_quota_error = "RESOURCE_EXHAUSTED" in str(e) or getattr(e, 'status_code', 0) == 429
                
                if is_quota_error:
                    exhausted_key = self.key_manager.keys[self.key_manager.index]
                    self.key_manager.mark_exhausted(exhausted_key)
                    try:
                        self.key_manager.rotate_key()
                        attempts += 1
                        continue # retry with next key
                    except RuntimeError:
                        raise RuntimeError("All Gemini API keys exhausted; generation failed.")
                else:
                    raise

    async def generate_with_image(
        self, 
        prompt: str, 
        image_base64: str, 
        image_mime_type: str = "image/png",
        **kwargs
    ) -> str:
        """
        Send prompt with image to Gemini Vision for visual analysis.
        
        Args:
            prompt: Text prompt describing what to analyze
            image_base64: Base64 encoded image data
            image_mime_type: MIME type of the image (e.g., "image/png", "image/jpeg")
            
        Returns:
            String response from the model
        """
        attempts = 0
        max_retries = len(self.key_manager.keys) + 1

        while attempts < max_retries:
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
                
                # Use vision-capable model
                response = await client.aio.models.generate_content(
                    model='gemini-2.0-flash-exp',  # Vision-capable model
                    contents=contents,
                    **kwargs
                )
                
                return response.text

            except Exception as e:
                is_quota_error = "RESOURCE_EXHAUSTED" in str(e) or getattr(e, 'status_code', 0) == 429
                
                if is_quota_error:
                    exhausted_key = self.key_manager.keys[self.key_manager.index]
                    self.key_manager.mark_exhausted(exhausted_key)
                    try:
                        self.key_manager.rotate_key()
                        attempts += 1
                        continue
                    except RuntimeError:
                        raise RuntimeError("All Gemini API keys exhausted; vision generation failed.")
                else:
                    raise
        
        raise RuntimeError("Failed to generate vision response after all retries")
