"""
Preview Browser Test Service
Orchestrates browser testing from the Preview panel context.

Reuses BrowserValidationAgent for actual testing, adds:
- Preview URL resolution (from E2B sandbox or PreviewProxyService)
- Real-time Socket.IO progress streaming
- Structured error categorization
- Self-healing integration (send errors back to router)
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional, List

logger = logging.getLogger(__name__)


class PreviewBrowserTestService:
    """Service that runs browser tests on a live preview and streams results."""

    async def run_test(
        self,
        project_id: str,
        validation_level: str = "standard",
        sid: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Main entry point: resolve URL → run BrowserValidationAgent → stream results.

        Args:
            project_id: The project to test.
            validation_level: "quick" | "standard" | "thorough"
            sid: Socket.IO session ID for progress streaming (optional).

        Returns:
            Structured test report with categorised errors and scores.
        """
        from app.core.socket_manager import SocketManager
        sm = SocketManager()

        start_time = datetime.now()

        # ---------- 1. Emit start event ----------
        await self._emit_progress(sm, sid, {
            "phase": "starting",
            "message": "Resolving preview URL…",
            "project_id": project_id,
        })

        # ---------- 2. Resolve preview URL ----------
        preview_url = await self._resolve_preview_url(project_id)

        if not preview_url:
            error_report = self._error_report(
                project_id, "No active preview found. Execute the project first."
            )
            await self._emit_progress(sm, sid, {
                "phase": "error",
                "message": error_report["error"],
            })
            return error_report

        await self._emit_progress(sm, sid, {
            "phase": "resolved",
            "message": f"Preview URL: {preview_url}",
            "url": preview_url,
        })

        # ---------- 3. Run BrowserValidationAgent ----------
        await self._emit_progress(sm, sid, {
            "phase": "validating",
            "message": f"Running {validation_level} browser validation…",
            "validation_level": validation_level,
        })

        raw_report = {}
        try:
            from app.agents.browser_validation_agent import BrowserValidationAgent
            from app.core.filesystem import BASE_PROJECTS_DIR

            validator = BrowserValidationAgent()
            project_path = str(BASE_PROJECTS_DIR / project_id)

            raw_report = await validator.comprehensive_validate(
                url=preview_url,
                project_path=project_path,
                validation_level=validation_level,
            )
        except ImportError:
            error_report = self._error_report(
                project_id, "Playwright is not installed on the server."
            )
            await self._emit_progress(sm, sid, {"phase": "error", "message": error_report["error"]})
            return error_report
        except Exception as exc:
            error_report = self._error_report(project_id, str(exc))
            await self._emit_progress(sm, sid, {"phase": "error", "message": str(exc)})
            return error_report

        # ---------- 4. Fetch Proxy Errors (Console/Network) ----------
        console_errors = []
        network_failures = []
        try:
            from app.services.preview_proxy_service import get_preview_proxy_service
            proxy = get_preview_proxy_service()
            # Try to find session by project_id
            session = await proxy.get_session_by_project(project_id)
            if session:
                console_errors = session.console_errors
                network_failures = session.network_failures
        except Exception as e:
            logger.warning(f"Failed to fetch proxy errors: {e}")

        # ---------- 5. Categorise & enrich ----------
        report = self._build_structured_report(
            project_id, preview_url, validation_level, raw_report, start_time,
            console_errors, network_failures
        )

        # ---------- 6. Emit completion ----------
        await self._emit_progress(sm, sid, {
            "phase": "complete",
            "message": f"Browser test complete: {report['overall_status']}",
            "overall_status": report["overall_status"],
            "total_issues": report["total_issues"]
        })

        return report

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    async def _resolve_preview_url(self, project_id: str) -> Optional[str]:
        """Try E2B sandbox first, then PreviewProxyService."""
        # 1. E2B sandbox
        try:
            from app.services.e2b_vscode_service import get_e2b_vscode_service
            e2b = get_e2b_vscode_service()
            sandbox = e2b.get_sandbox(project_id)
            if sandbox and sandbox.get("preview_url"):
                return sandbox["preview_url"]
        except Exception:
            pass

        # 2. PreviewProxyService sessions
        try:
            from app.services.preview_proxy_service import get_preview_proxy_service
            proxy = get_preview_proxy_service()
            for session in proxy.sessions.values():
                if session.get("project_id") == project_id:
                    return session.get("preview_url")
        except Exception:
            pass

        return None

    def _build_structured_report(
        self,
        project_id: str,
        url: str,
        level: str,
        raw: Dict[str, Any],
        start_time: datetime,
        console_errors: List[Dict] = None,
        network_failures: List[Dict] = None,
    ) -> Dict[str, Any]:
        """Enrich the raw BrowserValidationAgent report with metadata."""
        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        console_errors = console_errors or []
        network_failures = network_failures or []

        # Categorise issues from each test into buckets
        categories: Dict[str, list] = {
            "console_errors": [],
            "network_failures": [],
            "visual_issues": [],
            "accessibility": [],
            "performance": [],
            "seo": [],
            "interactivity": [],
            "responsiveness": [],
            "prompt_alignment": [], # Added prompt alignment
            "feature_interaction": [], # Added feature interaction
        }

        tests = raw.get("tests", {})
        
        # Add Proxy Errors as Tests so they appear in UI
        if console_errors:
            tests["console"] = {
                "status": "WARN", # Assume WARN for console errors
                "issues": [f"{e.get('type', 'Error')}: {e.get('message', str(e))}" for e in console_errors]
            }
            categories["console_errors"].extend(tests["console"]["issues"])
            
        if network_failures:
            tests["network"] = {
                "status": "WARN", 
                "issues": [f"{f.get('method', 'GET')} {f.get('url', '?')} - {f.get('error', 'Failed')}" for f in network_failures]
            }
            categories["network_failures"].extend(tests["network"]["issues"])

        # Process existing tests
        for test_name, result in tests.items():
            if test_name in ("console", "network"): continue # Already handled
            
            issues = result.get("issues", [])
            if test_name == "interactive":
                categories["interactivity"].extend(issues)
            elif test_name == "accessibility":
                categories["accessibility"].extend(issues)
            elif test_name == "responsive":
                categories["responsiveness"].extend(issues)
            elif test_name == "performance":
                categories["performance"].extend(issues)
            elif test_name == "seo":
                categories["seo"].extend(issues)
            elif test_name in ("links", "forms"):
                categories["interactivity"].extend(issues)
            elif test_name == "visual_overlap":
                 categories["visual_issues"].extend(issues)
            elif test_name == "prompt_alignment":
                 categories["prompt_alignment"].extend(issues)
            elif test_name == "feature_interaction":
                 categories["feature_interaction"].extend(issues)

        # Count total issues
        total_issues = sum(len(v) for v in categories.values())
        
        # Adjust overall status if proxy errors found
        overall_status = raw.get("overall_status", "UNKNOWN")
        if (console_errors or network_failures) and overall_status in ["PASS", "EXCELLENT", "GOOD"]:
            overall_status = "WARN"

        return {
            "project_id": project_id,
            "url": url,
            "validation_level": level,
            "overall_status": overall_status,
            "scores": raw.get("scores", {}),
            "categories": categories,
            "total_issues": total_issues,
            "tests": tests,
            "duration_ms": duration_ms,
            "timestamp": datetime.now().isoformat(),
            "error": raw.get("error"),
        }

    def _error_report(self, project_id: str, message: str) -> Dict[str, Any]:
        return {
            "project_id": project_id,
            "overall_status": "ERROR",
            "error": message,
            "scores": {},
            "categories": {},
            "total_issues": 0,
            "tests": {},
            "timestamp": datetime.now().isoformat(),
        }

    async def _emit_progress(
        self, sm, sid: Optional[str], data: Dict[str, Any]
    ) -> None:
        """Emit a preview_test_progress event."""
        try:
            if sid:
                await sm.emit("preview_test_progress", data, room=sid)
            else:
                await sm.emit("preview_test_progress", data)
        except Exception:
            pass


def get_preview_browser_test_service() -> PreviewBrowserTestService:
    """Factory / singleton accessor."""
    return PreviewBrowserTestService()
