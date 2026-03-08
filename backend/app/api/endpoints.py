from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime
import os
import json
import subprocess
import logging
import re

from app.core.sandbox_guard import get_sandbox_guard
import uuid

from app.agents.architect import ArchitectAgent
from app.agents.virtuoso import VirtuosoAgent
from app.agents.sentinel import SentinelAgent

from app.core.filesystem import (
    read_project_files,
    read_file,
    update_file_content,
    archive_project,
    BASE_PROJECTS_DIR
)

router = APIRouter()

# ========================= REQUEST MODELS =========================

class PromptRequest(BaseModel):
    prompt: str
    project_id: str

class CodeGenRequest(BaseModel):
    file_path: str
    description: str

class AuditRequest(BaseModel):
    file_path: str
    code: str

class UpdateFileRequest(BaseModel):
    path: str
    content: str

class AIUpdateRequest(BaseModel):
    file_path: str
    instruction: str

class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=10, max_length=5000)
    tech_stack: str = Field(default="Auto-detect")

    @validator("prompt")
    def validate_prompt(cls, v):
        return v.strip()

class TestGenerationRequest(BaseModel):
    tech_stack: Optional[str] = "Auto-detect"
    run_tests: bool = True

class BrowserValidationRequest(BaseModel):
    validation_level: str = "standard"

class URLValidationRequest(BaseModel):
    url: str
    validation_level: str = "standard"

class FileScanRequest(BaseModel):
    file_path: str


# ========================= HELPERS =========================

def _load_blueprint(project_id: str) -> dict:
    path = BASE_PROJECTS_DIR / project_id / "blueprint.json"
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return {"tech_stack": "Unknown", "projectType": "frontend"}


def check_command(cmd: str) -> bool:
    """Check if a command exists, validated through SandboxGuard."""
    try:
        guard = get_sandbox_guard()
        allowed, reason = guard.check_command(cmd)
        if not allowed:
            logging.getLogger(__name__).warning(f"check_command blocked: {cmd} — {reason}")
            return False
        subprocess.run(cmd.split(), capture_output=True, timeout=2)
        return True
    except Exception:
        return False


# ========================= CORE AGENTS =========================

@router.post("/architect/design")
async def run_architect(request: PromptRequest):
    agent = ArchitectAgent()
    result = await agent.design_system(request.prompt)
    return result


@router.post("/virtuoso/generate")
async def run_virtuoso(request: CodeGenRequest):
    agent = VirtuosoAgent()
    code = await agent.generate_code(request.file_path, request.description)
    return {"code": code}


@router.post("/sentinel/audit")
async def run_sentinel(request: AuditRequest):
    agent = SentinelAgent()
    return await agent.audit_code(request.file_path, request.code)


# ========================= AUTONOMOUS EXECUTION =========================

class AutonomousRequest(BaseModel):
    repo_url: str = Field(..., description="Git repository URL")
    objective: str = Field(..., min_length=10, max_length=1000, description="High-level objective")
    branch: Optional[str] = Field(None, description="Branch to checkout")
    tech_stack: str = Field(default="Auto-detect", description="Tech stack preference")
    max_iterations: int = Field(default=3, ge=1, le=10, description="Max self-healing iterations")

    @validator('repo_url')
    def validate_repo_url(cls, v):
        v = v.strip()
        # Block file:// protocol
        if v.lower().startswith('file://'):
            raise ValueError('file:// URLs are not allowed')
        # Block localhost and private IPs
        blocked = ['localhost', '127.0.0.1', '0.0.0.0', '10.', '192.168.', '172.16.']
        for b in blocked:
            if b in v.lower():
                raise ValueError(f'URL pointing to {b} is not allowed')
        # Must look like a URL or git path
        if not re.match(r'^https?://|^git@', v):
            raise ValueError('repo_url must start with https://, http://, or git@')
        return v


