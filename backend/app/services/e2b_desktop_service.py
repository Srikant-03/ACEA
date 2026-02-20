# ACEA Sentinel - E2B Desktop Service (Studio/Coder Mode)
# Creates full graphical desktop environments with VS Code and Chrome for human-centric development.
# This is an OPT-IN mode, never default. Uses E2B Desktop SDK with noVNC streaming.

import os
import asyncio
import logging
from typing import Dict, Optional, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

try:
    from e2b_desktop import Sandbox as DesktopSandbox
    E2B_DESKTOP_AVAILABLE = True
except ImportError:
    E2B_DESKTOP_AVAILABLE = False
    DesktopSandbox = None

logger = logging.getLogger(__name__)


# Configuration
E2B_API_KEY = os.getenv("E2B_API_KEY", "")
DESKTOP_DEFAULT_TIMEOUT_MINUTES = int(os.getenv("DESKTOP_SESSION_TIMEOUT", "60"))
DESKTOP_MAX_TIMEOUT_MINUTES = int(os.getenv("DESKTOP_MAX_TIMEOUT", "180"))  # 3 hours max
DESKTOP_IDLE_TIMEOUT_MINUTES = int(os.getenv("DESKTOP_IDLE_TIMEOUT", "15"))


class DesktopSessionStatus(Enum):
    """Status of a desktop session."""
    INITIALIZING = "initializing"
    STARTING_SERVICES = "starting_services"
    READY = "ready"
    IDLE_WARNING = "idle_warning"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"
    ERROR = "error"


@dataclass
class DesktopSession:
    """Represents a Studio/Coder Mode desktop session."""
    session_id: str
    project_id: str
    sandbox: Any  # DesktopSandbox instance
    created_at: datetime
    expires_at: datetime
    status: DesktopSessionStatus = DesktopSessionStatus.INITIALIZING
    last_activity: datetime = field(default_factory=datetime.now)
    novnc_url: Optional[str] = None
    vscode_status: str = "starting"
    chrome_status: str = "starting"
    error_message: Optional[str] = None
    
    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at
    
    def is_idle(self, idle_minutes: int = DESKTOP_IDLE_TIMEOUT_MINUTES) -> bool:
        return (datetime.now() - self.last_activity) > timedelta(minutes=idle_minutes)
    
    def time_remaining_minutes(self) -> int:
        remaining = self.expires_at - datetime.now()
        return max(0, int(remaining.total_seconds() / 60))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "project_id": self.project_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "time_remaining_minutes": self.time_remaining_minutes(),
            "novnc_url": self.novnc_url,
            "vscode_status": self.vscode_status,
            "chrome_status": self.chrome_status,
            "error_message": self.error_message,
        }


