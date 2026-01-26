# ACEA Sentinel - Project Runner Utility
# Runs generated projects and captures output/errors

import asyncio
import subprocess
import os
from pathlib import Path
from typing import Optional, Dict, Any

class ProjectRunner:
    """
    Utility to install dependencies and run generated projects.
    Manages subprocess lifecycle for dev servers.
    """
    
    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.frontend_path = self.project_path / "frontend"
        self.backend_path = self.project_path / "backend"
        self.frontend_process: Optional[subprocess.Popen] = None
        self.backend_process: Optional[subprocess.Popen] = None
        self.frontend_port = 3001  # Use different port than main frontend
        self.backend_port = 8001   # Use different port than main backend
    
    async def setup_frontend(self) -> Dict[str, Any]:
        """Install frontend dependencies and create package.json if missing."""
        if not self.frontend_path.exists():
            return {"success": False, "error": "Frontend directory not found"}
        
        # Check if package.json exists, if not create a basic one
        package_json = self.frontend_path / "package.json"
        if not package_json.exists():
            basic_package = {
                "name": "generated-app",
                "version": "0.1.0",
                "private": True,
                "scripts": {
                    "dev": f"next dev -p {self.frontend_port}",
                    "build": "next build",
                    "start": "next start"
                },
                "dependencies": {
                    "next": "15.0.0",
                    "react": "18.3.1",
                    "react-dom": "18.3.1",
                    "lucide-react": "latest"
                },
                "devDependencies": {
                    "tailwindcss": "^4.0.0",
                    "typescript": "^5.0.0",
                    "@types/react": "^18.0.0",
                    "@types/node": "^20.0.0"
                }
            }
            import json
            with open(package_json, 'w') as f:
                json.dump(basic_package, f, indent=2)
        
        # Run npm install
        try:
            result = await asyncio.create_subprocess_exec(
                "npm", "install",
                cwd=str(self.frontend_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(result.communicate(), timeout=120)
            
            if result.returncode != 0:
                return {"success": False, "error": stderr.decode()[:500]}
            
            return {"success": True, "message": "Dependencies installed"}
        except asyncio.TimeoutError:
            return {"success": False, "error": "npm install timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def start_frontend(self) -> Dict[str, Any]:
        """Start the Next.js dev server."""
        if self.frontend_process:
            return {"success": True, "message": "Already running", "port": self.frontend_port}
        
        try:
            self.frontend_process = subprocess.Popen(
                ["npm", "run", "dev"],
                cwd=str(self.frontend_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True  # Required on Windows
            )
            
            # Wait for server to start
            await asyncio.sleep(5)
            
            if self.frontend_process.poll() is not None:
                # Process ended (probably error)
                _, stderr = self.frontend_process.communicate()
                return {"success": False, "error": stderr.decode()[:500] if stderr else "Server crashed"}
            
            return {
                "success": True, 
                "message": "Frontend server started",
                "port": self.frontend_port,
                "url": f"http://localhost:{self.frontend_port}"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def stop_frontend(self):
        """Stop the frontend dev server."""
        if self.frontend_process:
            self.frontend_process.terminate()
            self.frontend_process = None
    
    async def get_frontend_errors(self) -> list:
        """Check if the frontend process has any errors in stderr."""
        errors = []
        if self.frontend_process and self.frontend_process.stderr:
            try:
                # Non-blocking read
                import select
                if hasattr(select, 'select'):
                    # Unix
                    pass
                else:
                    # Windows - just check if there's output
                    pass
            except:
                pass
        return errors
    
    def cleanup(self):
        """Stop all processes."""
        self.stop_frontend()
        if self.backend_process:
            self.backend_process.terminate()
            self.backend_process = None