@router.post("/autonomous/execute")
async def autonomous_execute(request: AutonomousRequest):
    """
    Main entry point for autonomous execution on existing repositories.
    
    Workflow:
    1. Clone repository
    2. Analyze codebase
    3. Create feature branch
    4. Generate plan
    5. Execute plan with self-healing
    6. Commit changes
    7. Generate report
    
    Returns job_id for tracking via Socket.IO
    """
    from app.core.git_adapter import get_git_adapter
    from app.agents.analyzer import get_analyzer_agent
    import uuid
    
    # Generate unique job ID
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    
    try:
        # 1. Clone repository
        git_adapter = get_git_adapter()
        success, message, repo_path = git_adapter.clone_repository(
            project_id=job_id,
            repo_url=request.repo_url,
            branch=request.branch
        )
        
        if not success:
            raise HTTPException(500, f"Failed to clone repository: {message}")
        
        # 2. Create feature branch
        success, message = git_adapter.create_feature_branch(job_id)
        if not success:
            raise HTTPException(500, f"Failed to create branch: {message}")
        
        # 3. Analyze repository
        analyzer = get_analyzer_agent()
        analysis = await analyzer.analyze_codebase(repo_path, request.objective)
        
        # 4-7. Launch the full LangGraph pipeline asynchronously
        # The graph will handle: plan → execute → test → fix → report
        import asyncio
        
        async def _run_autonomous_pipeline(job_id: str, repo_path: str, analysis: dict, request_data: dict):
            """Background task that runs the full LangGraph orchestration pipeline."""
            try:
                from app.core.orchestrator import graph
                from app.core.socket_manager import SocketManager
                
                sm = SocketManager()
                await sm.emit("agent_log", {
                    "agent_name": "SYSTEM",
                    "message": f"🚀 Starting autonomous pipeline for {request_data['repo_url']}"
                })
                
                initial_state = {
                    "messages": [],
                    "project_id": job_id,
                    "agent_id": job_id,
                    "run_id": job_id,
                    "user_prompt": request_data["objective"],
                    "tech_stack": request_data.get("tech_stack", "Auto-detect"),
                    "iteration_count": 0,
                    "max_iterations": request_data.get("max_iterations", 3),
                    "current_status": "planning",
                    "file_system": {},
                    "errors": [],
                    "retry_count": 0,
                    # Autonomous-specific fields
                    "repo_url": request_data["repo_url"],
                    "repo_path": repo_path,
                    "feature_branch": f"acea/{job_id}",
                    "analysis": analysis,
                }
                
                config = {"configurable": {"thread_id": job_id}}
                
                async for event in graph.astream(initial_state, config=config):
                    for node_name, state_update in event.items():
                        agent_name = node_name.upper()
                        await sm.emit("agent_status", {"agent_name": agent_name, "status": "working"})
                        if "messages" in state_update:
                            last_msg = state_update["messages"][-1]
                            await sm.emit("agent_log", {"agent_name": agent_name, "message": str(last_msg)})
                        await sm.emit("agent_status", {"agent_name": agent_name, "status": "success"})
                
                # 6. Commit changes if git adapter available
                try:
                    from app.core.git_adapter import get_git_adapter
                    git = get_git_adapter()
                    git.commit_changes(job_id, f"ACEA: {request_data['objective'][:60]}")
                    await sm.emit("agent_log", {"agent_name": "SYSTEM", "message": "✅ Changes committed to feature branch"})
                except Exception as commit_err:
                    await sm.emit("agent_log", {"agent_name": "SYSTEM", "message": f"⚠️ Commit skipped: {commit_err}"})
                
                # 7. Signal completion
                await sm.emit("mission_complete", {"project_id": job_id, "job_id": job_id})
                await sm.emit("agent_log", {"agent_name": "SYSTEM", "message": "🎉 Autonomous pipeline complete"})
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                sm = SocketManager()
                await sm.emit("mission_error", {"detail": str(e), "job_id": job_id})
        
        # Fire-and-forget: launch pipeline in background
        asyncio.create_task(_run_autonomous_pipeline(
            job_id, repo_path, analysis,
            {
                "repo_url": request.repo_url,
                "objective": request.objective,
                "tech_stack": request.tech_stack,
                "max_iterations": request.max_iterations,
            }
        ))
        
        return {
            "job_id": job_id,
            "status": "executing",
            "repository": request.repo_url,
            "objective": request.objective,
            "analysis": analysis,
            "message": "Autonomous pipeline launched. Track progress via Socket.IO events."
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Autonomous execution failed: {str(e)}")


# ========================= CHECKPOINT & RESUME =========================

@router.get("/checkpoints")
async def list_checkpoints():
    """List all available checkpoints."""
    from app.core.persistence import get_checkpoint_manager
    from app.core.config import settings
    
    manager = get_checkpoint_manager(settings.REDIS_URL)
    checkpoints = await manager.list_checkpoints()
    
    return {
        "checkpoints": checkpoints,
        "count": len(checkpoints)
    }


@router.get("/checkpoints/{job_id}")
async def get_checkpoint(job_id: str):
    """Get checkpoint details."""
    from app.core.persistence import get_checkpoint_manager
    from app.core.config import settings
    
    manager = get_checkpoint_manager(settings.REDIS_URL)
    checkpoint = await manager.load_checkpoint(job_id)
    
    if not checkpoint:
        raise HTTPException(404, "Checkpoint not found")
    
    return {
        "job_id": job_id,
        "checkpoint": checkpoint
    }


@router.post("/resume/{job_id}")
async def resume_execution(job_id: str):
    """
    Resume execution from checkpoint using ResumeEngine.
    
    Workflow:
    1. Load and validate checkpoint via ResumeEngine
    2. Reconnect Git, rebuild StrategyEngine
    3. Determine correct graph entry node (mid-plan resumption)
    4. Launch pipeline asynchronously from the correct point
    """
    from app.core.resume_engine import get_resume_engine, ResumeValidationError
    import asyncio
    
    engine = get_resume_engine()
    
    try:
        state, entry_node = await engine.resume(job_id)
    except ResumeValidationError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Resume failed: {str(e)}")
    
    # Launch the resumed pipeline asynchronously
    async def _run_resumed_pipeline():
        try:
            from app.core.orchestrator import graph
            from app.core.socket_manager import SocketManager
            
            sm = SocketManager()
            await sm.emit("agent_log", {
                "agent_name": "SYSTEM",
                "message": f"🔄 Resuming job {job_id} from node '{entry_node}' "
                           f"(iteration {state.iteration_count}, "
                           f"retries {state.total_retries_used}/{state.max_total_retries})"
            })
            
            config = {"configurable": {"thread_id": job_id}}
            
            async for event in graph.astream(state, config=config):
                for node_name, state_update in event.items():
                    agent_name = node_name.upper()
                    await sm.emit("agent_status", {"agent_name": agent_name, "status": "working"})
                    if "messages" in state_update:
                        last_msg = state_update["messages"][-1]
                        await sm.emit("agent_log", {"agent_name": agent_name, "message": str(last_msg)})
                    await sm.emit("agent_status", {"agent_name": agent_name, "status": "success"})
            
            await sm.emit("mission_complete", {"project_id": state.project_id, "job_id": job_id})
            await sm.emit("agent_log", {"agent_name": "SYSTEM", "message": "🎉 Resumed pipeline complete"})
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            sm = SocketManager()
            await sm.emit("mission_error", {"detail": str(e), "job_id": job_id})
    
    asyncio.create_task(_run_resumed_pipeline())
    
    return {
        "job_id": job_id,
        "status": "resuming",
        "resume_entry_node": entry_node,
        "iteration": state.iteration_count,
        "retries_used": state.total_retries_used,
        "message": "Execution resumed. Connect via Socket.IO for updates.",
        "last_checkpoint": getattr(state, '_checkpoint_meta', {})
    }


@router.delete("/checkpoints/{job_id}")
async def delete_checkpoint(job_id: str):
    """Delete checkpoint after manual cancellation."""
    from app.core.persistence import get_checkpoint_manager
    from app.core.config import settings
    
    manager = get_checkpoint_manager(settings.REDIS_URL)
    success = await manager.delete_checkpoint(job_id)
    
    if not success:
        raise HTTPException(500, "Failed to delete checkpoint")
    
    return {"job_id": job_id, "status": "deleted"}


# ========================= THOUGHT SIGNATURES =========================

@router.get("/signatures/{project_id}")
async def get_signatures(project_id: str):
    """
    Get all thought signatures for a project.
    
    Returns decision trail for audit and debugging.
    """
    from app.core.persistence import get_checkpoint_manager
    from app.core.config import settings
    
    manager = get_checkpoint_manager(settings.REDIS_URL)
    # Load latest checkpoint
    checkpoint = await manager.load_checkpoint(project_id)
    
    if not checkpoint:
        raise HTTPException(404, "Project not found")
    
    signatures = checkpoint.get("thought_signatures", [])
    
    return {
        "project_id": project_id,
        "signatures": signatures,
        "count": len(signatures),
        "agents": list(set(s.get("agent") for s in signatures))
    }


@router.get("/signatures/{project_id}/{signature_id}")
async def get_signature_detail(project_id: str, signature_id: str):
    """Get detailed view of single signature."""
    from app.core.persistence import get_checkpoint_manager
    from app.core.config import settings
    
    manager = get_checkpoint_manager(settings.REDIS_URL)
    checkpoint = await manager.load_checkpoint(project_id)
    
    if not checkpoint:
        raise HTTPException(404, "Project not found")
    
    signatures = checkpoint.get("thought_signatures", [])
    
    for sig in signatures:
        # signatures might be list of dicts if loaded from JSON
        sig_id = sig.get("signature_id") if isinstance(sig, dict) else sig.signature_id
        if sig_id == signature_id:
            return sig
    
    raise HTTPException(404, "Signature not found")


# ========================= ARTIFACTS =========================

@router.get("/artifacts/{job_id}")
async def get_artifact_report(job_id: str):
    """Get complete artifact report for a job."""
    from pathlib import Path
    
    from app.core.artifact_generator import get_artifact_generator
    gen = get_artifact_generator()
    report_path = Path(gen.artifacts_dir) / job_id / "report.json"
    
    if not report_path.exists():
        raise HTTPException(404, "Artifact report not found")
    
    with open(report_path, encoding='utf-8') as f:
        report = json.load(f)
    
    return report


@router.get("/artifacts/{job_id}/download")
async def download_artifacts(job_id: str):
    """Download all artifacts as ZIP."""
    from pathlib import Path
    import zipfile
    import tempfile
    
    from app.core.artifact_generator import get_artifact_generator
    gen = get_artifact_generator()
    job_dir = Path(gen.artifacts_dir) / job_id
    
    if not job_dir.exists():
        raise HTTPException(404, "Artifacts not found")
    
    # Create ZIP — use NamedTemporaryFile to avoid TOCTOU race condition  
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    zip_path = tmp.name
    tmp.close()
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in job_dir.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(job_dir)
                zipf.write(file_path, arcname)
    
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"{job_id}_artifacts.zip"
    )


