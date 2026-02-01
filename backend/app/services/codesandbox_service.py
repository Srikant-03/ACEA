# CodeSandbox Service - Cloud-Based Code Execution
# Default execution method. Falls back to Docker if CodeSandbox fails.

import os
import httpx
from typing import Dict, Optional
from pathlib import Path

from app.core.filesystem import BASE_PROJECTS_DIR, read_project_files


# CodeSandbox API configuration
CODESANDBOX_API_KEY = os.getenv("CODESANDBOX_API_KEY", "")
CODESANDBOX_DEFINE_URL = "https://codesandbox.io/api/v1/sandboxes/define"


class CodeSandboxService:
    """Manages code execution via CodeSandbox cloud sandboxes."""
    
    def __init__(self):
        self.active_sandboxes: Dict[str, str] = {}  # project_id -> sandbox_id
        self.api_key = CODESANDBOX_API_KEY
        
        if self.api_key:
            print("CodeSandboxService: API key configured")
        else:
            print("CodeSandboxService: No API key - using anonymous mode (may have rate limits)")
    
    def _prepare_files_payload(self, project_id: str) -> Dict:
        """
        Convert project files to CodeSandbox format.
        Format: { "path/to/file.js": { "content": "...", "isBinary": false } }
        """
        project_files = read_project_files(project_id)
        
        if not project_files:
            return {}
        
        files_payload = {}
        binary_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.ico', '.woff', '.woff2', '.ttf', '.eot', '.svg'}
        skip_dirs = {'node_modules', '.git', '__pycache__', '.next', 'dist', 'build'}
        
        for path, content in project_files.items():
            # Skip blueprint.json (internal file)
            if path == "blueprint.json":
                continue
            
            # Skip unwanted directories
            if any(skip_dir in path for skip_dir in skip_dirs):
                continue
                
            ext = Path(path).suffix.lower()
            is_binary = ext in binary_extensions
            
            if is_binary:
                # For binary files, we'd need to host them externally
                # Skip for now - CodeSandbox requires URL for binary files
                continue
            
            files_payload[path] = {
                "content": content,
                "isBinary": False
            }
        
        return files_payload
    
    def _get_default_package_json(self, blueprint: dict) -> dict:
        """Generate a default package.json based on tech stack."""
        tech_stack = blueprint.get("tech_stack", "").lower()
        
        if "next" in tech_stack:
            return {
                "name": "acea-nextjs-project",
                "version": "0.1.0",
                "private": True,
                "scripts": {
                    "dev": "next dev",
                    "build": "next build",
                    "start": "next start"
                },
                "dependencies": {
                    "next": "14.0.0",
                    "react": "^18",
                    "react-dom": "^18"
                }
            }
        elif "react" in tech_stack:
            return {
                "name": "acea-react-project",
                "version": "0.1.0",
                "private": True,
                "scripts": {
                    "start": "react-scripts start",
                    "build": "react-scripts build"
                },
                "dependencies": {
                    "react": "^18",
                    "react-dom": "^18",
                    "react-scripts": "5.0.1"
                }
            }
        elif "vue" in tech_stack:
            return {
                "name": "acea-vue-project",
                "version": "0.1.0",
                "private": True,
                "scripts": {
                    "dev": "vite",
                    "build": "vite build"
                },
                "dependencies": {
                    "vue": "^3.3.0"
                },
                "devDependencies": {
                    "vite": "^4.0.0",
                    "@vitejs/plugin-vue": "^4.0.0"
                }
            }
        else:
            # Default to vanilla JS
            return {
                "name": "acea-project",
                "version": "0.1.0",
                "private": True,
                "scripts": {
                    "start": "npx serve ."
                },
                "dependencies": {}
            }
    
    async def create_sandbox(self, project_id: str, blueprint: dict) -> Dict:
        """
        Create a CodeSandbox from project files.
        
        Returns:
        {
            "status": "success|error",
            "sandbox_id": str,
            "preview_url": str,
            "embed_url": str,
            "logs": str
        }
        """
        import json
        
        files_payload = self._prepare_files_payload(project_id)
        
        if not files_payload:
            return {
                "status": "error",
                "logs": "No files found in project",
                "preview_url": None,
                "embed_url": None,
                "sandbox_id": None
            }
        
        # Ensure package.json exists for Node projects
        if "package.json" not in files_payload:
            pkg = self._get_default_package_json(blueprint)
            files_payload["package.json"] = {
                "content": json.dumps(pkg, indent=2),
                "isBinary": False
            }
        
        # Build headers
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{CODESANDBOX_DEFINE_URL}?json=1",
                    json={"files": files_payload},
                    headers=headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    sandbox_id = data.get("sandbox_id")
                    
                    if sandbox_id:
                        self.active_sandboxes[project_id] = sandbox_id
                        
                        preview_url = f"https://{sandbox_id}.csb.app/"
                        embed_url = f"https://codesandbox.io/embed/{sandbox_id}?fontsize=14&hidenavigation=1&theme=dark&view=preview"
                        
                        return {
                            "status": "success",
                            "sandbox_id": sandbox_id,
                            "preview_url": preview_url,
                            "embed_url": embed_url,
                            "logs": f"✅ CodeSandbox created successfully!\n\n🆔 Sandbox ID: {sandbox_id}\n🌐 Preview: {preview_url}\n📦 Editor: https://codesandbox.io/s/{sandbox_id}"
                        }
                    else:
                        return {
                            "status": "error",
                            "logs": f"No sandbox_id in response: {data}",
                            "preview_url": None,
                            "embed_url": None,
                            "sandbox_id": None
                        }
                else:
                    error_text = response.text[:500] if response.text else "Unknown error"
                    return {
                        "status": "error",
                        "logs": f"CodeSandbox API error ({response.status_code}): {error_text}",
                        "preview_url": None,
                        "embed_url": None,
                        "sandbox_id": None
                    }
                    
        except httpx.TimeoutException:
            return {
                "status": "error",
                "logs": "CodeSandbox API timeout (60s). The project may be too large or the API is slow.",
                "preview_url": None,
                "embed_url": None,
                "sandbox_id": None
            }
        except httpx.ConnectError:
            return {
                "status": "error",
                "logs": "Cannot connect to CodeSandbox. Check internet connection.",
                "preview_url": None,
                "embed_url": None,
                "sandbox_id": None
            }
        except Exception as e:
            return {
                "status": "error",
                "logs": f"CodeSandbox error: {str(e)}",
                "preview_url": None,
                "embed_url": None,
                "sandbox_id": None
            }
    
    def get_sandbox_url(self, project_id: str) -> Optional[str]:
        """Get the preview URL for an existing sandbox."""
        sandbox_id = self.active_sandboxes.get(project_id)
        if sandbox_id:
            return f"https://{sandbox_id}.csb.app/"
        return None
    
    def get_embed_url(self, project_id: str) -> Optional[str]:
        """Get the embeddable URL for an existing sandbox."""
        sandbox_id = self.active_sandboxes.get(project_id)
        if sandbox_id:
            return f"https://codesandbox.io/embed/{sandbox_id}?fontsize=14&hidenavigation=1&theme=dark&view=preview"
        return None


# Singleton instance
_codesandbox_service = None

def get_codesandbox_service() -> CodeSandboxService:
    global _codesandbox_service
    if _codesandbox_service is None:
        _codesandbox_service = CodeSandboxService()
    return _codesandbox_service
