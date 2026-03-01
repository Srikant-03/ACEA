"""
Phase 6: Artifact Generator Tests
Tests for ArtifactGenerator, report generation, and API endpoints.
"""

import pytest
import json
import os
import tempfile
import shutil
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path

from app.core.artifact_generator import ArtifactGenerator, get_artifact_generator


# ─── Helper: Create a mock state ───

def make_mock_state(**overrides):
    """Create a mock AgentState with sensible defaults."""
    state = MagicMock()
    state.project_id = overrides.get("project_id", "test_job_123")
    state.user_prompt = overrides.get("user_prompt", "Add user auth")
    state.current_status = overrides.get("current_status", "release_ready")
    state.errors = overrides.get("errors", [])
    state.iteration_count = overrides.get("iteration_count", 2)
    state.retry_count = overrides.get("retry_count", 1)
    state.start_time = overrides.get("start_time", "")
    state.file_system = overrides.get("file_system", {
        "src/app.py": "print('hello')\n",
        "package.json": '{"name": "test"}'
    })
    state.test_results = overrides.get("test_results", {
        "total": 5, "passed": 4, "failed": 1, "skipped": 0
    })
    state.security_report = overrides.get("security_report", {
        "status": "PASSED", "vulnerabilities": []
    })
    state.visual_report = overrides.get("visual_report", {
        "status": "PASSED",
        "gemini_analysis": {"overall_quality": "Good"}
    })
    state.thought_signatures = overrides.get("thought_signatures", [])
    state.screenshot_paths = overrides.get("screenshot_paths", {})
    state.execution_plan = overrides.get("execution_plan", None)
    state.repo_url = overrides.get("repo_url", None)
    state.current_branch = overrides.get("current_branch", None)
    state.commit_history = overrides.get("commit_history", [])
    state.initial_commit = overrides.get("initial_commit", None)
    state.repo_path = overrides.get("repo_path", None)
    return state


# ─── Unit Tests: Status Determination ───

def test_status_success():
    gen = ArtifactGenerator(tempfile.mkdtemp())
    state = make_mock_state(current_status="release_ready", errors=[])
    assert gen._determine_status(state) == "success"


def test_status_failed_with_errors():
    gen = ArtifactGenerator(tempfile.mkdtemp())
    state = make_mock_state(errors=["SyntaxError"])
    assert gen._determine_status(state) == "failed"


def test_status_failed_with_error_status():
    gen = ArtifactGenerator(tempfile.mkdtemp())
    state = make_mock_state(current_status="release_error", errors=[])
    assert gen._determine_status(state) == "failed"


def test_status_partial():
    gen = ArtifactGenerator(tempfile.mkdtemp())
    state = make_mock_state(current_status="testing", errors=[])
    assert gen._determine_status(state) == "partial"


# ─── Unit Tests: Execution Summary ───

def test_execution_summary():
    gen = ArtifactGenerator(tempfile.mkdtemp())
    state = make_mock_state(iteration_count=3, retry_count=1)
    
    start = datetime(2026, 2, 11, 10, 0, 0)
    end = datetime(2026, 2, 11, 10, 15, 32)
    
    summary = gen._build_execution_summary(state, start, end)
    assert summary["duration_seconds"] == 932
    assert summary["iterations"] == 3
    assert summary["retry_count"] == 1


# ─── Unit Tests: Verification Summary ───

def test_verification_summary():
    gen = ArtifactGenerator(tempfile.mkdtemp())
    state = make_mock_state()
    
    v = gen._build_verification_summary(state)
    assert v["tests"]["total"] == 5
    assert v["tests"]["passed"] == 4
    assert v["security"]["status"] == "PASSED"
    assert v["visual_qa"]["overall_quality"] == "Good"


def test_verification_summary_empty():
    gen = ArtifactGenerator(tempfile.mkdtemp())
    state = make_mock_state(test_results=None, security_report=None, visual_report=None)
    
    v = gen._build_verification_summary(state)
    assert v["tests"]["total"] == 0
    assert v["security"]["status"] == "UNKNOWN"
    assert v["visual_qa"]["status"] == "UNKNOWN"


