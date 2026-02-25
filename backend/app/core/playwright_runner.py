"""
Playwright browser verification runner.

This script runs in a SEPARATE PROCESS to sidestep the Windows asyncio
event loop issue.  Uvicorn (which hosts the FastAPI backend) may use a
SelectorEventLoop internally, but Playwright requires a ProactorEventLoop
for subprocess support on Windows.

Usage (called by WatcherAgent):
    python -m app.core.playwright_runner <url> [--timeout 30] [--screenshot-dir screenshots]

Output: JSON on stdout with keys:
    status, errors, console_logs, screenshot, visual_issues, fix_this
"""

import asyncio
import json
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path


async def run_browser_check(url: str, timeout: int = 30, screenshot_dir: str = "screenshots") -> dict:
    """Launch Playwright, navigate to url, capture errors and screenshot."""
    errors = []
    console_logs = []
    network_failures = []
    screenshot_path = None
    visual_issues = []

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {
            "status": "SKIPPED",
            "reason": "Playwright not installed",
            "errors": [],
            "console_logs": [],
            "network_failures": [],
            "screenshot": None,
            "visual_issues": [],
            "fix_this": False,
        }

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            # Collect console messages
            def on_console(msg):
                entry = {
                    "type": msg.type,
                    "text": msg.text,
                    "timestamp": datetime.now().isoformat(),
                }
                console_logs.append(entry)

            page.on("console", on_console)

            # Collect uncaught exceptions
            page.on(
                "pageerror",
                lambda exc: errors.append(f"Page error: {str(exc)[:200]}"),
            )
            
            # Capture network request failures (404s, 500s, etc.) WITH URLs
            def on_response(response):
                if response.status >= 400:
                    from urllib.parse import urlparse
                    parsed = urlparse(response.url)
                    resource_path = parsed.path
                    network_failures.append({
                        "url": response.url,
                        "path": resource_path,
                        "status": response.status,
                        "method": response.request.method,
                    })
            
            page.on("response", on_response)

            try:
                response = await page.goto(
                    url, wait_until="networkidle", timeout=timeout * 1000
                )

                # Check HTTP status
                if response and response.status >= 400:
                    errors.append(
                        f"HTTP {response.status} {response.status_text}"
                    )

                # Wait a moment for async rendering
                await asyncio.sleep(2)

                # Screenshot
                screenshots = Path(screenshot_dir)
                screenshots.mkdir(parents=True, exist_ok=True)
                safe = url.replace("http://", "").replace("https://", "").replace("/", "_")[:50]
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = str(screenshots / f"{safe}_{ts}.png")
                await page.screenshot(path=screenshot_path, full_page=True)

                # Collect console errors (but skip generic 404 text — we have better network info)
                console_errors = [
                    log for log in console_logs if log["type"] == "error"
                ]
                for err in console_errors:
                    err_text = err["text"][:200]
                    # Skip generic "Failed to load resource" — network_failures has the details
                    if "Failed to load resource" in err_text:
                        continue
                    errors.append(err_text)
                
                # Add enriched network failure errors with actual paths
                for nf in network_failures:
                    errors.append(
                        f"FILE: {nf['path']} - {nf['status']} Not Found ({nf['method']} {nf['url']})"
                    )

            except Exception as nav_err:
                errors.append(f"Navigation failed: {str(nav_err)[:200]}")

            await browser.close()

    except Exception as e:
        errors.append(f"Browser error: {str(e)[:200]}")

    if errors:
        return {
            "status": "FAIL",
            "errors": errors,
            "console_logs": console_logs,
            "network_failures": network_failures,
            "screenshot": screenshot_path,
            "visual_issues": visual_issues,
            "fix_this": True,
        }
    else:
        return {
            "status": "PASS",
            "errors": [],
            "console_logs": console_logs,
            "network_failures": network_failures,
            "screenshot": screenshot_path,
            "visual_issues": [],
            "fix_this": False,
        }


def main():
    try:
        parser = argparse.ArgumentParser(description="Playwright browser check")
        parser.add_argument("url", help="URL to verify")
        parser.add_argument("--timeout", type=int, default=30, help="Navigation timeout in seconds")
        parser.add_argument("--screenshot-dir", default="screenshots", help="Directory for screenshots")
        args = parser.parse_args()

        # Ensure ProactorEventLoop on Windows
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

        result = asyncio.run(run_browser_check(args.url, args.timeout, args.screenshot_dir))
        # Print JSON result to stdout (the watcher reads this)
        print(json.dumps(result))
    except Exception as e:
        # Fallback JSON to ensure watcher doesn't crash
        fallback = {
            "status": "FAIL",
            "errors": [f"Runner Process Error: {str(e)}"],
            "console_logs": [],
            "screenshot": None,
            "visual_issues": [],
            "fix_this": False
        }
        print(json.dumps(fallback))

if __name__ == "__main__":
    main()
