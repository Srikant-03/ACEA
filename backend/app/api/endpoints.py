from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.agents.architect import ArchitectAgent
from app.agents.virtuoso import VirtuosoAgent
from app.agents.sentinel import SentinelAgent
from app.agents.oracle import OracleAgent
from app.agents.watcher import WatcherAgent
from app.agents.advisor import AdvisorAgent

router = APIRouter()

class PromptRequest(BaseModel):
    prompt: str
    project_id: str

@router.post("/architect/design")
async def run_architect(request: PromptRequest):
    agent = ArchitectAgent()
    result = await agent.design_system(request.prompt)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result

@router.post("/virtuoso/generate")
async def run_virtuoso(file_path: str, description: str):
    agent = VirtuosoAgent()
    code = await agent.generate_code(file_path, description)
    return {"code": code}

@router.post("/sentinel/audit")
async def run_sentinel(file_path: str, code: str):
    agent = SentinelAgent()
    result = await agent.audit_code(file_path, code)
    return result

from app.core.filesystem import read_project_files, read_file

@router.get("/projects/{project_id}/files")
async def get_project_files_route(project_id: str):
    # Return all files with content for initial load (efficient for small projects)
    # or just list. Let's return full dict for the "Replit" feel (instant click)
    files = read_project_files(project_id)
    return files

@router.get("/projects/{project_id}/files/content")
async def get_file_content_route(project_id: str, path: str):
    content = read_file(project_id, path)
    if content is None:
        raise HTTPException(status_code=404, detail="File not found")
    return {"content": content}

class UpdateFileRequest(BaseModel):
    path: str
    content: str

@router.put("/projects/{project_id}/files")
async def update_file_route(project_id: str, request: UpdateFileRequest):
    from app.core.filesystem import update_file_content
    success = update_file_content(project_id, request.path, request.content)
    if not success:
         raise HTTPException(status_code=500, detail="Failed to update file")
    return {"status": "updated", "path": request.path}

from fastapi.responses import FileResponse
import os

@router.get("/projects/{project_id}/download")
async def download_project_route(project_id: str):
    from app.core.filesystem import archive_project
    zip_path = archive_project(project_id)
    
    if not zip_path or not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail="Project not found or archive failed")
        
    return FileResponse(
        zip_path, 
        media_type='application/zip', 
        filename=f"{project_id}.zip"
    )

class GenerateRequest(BaseModel):
    prompt: str
    tech_stack: str = "Auto-detect"

@router.post("/generate")
async def generate_project_route(request: GenerateRequest):
    from app.core.socket_manager import SocketManager
    from app import event_handlers # Ensure handlers are loaded
    
    # We trigger the same 'start_mission' logic but via API
    # Since start_mission expects a socket ID (sid), we might need to decouple it 
    # OR we just trigger the graph directly here in background.
    
    # BETTTER APPROACH for Phase 1:
    # 1. Frontend connects socket first -> gets socket ID.
    # 2. Frontend calls this API with socket_id included?
    # NO, strictly speaking, this endpoint should just return a project_id 
    # and kick off the process.
    
    # For now, let's keep the user flow simple:
    # return a status saying "Use the WebSocket for real-time generation"
    # OR actually start the background task.
    
    return {"status": "use_socket_for_now", "message": "Please use the 'INITIATE LAUNCH' button which uses WebSocket for real-time logs."}

# ==================== EXECUTION ENDPOINTS ====================

from app.services.docker_service import get_docker_service
from app.core.filesystem import read_project_files
import json

def _load_blueprint(project_id: str) -> dict:
    """Load blueprint.json from project directory."""
    from app.core.filesystem import BASE_PROJECTS_DIR
    blueprint_path = BASE_PROJECTS_DIR / project_id / "blueprint.json"
    if blueprint_path.exists():
        with open(blueprint_path) as f:
            return json.load(f)
    return {"tech_stack": "Unknown", "projectType": "frontend"}

@router.post("/execute/{project_id}")
async def execute_project_route(project_id: str):
    """Execute project in Docker container."""
    docker_service = get_docker_service()
    blueprint = _load_blueprint(project_id)
    
    result = docker_service.execute_project(project_id, blueprint)
    
    return {
        "status": result["status"],
        "logs": result["logs"],
        "preview_url": result.get("preview_url"),
        "container_id": result.get("container_id")
    }

