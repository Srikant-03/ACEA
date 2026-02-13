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
    from app.services.e2b_service import get_e2b_service
    blueprint = _load_blueprint(project_id)
    e2b = get_e2b_service()
    return await e2b.create_sandbox(project_id, blueprint)


@router.get("/logs/{project_id}")
async def get_logs(project_id: str):
    from app.services.e2b_service import get_e2b_service
    e2b = get_e2b_service()
    return {"logs": await e2b.get_logs(project_id)}


@router.post("/stop/{project_id}")
async def stop_project(project_id: str):
    from app.services.e2b_service import get_e2b_service
    e2b = get_e2b_service()
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
    from app.services.e2b_service import get_e2b_service
    from app.agents.browser_validation_agent import BrowserValidationAgent

    if not check_command("python -m playwright --version"):
        raise HTTPException(500, "playwright not installed on server")

    e2b = get_e2b_service()
    sandbox = e2b.sandboxes.get(project_id)
    if not sandbox:
        raise HTTPException(400, "Run project first")

    agent = BrowserValidationAgent()
    return await agent.comprehensive_validate(
        url=sandbox["url"],
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