# ─── Unit Tests: Changes Summary ───

def test_changes_summary():
    gen = ArtifactGenerator(tempfile.mkdtemp())
    state = make_mock_state(file_system={
        "app.py": "line1\nline2\nline3",
        "index.html": "<html></html>"
    })
    
    changes = gen._build_changes_summary(state)
    assert "app.py" in changes["files_created"]
    assert changes["total_lines_added"] > 0


# ─── Unit Tests: Git Summary ───

def test_git_summary_with_repo():
    gen = ArtifactGenerator(tempfile.mkdtemp())
    state = make_mock_state(
        repo_url="https://github.com/user/repo.git",
        current_branch="acea/feature",
        commit_history=["abc123", "def456"]
    )
    
    git = gen._build_git_summary(state)
    assert git["repository"] == "https://github.com/user/repo.git"
    assert git["branch"] == "acea/feature"
    assert git["total_commits"] == 2


def test_git_summary_none_without_repo():
    gen = ArtifactGenerator(tempfile.mkdtemp())
    state = make_mock_state(repo_url=None)
    assert gen._build_git_summary(state) is None


# ─── Unit Tests: Signatures Summary ───

def test_signatures_summary():
    gen = ArtifactGenerator(tempfile.mkdtemp())
    
    mock_sig = MagicMock()
    mock_sig.signature_id = "sig_001"
    mock_sig.agent = "ARCHITECT"
    mock_sig.intent = "Design API"
    mock_sig.confidence = 0.9
    
    state = make_mock_state(thought_signatures=[mock_sig])
    
    sigs = gen._build_signatures_summary(state)
    assert len(sigs) == 1
    assert sigs[0]["agent"] == "ARCHITECT"
    assert sigs[0]["confidence"] == 0.9


def test_signatures_summary_dict():
    gen = ArtifactGenerator(tempfile.mkdtemp())
    state = make_mock_state(thought_signatures=[
        {"signature_id": "s1", "agent": "PLANNER", "intent": "Plan", "confidence": 0.8}
    ])
    # dict sigs don't have signature_id attribute, so they go through dict branch
    sigs = gen._build_signatures_summary(state)
    assert len(sigs) == 1


# ─── Integration Test: Full Report Generation ───

@pytest.mark.asyncio
async def test_generate_report_full():
    """Full report generation with all sections."""
    tmp_dir = tempfile.mkdtemp()
    gen = ArtifactGenerator(tmp_dir)
    
    state = make_mock_state(
        project_id="integration_test_job",
        user_prompt="Build a REST API",
        current_status="release_ready"
    )
    
    start = datetime(2026, 2, 11, 10, 0, 0)
    end = datetime(2026, 2, 11, 10, 5, 0)
    
    report = await gen.generate_report(state, start, end)
    
    assert report["job_id"] == "integration_test_job"
    assert report["status"] == "success"
    assert report["objective"] == "Build a REST API"
    assert "execution_summary" in report
    assert "verification" in report
    assert "thought_signatures" in report
    assert "artifacts" in report
    
    # Verify report.json was written to disk
    report_path = Path(tmp_dir) / "integration_test_job" / "report.json"
    assert report_path.exists()
    
    with open(report_path, encoding='utf-8') as f:
        saved = json.load(f)
    assert saved["job_id"] == "integration_test_job"
    
    # Cleanup
    shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_generate_report_failed_state():
    """Report correctly marks failed jobs."""
    tmp_dir = tempfile.mkdtemp()
    gen = ArtifactGenerator(tmp_dir)
    
    state = make_mock_state(
        project_id="failed_job",
        errors=["Critical crash"],
        current_status="error"
    )
    
    report = await gen.generate_report(state, datetime.now())
    assert report["status"] == "failed"
    
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ─── Singleton Test ───

def test_get_artifact_generator_singleton():
    """get_artifact_generator() returns same instance."""
    import app.core.artifact_generator as mod
    mod._artifact_generator = None  # Reset
    
    g1 = get_artifact_generator()
    g2 = get_artifact_generator()
    assert g1 is g2
    
    mod._artifact_generator = None  # Cleanup