@router.get("/logs/{project_id}")
async def get_logs_route(project_id: str):
    """Get real-time logs from running container."""
    docker_service = get_docker_service()
    logs = docker_service.get_container_logs(project_id)
    return {"logs": logs}

@router.post("/stop/{project_id}")
async def stop_project_route(project_id: str):
    """Stop running container."""
    docker_service = get_docker_service()
    success = docker_service.stop_container(project_id)
    return {"status": "stopped" if success else "not_found"}

@router.post("/debug/{project_id}")
async def debug_project_route(project_id: str):
    """Analyze execution logs and suggest fixes."""
    from app.agents.tester import TesterAgent
    
    docker_service = get_docker_service()
    tester = TesterAgent()
    
    # Get logs
    logs = docker_service.get_container_logs(project_id)
    blueprint = _load_blueprint(project_id)
    
    # Analyze
    result = await tester.analyze_execution(logs, blueprint)
    
    return {
        "issues_found": result.get("issues", []),
        "suggestions": result.get("suggestions", []),
        "fixes": result.get("fixes", []),
        "status": result.get("status", "unknown")
    }

@router.post("/generate-docs/{project_id}")
async def generate_docs_route(project_id: str):
    """Generate README.md for project."""
    from app.agents.documenter import DocumenterAgent
    from app.core.filesystem import update_file_content
    
    documenter = DocumenterAgent()
    blueprint = _load_blueprint(project_id)
    files = list(read_project_files(project_id).keys())
    
    readme = await documenter.generate_readme(
        blueprint, 
        files, 
        blueprint.get("description", "Project")
    )
    
    # Save to project
    success = update_file_content(project_id, "README.md", readme)
    
    return {
        "status": "generated" if success else "error",
        "content": readme[:500] + "..." if len(readme) > 500 else readme
    }

@router.get("/validate/{project_id}")
async def validate_project_route(project_id: str):
    """Validate project before download."""
    from app.agents.release import ReleaseAgent
    
    release = ReleaseAgent()
    blueprint = _load_blueprint(project_id)
    
    result = release.prepare_release(project_id, blueprint)
    
    return result

# ==================== AI EDIT & MONITORING ENDPOINTS ====================

class AIUpdateRequest(BaseModel):
    file_path: str
    instruction: str

@router.post("/update-file-ai/{project_id}")
async def ai_update_file(project_id: str, request: AIUpdateRequest):
    """
    AI-powered single file update.
    Uses minimal API call - only modifies one file.
    """
    from app.services.smart_orchestrator import get_smart_orchestrator
    from app.core.filesystem import read_file
    
    # Get current file content
    current_content = read_file(project_id, request.file_path)
    if current_content is None:
        raise HTTPException(status_code=404, detail="File not found")
    
    # AI update
    orchestrator = get_smart_orchestrator()
    updated_content = await orchestrator.update_single_file(
        project_id,
        request.file_path,
        current_content,
        request.instruction
    )
    
    return {
        "status": "success",
        "file_path": request.file_path,
        "updated_content": updated_content
    }

@router.get("/keys/status")
async def get_key_status():
    """Returns health status of all API keys."""
    from app.core.key_manager import KeyManager
    
    km = KeyManager()
    return km.get_status()

@router.post("/generate-optimized")
async def generate_project_optimized(request: GenerateRequest):
    """
    Optimized project generation using Smart Orchestrator.
    Uses combined prompts and caching for reduced API calls.
    """
    from app.services.smart_orchestrator import get_smart_orchestrator
    from app.core.filesystem import BASE_PROJECTS_DIR
    import uuid
    
    project_id = str(uuid.uuid4())
    orchestrator = get_smart_orchestrator()
    
    result = await orchestrator.generate_project_optimized(
        prompt=request.prompt,
        tech_stack=request.tech_stack if request.tech_stack != "Auto-detect" else None,
        include_docs=True
    )
    
    # Write files
    project_dir = BASE_PROJECTS_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    
    files = result.get("files", {})
    for path, content in files.items():
        file_path = project_dir / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w') as f:
            f.write(content)
    
    # Save blueprint
    blueprint = result.get("blueprint", {})
    with open(project_dir / "blueprint.json", 'w') as f:
        json.dump(blueprint, f, indent=2)
    
    return {
        "project_id": project_id,
        "status": "success",
        "source": result.get("source", "api"),
        "files_generated": len(files)
    }
