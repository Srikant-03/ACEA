# Execution Service - Unified Code Execution Layer
# Priority: CodeSandbox (default) -> Docker (fallback) -> Simulation (last resort)

import os
import time
import subprocess
import asyncio
from typing import Dict, Optional, List
from pathlib import Path

# Try to import docker, fall back if not available
try:
    import docker
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    print("Docker SDK not installed.")

from app.core.filesystem import BASE_PROJECTS_DIR


class ExecutionService:
    """
    Unified execution service that tries multiple backends.
    Priority: CodeSandbox -> Docker -> Simulation
    """
    
    def __init__(self):
        self.docker_client = None
        self.active_containers: Dict[str, str] = {}  # project_id -> container_id
        self.active_sandboxes: Dict[str, dict] = {}  # project_id -> {sandbox_id, urls}
        self.simulated_logs: Dict[str, List[str]] = {}     # project_id -> list of log lines
        self.execution_method: Dict[str, str] = {}   # project_id -> "codesandbox"|"docker"|"simulated"
        
        if DOCKER_AVAILABLE:
            try:
                self.docker_client = docker.from_env()
                self.docker_client.ping()
                print("ExecutionService: Docker available as fallback")
            except Exception as e:
                print(f"ExecutionService: Docker not available ({e})")
                self.docker_client = None
    
    async def execute_project(self, project_id: str, blueprint: dict) -> Dict:
        """
        Execute project using best available method.
        Priority: CodeSandbox -> Docker -> Simulation
        
        Returns:
        {
            "status": "success|error|simulated",
            "logs": str,
            "preview_url": Optional[str],
            "embed_url": Optional[str],
            "execution_method": str,
            "container_id": Optional[str]
        }
        """
        project_path = BASE_PROJECTS_DIR / project_id
        
        if not project_path.exists():
            return {
                "status": "error",
                "logs": f"Project directory not found: {project_id}",
                "preview_url": None,
                "embed_url": None,
                "execution_method": "none",
                "container_id": None
            }
        
        # 1. Try CodeSandbox first (cloud-based, works everywhere)
        codesandbox_result = await self._execute_codesandbox(project_id, blueprint)
        if codesandbox_result["status"] == "success":
            self.execution_method[project_id] = "codesandbox"
            return codesandbox_result
        
        print(f"CodeSandbox failed: {codesandbox_result.get('logs', 'Unknown error')}")
        
        # 2. Fallback to Docker if available
        if self.docker_client:
            docker_result = self._execute_docker(project_id, blueprint)
            if docker_result["status"] == "success":
                self.execution_method[project_id] = "docker"
                docker_result["execution_method"] = "docker"
                return docker_result
            print(f"Docker failed: {docker_result.get('logs', 'Unknown error')}")
        
        # 3. Last resort: simulation
        self.execution_method[project_id] = "simulated"
        return self._simulate_execution(project_id, blueprint)
    
    async def _execute_codesandbox(self, project_id: str, blueprint: dict) -> Dict:
        """Create and run project on CodeSandbox."""
        try:
            from app.services.codesandbox_service import get_codesandbox_service
            
            csb_service = get_codesandbox_service()
            result = await csb_service.create_sandbox(project_id, blueprint)
            
            if result["status"] == "success":
                self.active_sandboxes[project_id] = {
                    "sandbox_id": result["sandbox_id"],
                    "preview_url": result["preview_url"],
                    "embed_url": result["embed_url"]
                }
                
                return {
                    "status": "success",
                    "logs": result["logs"],
                    "preview_url": result["preview_url"],
                    "embed_url": result["embed_url"],
                    "execution_method": "codesandbox",
                    "container_id": result["sandbox_id"]
                }
            
            return result
            
        except Exception as e:
            return {
                "status": "error",
                "logs": f"CodeSandbox error: {str(e)}",
                "preview_url": None,
                "embed_url": None,
                "execution_method": "codesandbox",
                "container_id": None
            }
    
    def _execute_docker(self, project_id: str, blueprint: dict) -> Dict:
        """Execute project in Docker container."""
        project_path = BASE_PROJECTS_DIR / project_id
        
        try:
            image = self._get_docker_image(blueprint)
            command = self._get_run_command(blueprint)
            port = self._get_port(blueprint)
            
            # Pull image if not present
            try:
                self.docker_client.images.get(image)
            except docker.errors.ImageNotFound:
                print(f"Pulling image: {image}")
                self.docker_client.images.pull(image)
            
            # Create and start container
            container = self.docker_client.containers.run(
                image=image,
                command=command,
                volumes={
                    str(project_path.absolute()): {
                        'bind': '/workspace',
                        'mode': 'rw'
                    }
                },
                working_dir='/workspace',
                ports={f'{port}/tcp': None},
                mem_limit='512m',
                cpu_period=100000,
                cpu_quota=50000,
                detach=True,
                remove=False,
                name=f"acea_{project_id}_{int(time.time())}"
            )
            
            self.active_containers[project_id] = container.id
            
            # Wait a bit and get initial logs
            time.sleep(2)
            logs = container.logs(tail=100).decode('utf-8', errors='replace')
            
            # Get mapped port
            container.reload()
            port_bindings = container.attrs.get('NetworkSettings', {}).get('Ports', {})
            host_port = None
            if f'{port}/tcp' in port_bindings and port_bindings[f'{port}/tcp']:
                host_port = port_bindings[f'{port}/tcp'][0].get('HostPort')
            
            preview_url = f"http://localhost:{host_port}" if host_port else None
            
            return {
                "status": "success",
                "logs": logs,
                "preview_url": preview_url,
                "embed_url": None,
                "execution_method": "docker",
                "container_id": container.id
            }
            
        except Exception as e:
            return {
                "status": "error",
                "logs": f"Docker execution failed: {str(e)}",
                "preview_url": None,
                "embed_url": None,
                "execution_method": "docker",
                "container_id": None
            }
    
    def _simulate_execution(self, project_id: str, blueprint: dict) -> Dict:
        """Simulated execution when no execution backend is available."""
        project_path = BASE_PROJECTS_DIR / project_id
        
        files = list(project_path.glob("**/*"))
        file_list = [str(f.relative_to(project_path)) for f in files if f.is_file()]
        
        logs = f"""
=== SIMULATED EXECUTION ===
Project: {project_id}
Tech Stack: {blueprint.get('tech_stack', 'Unknown')}
Files: {len(file_list)}

[INFO] CodeSandbox and Docker unavailable.
[INFO] Running in simulation mode.
[SIM] Initializing runtime environment...
[SIM] Checking dependencies: {'package.json' in str(file_list)}
[SIM] Simulation started.

To enable real execution:
1. CodeSandbox: Ensure internet connectivity
2. Docker: Install and start Docker Desktop
"""
        self.simulated_logs[project_id] = [logs]
        
        return {
            "status": "simulated",
            "logs": logs,
            "preview_url": None,
            "embed_url": None,
            "execution_method": "simulated",
            "container_id": f"sim_{project_id}"
        }
    
    def _get_docker_image(self, blueprint: dict) -> str:
        """Determine Docker base image from blueprint."""
        stack = blueprint.get("tech_stack", "").lower()
        project_type = blueprint.get("projectType", "frontend")
        
        if "python" in stack or project_type == "backend":
            return "python:3.11-slim"
        elif "node" in stack or "react" in stack or "vue" in stack or "next" in stack:
            return "node:18-alpine"
        else:
            return "node:18-alpine"
    
    def _get_run_command(self, blueprint: dict) -> List[str]:
        """Get the command to run the project."""
        stack = blueprint.get("tech_stack", "").lower()
        
        if "python" in stack:
            return ["sh", "-c", "pip install -r requirements.txt 2>/dev/null; python main.py || python app.py || python -m flask run --host=0.0.0.0"]
        elif "next" in stack:
            return ["sh", "-c", "npm install && npm run dev"]
        elif "react" in stack or "vue" in stack:
            return ["sh", "-c", "npm install && npm start"]
        else:
            return ["sh", "-c", "npm install && npm start"]
    
    def _get_port(self, blueprint: dict) -> int:
        """Get the port to expose."""
        return blueprint.get("port", 3000)
    
    def get_logs(self, project_id: str, tail: int = 200) -> str:
        """Fetch logs from running execution."""
        method = self.execution_method.get(project_id)
        
        if method == "codesandbox":
            sandbox = self.active_sandboxes.get(project_id)
            if sandbox:
                return f"CodeSandbox running: {sandbox['preview_url']}\nView full logs at: https://codesandbox.io/s/{sandbox['sandbox_id']}"
            return "No active CodeSandbox for this project."
        
        elif method == "docker":
            container_id = self.active_containers.get(project_id)
            if not container_id:
                return "No active container for this project."
            try:
                container = self.docker_client.containers.get(container_id)
                return container.logs(tail=tail).decode('utf-8', errors='replace')
            except Exception as e:
                return f"Error fetching logs: {e}"
        
        else:
            if project_id in self.simulated_logs:
                # Add timestamp if it's been a while (mocking activity)
                current_logs = self.simulated_logs[project_id]
                if len(current_logs) < 50: # Limit simulation output
                     self.simulated_logs[project_id].append(f"[SIM] Activity at {time.strftime('%H:%M:%S')}...\n")
                return "".join(self.simulated_logs[project_id])
            return "No execution active for this project."
    
    def stop_execution(self, project_id: str) -> bool:
        """Stop running execution."""
        method = self.execution_method.get(project_id)
        
        if method == "codesandbox":
            # CodeSandbox doesn't need stopping - just clear reference
            if project_id in self.active_sandboxes:
                del self.active_sandboxes[project_id]
            if project_id in self.execution_method:
                del self.execution_method[project_id]
            return True
        
        elif method == "docker":
            container_id = self.active_containers.get(project_id)
            if not container_id:
                return False
            try:
                container = self.docker_client.containers.get(container_id)
                container.stop(timeout=5)
                container.remove()
                del self.active_containers[project_id]
                del self.execution_method[project_id]
                return True
            except Exception as e:
                print(f"Error stopping container: {e}")
                return False
        
        else:
            if project_id in self.simulated_logs:
                del self.simulated_logs[project_id]
            if project_id in self.execution_method:
                del self.execution_method[project_id]
            return True
    
    def cleanup_old_containers(self, max_age_hours: int = 2) -> int:
        """Remove Docker containers older than specified hours."""
        if not self.docker_client:
            return 0
        
        removed = 0
        try:
            containers = self.docker_client.containers.list(all=True, filters={"name": "acea_"})
            for container in containers:
                if container.status in ['exited', 'dead']:
                    container.remove()
                    removed += 1
        except Exception as e:
            print(f"Cleanup error: {e}")
        
        return removed


# Singleton instance
_execution_service = None

def get_execution_service() -> ExecutionService:
    global _execution_service
    if _execution_service is None:
        _execution_service = ExecutionService()
    return _execution_service


# Backward compatibility aliases
DockerService = ExecutionService
get_docker_service = get_execution_service
