# ACEA Sentinel - The Watcher Agent (REAL BROWSER TESTING)
# Uses Playwright to actually run and verify generated projects
# Enhanced with Gemini Vision integration for semantic UI debugging

import asyncio
import json
import os
import base64
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class VisualArtifacts:
    """Comprehensive visual capture from browser testing."""
    above_fold_screenshot: Optional[str] = None  # Path to above-fold screenshot
    full_page_screenshot: Optional[str] = None   # Path to full-page screenshot
    console_errors: List[Dict] = field(default_factory=list)
    console_warnings: List[Dict] = field(default_factory=list)
    network_failures: List[Dict] = field(default_factory=list)
    dom_summary: Optional[Dict] = None  # Headings, interactive elements, etc.
    page_metrics: Optional[Dict] = None  # Performance metrics
    gemini_analysis: Optional[Dict] = None  # Gemini Vision analysis result
    captured_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "above_fold_screenshot": self.above_fold_screenshot,
            "full_page_screenshot": self.full_page_screenshot,
            "console_errors": self.console_errors,
            "console_warnings": self.console_warnings,
            "network_failures": self.network_failures,
            "dom_summary": self.dom_summary,
            "page_metrics": self.page_metrics,
            "gemini_analysis": self.gemini_analysis,
            "captured_at": self.captured_at,
        }


