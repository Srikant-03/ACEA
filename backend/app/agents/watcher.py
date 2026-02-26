# ACEA Sentinel - The Watcher Agent (REAL BROWSER TESTING)
# Uses Playwright to actually run and verify generated projects
# Enhanced with Gemini Vision integration for semantic UI debugging

import asyncio
import json
import os
import sys
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
        
        On Windows, delegates to a subprocess to avoid event loop issues.
        """
        from app.core.socket_manager import SocketManager
        sm = SocketManager()
        
        await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"Launching browser for {url}..."})
        
        # On Windows, use subprocess-based runner to avoid asyncio event loop issues
        if sys.platform == "win32":
            return await self._verify_page_subprocess(url, sm)
        else:
            return await self._verify_page_direct(url, sm)
    
    async def _verify_page_subprocess(self, url: str, sm) -> Dict[str, Any]:
        """Run Playwright in a separate process (Windows fix for ProactorEventLoop)."""
        import subprocess
        
        try:
            python_exe = sys.executable
            runner_module = "app.core.playwright_runner"
            
            await sm.emit("agent_log", {
                "agent_name": "WATCHER",
                "message": "Using subprocess runner for Windows compatibility..."
            })
            
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    [python_exe, "-m", runner_module, url, "--timeout", "30"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/
                )
            )
            
            if result.returncode != 0:
                error_msg = result.stderr.strip()[:200] if result.stderr else "Unknown error"
                await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"Browser runner error: {error_msg}"})
                return {
                    "status": "FAIL",
                    "errors": [f"Playwright runner failed: {error_msg}"],
                    "console_logs": [],
                    "screenshot": None,
                    "visual_issues": [],
                    "fix_this": False  # Runner failure is not a code generation issue
                }
            
            import json as _json
            report = _json.loads(result.stdout.strip())
            
            # Run visual QA on screenshot if available
            if report.get("screenshot") and report["status"] == "PASS":
                try:
                    visual_issues = await self.analyze_visuals(
                        report["screenshot"], report.get("console_logs", []), sm
                    )
                    if visual_issues:
                        report["visual_issues"] = visual_issues
                        report["errors"].extend([issue['issue'] for issue in visual_issues])
                        if report["errors"]:
                            report["status"] = "FAIL"
                            report["fix_this"] = True
                except Exception as vis_err:
                    await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"Visual QA skipped: {str(vis_err)[:60]}"})
            
            # Emit results
            if report["status"] == "PASS":
                await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "Page loaded successfully!"})
            else:
                await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"Found {len(report.get('errors', []))} errors"})
                for err in report.get("errors", [])[:3]:
                    await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"  → {str(err)[:100]}"})
            
            return report
            
        except subprocess.TimeoutExpired:
            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "⚠️ Browser verification timed out"})
            return {
                "status": "FAIL",
                "errors": ["Browser verification timed out (60s)"],
                "console_logs": [],
                "screenshot": None,
                "visual_issues": [],
                "fix_this": False
            }
        except Exception as e:
            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"⚠️ Browser runner error: {str(e)[:80]}"})
            return {
                "status": "SKIPPED",
                "reason": str(e),
                "errors": [],
                "fix_this": False
            }
    
    async def _verify_page_direct(self, url: str, sm) -> Dict[str, Any]:
        """Direct Playwright execution (non-Windows or when subprocess is not needed)."""
        errors = []
        console_logs = []
        screenshot_path = None
        visual_issues = []
        
        try:
            from playwright.async_api import async_playwright
            
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
                    
                    # Visual QA
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
            err_msg = str(e) or type(e).__name__
            errors.append(f"Browser error: {err_msg}")
        
        # Analyze results
        console_errors = [log for log in console_logs if log["type"] == "error"]
        all_errors = errors + [err["text"] for err in console_errors]
        
        if all_errors:
            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"Found {len(all_errors)} errors"})
            for err in all_errors[:3]:
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
        
        # --- 1. DETECT EXECUTION CONFIGURATION ---
        from app.core.filesystem import read_project_files
        from app.core.project_runner import ProjectRunner
        
        # Create runner early so we can use its port
        runner = ProjectRunner(project_path)
        port = runner.frontend_port  # 3001 by default — avoids conflict with frontend dev server
        
        # Try to load blueprint for authoritative type
        blueprint = {}
        try:
            blueprint_path = project_path_obj / "blueprint.json"
            if blueprint_path.exists():
                blueprint = json.loads(blueprint_path.read_text())
        except:
            pass
            
        # Helper to detect files (mirroring E2B logic)
        files = {str(p.relative_to(project_path_obj)): "" for p in project_path_obj.rglob("*") if p.is_file()}
        
        # Reuse E2B service logic for consistency (or duplicate slightly if import is hard)
        # We will duplicate slightly to avoid circular dependency with Service Layer
        
        architect_type = blueprint.get("project_type", "dynamic")
        
        # Configuration Defaults
        install_cmd = "npm install"
        run_cmd = "npm run dev"
        
        # A. Check for startup_script_or_command file (authoritative if present)
        startup_file = project_path_obj / "startup_script_or_command"
        if startup_file.exists():
            custom_cmd = startup_file.read_text(encoding="utf-8", errors="ignore").strip()
            if custom_cmd:
                run_cmd = custom_cmd
                await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"🔹 Using startup command: {custom_cmd}"})
        
        # B. Check for package.json scripts to pick best run command
        frontend_pkg = runner.frontend_path / "package.json"
        pkg_scripts = {}
        if frontend_pkg.exists():
            try:
                pkg_data = json.loads(frontend_pkg.read_text(encoding="utf-8", errors="ignore"))
                pkg_scripts = pkg_data.get("scripts", {})
            except Exception:
                pass
        
        # STATIC
        if architect_type == "static":
            install_cmd = ""
            run_cmd = f"python3 -m http.server {port} --directory frontend"
            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "🔹 Detected STATIC project (explicit)."})
            
        elif any("vite.config" in f for f in files):
             await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "🔹 Detected VITE project."})
             run_cmd = "npm run dev"
             
        elif any("next.config" in f for f in files):
             await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "🔹 Detected NEXT.JS project."})
             run_cmd = "npm run dev"
             
        elif any("requirements.txt" in f for f in files):
             await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "🔹 Detected PYTHON project."})
             install_cmd = "pip install -r requirements.txt"
             # Try to guess run command
             if any("main.py" in f for f in files):
                 port = 8000
                 runner.frontend_port = port
                 run_cmd = f"uvicorn main:app --reload --host 0.0.0.0 --port {port}"
             elif any("app.py" in f for f in files):
                 port = 5000
                 runner.frontend_port = port
                 run_cmd = "python app.py"
             else:
                 run_cmd = "python main.py"
        
        elif any("Cargo.toml" in f for f in files):
             await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "🔹 Detected RUST project."})
             install_cmd = "cargo build"
             run_cmd = "cargo run"
             port = 3000 # Default for many Rust frameworks, runner handles env var
             runner.frontend_port = port

        elif any("Gemfile" in f for f in files):
             await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "🔹 Detected RUBY/RAILS project."})
             install_cmd = "bundle install"
             run_cmd = "rails server -b 0.0.0.0"
             port = 3000
             runner.frontend_port = port

        elif any("composer.json" in f for f in files):
             await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "🔹 Detected PHP/LARAVEL project."})
             install_cmd = "composer install"
             if any("artisan" in f for f in files):
                 run_cmd = "php artisan serve --host=0.0.0.0"
             else:
                 run_cmd = "php -S 0.0.0.0:8000"
             port = 8000
             runner.frontend_port = port
        
        elif any(f.endswith(".csproj") for f in files):
             await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "🔹 Detected .NET project."})
             install_cmd = "dotnet restore"
             run_cmd = "dotnet run"
             # Port handled via ASPNETCORE_URLS in runner
             port = 5000
             runner.frontend_port = port

        elif any("CMakeLists.txt" in f for f in files):
             await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "🔹 Detected C++ (CMake) project."})
             # Build process for C++ is multi-step
             install_cmd = "mkdir -p build && cd build && cmake .. && make"
             # Naive assumption: executable is named 'main' or 'app'
             # Ideally Architect should specify this in startup_script_or_command
             run_cmd = "./build/main" 
             port = 8080
             runner.frontend_port = port
        
        elif any(f.endswith("server.js") or f.endswith("index.js") or f.endswith("app.js") for f in files):
             # Express.js / vanilla Node.js server
             await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "🔹 Detected NODE/EXPRESS project."})
             # Pick the best npm script: prefer "dev", fall back to "start"
             if "dev" in pkg_scripts:
                 run_cmd = "npm run dev"
             elif "start" in pkg_scripts:
                 run_cmd = "npm start"
             else:
                 # Direct fallback: run server.js
                 server_file = None
                 for f in files:
                     if f.endswith("server.js"):
                         server_file = f
                         break
                 if server_file:
                     run_cmd = f"node {server_file.split('/')[-1]}"
                 else:
                     run_cmd = "node index.js"
        
        else:
             await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "🔹 Defaulting to NODE/DYNAMIC project."})
             # Fallback: use dev if present, else start
             if "dev" not in pkg_scripts and "start" in pkg_scripts:
                 run_cmd = "npm start"

        
        # --- 2. EXECUTE PROJECT ---
        try:
            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "🚀 Starting Execution Bootstrap..."})
            
            # Step A: Setup
            if install_cmd:
                setup_result = await runner.setup_frontend(install_cmd)
                if not setup_result["success"]:
                    err_msg = setup_result["error"]
                    # If tool is missing, skip verification (don't fail)
                    if setup_result.get("code") == "MISSING_TOOL":
                        await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"⚠️ Skipped Verification: {err_msg}"})
                        return {"status": "SKIPPED", "phase": "setup", "errors": [f"Skipped: {err_msg} (Please install tool to verify)"], "fix_this": False}
                    
                    await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"❌ Setup Failed: {err_msg}"})
                    return {"status": "FAIL", "phase": "setup", "errors": [f"Setup Failed ({install_cmd}): {err_msg}"], "fix_this": True}
            
            # Step B: Start Server
            start_result = await runner.start_frontend(run_cmd)
            port = start_result.get("port", port) # Update port if runner assigned one
            
            if not start_result["success"]:
                err_msg = start_result["error"]
                await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"❌ Startup Failed: {err_msg}"})
                return {"status": "FAIL", "phase": "startup", "errors": [f"Startup Failed ({run_cmd}): {err_msg}"], "fix_this": True}

            url = start_result.get("url", f"http://localhost:{port}")
            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"✅ Server running at {url}"})
            
            # Notify frontend to auto-show preview
            await sm.emit("preview_ready", {
                "url": url,
                "project_id": project_id,
                "port": port
            })
            
            # --- 3. PHASE 0: SANITY CHECK ---
            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "Phase 0: Runtime Readiness Check..."})
            
            # Simple HTTP availability check with RETRY
            import httpx
            import asyncio
            connected = False
            last_error = ""
            
            # Increase timeout to 60s for compiled languages (Rust/C++)
            for attempt in range(12):  # 12 attempts * 5s = 60s max wait
                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(url, timeout=5.0)
                        if resp.status_code < 500:
                            connected = True
                            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"✅ HTTP {resp.status_code} OK"})
                            break
                        last_error = f"Server returned {resp.status_code}"
                except Exception as e:
                    last_error = str(e)
                
                if attempt < 5:
                    await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"⏳ Waiting for server... ({attempt+1}/6)"})
                    await asyncio.sleep(5)
            
            if not connected:
                 return {"status": "FAIL", "phase": "sanity_check", "errors": [f"Could not connect to server after 30s: {last_error}"], "fix_this": True}

            # --- 4. PHASE 1: BROWSER VERIFICATION ---
            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "Phase 1: Browser Validation..."})
            result = await self.verify_page(url)
            
            # --- 5. PHASE 2: DEV SERVER LOG ANALYSIS ---
            # The dev server (Next.js/Vite/webpack) logs compile errors to stdout/stderr.
            # These are captured by runner._capture_output → runner.logs.
            # Scan them for errors that HTTP status codes or Playwright may have missed.
            server_errors = []
            error_patterns = [
                "Module not found",
                "Can't resolve",
                "SyntaxError",
                "TypeError",
                "ReferenceError",
                "ENOENT",
                "Cannot find module",
                "Failed to compile",
                "Build error",
                # "Error:" removed because it's too generic and catches "0 errors"
            ]
            for log_line in runner.logs:
                for pattern in error_patterns:
                    if pattern in log_line:
                        # Clean up the error line and avoid duplicates
                        clean = log_line.strip()[:200]
                        if clean and clean not in server_errors:
                            server_errors.append(clean)
                        break  # Only match one pattern per line
            
            if server_errors:
                await sm.emit("agent_log", {
                    "agent_name": "WATCHER",
                    "message": f"📋 Found {len(server_errors)} errors in dev server logs"
                })
                for err in server_errors[:3]:
                    await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"  → {err[:120]}"})
                
                # Merge server errors into the Playwright result
                existing_errors = result.get("errors", [])
                all_errors = existing_errors + server_errors
                result["errors"] = all_errors
                result["status"] = "FAIL"
                result["fix_this"] = True
            
            return result

        finally:
            runner.cleanup()
    
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
        # Universal Project Structure Check
        # Check for ANY valid entry point or manifest
        valid_indicators = [
            # Node/Frontend
            frontend_dir / "app" / "page.tsx",
            frontend_dir / "pages" / "index.tsx",
            frontend_dir / "src" / "App.jsx",
            frontend_dir / "src" / "App.tsx",
            frontend_dir / "src" / "main.ts", # NestJS
            frontend_dir / "src" / "server.ts", # Express-TS
            frontend_dir / "index.html",
            frontend_dir / "package.json",
            
            # Rust
            frontend_dir / "Cargo.toml",
            frontend_dir / "src" / "main.rs",
            
            # Python
            frontend_dir / "requirements.txt",
            frontend_dir / "main.py",
            frontend_dir / "app.py",
            
            # Ruby
            frontend_dir / "Gemfile",
            frontend_dir / "config.ru",
            
            # PHP
            frontend_dir / "composer.json",
            frontend_dir / "artisan",
            frontend_dir / "index.php",
            
            # .NET
            *(list(frontend_dir.glob("*.csproj"))),
            
            # C++
            frontend_dir / "CMakeLists.txt",
            frontend_dir / "src" / "main.cpp",
        ]
        
        # Flatten the list (handle glob results)
        is_valid = False
        for path in valid_indicators:
            if isinstance(path, Path) and path.exists():
                is_valid = True
                break
        
        if not is_valid:
             # Check root as fallback
            root_indicators = [
                BASE_PROJECTS_DIR / project_id / "Cargo.toml",
                BASE_PROJECTS_DIR / project_id / "Gemfile",
                BASE_PROJECTS_DIR / project_id / "composer.json",
                BASE_PROJECTS_DIR / project_id / "requirements.txt",
                BASE_PROJECTS_DIR / project_id / "index.html",
            ]
            for path in root_indicators:
                if path.exists():
                    is_valid = True
                    break

        if not is_valid:
            return {
                "status": "FAIL",
                "errors": ["No valid project structure found (Missing manifest or entry point)"],
                "fix_this": True
            }
        
        # If we found valid files, pass.
        # Syntax check only for JS/TS/Py files for now
        check_path = frontend_dir
        if (frontend_dir / "src").exists():
            check_path = frontend_dir / "src"
            
        errors = []
        # Support .tsx, .jsx, .ts, .js, .py, .rs, .php, .rb
        extensions = ["*.tsx", "*.jsx", "*.ts", "*.js", "*.py", "*.rs", "*.php", "*.rb"]
        files_to_check = []
        for ext in extensions:
            files_to_check.extend(list(check_path.glob(ext)))
        
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
