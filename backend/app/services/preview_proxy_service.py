# ACEA Sentinel - Preview Proxy Service
# Manages preview sessions with semantic URLs, proxying sandbox outputs securely.
# Users never connect directly to sandbox ports - all traffic goes through this proxy.

import os
import asyncio
import logging
import uuid
import httpx
from typing import Dict, Optional, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class PreviewSessionStatus(Enum):
    """Status of a preview session."""
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    ERROR = "error"


@dataclass
class PreviewSession:
    """Represents a managed preview session."""
    session_id: str
    project_id: str
    sandbox_url: str  # Internal E2B sandbox URL
    sandbox_port: int
    created_at: datetime
    expires_at: datetime
    status: PreviewSessionStatus = PreviewSessionStatus.PENDING
    last_accessed: datetime = field(default_factory=datetime.now)
    screenshot_path: Optional[str] = None
    console_errors: list = field(default_factory=list)
    network_failures: list = field(default_factory=list)
    
    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "project_id": self.project_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "has_screenshot": self.screenshot_path is not None,
            "console_error_count": len(self.console_errors),
            "network_failure_count": len(self.network_failures),
        }


class PreviewProxyService:
    """
    Managed Preview Service that proxies sandbox outputs securely.
    
    Key features:
    - Semantic preview URLs (not raw localhost)
    - CORS handling and security headers
    - Session management with expiration
    - Screenshot capture integration
    - Console error and network failure tracking
    """
    
    # Configuration
    SESSION_TIMEOUT_MINUTES = int(os.getenv("PREVIEW_SESSION_TIMEOUT", "30"))
    MAX_SESSIONS_PER_PROJECT = 5
    CLEANUP_INTERVAL_SECONDS = 60
    
    def __init__(self):
        self.sessions: Dict[str, PreviewSession] = {}  # session_id -> session
        self.project_sessions: Dict[str, list] = {}  # project_id -> [session_ids]
        self._cleanup_task: Optional[asyncio.Task] = None
        self._http_client: Optional[httpx.AsyncClient] = None
        logger.info("PreviewProxyService initialized")
    
    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True,
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
            )
        return self._http_client
    
    async def start_cleanup_task(self):
        """Start background task for cleaning up expired sessions."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Started session cleanup background task")
    
    async def _cleanup_loop(self):
        """Background loop to clean up expired sessions."""
        while True:
            try:
                await asyncio.sleep(self.CLEANUP_INTERVAL_SECONDS)
                await self._cleanup_expired_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
    
    async def _cleanup_expired_sessions(self):
        """Remove expired sessions."""
        expired = [
            session_id for session_id, session in self.sessions.items()
            if session.is_expired()
        ]
        for session_id in expired:
            await self.terminate_session(session_id)
            logger.info(f"Cleaned up expired session: {session_id}")
    
    async def create_preview_session(
        self,
        project_id: str,
        sandbox_url: str,
        sandbox_port: int = 3000,
        timeout_minutes: Optional[int] = None
    ) -> PreviewSession:
        """
        Create a new managed preview session.
        
        Args:
            project_id: The project ID
            sandbox_url: The internal E2B sandbox URL (e.g., https://abc123.e2b.dev)
            sandbox_port: Port the app is running on inside the sandbox
            timeout_minutes: Optional custom timeout
            
        Returns:
            PreviewSession object with semantic session_id
        """
        # Limit sessions per project
        if project_id in self.project_sessions:
            if len(self.project_sessions[project_id]) >= self.MAX_SESSIONS_PER_PROJECT:
                # Terminate oldest session
                oldest_id = self.project_sessions[project_id][0]
                await self.terminate_session(oldest_id)
        
        # Create new session
        session_id = str(uuid.uuid4())[:8]  # Short, readable ID
        timeout = timeout_minutes or self.SESSION_TIMEOUT_MINUTES
        now = datetime.now()
        
        session = PreviewSession(
            session_id=session_id,
            project_id=project_id,
            sandbox_url=sandbox_url,
            sandbox_port=sandbox_port,
            created_at=now,
            expires_at=now + timedelta(minutes=timeout),
            status=PreviewSessionStatus.ACTIVE,
            last_accessed=now
        )
        
        # Store session
        self.sessions[session_id] = session
        if project_id not in self.project_sessions:
            self.project_sessions[project_id] = []
        self.project_sessions[project_id].append(session_id)
        
        logger.info(f"Created preview session {session_id} for project {project_id}")
        return session
    
    async def get_session(self, session_id: str) -> Optional[PreviewSession]:
        """Get a session by ID."""
        session = self.sessions.get(session_id)
        if session and session.is_expired():
            session.status = PreviewSessionStatus.EXPIRED
        return session
    
    async def get_session_by_project(self, project_id: str) -> Optional[PreviewSession]:
        """Get the most recent active session for a project."""
        if project_id not in self.project_sessions:
            return None
        
        for session_id in reversed(self.project_sessions[project_id]):
            session = self.sessions.get(session_id)
            if session and not session.is_expired():
                return session
        return None
    
    async def proxy_request(
        self,
        session_id: str,
        path: str = "/",
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        body: Optional[bytes] = None
    ) -> Dict[str, Any]:
        """
        Proxy a request to the sandbox.
        
        Args:
            session_id: The preview session ID
            path: Request path (e.g., "/", "/api/data")
            method: HTTP method
            headers: Optional request headers
            body: Optional request body
            
        Returns:
            Dict with status, headers, and body
        """
        session = await self.get_session(session_id)
        if not session:
            return {
                "status": 404,
                "error": "Session not found",
                "body": None
            }
        
        if session.is_expired():
            return {
                "status": 410,
                "error": "Session expired",
                "body": None
            }
        
        # Update last accessed
        session.last_accessed = datetime.now()
        
        # Build target URL
        target_url = f"{session.sandbox_url}:{session.sandbox_port}{path}"
        
        try:
            client = await self._get_http_client()
            
            response = await client.request(
                method=method,
                url=target_url,
                headers=headers or {},
                content=body
            )
            
            return {
                "status": response.status_code,
                "headers": dict(response.headers),
                "body": response.content,
                "content_type": response.headers.get("content-type", "text/html")
            }
            
        except httpx.TimeoutException:
            logger.warning(f"Timeout proxying to {target_url}")
            return {
                "status": 504,
                "error": "Gateway timeout - sandbox not responding",
                "body": None
            }
        except httpx.ConnectError as e:
            logger.warning(f"Connection error proxying to {target_url}: {e}")
            return {
                "status": 502,
                "error": "Bad gateway - cannot connect to sandbox",
                "body": None
            }
        except Exception as e:
            logger.error(f"Error proxying request: {e}")
            return {
                "status": 500,
                "error": str(e),
                "body": None
            }
    
    async def record_console_error(self, session_id: str, error: Dict[str, Any]):
        """Record a console error captured from the preview."""
        session = await self.get_session(session_id)
        if session:
            session.console_errors.append({
                **error,
                "timestamp": datetime.now().isoformat()
            })
            logger.debug(f"Recorded console error for session {session_id}")
    
    async def record_network_failure(self, session_id: str, failure: Dict[str, Any]):
        """Record a network failure captured from the preview."""
        session = await self.get_session(session_id)
        if session:
            session.network_failures.append({
                **failure,
                "timestamp": datetime.now().isoformat()
            })
            logger.debug(f"Recorded network failure for session {session_id}")
    
    async def set_screenshot_path(self, session_id: str, path: str):
        """Set the path to a captured screenshot."""
        session = await self.get_session(session_id)
        if session:
            session.screenshot_path = path
    
    async def get_visual_artifacts(self, session_id: str) -> Dict[str, Any]:
        """Get all visual artifacts for a session (for Watcher agent)."""
        session = await self.get_session(session_id)
        if not session:
            return {"error": "Session not found"}
        
        return {
            "session_id": session_id,
            "project_id": session.project_id,
            "screenshot_path": session.screenshot_path,
            "console_errors": session.console_errors,
            "network_failures": session.network_failures,
            "status": session.status.value
        }
    
    async def extend_session(self, session_id: str, minutes: int = 30) -> bool:
        """Extend a session's expiration time."""
        session = await self.get_session(session_id)
        if not session:
            return False
        
        session.expires_at = datetime.now() + timedelta(minutes=minutes)
        logger.info(f"Extended session {session_id} by {minutes} minutes")
        return True
    
    async def terminate_session(self, session_id: str) -> bool:
        """Terminate a preview session."""
        session = self.sessions.pop(session_id, None)
        if not session:
            return False
        
        # Remove from project list
        if session.project_id in self.project_sessions:
            try:
                self.project_sessions[session.project_id].remove(session_id)
                if not self.project_sessions[session.project_id]:
                    del self.project_sessions[session.project_id]
            except ValueError:
                pass
        
        logger.info(f"Terminated preview session {session_id}")
        return True
    
    async def terminate_project_sessions(self, project_id: str) -> int:
        """Terminate all sessions for a project."""
        if project_id not in self.project_sessions:
            return 0
        
        session_ids = list(self.project_sessions.get(project_id, []))
        count = 0
        for session_id in session_ids:
            if await self.terminate_session(session_id):
                count += 1
        
        return count
    
    def get_semantic_url(self, session_id: str, base_url: str = "") -> str:
        """
        Generate a semantic preview URL for the session.
        
        Instead of: https://abc123.e2b.dev:3000
        Returns: {base_url}/preview/{session_id}
        """
        return f"{base_url}/api/preview/{session_id}"
    
    async def cleanup_all(self):
        """Cleanup all sessions and resources."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        if self._http_client:
            await self._http_client.aclose()
        
        session_count = len(self.sessions)
        self.sessions.clear()
        self.project_sessions.clear()
        logger.info(f"Cleaned up {session_count} preview sessions")


# Singleton instance
_preview_proxy_service: Optional[PreviewProxyService] = None


def get_preview_proxy_service() -> PreviewProxyService:
    """Get the singleton Preview Proxy service instance."""
    global _preview_proxy_service
    if _preview_proxy_service is None:
        _preview_proxy_service = PreviewProxyService()
    return _preview_proxy_service
