# ACEA Sentinel - Project Runner Utility
# Runs generated projects and captures output/errors

import asyncio
import subprocess
import os
import threading
from pathlib import Path
from typing import Optional, Dict, Any

class ProjectRunner:
    """
    Utility to install dependencies and run generated projects.
    Manages subprocess lifecycle for dev servers.
    """
    
    # Static dict to hold runners by project_id to persist state across API calls
    # This is a simple in-memory storage for the session
    _instances = {}

    def __init__(self, project_path: str, project_id: str = None):
        self.project_path = Path(project_path)
        self.frontend_path = self.project_path / "frontend"
        self.frontend_process: Optional[subprocess.Popen] = None
        self.frontend_port = 3001
        self.logs = []
        self.project_id = project_id
        
        # Store instance if ID provided
        if project_id:
            ProjectRunner._instances[project_id] = self

    @classmethod
    def get_instance(cls, project_id: str):
        return cls._instances.get(project_id)

    def _log(self, message: str):
        print(f"[Run:{self.project_id}] {message}")
        self.logs.append(message)
        # Keep log size manageable
        if len(self.logs) > 1000:
            self.logs.pop(0)

    def _capture_output(self, process, stream_name):
        stream = getattr(process, stream_name)
        for line in iter(stream.readline, b''):
            decoded = line.decode('utf-8', errors='replace').rstrip()
            if decoded:
                self._log(decoded)
        stream.close()

    async def setup_frontend(self) -> Dict[str, Any]:
        """Install frontend dependencies and create package.json if missing."""
        if not self.frontend_path.exists():
            return {"success": False, "error": "Frontend directory not found"}
        
        # Check if package.json exists, if not create a basic one
        package_json = self.frontend_path / "package.json"
        if not package_json.exists():
            self._log("Creating package.json...")
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
                    "typescript": "^5.0.0",
                    "@types/react": "^18.0.0",
                    "@types/node": "^20.0.0"
                }
            }
            import json
            with open(package_json, 'w') as f:
                json.dump(basic_package, f, indent=2)
        
        
        self._log("Installing dependencies (npm install)... this may take a minute.")
        try:
            # Use shell=True for Windows compatibility with npm
            process = subprocess.Popen(
                ["npm", "install"],
                cwd=str(self.frontend_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True
            )
            # We can't easily stream logs from this blocking call without complex async piping
            # relying on wait()
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                err_msg = stderr.decode()
                stdout_msg = stdout.decode() # also capture stdout as npm often puts errors there
                full_log = f"{stdout_msg}\n{err_msg}"
                self._log(f"npm install failed: {err_msg[:200]}") # Log short version
                return {"success": False, "error": full_log[:3000]} # Return LONG version for Tester
            
            self._log("Dependencies installed successfully.")
            return {"success": True, "message": "Dependencies installed"}
        except Exception as e:
            self._log(f"Setup Exception: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def start_frontend(self) -> Dict[str, Any]:
        """Start the Next.js dev server."""
        if self.frontend_process and self.frontend_process.poll() is None:
            return {"success": True, "message": "Already running", "port": self.frontend_port, "url": f"http://localhost:{self.frontend_port}"}
        
        try:
            self._log(f"Starting server on port {self.frontend_port}...")
            # Kill anything running on this port (Windows specific)
            subprocess.run(f"netstat -ano | findstr :{self.frontend_port} && taskkill /F /PID $(netstat -ano | findstr :{self.frontend_port} | awk '{{print $5}}')", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)

            self.frontend_process = subprocess.Popen(
                ["npm", "run", "dev"],
                cwd=str(self.frontend_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True
            )
            
            # Start background threads to capture logs
            t_out = threading.Thread(target=self._capture_output, args=(self.frontend_process, 'stdout'))
            t_out.daemon = True
            t_out.start()
            
            t_err = threading.Thread(target=self._capture_output, args=(self.frontend_process, 'stderr'))
            t_err.daemon = True
            t_err.start()
            
            # Wait for server to be responsive (Health Check)
            import urllib.request
            import time
            
            self._log("Waiting for server to become responsive...")
            server_ready = False
            for i in range(30):  # Retry for 30 seconds
                try:
                    with urllib.request.urlopen(f"http://localhost:{self.frontend_port}", timeout=1) as response:
                        if response.status < 500:
                            server_ready = True
                            break
                except Exception:
                    await asyncio.sleep(1)
            
            if not server_ready:
                self._log("Server start timed out (30s).")
                # Don't kill it immediately, let the user check logs, but report failure to watcher?
                # Actually, if it's not ready, watcher will fail anyway.
                # proceed to return, watcher verify_page will catch the connection error.
            else:
                self._log("Server is responsive!")
            
            if self.frontend_process.poll() is not None:
                self._log("Server stopped immediately.")
                return {"success": False, "error": "Server stopped immediately check logs"}
            
            url = f"http://localhost:{self.frontend_port}"
            self._log(f"Server available at {url}")
            
            return {
                "success": True, 
                "message": "Frontend server started",
                "port": self.frontend_port,
                "url": url
            }
        except Exception as e:
            self._log(f"Start Exception: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def stop_frontend(self):
        """Stop the frontend dev server."""
        if self.frontend_process:
            self._log("Stopping server...")
            # Simple terminate often doesn't kill child processes on Windows with shell=True
            # But we'll try
            subprocess.run(f"taskkill /F /T /PID {self.frontend_process.pid}", shell=True)
            self.frontend_process = None
            self._log("Server stopped.")
            
    def get_captured_logs(self) -> str:
        return "\n".join(self.logs)

    def cleanup(self):
        self.stop_frontend()