class E2BDesktopService:
    """
    E2B Desktop integration for Studio/Coder Mode.
    
    Creates full graphical Ubuntu desktop environments via noVNC streaming.
    Features:
    - Side-by-side VS Code and Chrome instances
    - Real localhost previews within the desktop
    - Time-boxing and idle-suspension controls
    - Explicit mode switching
    
    WARNING: This is significantly more expensive than standard sandboxes!
    Only activate when explicitly requested by users.
    """
    
    def __init__(self):
        self.sessions: Dict[str, DesktopSession] = {}  # session_id -> session
        self.project_sessions: Dict[str, str] = {}  # project_id -> session_id (1:1)
        self._monitor_task: Optional[asyncio.Task] = None
        
        if not E2B_DESKTOP_AVAILABLE:
            logger.warning(
                "E2B Desktop SDK not available. Install with: pip install e2b-desktop"
            )
        
        logger.info("E2BDesktopService initialized")
    
    def is_available(self) -> bool:
        """Check if E2B Desktop SDK is available."""
        return E2B_DESKTOP_AVAILABLE and bool(E2B_API_KEY)
    
    async def start_monitoring(self):
        """Start background task for monitoring idle sessions."""
        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(self._monitor_loop())
            logger.info("Started desktop session monitoring")
    
    async def _monitor_loop(self):
        """Background loop to monitor and suspend idle sessions."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                await self._check_idle_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in desktop monitor loop: {e}")
    
    async def _check_idle_sessions(self):
        """Check for idle sessions and handle suspension."""
        for session_id, session in list(self.sessions.items()):
            if session.status == DesktopSessionStatus.READY:
                if session.is_expired():
                    logger.info(f"Desktop session {session_id} expired, terminating")
                    await self.terminate_session(session_id)
                elif session.is_idle():
                    logger.info(f"Desktop session {session_id} idle, suspending")
                    await self.suspend_session(session_id)
    
    async def create_desktop_environment(
        self,
        project_id: str,
        files: Dict[str, str],
        on_progress: Optional[Callable[[str], None]] = None,
        timeout_minutes: int = DESKTOP_DEFAULT_TIMEOUT_MINUTES
    ) -> Dict[str, Any]:
        """
        Create a full desktop environment with VS Code and Chrome.
        
        Args:
            project_id: The project ID
            files: Dict of filepath -> content to sync
            on_progress: Optional callback for progress updates
            timeout_minutes: Session timeout (max: DESKTOP_MAX_TIMEOUT_MINUTES)
            
        Returns:
            Dict with session info including noVNC URL
        """
        def log(msg: str):
            logger.info(f"[Desktop:{project_id}] {msg}")
            if on_progress:
                on_progress(msg)
        
        def error_response(message: str):
            return {
                "status": "error",
                "message": message,
                "novnc_url": None,
                "session": None
            }
        
        # Check availability
        if not self.is_available():
            return error_response(
                "E2B Desktop SDK not available. Please install: pip install e2b-desktop"
            )
        
        # Check if project already has a session
        if project_id in self.project_sessions:
            existing_id = self.project_sessions[project_id]
            if existing_id in self.sessions:
                session = self.sessions[existing_id]
                if not session.is_expired():
                    log("Returning existing desktop session")
                    return {
                        "status": "ready",
                        "message": "Using existing desktop session",
                        "novnc_url": session.novnc_url,
                        "session": session.to_dict()
                    }
                else:
                    await self.terminate_session(existing_id)
        
        # Validate timeout
        timeout_minutes = min(timeout_minutes, DESKTOP_MAX_TIMEOUT_MINUTES)
        
        try:
            log("Creating E2B Desktop sandbox...")
            
            # Create desktop sandbox
            sandbox = DesktopSandbox(
                api_key=E2B_API_KEY,
                timeout=timeout_minutes * 60  # Seconds
            )
            
            # Create session record
            import uuid
            session_id = str(uuid.uuid4())[:8]
            now = datetime.now()
            
            session = DesktopSession(
                session_id=session_id,
                project_id=project_id,
                sandbox=sandbox,
                created_at=now,
                expires_at=now + timedelta(minutes=timeout_minutes),
                status=DesktopSessionStatus.STARTING_SERVICES
            )
            
            self.sessions[session_id] = session
            self.project_sessions[project_id] = session_id
            
            # Sync project files
            log("Syncing project files to desktop...")
            project_dir = "/home/user/project"
            await self._sync_files_to_desktop(sandbox, files, project_dir)
            
            # Start VS Code
            log("Starting VS Code (code-server)...")
            session.vscode_status = "starting"
            await self._start_vscode(sandbox, project_dir)
            session.vscode_status = "ready"
            
            # Start Chrome positioned next to VS Code
            log("Starting Chrome browser...")
            session.chrome_status = "starting"
            await self._start_chrome(sandbox)
            session.chrome_status = "ready"
            
            # Get noVNC URL for streaming
            log("Getting noVNC stream URL...")
            novnc_url = sandbox.get_vnc_url()
            session.novnc_url = novnc_url
            session.status = DesktopSessionStatus.READY
            
            log("Desktop environment ready!")
            
            return {
                "status": "ready",
                "message": "Desktop environment is ready",
                "novnc_url": novnc_url,
                "session": session.to_dict()
            }
            
        except Exception as e:
            logger.error(f"Error creating desktop environment: {e}")
            # Cleanup on failure
            if project_id in self.project_sessions:
                session_id = self.project_sessions.pop(project_id)
                self.sessions.pop(session_id, None)
            
            return error_response(f"Failed to create desktop: {str(e)}")
    
    async def _sync_files_to_desktop(
        self,
        sandbox: Any,
        files: Dict[str, str],
        project_dir: str
    ):
        """Sync project files to the desktop sandbox."""
        # Create project directory
        sandbox.filesystem.make_dir(project_dir)
        
        for filepath, content in files.items():
            full_path = f"{project_dir}/{filepath}"
            # Create parent directories
            parent = "/".join(full_path.split("/")[:-1])
            if parent:
                try:
                    sandbox.filesystem.make_dir(parent)
                except:
                    pass  # Directory might already exist
            
            # Write file
            sandbox.filesystem.write(full_path, content)
    
    async def _start_vscode(self, sandbox: Any, project_dir: str):
        """Start VS Code (code-server) in the desktop."""
        # Install code-server if needed
        sandbox.commands.run("which code-server || npm install -g code-server", timeout=120)
        
        # Start code-server in background, positioned on left half
        sandbox.commands.run(
            f"code-server --auth none --bind-addr 0.0.0.0:8080 {project_dir} &",
            timeout=30
        )
        
        # Wait for it to start
        await asyncio.sleep(3)
        
        # Open in browser on the left side
        sandbox.commands.run(
            'chromium-browser --window-position=0,0 --window-size=960,1080 http://localhost:8080 &',
            timeout=10
        )
    
    async def _start_chrome(self, sandbox: Any):
        """Start Chrome browser on the right side for preview."""
        # Open Chrome on the right half for localhost preview
        sandbox.commands.run(
            'chromium-browser --window-position=960,0 --window-size=960,1080 http://localhost:3000 &',
            timeout=10
        )
    
    async def get_session(self, session_id: str) -> Optional[DesktopSession]:
        """Get a session by ID."""
        return self.sessions.get(session_id)
    
    async def get_session_by_project(self, project_id: str) -> Optional[DesktopSession]:
        """Get the session for a project."""
        session_id = self.project_sessions.get(project_id)
        if session_id:
            return self.sessions.get(session_id)
        return None
    
    async def record_activity(self, session_id: str):
        """Record user activity to prevent idle suspension."""
        session = await self.get_session(session_id)
        if session:
            session.last_activity = datetime.now()
            if session.status == DesktopSessionStatus.IDLE_WARNING:
                session.status = DesktopSessionStatus.READY
    
    async def extend_session(
        self,
        session_id: str,
        additional_minutes: int = 30
    ) -> Dict[str, Any]:
        """Extend a session's timeout."""
        session = await self.get_session(session_id)
        if not session:
            return {"success": False, "error": "Session not found"}
        
        # Calculate new expiration
        new_expiry = session.expires_at + timedelta(minutes=additional_minutes)
        max_expiry = session.created_at + timedelta(minutes=DESKTOP_MAX_TIMEOUT_MINUTES)
        
        if new_expiry > max_expiry:
            new_expiry = max_expiry
            additional_minutes = int((new_expiry - session.expires_at).total_seconds() / 60)
        
        session.expires_at = new_expiry
        
        logger.info(f"Extended desktop session {session_id} by {additional_minutes} min")
        return {
            "success": True,
            "new_expires_at": new_expiry.isoformat(),
            "time_remaining_minutes": session.time_remaining_minutes()
        }
    
    async def suspend_session(self, session_id: str) -> bool:
        """Suspend an idle session (can be resumed)."""
        session = await self.get_session(session_id)
        if not session or session.status == DesktopSessionStatus.SUSPENDED:
            return False
        
        try:
            # Pause the sandbox
            if session.sandbox:
                session.sandbox.pause()
            session.status = DesktopSessionStatus.SUSPENDED
            logger.info(f"Suspended desktop session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Error suspending session {session_id}: {e}")
            return False
    
    async def resume_session(self, session_id: str) -> Dict[str, Any]:
        """Resume a suspended session."""
        session = await self.get_session(session_id)
        if not session:
            return {"success": False, "error": "Session not found"}
        
        if session.is_expired():
            await self.terminate_session(session_id)
            return {"success": False, "error": "Session expired"}
        
        if session.status != DesktopSessionStatus.SUSPENDED:
            return {"success": True, "message": "Session already active"}
        
        try:
            # Resume the sandbox
            if session.sandbox:
                session.sandbox.resume()
            session.status = DesktopSessionStatus.READY
            session.last_activity = datetime.now()
            logger.info(f"Resumed desktop session {session_id}")
            return {
                "success": True,
                "novnc_url": session.novnc_url,
                "session": session.to_dict()
            }
        except Exception as e:
            logger.error(f"Error resuming session {session_id}: {e}")
            return {"success": False, "error": str(e)}
    
    async def terminate_session(self, session_id: str) -> bool:
        """Terminate a desktop session."""
        session = self.sessions.pop(session_id, None)
        if not session:
            return False
        
        # Remove from project mapping
        if session.project_id in self.project_sessions:
            del self.project_sessions[session.project_id]
        
        # Kill the sandbox
        try:
            if session.sandbox:
                session.sandbox.kill()
        except Exception as e:
            logger.warning(f"Error killing sandbox for session {session_id}: {e}")
        
        logger.info(f"Terminated desktop session {session_id}")
        return True
    
    async def terminate_project_session(self, project_id: str) -> bool:
        """Terminate the desktop session for a project."""
        session_id = self.project_sessions.get(project_id)
        if session_id:
            return await self.terminate_session(session_id)
        return False
    
    async def cleanup_all(self):
        """Cleanup all desktop sessions."""
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        session_ids = list(self.sessions.keys())
        for session_id in session_ids:
            await self.terminate_session(session_id)
        
        logger.info(f"Cleaned up {len(session_ids)} desktop sessions")
    
    async def sync_files_from_desktop(
        self,
        session_id: str,
        target_dir: str = "/home/user/project"
    ) -> Dict[str, str]:
        """
        Sync files FROM the desktop back to the backend.
        
        Returns:
            Dict of filepath -> content
        """
        session = await self.get_session(session_id)
        if not session or not session.sandbox:
            return {}
        
        try:
            files = {}
            
            # Get file list
            result = session.sandbox.commands.run(
                f"find {target_dir} -type f -not -path '*/node_modules/*' -not -path '*/.git/*'",
                timeout=30
            )
            
            file_paths = result.stdout.strip().split('\n') if result.stdout else []
            
            for file_path in file_paths:
                if not file_path:
                    continue
                try:
                    content = session.sandbox.filesystem.read(file_path)
                    relative_path = file_path.replace(f"{target_dir}/", "")
                    files[relative_path] = content
                except Exception as e:
                    logger.warning(f"Could not read file {file_path}: {e}")
            
            logger.info(f"Synced {len(files)} files from desktop session {session_id}")
            return files
            
        except Exception as e:
            logger.error(f"Error syncing files from desktop: {e}")
            return {}
    
    async def run_command(
        self,
        session_id: str,
        command: str,
        cwd: str = "/home/user/project",
        timeout: int = 60
    ) -> Dict[str, Any]:
        """
        Run a command in the desktop sandbox.
        
        Returns:
            Dict with stdout, stderr, exit_code
        """
        session = await self.get_session(session_id)
        if not session or not session.sandbox:
            return {"error": "Session not found", "stdout": "", "stderr": "", "exit_code": -1}
        
        try:
            # Record activity
            session.last_activity = datetime.now()
            
            result = session.sandbox.commands.run(
                f"cd {cwd} && {command}",
                timeout=timeout
            )
            
            return {
                "stdout": result.stdout or "",
                "stderr": result.stderr or "",
                "exit_code": result.exit_code
            }
            
        except Exception as e:
            logger.error(f"Error running command in desktop: {e}")
            return {"error": str(e), "stdout": "", "stderr": "", "exit_code": -1}
    
    async def start_dev_server(
        self,
        session_id: str,
        project_dir: str = "/home/user/project",
        port: int = 3000
    ) -> Dict[str, Any]:
        """
        Start a development server in the sandbox.
        
        Returns:
            Dict with status and preview URL info
        """
        session = await self.get_session(session_id)
        if not session or not session.sandbox:
            return {"error": "Session not found"}
        
        try:
            # Detect project type and run appropriate dev server
            sandbox = session.sandbox
            
            # Check for package.json (Node.js project)
            has_package = sandbox.filesystem.exists(f"{project_dir}/package.json")
            
            if has_package:
                # Install dependencies if needed
                sandbox.commands.run(
                    f"cd {project_dir} && npm install",
                    timeout=120
                )
                
                # Start dev server in background
                sandbox.commands.run(
                    f"cd {project_dir} && PORT={port} npm run dev &",
                    timeout=10
                )
                
                # Open Chrome to the preview
                await asyncio.sleep(3)  # Wait for server to start
                sandbox.commands.run(
                    f'chromium-browser --window-position=960,0 --window-size=960,1080 http://localhost:{port} &',
                    timeout=10
                )
                
                return {
                    "status": "running",
                    "type": "npm",
                    "port": port,
                    "local_url": f"http://localhost:{port}"
                }
            
            # Check for Python project
            has_requirements = sandbox.filesystem.exists(f"{project_dir}/requirements.txt")
            if has_requirements:
                sandbox.commands.run(
                    f"cd {project_dir} && pip install -r requirements.txt",
                    timeout=120
                )
                
                # Try to run main.py or app.py
                main_file = "main.py" if sandbox.filesystem.exists(f"{project_dir}/main.py") else "app.py"
                sandbox.commands.run(
                    f"cd {project_dir} && python {main_file} &",
                    timeout=10
                )
                
                return {
                    "status": "running",
                    "type": "python",
                    "port": 8000,
                    "local_url": "http://localhost:8000"
                }
            
            # Check for index.html (static site)
            has_html = sandbox.filesystem.exists(f"{project_dir}/index.html")
            if has_html:
                sandbox.commands.run(
                    f"cd {project_dir} && python -m http.server {port} &",
                    timeout=10
                )
                
                return {
                    "status": "running",
                    "type": "static",
                    "port": port,
                    "local_url": f"http://localhost:{port}"
                }
            
            return {"status": "unknown", "message": "Could not detect project type"}
            
        except Exception as e:
            logger.error(f"Error starting dev server: {e}")
            return {"error": str(e)}
    
    async def get_file_tree(
        self,
        session_id: str,
        root_dir: str = "/home/user/project"
    ) -> Dict[str, Any]:
        """
        Get file tree structure from the desktop sandbox.
        
        Returns:
            Dict representing the file tree
        """
        session = await self.get_session(session_id)
        if not session or not session.sandbox:
            return {"error": "Session not found"}
        
        try:
            result = session.sandbox.commands.run(
                f"find {root_dir} -type f -o -type d | sort | head -500",
                timeout=30
            )
            
            paths = result.stdout.strip().split('\n') if result.stdout else []
            
            # Build tree structure
            tree = {"name": "project", "type": "directory", "children": []}
            
            for path in paths:
                if not path or path == root_dir:
                    continue
                
                relative = path.replace(f"{root_dir}/", "")
                if 'node_modules' in relative or '.git' in relative:
                    continue
                
                parts = relative.split('/')
                current = tree
                
                for i, part in enumerate(parts):
                    is_last = i == len(parts) - 1
                    
                    # Find or create child
                    found = None
                    for child in current.get("children", []):
                        if child["name"] == part:
                            found = child
                            break
                    
                    if not found:
                        found = {
                            "name": part,
                            "type": "file" if is_last else "directory",
                            "path": relative if is_last else "/".join(parts[:i+1]),
                        }
                        if not is_last:
                            found["children"] = []
                        current.setdefault("children", []).append(found)
                    
                    current = found
            
            return tree
            
        except Exception as e:
            logger.error(f"Error getting file tree: {e}")
            return {"error": str(e)}
    
    async def write_file(
        self,
        session_id: str,
        file_path: str,
        content: str
    ) -> bool:
        """Write a file to the desktop sandbox."""
        session = await self.get_session(session_id)
        if not session or not session.sandbox:
            return False
        
        try:
            full_path = f"/home/user/project/{file_path}"
            # Create parent directory
            parent = "/".join(full_path.split("/")[:-1])
            try:
                session.sandbox.filesystem.make_dir(parent)
            except:
                pass
            
            session.sandbox.filesystem.write(full_path, content)
            session.last_activity = datetime.now()
            return True
        except Exception as e:
            logger.error(f"Error writing file: {e}")
            return False
    
    async def read_file(
        self,
        session_id: str,
        file_path: str
    ) -> Optional[str]:
        """Read a file from the desktop sandbox."""
        session = await self.get_session(session_id)
        if not session or not session.sandbox:
            return None
        
        try:
            full_path = f"/home/user/project/{file_path}"
            content = session.sandbox.filesystem.read(full_path)
            session.last_activity = datetime.now()
            return content
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            return None


# Singleton instance
_e2b_desktop_service: Optional[E2BDesktopService] = None


def get_e2b_desktop_service() -> E2BDesktopService:
    """Get the singleton E2B Desktop service instance."""
    global _e2b_desktop_service
    if _e2b_desktop_service is None:
        _e2b_desktop_service = E2BDesktopService()
    return _e2b_desktop_service
