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

    agent = WatcherAgent()
    result = await agent.verify_url(url)
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
