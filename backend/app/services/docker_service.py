# Docker Service - Container Execution Layer
# Handles project execution in isolated Docker containers

import os
import time
import subprocess
from typing import Dict, Optional, List
from pathlib import Path

# Try to import docker, fall back to simulation if not available
try:
    import docker
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    print("Docker SDK not installed. Using simulated execution.")

from app.core.filesystem import BASE_PROJECTS_DIR


class DockerService:
    """Manages Docker container execution for generated projects."""
    
    def __init__(self):
        self.client = None
        self.active_containers: Dict[str, str] = {}  # project_id -> container_id
        
        if DOCKER_AVAILABLE:
            try:
                self.client = docker.from_env()
                self.client.ping()
                print("DockerService: Connected to Docker daemon")
            except Exception as e:
                print(f"DockerService: Docker not available ({e}). Using simulation.")
                self.client = None
    
    def _get_base_image(self, blueprint: dict) -> str:
        """Determine Docker base image from blueprint."""
        stack = blueprint.get("tech_stack", "").lower()
        project_type = blueprint.get("projectType", "frontend")
        
        if "python" in stack or project_type == "backend":
            return "python:3.11-slim"
        elif "node" in stack or "react" in stack or "vue" in stack or "next" in stack:
            return "node:18-alpine"
        else:
            return "node:18-alpine"  # Default to Node for frontend
    
    def _get_run_command(self, blueprint: dict) -> List[str]:
        """Get the command to run the project."""
        stack = blueprint.get("tech_stack", "").lower()
        entry = blueprint.get("entrypoint", "")
        
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
    
    def execute_project(self, project_id: str, blueprint: dict) -> Dict:
        """
        Execute project in isolated Docker container.
        
        Returns:
        {
            "status": "success|error|simulated",
            "logs": str,
            "preview_url": Optional[str],
            "container_id": str
        }
        """
        project_path = BASE_PROJECTS_DIR / project_id
        
        if not project_path.exists():
            return {
                "status": "error",
                "logs": f"Project directory not found: {project_id}",
                "preview_url": None,
                "container_id": None
            }
        
        # If Docker not available, use simulated execution
        if not self.client:
            return self._simulate_execution(project_id, blueprint)
        
        try:
            image = self._get_base_image(blueprint)
            command = self._get_run_command(blueprint)
            port = self._get_port(blueprint)
            
            # Pull image if not present
            try:
                self.client.images.get(image)
            except docker.errors.ImageNotFound:
                print(f"Pulling image: {image}")
                self.client.images.pull(image)
            
            # Create and start container
            container = self.client.containers.run(
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
                "container_id": container.id
            }
            
        except Exception as e:
            return {
                "status": "error",
                "logs": f"Docker execution failed: {str(e)}",
                "preview_url": None,
                "container_id": None
            }
    
    def _simulate_execution(self, project_id: str, blueprint: dict) -> Dict:
        """Simulated execution when Docker is not available."""
        project_path = BASE_PROJECTS_DIR / project_id
        
        # Check what files exist
        files = list(project_path.glob("**/*"))
        file_list = [str(f.relative_to(project_path)) for f in files if f.is_file()]
        
        logs = f"""
=== SIMULATED EXECUTION ===
Project: {project_id}
Tech Stack: {blueprint.get('tech_stack', 'Unknown')}
Files: {len(file_list)}

File Structure:
{chr(10).join(f'  - {f}' for f in file_list[:20])}

Note: Docker is not available. Install Docker Desktop for real execution.
This is a simulation showing the project structure.

To run manually:
  cd {project_path}
  npm install && npm start   # For Node projects
  pip install -r requirements.txt && python main.py   # For Python projects
"""
        
        return {
            "status": "simulated",
            "logs": logs,
            "preview_url": None,
            "container_id": f"sim_{project_id}"
        }
    
    def get_container_logs(self, project_id: str, tail: int = 200) -> str:
        """Fetch logs from running container."""
        if not self.client:
            return "Docker not available. Logs unavailable in simulation mode."
        
        container_id = self.active_containers.get(project_id)
        if not container_id:
            return "No active container for this project."
        
        try:
            container = self.client.containers.get(container_id)
            return container.logs(tail=tail).decode('utf-8', errors='replace')
        except Exception as e:
            return f"Error fetching logs: {e}"
    
    def stop_container(self, project_id: str) -> bool:
        """Stop and remove container."""
        if not self.client:
            if project_id in self.active_containers:
                del self.active_containers[project_id]
            return True
        
        container_id = self.active_containers.get(project_id)
        if not container_id:
            return False
        
        try:
            container = self.client.containers.get(container_id)
            container.stop(timeout=5)
            container.remove()
            del self.active_containers[project_id]
            return True
        except Exception as e:
            print(f"Error stopping container: {e}")
            return False
    
    def cleanup_old_containers(self, max_age_hours: int = 2) -> int:
        """Remove containers older than specified hours."""
        if not self.client:
            return 0
        
        removed = 0
        try:
            containers = self.client.containers.list(all=True, filters={"name": "acea_"})
            for container in containers:
                created = container.attrs.get('Created', '')
                # Simple cleanup - remove stopped containers
                if container.status in ['exited', 'dead']:
                    container.remove()
                    removed += 1
        except Exception as e:
            print(f"Cleanup error: {e}")
        
        return removed


# Singleton instance
_docker_service = None

def get_docker_service() -> DockerService:
    global _docker_service
    if _docker_service is None:
        _docker_service = DockerService()
    return _docker_service
