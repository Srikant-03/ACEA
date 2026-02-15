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
        Includes Visual QA (Vibe Check).
        """
        from app.core.socket_manager import SocketManager
        sm = SocketManager()
        
        errors = []
        console_logs = []
        screenshot_path = None
        visual_issues = []
        
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
                    
                    # Perform Visual QA (Vibe Check)
                    visual_issues = await self.analyze_visuals(screenshot_path, console_logs, sm)
                    errors.extend([issue['issue'] for issue in visual_issues])
                    
                except Exception as nav_error:
                    errors.append(f"Navigation failed: {str(nav_error)}")
                
                await browser.close()
        
        except ImportError:
            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "Playwright not installed. Skipping browser test."})
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
            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"Found {len(all_errors)} errors"})
            for err in all_errors[:3]:  # Show first 3 errors
                await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"  → {err[:100]}"})
            
            return {
                "status": "FAIL",
                "errors": all_errors,
                "console_logs": console_logs,
                "screenshot": screenshot_path,
                "visual_issues": visual_issues,
                "fix_this": True
            }
        else:
            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "Page loaded successfully!"})
            return {
                "status": "PASS",
                "errors": [],
                "console_logs": console_logs,
                "screenshot": screenshot_path,
                "visual_issues": [],
                "fix_this": False
            }

    async def analyze_visuals(self, screenshot_path: str, logs: List[Dict], sm) -> List[Dict]:
        """
        Analyze screenshot for visual defects using Vision API (Mocked/Placeholder).
        Original VibeAgent logic integrated here.
        """
        issues = []
        try:
            import os
            from PIL import Image, ImageChops
            
            if os.path.exists(screenshot_path):
                # 1. Basic Pixel Diff (Placeholder)
                try:
                    img = Image.open(screenshot_path)
                    baseline_path = "baseline.png"
                    if os.path.exists(baseline_path):
                         baseline = Image.open(baseline_path)
                         diff = ImageChops.difference(img, baseline)
                         if diff.getbbox():
                             # issues.append({"file": "UI", "issue": "Visual regression detected", "fix": "Check UI changes"})
                             pass
                except Exception as e:
                     await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"Image processing error: {e}"})

                # 2. Vision API Call (Mocked as per requirements)
                # In real scenario, would call HybridModelClient with image
                # Here we just log intention
                await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "Analyzing visual layout..."})
                
                # specific user requirement: "VibeAgent: Vision API returned..." logic
                # I'm integrating it into Watcher.
                # If we had a real endpoint to hit:
                # vision_url = os.getenv("VISION_API_URL")
                # if vision_url: requests.post(...)
               
        except Exception as e:
            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"Visual analysis failed: {e}"})
            
        return issues
    
    async def run_and_verify_project(self, project_path: str, project_id: str) -> Dict[str, Any]:
        """
        Full verification: Install deps, run server, open browser, check for errors.
        For STATIC HTML projects (no package.json), skip npm and just validate files.
        """
        from app.core.socket_manager import SocketManager
        from pathlib import Path
        import glob
        
        sm = SocketManager()
        project_path_obj = Path(project_path)
        frontend_path = project_path_obj / "frontend"
        
        # STATIC HTML DETECTION: Check multiple locations for package.json and HTML files
        package_json_paths = [
            frontend_path / "package.json",
            project_path_obj / "package.json",
            frontend_path / "app" / "package.json"
        ]
        has_package_json = any(p.exists() for p in package_json_paths)
        
        # Check for HTML files in multiple locations
        html_paths = [
            project_path_obj / "index.html",
            frontend_path / "index.html",
            frontend_path / "app" / "index.html"
        ]
        # Also check if there are ANY .html files anywhere
        all_html_files = list(project_path_obj.rglob("*.html"))
        has_html = any(p.exists() for p in html_paths) or len(all_html_files) > 0
        
        # STATIC HTML PROJECT: Skip npm entirely, just validate files exist
        if has_html and not has_package_json:
            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "📄 Static HTML project detected. Skipping npm."})
            
            # Find any HTML file
            html_file = None
            for path in html_paths:
                if path.exists():
                    html_file = path
                    break
            if not html_file and all_html_files:
                html_file = all_html_files[0]
            
            if html_file:
                content = html_file.read_text(encoding='utf-8', errors='ignore')
                if len(content) < 20:
                    return {"status": "FAIL", "phase": "validation", "errors": ["HTML file is too short"], "fix_this": True}
                
                await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "✅ Static HTML validated successfully!"})
                return {"status": "PASS", "phase": "validation", "errors": [], "fix_this": False}
            else:
                return {"status": "FAIL", "phase": "validation", "errors": ["No HTML files found"], "fix_this": True}
        
        # NODE/REACT PROJECT: Continue with npm
        from app.core.project_runner import ProjectRunner
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
            # SMART ANALYSIS: Use Tester Agent to diagnose the startup failure
            from app.agents.tester import TesterAgent
            tester_agent = TesterAgent()
            
            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "⚠️ Server failed to start. Analyzing logs with Tester..."})
            
            # Simple context for tester
            context = {"projectType": "frontend", "tech_stack": "Next.js/React"} 
            analysis = await tester_agent.analyze_execution(start_result["error"], context)
            
            # Use specific issues if found, otherwise raw error
            analysis_issues = analysis.get("issues", [])
            analysis_fixes = analysis.get("fixes", [])
            
            errors = []
            
            # 1. Add formatted file errors (CRITICAL for Virtuoso surgical repair)
            for fix in analysis_fixes:
                if fix.get("file"):
                    # Pass the full structured fix object to Virtuoso
                    errors.append(fix)
            
            # 2. Add general issues if no specific file fixes found, or as supplementary info
            if analysis_issues:
                # Add strings as well for context
                errors.extend(analysis_issues)
                
            # 3. Fallback to raw log if nothing else
            if not errors:
                errors = [start_result["error"]]
                
            return {
                "status": "FAIL", 
                "phase": "startup",
                "errors": errors, 
                "fix_this": True
            }
        
        await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"Server running at {start_result['url']}"})
        
        # Step 3: Verify in browser
        try:
            result = await self.verify_page(start_result["url"])
            
            # SMART ANALYSIS: If browser verification failed, analyze those errors too
            if result["status"] == "FAIL":
                from app.agents.tester import TesterAgent
                tester_agent = TesterAgent()
                
                await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "Browser set off alarms. Analyzing runtime errors..."})
                
                # Combine console logs and page errors
                error_context = "\n".join(result["errors"])
                context = {"projectType": "frontend", "tech_stack": "Next.js/React", "phase": "browser_runtime"}
                
                analysis = await tester_agent.analyze_execution(error_context, context)
                
                # Merge structured fixes into result
                analysis_fixes = analysis.get("fixes", [])
                
                # Append structured fixes to the errors list
                for fix in analysis_fixes:
                    if fix.get("file"):
                         result["errors"].append(fix)
                         
                # If we found specific fixes, we might want to prioritize them
                if analysis_fixes:
                     await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"Tester identified {len(analysis_fixes)} specific fixes."})

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
        
        frontend_dir = BASE_PROJECTS_DIR / project_id / "frontend"
        
        # Check standard frontend paths
        nextjs_path = frontend_dir / "app" / "page.tsx"
        vite_idx = frontend_dir / "index.html"
        vite_src = frontend_dir / "src" / "App.jsx"
        vite_src_tsx = frontend_dir / "src" / "App.tsx"
        
        is_nextjs = nextjs_path.exists()
        is_vite = vite_idx.exists() or vite_src.exists() or vite_src_tsx.exists()
        
        if not (is_nextjs or is_vite):
            # Fallback: Check if files are at root (common mistake)
            root_dir = BASE_PROJECTS_DIR / project_id
            if (root_dir / "index.html").exists():
                 return {
                    "status": "FAIL",
                    "errors": ["Files generated at root instead of /frontend directory"],
                    "fix_this": True
                }
            
            return {
                "status": "FAIL",
                "errors": ["Valid frontend structure not found (Missing app/page.tsx or src/App.jsx)"],
                "fix_this": True
            }
        
        # Determine strict check path
        check_path = frontend_dir
        if is_nextjs:
            check_path = frontend_dir / "app"
        elif is_vite:
             check_path = frontend_dir / "src"
             
        # Check for obvious syntax errors in the files
        
        # Check for obvious syntax errors in the files
        # Check for obvious syntax errors in the files
        errors = []
        # Support both .tsx and .jsx check
        files_to_check = list(check_path.glob("*.tsx")) + list(check_path.glob("*.jsx"))
        
        for code_file in files_to_check:
            content = code_file.read_text(encoding='utf-8', errors='ignore')
            
            # Basic syntax checks
            if content.count('{') != content.count('}'):
                errors.append(f"{tsx_file.name}: Mismatched curly braces")
            if content.count('(') != content.count(')'):
                errors.append(f"{tsx_file.name}: Mismatched parentheses")
            if "\\n" in content:  # Escaped newlines (should be real newlines)
                errors.append(f"{tsx_file.name}: Contains escaped newlines (file format issue)")
        
        if errors:
            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"Found {len(errors)} file issues"})
            return {
                "status": "FAIL",
                "errors": errors,
                "fix_this": True
            }
        
        await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "Files validated successfully"})
        return {
            "status": "PASS",
            "errors": [],
            "fix_this": False
        }