class WatcherAgent:
    """
    Enhanced Watcher Agent with comprehensive visual debugging capabilities.
    
    Features:
    - Headless Chromium via Playwright
    - Above-the-fold and full-page screenshot capture
    - Console error and network failure tracking
    - DOM summary extraction
    - Gemini Vision integration for semantic UI analysis
    """
    
    def __init__(self):
        self.browser = None
        self.page = None
        self._vision_client = None
    
    async def _get_vision_client(self):
        """Get the HybridModelClient for vision analysis."""
        if self._vision_client is None:
            try:
                from app.core.HybridModelClient import HybridModelClient
                from app.core.key_manager import KeyManager
                import os
                
                api_keys = os.getenv("GEMINI_API_KEYS", "").split(",")
                if api_keys and api_keys[0]:
                    key_manager = KeyManager(api_keys)
                    self._vision_client = HybridModelClient(key_manager)
            except Exception as e:
                print(f"Warning: Could not initialize vision client: {e}")
        return self._vision_client
    
    async def capture_visual_artifacts(self, url: str) -> VisualArtifacts:
        """
        Comprehensive visual capture from a URL.
        
        Captures:
        - Above-the-fold screenshot (viewport only)
        - Full-page screenshot
        - Console errors and warnings
        - Network failures
        - DOM summary (headings, buttons, forms, links)
        - Page performance metrics
        """
        from app.core.socket_manager import SocketManager
        sm = SocketManager()
        
        artifacts = VisualArtifacts()
        
        try:
            from playwright.async_api import async_playwright
            
            await sm.emit("agent_log", {
                "agent_name": "WATCHER", 
                "message": f"Capturing visual artifacts from {url}..."
            })
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    device_scale_factor=1
                )
                page = await context.new_page()
                
                # Track console messages
                def on_console(msg):
                    entry = {
                        "type": msg.type,
                        "text": msg.text,
                        "timestamp": datetime.now().isoformat()
                    }
                    if msg.type == "error":
                        artifacts.console_errors.append(entry)
                    elif msg.type == "warning":
                        artifacts.console_warnings.append(entry)
                
                page.on("console", on_console)
                
                # Track page errors
                page.on("pageerror", lambda exc: artifacts.console_errors.append({
                    "type": "exception",
                    "text": str(exc),
                    "timestamp": datetime.now().isoformat()
                }))
                
                # Track network failures
                page.on("requestfailed", lambda req: artifacts.network_failures.append({
                    "url": req.url,
                    "method": req.method,
                    "failure": req.failure,
                    "timestamp": datetime.now().isoformat()
                }))
                
                try:
                    # Navigate with network idle
                    response = await page.goto(url, wait_until="networkidle", timeout=30000)
                    
                    # Wait for any async rendering
                    await asyncio.sleep(2)
                    
                    # Create screenshots directory
                    screenshots_dir = Path("screenshots")
                    screenshots_dir.mkdir(exist_ok=True)
                    
                    # Generate unique filename base
                    safe_url = url.replace("http://", "").replace("https://", "").replace("/", "_")[:50]
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    base_name = f"{safe_url}_{timestamp}"
                    
                    # 1. Above-the-fold screenshot (viewport only)
                    above_fold_path = screenshots_dir / f"{base_name}_above_fold.png"
                    await page.screenshot(path=str(above_fold_path), full_page=False)
                    artifacts.above_fold_screenshot = str(above_fold_path)
                    
                    # 2. Full-page screenshot
                    full_page_path = screenshots_dir / f"{base_name}_full_page.png"
                    await page.screenshot(path=str(full_page_path), full_page=True)
                    artifacts.full_page_screenshot = str(full_page_path)
                    
                    await sm.emit("agent_log", {
                        "agent_name": "WATCHER",
                        "message": f"Screenshots saved: {above_fold_path.name}, {full_page_path.name}"
                    })
                    
                    # 3. Extract DOM summary
                    artifacts.dom_summary = await self._extract_dom_summary(page)
                    
                    # 4. Get performance metrics
                    artifacts.page_metrics = await self._get_page_metrics(page)
                    
                except Exception as nav_error:
                    artifacts.console_errors.append({
                        "type": "navigation_error",
                        "text": str(nav_error),
                        "timestamp": datetime.now().isoformat()
                    })
                
                await browser.close()
                
        except ImportError:
            await sm.emit("agent_log", {
                "agent_name": "WATCHER",
                "message": "Playwright not installed. Skipping visual capture."
            })
        except Exception as e:
            artifacts.console_errors.append({
                "type": "capture_error",
                "text": str(e),
                "timestamp": datetime.now().isoformat()
            })
        
        return artifacts
    
    async def _extract_dom_summary(self, page) -> Dict[str, Any]:
        """Extract a summary of the page DOM for semantic analysis."""
        try:
            summary = await page.evaluate('''() => {
                const result = {
                    title: document.title,
                    headings: [],
                    buttons: [],
                    links: [],
                    forms: [],
                    images: [],
                    interactive_elements: []
                };
                
                // Headings
                document.querySelectorAll('h1, h2, h3').forEach(h => {
                    result.headings.push({
                        level: h.tagName.toLowerCase(),
                        text: h.innerText.slice(0, 100)
                    });
                });
                
                // Buttons
                document.querySelectorAll('button, [role="button"], input[type="submit"]').forEach(b => {
                    result.buttons.push({
                        text: b.innerText?.slice(0, 50) || b.value?.slice(0, 50) || '',
                        disabled: b.disabled
                    });
                });
                
                // Links
                document.querySelectorAll('a[href]').forEach(a => {
                    result.links.push({
                        text: a.innerText?.slice(0, 50) || '',
                        href: a.href?.slice(0, 100) || ''
                    });
                });
                
                // Forms
                document.querySelectorAll('form').forEach(f => {
                    result.forms.push({
                        action: f.action || '',
                        method: f.method || 'get',
                        inputs: f.querySelectorAll('input, textarea, select').length
                    });
                });
                
                // Images
                document.querySelectorAll('img').forEach(img => {
                    result.images.push({
                        alt: img.alt || '',
                        src: img.src?.slice(0, 100) || '',
                        width: img.naturalWidth,
                        height: img.naturalHeight
                    });
                });
                
                // Interactive elements count
                result.interactive_elements = document.querySelectorAll(
                    'button, a, input, select, textarea, [onclick], [role="button"]'
                ).length;
                
                return result;
            }''')
            return summary
        except Exception as e:
            return {"error": str(e)}
    
    async def _get_page_metrics(self, page) -> Dict[str, Any]:
        """Get page performance metrics."""
        try:
            metrics = await page.evaluate('''() => {
                const perf = performance.getEntriesByType('navigation')[0] || {};
                return {
                    dom_content_loaded: perf.domContentLoadedEventEnd - perf.navigationStart || null,
                    load_complete: perf.loadEventEnd - perf.navigationStart || null,
                    first_paint: performance.getEntriesByName('first-paint')[0]?.startTime || null,
                    first_contentful_paint: performance.getEntriesByName('first-contentful-paint')[0]?.startTime || null
                };
            }''')
            return metrics
        except Exception as e:
            return {"error": str(e)}
    
    async def analyze_with_gemini_vision(
        self,
        artifacts: VisualArtifacts,
        context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Analyze visual artifacts using Gemini Vision for semantic UI debugging.
        
        Returns analysis of:
        - Layout issues
        - Visual regressions
        - Accessibility concerns
        - Design consistency
        - UI/UX problems
        """
        from app.core.socket_manager import SocketManager
        sm = SocketManager()
        
        client = await self._get_vision_client()
        if not client:
            return {
                "status": "skipped",
                "reason": "Vision client not available"
            }
        
        # Prefer above-fold screenshot for faster analysis
        screenshot_path = artifacts.above_fold_screenshot or artifacts.full_page_screenshot
        if not screenshot_path or not os.path.exists(screenshot_path):
            return {
                "status": "error",
                "reason": "No screenshot available for analysis"
            }
        
        try:
            await sm.emit("agent_log", {
                "agent_name": "WATCHER",
                "message": "Analyzing UI with Gemini Vision..."
            })
            
            # Read and encode screenshot
            with open(screenshot_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
            
            # Build analysis prompt
            dom_info = json.dumps(artifacts.dom_summary, indent=2) if artifacts.dom_summary else "N/A"
            console_errors = json.dumps(artifacts.console_errors[:5], indent=2) if artifacts.console_errors else "None"
            
            prompt = f"""Analyze this web application screenshot for UI/UX issues.

Context:
- DOM Summary: {dom_info}
- Console Errors: {console_errors}
- Project Context: {json.dumps(context) if context else 'N/A'}

Please analyze the following aspects and report any issues:

1. **Layout Issues**: Overlapping elements, misalignment, broken layouts
2. **Visual Defects**: Missing images, broken styling, rendering problems
3. **Accessibility**: Color contrast, text readability, missing labels
4. **UI/UX Problems**: Confusing navigation, poor visual hierarchy, inconsistent styling
5. **Responsiveness**: Clipping, overflow, spacing issues

Respond in JSON format:
{{
    "overall_quality": "good" | "acceptable" | "needs_work" | "broken",
    "issues": [
        {{
            "category": "layout|visual|accessibility|ux|responsiveness",
            "severity": "critical|warning|info",
            "description": "what is wrong",
            "suggestion": "how to fix it",
            "location": "where on the page"
        }}
    ],
    "positive_aspects": ["list of good things about the UI"],
    "summary": "one-line summary of the overall UI quality"
}}"""

            # Call Gemini with vision
            response = await client.generate_with_image(
                prompt=prompt,
                image_base64=image_data,
                image_mime_type="image/png"
            )
            
            # Parse response
            try:
                # Try to extract JSON from response
                if "```json" in response:
                    json_str = response.split("```json")[1].split("```")[0].strip()
                elif "```" in response:
                    json_str = response.split("```")[1].split("```")[0].strip()
                else:
                    json_str = response.strip()
                
                analysis = json.loads(json_str)
                artifacts.gemini_analysis = analysis
                
                # Log summary
                issue_count = len(analysis.get("issues", []))
                quality = analysis.get("overall_quality", "unknown")
                await sm.emit("agent_log", {
                    "agent_name": "WATCHER",
                    "message": f"Vision analysis: {quality} ({issue_count} issues found)"
                })
                
                return {
                    "status": "success",
                    "analysis": analysis
                }
                
            except json.JSONDecodeError:
                return {
                    "status": "success",
                    "analysis": {"raw_response": response}
                }
                
        except Exception as e:
            await sm.emit("agent_log", {
                "agent_name": "WATCHER",
                "message": f"Vision analysis failed: {e}"
            })
            return {
                "status": "error",
                "reason": str(e)
            }
    
    async def verify_page(self, url: str) -> Dict[str, Any]:
        """
        REAL browser verification using Playwright.
        Opens the URL, captures screenshot, and checks for errors.
        Includes Visual QA (Vibe Check) with Gemini Vision.
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
                    
                    # Perform Visual QA (Vibe Check) - Enhanced with Gemini Vision
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
        Analyze screenshot for visual defects using Gemini Vision.
        Enhanced from placeholder to use real vision API.
        """
        issues = []
        try:
            if os.path.exists(screenshot_path):
                await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "Analyzing visual layout with Gemini Vision..."})
                
                # Create artifacts for vision analysis
                artifacts = VisualArtifacts(
                    above_fold_screenshot=screenshot_path,
                    console_errors=[{"type": log["type"], "text": log["text"]} for log in logs if log["type"] == "error"]
                )
                
                # Run Gemini Vision analysis
                result = await self.analyze_with_gemini_vision(artifacts)
                
                if result.get("status") == "success":
                    analysis = result.get("analysis", {})
                    
                    # Convert Gemini issues to our format
                    for issue in analysis.get("issues", []):
                        if issue.get("severity") in ["critical", "warning"]:
                            issues.append({
                                "file": "UI",
                                "issue": f"[{issue.get('category', 'visual')}] {issue.get('description', '')}",
                                "fix": issue.get("suggestion", "Review UI layout")
                            })
                    
                    # Log summary
                    quality = analysis.get("overall_quality", "unknown")
                    await sm.emit("agent_log", {
                        "agent_name": "WATCHER",
                        "message": f"Visual QA: {quality} - {analysis.get('summary', 'Analysis complete')}"
                    })
                else:
                    await sm.emit("agent_log", {
                        "agent_name": "WATCHER",
                        "message": f"Vision analysis: {result.get('reason', 'skipped')}"
                    })
               
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
                errors.append(f"{code_file.name}: Mismatched curly braces")
            if content.count('(') != content.count(')'):
                errors.append(f"{code_file.name}: Mismatched parentheses")
            if "\\n" in content:  # Escaped newlines (should be real newlines)
                errors.append(f"{code_file.name}: Contains escaped newlines (file format issue)")
        
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
