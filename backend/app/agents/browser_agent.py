# app/agents/browser_agent.py
from playwright.async_api import async_playwright
from app.agents.state import AgentState
import asyncio

class BrowserAgent:
    async def run(self, state: AgentState) -> AgentState:
        """
        Navigate to the project's preview URL, run validations, and 
        update state.
        - state.preview_url should contain the HTTP URL of the app.
        - On each step, capture screenshot and console logs.
        """
        # Ensure preview_url exists, or try to infer it/mock it
        # The prompt implies state.preview_url exists. 
        # But AgentState definition in Dev 1 task didn't explicitly have preview_url.
        # "state.preview_url should contain..." - maybe it's added by previous steps or I should add it to dataclass?
        # User defined AgentState in Dev 1, but Dev 2 prompt references state.preview_url.
        # I will assume it's dynamically added or I should add it if missing?
        # Standard Python objects allow dynamic attributes if not slotted? Dataclasses don't.
        # But I added `get` / `__getitem__` to AgentState which uses getattr.
        # I will check if I can access it safely.
        
        url = getattr(state, "preview_url", None)
        if not url:
            # Fallback or error?
            state.messages.append("BrowserAgent: No preview_url found in state.")
            return state

        state.messages.append(f"BrowserAgent starting. URL: {url}")
        
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()
                
                console_errors = []
                page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
                
                try:
                    await page.goto(url, timeout=60000)
                    # Wait for page to load fully (customize as needed)
                    await page.wait_for_load_state("networkidle")
                except Exception as e:
                    state.messages.append(f"BrowserAgent: Navigation failed: {e}")
                    # Continue to try screenshot anyway?
                
                # Take full-page screenshot
                # Ensure directory exists?
                import os
                os.makedirs("screenshots", exist_ok=True)
                
                step_num = len(state.screenshot_paths) + 1
                screenshot_path = f"screenshots/{state.agent_id}_step_{step_num}.png"
                
                try:
                    await page.screenshot(path=screenshot_path, full_page=True)
                    state.screenshot_paths[step_num] = screenshot_path
                except Exception as e:
                     state.messages.append(f"BrowserAgent: Screenshot failed: {e}")

                # Log console errors
                if console_errors:
                    for error in console_errors:
                        state.messages.append(f"Console error: {error}")
                
                await browser.close()
                
                # Placeholder for anomaly detection on screenshot (optional):
                # If pixel diff detects issue, add to state.issues (VibeAgent will also check)
                
                state.messages.append("BrowserAgent finished.")
                
        except Exception as e:
            state.messages.append(f"BrowserAgent failed: {e}")
            
        return state
