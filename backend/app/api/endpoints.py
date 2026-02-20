from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime
import os
import json
import subprocess
import logging
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
    try:
        subprocess.run(cmd, shell=True, capture_output=True, timeout=2)
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
        raise HTTPException(404, "No active Studio Mode session")
    
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

