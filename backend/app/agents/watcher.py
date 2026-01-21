# ACEA Sentinel - The Watcher Agent (REAL BROWSER TESTING)
# Uses Playwright to actually run and verify generated projects

import asyncio
import json
from pathlib import Path
from typing import Dict, Any, List

class WatcherAgent:
    def __init__(self):
        self.browser = None
        self.page = None
    
    async def verify_page(self, url: str) -> Dict[str, Any]:
        """
        REAL browser verification using Playwright.
        Opens the URL, captures screenshot, and checks for errors.
        """
        from app.core.socket_manager import SocketManager
        sm = SocketManager()
        
        errors = []
        console_logs = []
        screenshot_path = None
        
        try:
            from playwright.async_api import async_playwright
            
            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"Launching browser for {url}..."})
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()
                
                # Capture console messages
                page.on("console", lambda msg: console_logs.append({
                    "type": msg.type,
                    "text": msg.text
                }))
                
                # Capture page errors
                page.on("pageerror", lambda exc: errors.append(str(exc)))
                
                try:
                    # Navigate to URL with timeout
                    response = await page.goto(url, wait_until="networkidle", timeout=30000)
                    
                    if response is None or response.status >= 400:
                        errors.append(f"HTTP Error: {response.status if response else 'No response'}")
                    
                    # Wait a bit for any async rendering
                    await asyncio.sleep(2)
                    
                    # Take screenshot
                    screenshot_path = f"screenshots/{url.replace('http://', '').replace('/', '_')}.png"
                    Path("screenshots").mkdir(exist_ok=True)
                    await page.screenshot(path=screenshot_path, full_page=True)
                    
                    await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"Screenshot saved: {screenshot_path}"})
                    
                except Exception as nav_error:
                    errors.append(f"Navigation failed: {str(nav_error)}")
                
                await browser.close()
        
        except ImportError:
            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "⚠️ Playwright not installed. Skipping browser test."})
            return {
                "status": "SKIPPED",
                "reason": "Playwright not installed",
                "errors": [],
                "fix_this": False
            }
        
        except Exception as e:
            errors.append(f"Browser error: {str(e)}")
        
        # Analyze results
        console_errors = [log for log in console_logs if log["type"] == "error"]
        all_errors = errors + [err["text"] for err in console_errors]
        
        if all_errors:
            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"❌ Found {len(all_errors)} errors"})
            for err in all_errors[:3]:  # Show first 3 errors
                await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"  → {err[:100]}"})
            
            return {
                "status": "FAIL",
                "errors": all_errors,
                "console_logs": console_logs,
                "screenshot": screenshot_path,
                "fix_this": True
            }
        else:
            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "✅ Page loaded successfully!"})
            return {
                "status": "PASS",
                "errors": [],
                "console_logs": console_logs,
                "screenshot": screenshot_path,
                "fix_this": False
            }
    
    async def run_and_verify_project(self, project_path: str, project_id: str) -> Dict[str, Any]:
        """
        Full verification: Install deps, run server, open browser, check for errors.
        This is the REAL self-healing entry point.
        """
        from app.core.socket_manager import SocketManager
        from app.core.project_runner import ProjectRunner
        
        sm = SocketManager()
        runner = ProjectRunner(project_path)
        
        await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "Setting up project for verification..."})
        
        # Step 1: Setup dependencies
        setup_result = await runner.setup_frontend()
        if not setup_result["success"]:
            return {
                "status": "FAIL",
                "phase": "setup",
                "errors": [setup_result["error"]],
                "fix_this": True
            }
        
        await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "Dependencies installed. Starting server..."})
        
        # Step 2: Start server
        start_result = await runner.start_frontend()
        if not start_result["success"]:
            return {
                "status": "FAIL", 
                "phase": "startup",
                "errors": [start_result["error"]],
                "fix_this": True
            }
        
        await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"Server running at {start_result['url']}"})
        
        # Step 3: Verify in browser
        try:
            result = await self.verify_page(start_result["url"])
        finally:
            # Always cleanup
            runner.cleanup()
        
        return result
    
    async def quick_verify(self, project_id: str) -> Dict[str, Any]:
        """
        Quick verification without running the full server.
        Just checks if the static files are accessible via the backend mount.
        """
        from app.core.socket_manager import SocketManager
        sm = SocketManager()
        
        # The backend serves generated projects at /preview/{project_id}/
        # For Next.js apps, there's no index.html - we need to check the files exist
        
        from app.core.filesystem import BASE_PROJECTS_DIR
        project_path = BASE_PROJECTS_DIR / project_id / "frontend" / "app"
        
        if not project_path.exists():
            return {
                "status": "FAIL",
                "errors": ["Frontend app directory not found"],
                "fix_this": True
            }
        
        page_file = project_path / "page.tsx"
        if not page_file.exists():
            return {
                "status": "FAIL",
                "errors": ["Main page.tsx not found"],
                "fix_this": True
            }
        
        # Check for obvious syntax errors in the files
        errors = []
        for tsx_file in project_path.glob("*.tsx"):
            content = tsx_file.read_text(encoding='utf-8', errors='ignore')
            
            # Basic syntax checks
            if content.count('{') != content.count('}'):
                errors.append(f"{tsx_file.name}: Mismatched curly braces")
            if content.count('(') != content.count(')'):
                errors.append(f"{tsx_file.name}: Mismatched parentheses")
            if "\\n" in content:  # Escaped newlines (should be real newlines)
                errors.append(f"{tsx_file.name}: Contains escaped newlines (file format issue)")
        
        if errors:
            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"❌ Found {len(errors)} file issues"})
            return {
                "status": "FAIL",
                "errors": errors,
                "fix_this": True
            }
        
        await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "✅ Files validated successfully"})
        return {
            "status": "PASS",
            "errors": [],
            "fix_this": False
        }
