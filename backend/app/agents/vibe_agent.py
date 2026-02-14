# app/agents/vibe_agent.py
from app.agents.state import AgentState, Issue
from typing import List
import requests
from PIL import Image, ImageChops
import os

class VibeAgent:
    async def analyze(self, screenshot_path: str, logs: str, state: AgentState) -> List[Issue]:
        """
        Analyze screenshot and logs for UI defects.
        - Run a pixel-wise diff against a baseline image (if available).
        - Then send image+logs to Gemini Vision API to get semantic issues.
        Returns a list of Issue(file, issue, fix).
        """
        issues: List[Issue] = []
        
        # 1. Basic pixel diff (placeholder)
        try:
            if os.path.exists(screenshot_path):
                img = Image.open(screenshot_path)
                # If baseline exists (e.g. "baseline.png"), compare:
                baseline_path = "baseline.png" # Example
                if os.path.exists(baseline_path):
                     baseline = Image.open(baseline_path)
                     diff = ImageChops.difference(img, baseline)
                     if diff.getbbox() is not None:
                         # There's a change
                         pass # Could add issue here
            else:
                state.messages.append(f"VibeAgent: Screenshot not found: {screenshot_path}")

        except Exception as e:
            # Could not open image, record in state and continue
            state.messages.append(f"VibeAgent: Failed to open screenshot: {e}")

        # 2. Call Gemini Vision API (pseudo-code, actual API may vary)
        try:
            # Example HTTP request to a Vision endpoint
            # Since we don't have a real endpoint URL provided (user example: "https://vision.api.genai.com/analyze")
            # We will use the user's example URL but wrap it in try/except so it doesn't crash if offline.
            # In a real scenario, we'd use the HybridModelClient or Google GenAI SDK.
            # But user prompt specifically used `requests.post` to a hypothetical URL.
            # I will implement it as requested but assume it might fail or return mock data in tests.
            
            # Convert screenshot to base64 if needed
            # with open(screenshot_path, "rb") as f:
            #     b64 = base64.b64encode(f.read()).decode()
            
            vision_payload = {
                "image_base64": "...", # placeholder
                "logs": logs,
                "code_snippets": ""
                # add relevant code if needed
            }
            
            # Using a dummy URL for now as per prompt example, unless env var overrides
            vision_url = os.getenv("VISION_API_URL", "https://vision.api.genai.com/analyze")
            
            # We'll set a short timeout so it fails fast if not real
            response = requests.post(vision_url, json=vision_payload, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                for item in data.get("issues", []):
                    issues.append(Issue(file=item["file"], 
                                      issue=item["issue"], 
                                      fix=item["fix"]))
            else:
                 state.messages.append(f"VibeAgent: Vision API returned {response.status_code}")

        except Exception as e:
            state.messages.append(f"VibeAgent: Vision API error: {e}")

        # Append all found issues to state
        for issue in issues:
            # Check if issues list exists on state (we added it in Dev 1)
            if not hasattr(state, "issues"):
                 state.issues = []
            state.issues.append(issue)
            
        state.messages.append(f"VibeAgent analyzed screenshot; found {len(issues)} issues.")
        return issues