# ========================= METRICS & STRATEGY DASHBOARD (G16) =========================

@router.get("/metrics/{job_id}")
async def get_job_metrics(job_id: str):
    """
    Returns MetricsCollector summary for the given job.
    Includes token usage, latency, cache hit rate, and event timeline.
    """
    from app.core.persistence import get_checkpoint_manager
    from app.core.config import settings
    
    manager = get_checkpoint_manager(settings.REDIS_URL)
    checkpoint = await manager.load_checkpoint(job_id)
    
    if not checkpoint:
        raise HTTPException(404, "Job not found")
    
    # Rebuild metrics from checkpoint if available
    metrics_data = checkpoint.get("metrics", {})
    
    # Also try live MetricsCollector if this is the active job
    try:
        from app.core.metrics_collector import get_metrics_collector
        mc = get_metrics_collector()
        live_summary = mc.summary()
        # Merge live data with checkpoint data
        metrics_data = {**metrics_data, **live_summary}
    except Exception:
        pass
    
    return {
        "job_id": job_id,
        "metrics": metrics_data,
        "has_live_data": bool(metrics_data.get("timers"))
    }


@router.get("/strategy/{job_id}")
async def get_strategy_history(job_id: str):
    """
    Returns StrategyEngine attempt history for the given job.
    Shows escalation path, retry budget usage, and per-strategy outcomes.
    """
    from app.core.persistence import get_checkpoint_manager
    from app.core.config import settings
    
    manager = get_checkpoint_manager(settings.REDIS_URL)
    checkpoint = await manager.load_checkpoint(job_id)
    
    if not checkpoint:
        raise HTTPException(404, "Job not found")
    
    strategy_history = checkpoint.get("strategy_history", [])
    engine_state = checkpoint.get("strategy_engine_state", {})
    
    # Rebuild engine summary if state available
    engine_summary = {}
    if engine_state:
        try:
            from app.core.strategy_engine import StrategyEngine
            engine = StrategyEngine.from_dict(engine_state)
            engine_summary = engine.get_summary()
        except Exception:
            pass
    
    return {
        "job_id": job_id,
        "strategy_history": strategy_history,
        "total_attempts": len(strategy_history),
        "retries_used": checkpoint.get("total_retries_used", 0),
        "max_retries": checkpoint.get("max_total_retries", 5),
        "engine_summary": engine_summary,
        "current_strategy": checkpoint.get("current_repair_strategy")
    }


