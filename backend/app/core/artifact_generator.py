"""
Artifact Generator
Creates comprehensive final reports with all evidence, decisions, and artifacts.
"""

import os
import json
import logging
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class ArtifactGenerator:
    """
    Generates unified artifact reports.
    
    Includes:
    - Execution summary
    - Plan and steps
    - Code changes
    - Test results
    - Security scan
    - Visual QA
    - Decision trail (thought signatures)
    - Screenshots
    """
    
    def __init__(self, artifacts_dir: str = None):
        if artifacts_dir is None:
            # Use project-relative path, fallback to temp
            base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            artifacts_dir = os.path.join(base, "artifacts")
        self.artifacts_dir = Path(artifacts_dir)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    async def generate_report(
        self,
        state,
        start_time: datetime,
        end_time: Optional[datetime] = None
    ) -> Dict:
        """
        Generate complete structured artifact report.
        
        Produces:
        - report.json (machine-readable structured report)
        - report.md (human-readable summary)
        - decisions.json (thought signature trail)
        - *.patch (diff archives per commit)
        """
        if end_time is None:
            end_time = datetime.now()
        
        job_id = state.project_id or "unknown"
        job_dir = self.artifacts_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        
        # Build report sections
        report = {
            "version": "2.0",
            "job_id": job_id,
            "status": self._determine_status(state),
            "objective": getattr(state, "user_prompt", ""),
            "execution_summary": self._build_execution_summary(state, start_time, end_time),
            "plan": self._build_plan_summary(state),
            "changes": self._build_changes_summary(state),
            "verification": self._build_verification_summary(state),
            "thought_signatures": self._build_signatures_summary(state),
            "strategy_history": getattr(state, "strategy_history", []),
            "git": self._build_git_summary(state),
            "diff_archive": self._generate_diff_archive(state, job_dir),
            "metrics": self._build_metrics(state, start_time, end_time),
            "artifacts": self._save_artifacts(state, job_dir)
        }
        
        # Save structured JSON report
        report_path = job_dir / "report.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, default=str)
        
        # Save human-readable markdown report
        self._save_markdown_report(report, job_dir)
        
        logger.info(f"Artifact report saved: {report_path}")
        
        return report
    
    def _determine_status(self, state) -> str:
        """Determine final job status."""
        errors = getattr(state, "errors", [])
        status = getattr(state, "current_status", "")
        
        if errors:
            return "failed"
        if status in ("error", "release_error"):
            return "failed"
        if status == "release_ready":
            return "success"
        return "partial"
    
    def _build_execution_summary(
        self,
        state,
        start_time: datetime,
        end_time: datetime
    ) -> Dict:
        """Build execution summary."""
        duration = (end_time - start_time).total_seconds()
        
        steps_completed = 0
        plan = getattr(state, "execution_plan", None)
        if plan and hasattr(plan, "steps"):
            steps_completed = sum(
                1 for step in plan.steps
                if getattr(step, "status", "") == "success"
            )
        
        return {
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": int(duration),
            "iterations": getattr(state, "iteration_count", 0),
            "steps_completed": steps_completed,
            "retry_count": getattr(state, "retry_count", 0),
            "total_retries_used": getattr(state, "total_retries_used", 0),
            "max_total_retries": getattr(state, "max_total_retries", 5),
            "last_strategy": getattr(state, "current_repair_strategy", None)
        }
    
    def _build_plan_summary(self, state) -> Optional[Dict]:
        """Build plan summary."""
        plan = getattr(state, "execution_plan", None)
        if not plan:
            return None
        
        steps = getattr(plan, "steps", [])
        return {
            "strategy": getattr(plan, "strategy", ""),
            "total_steps": len(steps),
            "steps": [
                {
                    "id": getattr(step, "id", ""),
                    "action": getattr(step, "action", "").value if hasattr(getattr(step, "action", None), "value") else str(getattr(step, "action", "")),
                    "intent": getattr(step, "intent", ""),
                    "status": getattr(step, "status", "pending")
                }
                for step in steps
            ]
        }
    
    def _build_changes_summary(self, state) -> Dict:
        """Build code changes summary."""
        changes = {
            "files_created": [],
            "files_modified": [],
            "files_deleted": [],
            "total_lines_added": 0,
            "total_lines_removed": 0
        }
        
        # From file system state
        file_system = getattr(state, "file_system", {})
        if file_system:
            changes["files_created"] = list(file_system.keys())[:20]
            # Estimate lines from file content
            for content in file_system.values():
                if isinstance(content, str):
                    changes["total_lines_added"] += content.count("\n") + 1
        
        return changes
    
    def _build_verification_summary(self, state) -> Dict:
        """Build verification summary."""
        test_results = getattr(state, "test_results", {}) or {}
        security_report = getattr(state, "security_report", {}) or {}
        visual_report = getattr(state, "visual_report", {}) or {}
        
        return {
            "tests": {
                "total": test_results.get("total", 0),
                "passed": test_results.get("passed", 0),
                "failed": test_results.get("failed", 0),
                "skipped": test_results.get("skipped", 0)
            },
            "security": {
                "status": security_report.get("status", "UNKNOWN"),
                "vulnerabilities": len(security_report.get("vulnerabilities", []))
            },
            "visual_qa": {
                "status": visual_report.get("status", "UNKNOWN"),
                "overall_quality": visual_report.get(
                    "gemini_analysis", {}
                ).get("overall_quality", "N/A")
            }
        }
    
    def _build_signatures_summary(self, state) -> List[Dict]:
        """Build thought signatures summary."""
        sigs = getattr(state, "thought_signatures", [])
        if not sigs:
            return []
        
        result = []
        for sig in sigs[:10]:  # First 10
            if hasattr(sig, "signature_id"):
                result.append({
                    "signature_id": sig.signature_id,
                    "agent": sig.agent,
                    "intent": sig.intent,
                    "confidence": sig.confidence
                })
            elif isinstance(sig, dict):
                result.append({
                    "signature_id": sig.get("signature_id", ""),
                    "agent": sig.get("agent", ""),
                    "intent": sig.get("intent", ""),
                    "confidence": sig.get("confidence", 0)
                })
        return result
    
    def _save_artifacts(self, state, job_dir: Path) -> Dict:
        """Save artifact files and return paths."""
        artifacts = {}
        
        # 1. Save thought signatures as decisions.json
        sigs = getattr(state, "thought_signatures", [])
        if sigs:
            sigs_path = job_dir / "decisions.json"
            sig_dicts = []
            for s in sigs:
                if hasattr(s, "to_dict"):
                    sig_dicts.append(s.to_dict())
                elif isinstance(s, dict):
                    sig_dicts.append(s)
            with open(sigs_path, 'w', encoding='utf-8') as f:
                json.dump(sig_dicts, f, indent=2, default=str)
            artifacts["decisions"] = str(sigs_path)
        
        # 2. Copy screenshots
        screenshot_paths = getattr(state, "screenshot_paths", {})
        if screenshot_paths:
            screenshots = []
            for step_id, screenshot_path in screenshot_paths.items():
                src = Path(screenshot_path)
                if src.exists():
                    import shutil
                    dest = job_dir / f"screenshot_{step_id}.png"
                    shutil.copy(src, dest)
                    screenshots.append(str(dest))
            if screenshots:
                artifacts["screenshots"] = screenshots
        
        # 3. Save file listing
        file_system = getattr(state, "file_system", {})
        if file_system:
            listing_path = job_dir / "file_listing.json"
            listing = {path: len(content) if isinstance(content, str) else 0
                       for path, content in file_system.items()}
            with open(listing_path, 'w', encoding='utf-8') as f:
                json.dump(listing, f, indent=2)
            artifacts["file_listing"] = str(listing_path)
        
        return artifacts
    
    def _build_git_summary(self, state) -> Optional[Dict]:
        """Build git summary."""
        repo_url = getattr(state, "repo_url", None)
        if not repo_url:
            return None
        
        commits = getattr(state, "commit_history", [])
        return {
            "repository": repo_url,
            "branch": getattr(state, "current_branch", "unknown"),
            "commits": commits[:10],
            "total_commits": len(commits),
            "initial_commit": getattr(state, "initial_commit", None)
        }
    
    def _generate_diff_archive(self, state, job_dir: Path) -> Optional[Dict]:
        """Generate diff patches for all commits."""
        project_id = getattr(state, "project_id", None)
        if not project_id:
            return None
        
        try:
            from app.core.git_adapter import get_git_adapter
            git = get_git_adapter()
            
            initial = getattr(state, "initial_commit", None)
            if not initial:
                return None
            
            diff = git.get_diff(project_id, from_commit=initial)
            if diff:
                diff_path = job_dir / "changes.patch"
                with open(diff_path, 'w', encoding='utf-8', errors='replace') as f:
                    f.write(diff)
                return {
                    "patch_file": str(diff_path),
                    "from_commit": initial,
                    "diff_lines": diff.count('\n')
                }
        except Exception as e:
            logger.warning(f"Failed to generate diff archive: {e}")
        
        return None
    
    def _build_metrics(self, state, start_time, end_time) -> Dict:
        """Build performance metrics from state."""
        duration = (end_time - start_time).total_seconds()
        metrics = getattr(state, "metrics", {}) or {}
        
        return {
            "total_duration_seconds": int(duration),
            "iterations_used": getattr(state, "iteration_count", 0),
            "retries_used": getattr(state, "total_retries_used", 0),
            "files_generated": len(getattr(state, "file_system", {})),
            "thought_signatures_captured": len(getattr(state, "thought_signatures", [])),
            "strategy_attempts": len(getattr(state, "strategy_history", [])),
            **metrics  # Merge any additional metrics from MetricsCollector
        }
    
    def _save_markdown_report(self, report: Dict, job_dir: Path):
        """Generate a human-readable markdown report."""
        lines = []
        lines.append(f"# ACEA Report: {report['job_id']}")
        lines.append(f"")
        lines.append(f"**Status:** {report['status']}  ")
        lines.append(f"**Objective:** {report.get('objective', 'N/A')}")
        lines.append(f"")
        
        # Execution summary
        ex = report.get('execution_summary', {})
        lines.append(f"## Execution")
        lines.append(f"- Duration: {ex.get('duration_seconds', 0)}s")
        lines.append(f"- Iterations: {ex.get('iterations', 0)}")
        lines.append(f"- Retries: {ex.get('total_retries_used', 0)}/{ex.get('max_total_retries', 5)}")
        lines.append(f"")
        
        # Verification
        ver = report.get('verification', {})
        tests = ver.get('tests', {})
        if tests.get('total', 0) > 0:
            lines.append(f"## Tests")
            lines.append(f"- Passed: {tests.get('passed', 0)}/{tests.get('total', 0)}")
            lines.append(f"- Failed: {tests.get('failed', 0)}")
            lines.append(f"")
        
        # Strategy history
        sh = report.get('strategy_history', [])
        if sh:
            lines.append(f"## Strategy History")
            for attempt in sh:
                emoji = '✅' if attempt.get('success') else '❌'
                lines.append(f"- {emoji} {attempt.get('strategy', '?')} "
                           f"(errors: {len(attempt.get('errors_before', []))} → "
                           f"{len(attempt.get('errors_after', []))})")
            lines.append(f"")
        
        # Thought signatures
        sigs = report.get('thought_signatures', [])
        if sigs:
            lines.append(f"## Decision Trail ({len(sigs)} signatures)")
            for sig in sigs[:5]:
                lines.append(f"- **{sig.get('agent', '?')}**: {sig.get('intent', 'N/A')[:80]} "
                           f"(confidence: {sig.get('confidence', 0):.0%})")
            lines.append(f"")
        
        md_path = job_dir / "report.md"
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        return str(md_path)


# Singleton
_artifact_generator = None


def get_artifact_generator() -> ArtifactGenerator:
    """Get singleton ArtifactGenerator."""
    global _artifact_generator
    if _artifact_generator is None:
        _artifact_generator = ArtifactGenerator()
    return _artifact_generator