# ========================= DEBUG & DOCUMENTATION =========================

@router.post("/debug/{project_id}")
async def debug_project(project_id: str):
    """
    AI-powered debug analysis for a project.
    
    Analyzes execution logs, identifies issues, and suggests fixes
    using the TesterAgent's diagnostic capabilities.
    """
    from app.agents.tester import TesterAgent
    from pathlib import Path
    
    project_dir = BASE_PROJECTS_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(404, f"Project not found: {project_id}")
    
    # Collect execution logs from multiple sources
    log_sources = []
    
    # 1. Check for execution logs file
    log_file = project_dir / "execution.log"
    if log_file.exists():
        log_sources.append(log_file.read_text(encoding="utf-8", errors="replace"))
    
    # 2. Check for npm/build error logs
    for log_name in ["npm-debug.log", "build.log", "error.log"]:
        lf = project_dir / log_name
        if lf.exists():
            log_sources.append(f"--- {log_name} ---\n{lf.read_text(encoding='utf-8', errors='replace')}")
    
    # 3. Scan source files for obvious issues (syntax errors, missing imports)
    source_files = {}
    for ext in ["*.py", "*.js", "*.ts", "*.tsx", "*.jsx", "*.html", "*.css"]:
        for f in project_dir.rglob(ext):
            if "node_modules" not in str(f) and ".next" not in str(f):
                try:
                    rel = str(f.relative_to(project_dir))
                    source_files[rel] = f.read_text(encoding="utf-8", errors="replace")[:2000]  # First 2KB
                except Exception:
                    pass
    
    combined_logs = "\n\n".join(log_sources) if log_sources else "No execution logs available."
    
    try:
        tester = TesterAgent()
        analysis = await tester.analyze_execution(
            logs=combined_logs,
            context={
                "project_id": project_id,
                "file_count": len(source_files),
                "files_summary": list(source_files.keys())[:20],
                "source_snippets": dict(list(source_files.items())[:5])  # Top 5 files for context
            }
        )
        
        return {
            "project_id": project_id,
            "status": "analyzed",
            "issues_found": analysis.get("issues", []),
            "suggestions": analysis.get("suggestions", []),
            "severity": analysis.get("severity", "info"),
            "quick_check": tester.quick_check(combined_logs) if hasattr(tester, 'quick_check') else None
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Debug analysis failed: {str(e)}")


@router.post("/generate-docs/{project_id}")
async def generate_docs(project_id: str):
    """
    Generate README.md documentation for a project.
    
    Uses the DocumenterAgent to analyze the project structure
    and generate comprehensive documentation.
    """
    from app.agents.documenter import DocumenterAgent
    from pathlib import Path
    
    project_dir = BASE_PROJECTS_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(404, f"Project not found: {project_id}")
    
    # Load blueprint if available
    blueprint = _load_blueprint(project_id)
    
    # Build project context from file system
    project_files = read_project_files(project_id)
    project_context = {
        "project_id": project_id,
        "file_list": sorted(project_files.keys()) if isinstance(project_files, dict) else [],
        "tech_stack": blueprint.get("tech_stack", "Unknown"),
        "project_type": blueprint.get("projectType", "frontend"),
        "project_name": blueprint.get("project_name", project_id),
    }
    
    try:
        documenter = DocumenterAgent()
        readme_content = await documenter.generate_readme(
            context=project_context,
            blueprint=blueprint
        )
        
        # Write README.md to project directory
        readme_path = project_dir / "README.md"
        readme_path.write_text(readme_content, encoding="utf-8")
        
        # Also update in-memory file system for frontend
        return {
            "status": "generated",
            "project_id": project_id,
            "file": "README.md",
            "content": readme_content,
            "message": "README.md generated successfully"
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Documentation generation failed: {str(e)}")


# ========================= FILESYSTEM =========================

@router.get("/projects/{project_id}/files")
async def get_project_files(project_id: str):
    return read_project_files(project_id)


@router.get("/projects/{project_id}/files/content")
async def get_file_content(project_id: str, path: str):
    content = read_file(project_id, path)
    if content is None:
        raise HTTPException(404, "File not found")
    return {"content": content}


@router.put("/projects/{project_id}/files")
async def update_file(project_id: str, request: UpdateFileRequest):
    if not update_file_content(project_id, request.path, request.content):
        raise HTTPException(500, "Failed to update file")
    return {"status": "updated"}


@router.delete("/projects/{project_id}/files")
async def delete_file_endpoint(project_id: str, path: str):
    from app.core.filesystem import delete_file
    from app.services.e2b_vscode_service import get_e2b_vscode_service
    
    # 1. Delete from local filesystem
    if not delete_file(project_id, path):
        raise HTTPException(500, "Failed to delete file")
    
    # 2. Delete from sandbox if active
    e2b = get_e2b_vscode_service()
    await e2b.delete_file_in_sandbox(project_id, path)
    
    return {"status": "deleted"}


@router.get("/projects/{project_id}/download")
async def download_project(project_id: str):
    zip_path = archive_project(project_id)
    if not zip_path or not os.path.exists(zip_path):
        raise HTTPException(404, "Archive failed")
    return FileResponse(zip_path, media_type="application/zip", filename=f"{project_id}.zip")


# ========================= AI FILE EDIT =========================

@router.post("/update-file-ai/{project_id}")
async def ai_update_file(project_id: str, request: AIUpdateRequest):
    from app.services.smart_orchestrator import get_smart_orchestrator

    content = read_file(project_id, request.file_path)
    if content is None:
        raise HTTPException(404, "File not found")

    orchestrator = get_smart_orchestrator()
    updated = await orchestrator.update_single_file(
        project_id, request.file_path, content, request.instruction
    )

    update_file_content(project_id, request.file_path, updated)
    return {"status": "success"}


# ========================= EXECUTION (E2B) =========================

@router.post("/execute/{project_id}")
async def execute_project(project_id: str):
    from app.services.e2b_vscode_service import get_e2b_vscode_service
    blueprint = _load_blueprint(project_id)
    e2b = get_e2b_vscode_service()
    return await e2b.create_vscode_environment(project_id, blueprint)


@router.get("/logs/{project_id}")
async def get_logs(project_id: str):
    from app.services.e2b_vscode_service import get_e2b_vscode_service
    e2b = get_e2b_vscode_service()
    return {"logs": await e2b.get_logs(project_id)}


@router.post("/stop/{project_id}")
async def stop_project(project_id: str):
    from app.services.e2b_vscode_service import get_e2b_vscode_service
    e2b = get_e2b_vscode_service()
    return await e2b.stop_sandbox(project_id)


@router.post("/vscode/stop/{project_id}")
async def stop_vscode_project(project_id: str):
    """Alias for stop_project to match frontend expectation."""
    return await stop_project(project_id)


# ========================= TESTING AGENT =========================

@router.post("/test/{project_id}")
async def test_project(project_id: str, request: TestGenerationRequest):
    from app.agents.testing_agent import TestingAgent

    if not check_command("pytest --version"):
        raise HTTPException(500, "pytest not installed on server")

    files = read_project_files(project_id)
    if not files:
        raise HTTPException(404, "Project not found")

    project_path = str(BASE_PROJECTS_DIR / project_id)
    agent = TestingAgent()

    if request.run_tests:
        return await agent.generate_and_run_tests(
            project_path=project_path,
            file_system=files,
            tech_stack=request.tech_stack
        )
    else:
        return await agent.quick_validate(project_path)


# ========================= BROWSER VALIDATION =========================

@router.post("/validate-browser/{project_id}")
async def validate_browser(project_id: str, request: BrowserValidationRequest):
    from app.services.e2b_vscode_service import get_e2b_vscode_service
    from app.agents.browser_validation_agent import BrowserValidationAgent

    if not check_command("python -m playwright --version"):
        raise HTTPException(500, "playwright not installed on server")

    e2b = get_e2b_vscode_service()
    sandbox = e2b.get_sandbox(project_id)
    if not sandbox:
        raise HTTPException(400, "Run project first")

    agent = BrowserValidationAgent()
    return await agent.comprehensive_validate(
        url=sandbox["preview_url"],
        project_path=str(BASE_PROJECTS_DIR / project_id),
        validation_level=request.validation_level
    )


@router.post("/validate-browser/url")
async def validate_url(request: URLValidationRequest):
    from app.agents.browser_validation_agent import BrowserValidationAgent

    if not check_command("python -m playwright --version"):
        raise HTTPException(500, "playwright not installed on server")

    agent = BrowserValidationAgent()
    return await agent.comprehensive_validate(
        url=request.url,
        project_path="",
        validation_level=request.validation_level
    )


@router.post("/preview-browser-test/{project_id}")
async def run_preview_browser_test(project_id: str, request: BrowserValidationRequest):
    """
    Run browser validation on the live preview (REST alternative to Socket.IO).
    Uses PreviewBrowserTestService for URL resolution and structured reporting.
    """
    from app.services.preview_browser_test_service import get_preview_browser_test_service
    service = get_preview_browser_test_service()
    return await service.run_test(project_id, request.validation_level)


# ========================= SECURITY =========================

@router.post("/security-scan/{project_id}")
async def security_scan(project_id: str):
    if not check_command("bandit --version"):
        raise HTTPException(500, "bandit not installed on server")

    files = read_project_files(project_id)
    sentinel = SentinelAgent()
    return await sentinel.batch_audit(files)


@router.post("/security-scan/{project_id}/file")
async def security_scan_file(project_id: str, request: FileScanRequest):
    if not check_command("bandit --version"):
        raise HTTPException(500, "bandit not installed on server")

    content = read_file(project_id, request.file_path)
    sentinel = SentinelAgent()
    return await sentinel.audit_code(request.file_path, content)


@router.get("/security-scan/{project_id}/report")
async def security_report(project_id: str):
    files = read_project_files(project_id)
    sentinel = SentinelAgent()
    result = await sentinel.batch_audit(files)

    report = f"""# Security Scan Report
**Project ID:** {project_id}
**Scan Date:** {datetime.now().isoformat()}
**Status:** {result['status']}
"""
    return {"report": report}


# ========================= PREVIEW PROXY (ACEA SENTINEL) =========================

class PreviewRequest(BaseModel):
    timeout_minutes: int = 30

@router.post("/preview/{project_id}")
async def create_preview_session(project_id: str, request: PreviewRequest = None):
    """Create a managed preview session with semantic URL."""
    from app.services.e2b_vscode_service import get_e2b_vscode_service
    from app.services.preview_proxy_service import get_preview_proxy_service
    
    e2b_service = get_e2b_vscode_service()
    proxy_service = get_preview_proxy_service()
    
    # Get sandbox info
    sandbox_info = e2b_service.get_sandbox(project_id)
    if not sandbox_info:
        raise HTTPException(400, "No active sandbox for project. Execute project first.")
    
    # Create preview session
    timeout = request.timeout_minutes if request else 30
    session = await proxy_service.create_preview_session(
        project_id=project_id,
        sandbox_url=sandbox_info.get("preview_url", ""),
        sandbox_port=3000,
        timeout_minutes=timeout
    )
    
    return {
        "session_id": session.session_id,
        "preview_url": proxy_service.get_semantic_url(session.session_id),
        "expires_at": session.expires_at.isoformat(),
        "status": session.status.value
    }


@router.get("/preview/{session_id}/info")
async def get_preview_info(session_id: str):
    """Get information about a preview session."""
    from app.services.preview_proxy_service import get_preview_proxy_service
    
    proxy_service = get_preview_proxy_service()
    session = await proxy_service.get_session(session_id)
    
    if not session:
        raise HTTPException(404, "Preview session not found")
    
    return session.to_dict()


@router.delete("/preview/{session_id}")
async def terminate_preview_session(session_id: str):
    """Terminate a preview session."""
    from app.services.preview_proxy_service import get_preview_proxy_service
    
    proxy_service = get_preview_proxy_service()
    success = await proxy_service.terminate_session(session_id)
    
    if not success:
        raise HTTPException(404, "Preview session not found")
    
    return {"status": "terminated"}


# ========================= STUDIO MODE (ACEA SENTINEL) =========================

class StudioModeRequest(BaseModel):
    timeout_minutes: int = 60

@router.post("/studio/{project_id}")
async def activate_studio_mode(project_id: str, request: StudioModeRequest = None):
    """Activate Studio/Coder Mode with full desktop environment."""
    from app.services.e2b_desktop_service import get_e2b_desktop_service
    from app.core.filesystem import read_project_files
    
    desktop_service = get_e2b_desktop_service()
    
    if not desktop_service.is_available():
        raise HTTPException(
            503,
            "Studio Mode not available. E2B Desktop SDK not installed."
        )
    
    # Get project files
    files = read_project_files(project_id)
    if not files:
        raise HTTPException(404, "Project not found")
    
    # Convert file tree to flat dict
    file_dict = {}
    def flatten_files(node, path=""):
        if isinstance(node, dict):
            if "content" in node:
                file_dict[path] = node["content"]
            else:
                for key, value in node.items():
                    new_path = f"{path}/{key}" if path else key
                    flatten_files(value, new_path)
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, dict) and "path" in item:
                    flatten_files(item, item["path"])
    
    flatten_files(files)
    
    # Create desktop environment
    timeout = request.timeout_minutes if request else 60
    result = await desktop_service.create_desktop_environment(
        project_id=project_id,
        files=file_dict,
        timeout_minutes=timeout
    )
    
    if result["status"] == "error":
        raise HTTPException(500, result["message"])
    
    return result


@router.get("/studio/{project_id}")
async def get_studio_status(project_id: str):
    """Get status of Studio Mode session."""
    from app.services.e2b_desktop_service import get_e2b_desktop_service
    
    desktop_service = get_e2b_desktop_service()
    session = await desktop_service.get_session_by_project(project_id)
    
    if not session:
        return {"active": False}
    
    return {
        "active": True,
        "session": session.to_dict()
    }


@router.post("/studio/{project_id}/extend")
async def extend_studio_session(project_id: str, request: StudioModeRequest = None):
    """Extend Studio Mode session time."""
    from app.services.e2b_desktop_service import get_e2b_desktop_service
    
    desktop_service = get_e2b_desktop_service()
    session = await desktop_service.get_session_by_project(project_id)
    
    if not session:
        raise HTTPException(404, "No active Studio Mode session")
    
    minutes = request.timeout_minutes if request else 30
    result = await desktop_service.extend_session(session.session_id, minutes)
    
    return result


@router.delete("/studio/{project_id}")
async def deactivate_studio_mode(project_id: str):
    """Deactivate Studio Mode and return to Preview Mode."""
    from app.services.e2b_desktop_service import get_e2b_desktop_service
    
    desktop_service = get_e2b_desktop_service()
    success = await desktop_service.terminate_project_session(project_id)
    
    if not success:
        raise HTTPException(404, "No active Studio Mode session")
    
    return {"status": "deactivated", "mode": "preview"}


@router.post("/studio/{project_id}/sync")
async def sync_files_from_studio(project_id: str):
    """
    Sync files from Studio Mode sandbox back to backend.
    
    Call this before deactivating Studio Mode to save changes.
    """
    from app.services.e2b_desktop_service import get_e2b_desktop_service
    from app.core.filesystem import write_project_files
    
    desktop_service = get_e2b_desktop_service()
    session = await desktop_service.get_session_by_project(project_id)
    
    if not session:
        # If no session, just return success to avoid 404 spam in frontend
        return {
            "status": "no_session",
            "files_count": 0,
            "files": []
        }
    
    files = await desktop_service.sync_files_from_desktop(session.session_id)
    
    if files:
        # Write files to backend storage
        write_project_files(project_id, files)
    
    return {
        "status": "synced",
        "files_count": len(files),
        "files": list(files.keys())[:50]  # Return first 50 file names
    }


class StudioCommandRequest(BaseModel):
    command: str
    cwd: Optional[str] = None
    timeout: int = 60


@router.post("/studio/{project_id}/command")
async def run_studio_command(project_id: str, request: StudioCommandRequest):
    """Run a command in the Studio Mode sandbox."""
    from app.services.e2b_desktop_service import get_e2b_desktop_service
    
    desktop_service = get_e2b_desktop_service()
    session = await desktop_service.get_session_by_project(project_id)
    
    if not session:
        raise HTTPException(404, "No active Studio Mode session")
    
    result = await desktop_service.run_command(
        session.session_id,
        request.command,
        request.cwd or "/home/user/project",
        request.timeout
    )
    
    return result


@router.post("/studio/{project_id}/dev-server")
async def start_studio_dev_server(project_id: str, port: int = 3000):
    """Start development server in Studio Mode."""
    from app.services.e2b_desktop_service import get_e2b_desktop_service
    
    desktop_service = get_e2b_desktop_service()
    session = await desktop_service.get_session_by_project(project_id)
    
    if not session:
        raise HTTPException(404, "No active Studio Mode session")
    
    result = await desktop_service.start_dev_server(session.session_id, port=port)
    return result


@router.get("/studio/{project_id}/files")
async def get_studio_files(project_id: str):
    """Get file tree from Studio Mode sandbox."""
    from app.services.e2b_desktop_service import get_e2b_desktop_service
    
    desktop_service = get_e2b_desktop_service()
    session = await desktop_service.get_session_by_project(project_id)
    
    if not session:
        raise HTTPException(404, "No active Studio Mode session")
    
    tree = await desktop_service.get_file_tree(session.session_id)
    return tree


class StudioFileRequest(BaseModel):
    path: str
    content: Optional[str] = None


@router.get("/studio/{project_id}/file")
async def read_studio_file(project_id: str, path: str):
    """Read a file from Studio Mode sandbox."""
    from app.services.e2b_desktop_service import get_e2b_desktop_service
    
    desktop_service = get_e2b_desktop_service()
    session = await desktop_service.get_session_by_project(project_id)
    
    if not session:
        raise HTTPException(404, "No active Studio Mode session")
    
    content = await desktop_service.read_file(session.session_id, path)
    
    if content is None:
        raise HTTPException(404, f"File not found: {path}")
    
    return {"path": path, "content": content}


@router.put("/studio/{project_id}/file")
async def write_studio_file(project_id: str, request: StudioFileRequest):
    """Write a file to Studio Mode sandbox."""
    from app.services.e2b_desktop_service import get_e2b_desktop_service
    
    desktop_service = get_e2b_desktop_service()
    session = await desktop_service.get_session_by_project(project_id)
    
    if not session:
        raise HTTPException(404, "No active Studio Mode session")
    
    if request.content is None:
        raise HTTPException(400, "Content is required")
    
    success = await desktop_service.write_file(
        session.session_id,
        request.path,
        request.content
    )
    
    if not success:
        raise HTTPException(500, "Failed to write file")
    
    return {"status": "written", "path": request.path}


@router.post("/studio/{project_id}/heartbeat")
async def studio_heartbeat(project_id: str):
    """
    Record activity heartbeat to prevent idle suspension.
    
    Call this periodically (e.g., every 5 minutes) to keep session alive.
    """
    from app.services.e2b_desktop_service import get_e2b_desktop_service
    
    desktop_service = get_e2b_desktop_service()
    session = await desktop_service.get_session_by_project(project_id)
    
    if not session:
        raise HTTPException(404, "No active Studio Mode session")
    
    await desktop_service.record_activity(session.session_id)
    
    return {
        "status": "ok",
        "time_remaining_minutes": session.time_remaining_minutes(),
        "session_status": session.status.value
    }


@router.post("/studio/{project_id}/resume")
async def resume_studio_session(project_id: str):
    """Resume a suspended Studio Mode session."""
    from app.services.e2b_desktop_service import get_e2b_desktop_service
    
    desktop_service = get_e2b_desktop_service()
    session = await desktop_service.get_session_by_project(project_id)
    
    if not session:
        raise HTTPException(404, "No Studio Mode session to resume")
    
    result = await desktop_service.resume_session(session.session_id)
    
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Failed to resume"))
    
    return result


# ========================= VISUAL ARTIFACTS (ACEA SENTINEL) =========================

@router.get("/visual-artifacts/{project_id}")
async def get_visual_artifacts(project_id: str):
    """Get visual artifacts captured by Watcher agent."""
    from app.services.preview_proxy_service import get_preview_proxy_service
    
    proxy_service = get_preview_proxy_service()
    session = await proxy_service.get_session_by_project(project_id)
    
    if not session:
        return {
            "has_artifacts": False,
            "message": "No active preview session"
        }
    
    artifacts = await proxy_service.get_visual_artifacts(session.session_id)
    artifacts["has_artifacts"] = True
    return artifacts


@router.post("/visual-qa/{project_id}")
async def trigger_visual_qa(project_id: str):
    """Trigger Gemini Vision analysis on current preview."""
    from app.agents.watcher import WatcherAgent
    from app.services.e2b_vscode_service import get_e2b_vscode_service
    
    e2b_service = get_e2b_vscode_service()
    sandbox_info = e2b_service.get_sandbox(project_id)
    
    if not sandbox_info:
        raise HTTPException(400, "No active sandbox. Execute project first.")
    
    preview_url = sandbox_info.get("preview_url")
    if not preview_url:
        raise HTTPException(400, "No preview URL available")
    
    watcher = WatcherAgent()
    
    # Capture visual artifacts
    artifacts = await watcher.capture_visual_artifacts(preview_url)
    
    # Run Gemini Vision analysis
    context = {"project_id": project_id}
    analysis_result = await watcher.analyze_with_gemini_vision(artifacts, context)
    
    return {
        "artifacts": artifacts.to_dict(),
        "analysis": analysis_result
    }


# ========================= RELEASE AGENT (PHASE 2) =========================

class ReleaseRequest(BaseModel):
    deploy_targets: Optional[list] = None  # e.g., ["vercel", "docker"]
    generate_readme: bool = True
    generate_cicd: bool = True


@router.post("/release/{project_id}")
async def prepare_release(project_id: str, request: ReleaseRequest = None):
    """
    Prepare project for release with deployment artifacts.
    
    Generates:
    - Dockerfile or platform-specific config (vercel.json, netlify.toml)
    - CI/CD workflows (.github/workflows/ci.yml)
    - release.json manifest
    - README.md if missing
    """
    from app.agents.release import ReleaseAgent, DeployTarget
    
    # Verify project exists
    project_path = BASE_PROJECTS_DIR / project_id
    if not project_path.exists():
        raise HTTPException(404, f"Project not found: {project_id}")
    
    # Load blueprint if available
    blueprint = _load_blueprint(project_id)
    
    # Parse deploy targets
    deploy_targets = None
    if request and request.deploy_targets:
        deploy_targets = []
        for target in request.deploy_targets:
            try:
                deploy_targets.append(DeployTarget(target.lower()))
            except ValueError:
                pass  # Skip invalid targets
    
    release_agent = ReleaseAgent()
    report = await release_agent.prepare_release(
        project_id=project_id,
        blueprint=blueprint,
        deploy_targets=deploy_targets,
        generate_readme=request.generate_readme if request else True,
        generate_cicd=request.generate_cicd if request else True
    )
    
    return report.to_dict()


@router.get("/release/{project_id}/download")
async def download_release(project_id: str):
    """Download project as ZIP archive with all generated artifacts."""
    from app.agents.release import ReleaseAgent
    
    project_path = BASE_PROJECTS_DIR / project_id
    if not project_path.exists():
        raise HTTPException(404, f"Project not found: {project_id}")
    
    release_agent = ReleaseAgent()
    archive_path = release_agent.create_archive(project_id)
    
    if not os.path.exists(archive_path):
        raise HTTPException(500, "Failed to create archive")
    
    return FileResponse(
        path=archive_path,
        media_type="application/zip",
        filename=f"{project_id}.zip"
    )

