# E2B Cloud Sandbox Service
# Manages cloud-based code execution via E2B sandboxes

import os
import asyncio
import logging
from typing import Dict, Optional, Any, Callable
from pathlib import Path

from e2b_code_interpreter import Sandbox, wait_for_port

from app.core.filesystem import read_project_files

logger = logging.getLogger(__name__)

# E2B Configuration
E2B_API_KEY = os.getenv("E2B_API_KEY", "")
E2B_TIMEOUT_SECONDS = int(os.getenv("E2B_TIMEOUT", "1200"))  # 20 min default, configurable


class E2BService:
    """Manages code execution via E2B cloud sandboxes."""
    
    def __init__(self):
        self.active_sandboxes: Dict[str, Sandbox] = {}  # project_id -> sandbox
        self.sandbox_info: Dict[str, Dict] = {}  # project_id -> {sandbox_id, preview_url, logs}
        
        if E2B_API_KEY:
            logger.info(f"E2BService: API key configured, timeout={E2B_TIMEOUT_SECONDS}s")
        else:
            logger.warning("E2BService: No E2B_API_KEY found in environment!")
    
    def _detect_project_config(self, blueprint: dict, files: Dict[str, str]) -> Dict[str, Any]:
        """Detect project type and return install/run commands."""
        tech_stack = blueprint.get("tech_stack", "").lower()
        
        # Check for specific files
        has_package_json = any("package.json" in f for f in files.keys())
        has_requirements_txt = any("requirements.txt" in f for f in files.keys())
        has_go_mod = any("go.mod" in f for f in files.keys())
        has_cargo_toml = any("Cargo.toml" in f for f in files.keys())
        has_pom_xml = any("pom.xml" in f for f in files.keys())
        has_index_html = any("index.html" in f for f in files.keys())
        
        # Detect framework from files
        is_nextjs = any("next.config" in f for f in files.keys()) or "next" in tech_stack
        is_flask = has_requirements_txt and ("flask" in tech_stack or any("app.py" in f for f in files.keys()))
        is_django = "django" in tech_stack or any("manage.py" in f for f in files.keys())
        
        # Default config
        config = {
            "install_cmd": "",
            "run_cmd": "",
            "port": 3000,
            "work_dir": "/home/user/project",
            "project_type": "unknown"
        }
        
        # Next.js
        if is_nextjs:
            config.update({
                "install_cmd": "npm install",
                "run_cmd": "npm run dev -- -p 3000",
                "port": 3000,
                "project_type": "nextjs"
            })
        # React/Node.js
        elif has_package_json and ("react" in tech_stack or any(".tsx" in f or ".jsx" in f for f in files.keys())):
            config.update({
                "install_cmd": "npm install",
                "run_cmd": "npm start",
                "port": 3000,
                "project_type": "react"
            })
        elif has_package_json:
            config.update({
                "install_cmd": "npm install",
                "run_cmd": "npm start",
                "port": 3000,
                "project_type": "nodejs"
            })
        # Flask
        elif is_flask:
            config.update({
                "install_cmd": "pip install -r requirements.txt" if has_requirements_txt else "pip install flask",
                "run_cmd": "python app.py",
                "port": 5000,
                "project_type": "flask"
            })
        # Django
        elif is_django:
            config.update({
                "install_cmd": "pip install -r requirements.txt" if has_requirements_txt else "pip install django",
                "run_cmd": "python manage.py runserver 0.0.0.0:8000",
                "port": 8000,
                "project_type": "django"
            })
        # Go
        elif has_go_mod or "go" in tech_stack:
            config.update({
                "install_cmd": "go mod tidy",
                "run_cmd": "go run main.go",
                "port": 8080,
                "project_type": "go"
            })
        # Rust
        elif has_cargo_toml or "rust" in tech_stack:
            config.update({
                "install_cmd": "cargo build",
                "run_cmd": "cargo run",
                "port": 8080,
                "project_type": "rust"
            })
        # Java/Spring
        elif has_pom_xml or "java" in tech_stack or "spring" in tech_stack:
            config.update({
                "install_cmd": "",
                "run_cmd": "mvn spring-boot:run",
                "port": 8080,
                "project_type": "java"
            })
        # Static HTML
        elif has_index_html:
            config.update({
                "install_cmd": "",  # No install needed
                "run_cmd": "python3 -m http.server 3000",  # Python http server always available
                "port": 3000,
                "project_type": "static"
            })
        # Python script
        elif any(f.endswith(".py") for f in files.keys()):
            entrypoint = blueprint.get("entrypoint", "main.py")
            config.update({
                "install_cmd": "pip install -r requirements.txt" if has_requirements_txt else "",
                "run_cmd": f"python {entrypoint}",
                "port": 8000,
                "project_type": "python"
            })
        
        return config
    
    async def create_sandbox(
        self, 
        project_id: str, 
        blueprint: dict,
        on_progress: Optional[Callable[[str], None]] = None
    ) -> Dict[str, Any]:
        """
        Create an E2B sandbox, upload project files, install dependencies, and start the app.
        Automatically closes any existing sandbox for this project first.
        
        Args:
            project_id: Project identifier
            blueprint: Project blueprint with tech_stack info
            on_progress: Optional callback for progress updates
        
        Returns:
            {
                "status": "running" | "error",
                "logs": str,
                "preview_url": str | None,
                "sandbox_id": str | None,
                "message": str,
                "stage": str  # Current stage for frontend display
            }
        """
        logs = []
        
        def log(msg: str, stage: str = ""):
            logs.append(msg)
            logger.info(f"[E2B:{project_id}] {msg}")
            if on_progress:
                on_progress(msg)
        
        def error_response(message: str, user_message: str = None) -> Dict[str, Any]:
            return {
                "status": "error",
                "logs": "\n".join(logs),
                "preview_url": None,
                "sandbox_id": None,
                "message": user_message or message,
                "stage": "error"
            }
        
        # === API Key Check ===
        if not E2B_API_KEY:
            return error_response(
                "E2B_API_KEY not configured",
                "E2B API key missing. Add E2B_API_KEY to your .env file."
            )
        
        # === Close existing sandbox for this project (prevent duplicate charges) ===
        if project_id in self.active_sandboxes:
            log("Closing existing sandbox...")
            await self.stop_sandbox(project_id)
        
        try:
            # === Read project files ===
            project_files = read_project_files(project_id)
            if not project_files:
                return error_response("No project files found", "Project is empty - nothing to run.")
            
            log(f"Found {len(project_files)} files")
            
            # === Detect project configuration ===
            config = self._detect_project_config(blueprint, project_files)
            log(f"Project type: {config['project_type']}")
            
            # === Create sandbox ===
            log("🚀 Creating sandbox (this takes 2-3 seconds)...")
            try:
                sandbox = Sandbox.create(api_key=E2B_API_KEY)
                sandbox_id = sandbox.sandbox_id
                log(f"✅ Sandbox ready: {sandbox_id[:8]}...")
            except Exception as e:
                error_str = str(e).lower()
                if "unauthorized" in error_str or "invalid" in error_str:
                    return error_response(str(e), "Invalid E2B API key. Please check your .env file.")
                elif "rate limit" in error_str:
                    return error_response(str(e), "E2B rate limit reached. Please try again in a moment.")
                elif "quota" in error_str or "credit" in error_str:
                    return error_response(str(e), "E2B credits exhausted. Please add credits to your account.")
                else:
                    return error_response(str(e), f"Failed to create sandbox: {str(e)}")
            
            # === Upload files ===
            log("Uploading project files...")
            work_dir = config["work_dir"]
            uploaded = 0
            
            for file_path, content in project_files.items():
                if file_path == "blueprint.json":
                    continue
                
                full_path = f"{work_dir}/{file_path}"
                
                try:
                    parent_dir = str(Path(full_path).parent)
                    sandbox.commands.run(f"mkdir -p {parent_dir}")
                    sandbox.files.write(full_path, content)
                    uploaded += 1
                except Exception as e:
                    log(f"Failed to upload {file_path}: {str(e)[:50]}")
            
            log(f"Uploaded {uploaded} files")
            
            # === Install dependencies ===
            if config["install_cmd"]:
                log(f"Installing dependencies...")
                try:
                    install_output = []
                    result = sandbox.commands.run(
                        config["install_cmd"],
                        cwd=work_dir,
                        timeout=300,
                        on_stdout=lambda data: install_output.append(f"[stdout] {data}"),
                        on_stderr=lambda data: install_output.append(f"[stderr] {data}")
                    )
                    if result.exit_code != 0:
                        stderr = result.stderr[:500] if result.stderr else "Unknown error"
                        log(f"Install failed (exit {result.exit_code}): {stderr}")
                        # Log captured output for debugging
                        for line in install_output[-10:]:  # Last 10 lines
                            log(f"  {line}")
                    else:
                        log("Dependencies installed")
                except Exception as e:
                    log(f"Install error: {str(e)[:100]}")
            
            # === Start application ===
            log(f"Starting application: {config['run_cmd']}")
            port = config["port"]
            
            try:
                # Use background command with proper logging setup
                run_cmd = f"cd {work_dir} && {config['run_cmd']} 2>&1 | tee /tmp/app.log"
                cmd_handle = sandbox.commands.run(run_cmd, background=True)
                log("Application process started in background")
                
                # Store the command handle for log streaming later
                self.sandbox_info[project_id] = {"cmd_handle": cmd_handle}
                
            except Exception as e:
                log(f"Start error: {str(e)[:100]}")
            
            # === Wait for port using SDK helper ===
            log(f"Waiting for port {port} to be ready...")
            try:
                # Use SDK's wait_for_port helper (creates a condition)
                port_condition = wait_for_port(port)
                
                # Poll for port readiness with timeout
                port_ready = False
                for attempt in range(15):  # 15 attempts * 2s = 30s max
                    await asyncio.sleep(2)
                    
                    # Check app logs for errors or startup messages
                    log_result = sandbox.commands.run("cat /tmp/app.log 2>/dev/null | tail -15")
                    if log_result.stdout:
                        recent_logs = log_result.stdout.strip()
                        # Log important lines
                        for line in recent_logs.split('\n')[-5:]:
                            if line.strip():
                                log(f"📋 {line[:100]}")
                    
                    # Check if port is listening
                    check_result = sandbox.commands.run(f"ss -tlnp | grep :{port} || lsof -i :{port} 2>/dev/null || echo ''")
                    if check_result.stdout and str(port) in check_result.stdout:
                        port_ready = True
                        log(f"✅ Port {port} is now listening!")
                        break
                    
                    # Check for crash indicators
                    if log_result.stdout:
                        lower_logs = log_result.stdout.lower()
                        if "error" in lower_logs or "exception" in lower_logs or "exited" in lower_logs:
                            log(f"⚠️ Possible error detected in logs (attempt {attempt+1}/15)")
                
                if not port_ready:
                    log(f"⚠️ Port {port} not ready after 30s, proceeding anyway")
                    # Final log dump for debugging
                    log_result = sandbox.commands.run("cat /tmp/app.log 2>/dev/null | tail -30")
                    if log_result.stdout:
                        log(f"Full logs:\\n{log_result.stdout[:800]}")
                        
            except Exception as e:
                log(f"Port wait error: {str(e)[:100]}")
            
            # === Construct preview URL using E2B SDK method ===
            port = config["port"]
            host = sandbox.get_host(port)
            preview_url = f"https://{host}"
            log(f"🌐 Preview: {preview_url}")
            
            # === Store sandbox reference ===
            self.active_sandboxes[project_id] = sandbox
            self.sandbox_info[project_id] = {
                "sandbox_id": sandbox_id,
                "preview_url": preview_url,
                "port": port,
                "config": config,
                "logs": "\n".join(logs)
            }
            
            return {
                "status": "running",
                "logs": "\n".join(logs),
                "preview_url": preview_url,
                "sandbox_id": sandbox_id,
                "message": f"Running on E2B ({config['project_type']})",
                "stage": "running"
            }
            
        except Exception as e:
            error_msg = str(e)
            log(f"Error: {error_msg}")
            logger.exception(f"E2B error for project {project_id}")
            
            # User-friendly error messages
            if "connection" in error_msg.lower() or "timeout" in error_msg.lower():
                user_msg = "Could not connect to E2B. Please check your internet connection."
            elif "api" in error_msg.lower():
                user_msg = "E2B API error. The service may be temporarily unavailable."
            else:
                user_msg = f"Sandbox error: {error_msg[:100]}"
            
            return error_response(error_msg, user_msg)
    
    def get_sandbox(self, project_id: str) -> Optional[Dict]:
        """Get info about an active sandbox."""
        return self.sandbox_info.get(project_id)
    
    async def get_logs(self, project_id: str) -> str:
        """Get logs from running sandbox."""
        sandbox = self.active_sandboxes.get(project_id)
        info = self.sandbox_info.get(project_id, {})
        
        if not sandbox:
            return info.get("logs", "No sandbox running")
        
        try:
            result = sandbox.commands.run("cat /tmp/app.log 2>/dev/null || echo 'No logs yet'")
            app_logs = result.stdout or ""
            creation_logs = info.get("logs", "")
            return f"{creation_logs}\n\n--- Application Output ---\n{app_logs}"
        except Exception as e:
            return f"Failed to fetch logs: {str(e)}"
    
    async def stop_sandbox(self, project_id: str) -> Dict[str, str]:
        """Stop and cleanup a sandbox."""
        sandbox = self.active_sandboxes.get(project_id)
        
        if not sandbox:
            return {"status": "not_found", "message": "No active sandbox"}
        
        try:
            sandbox.kill()
            logger.info(f"Killed sandbox for project {project_id}")
        except Exception as e:
            logger.warning(f"Error killing sandbox: {e}")
        
        self.active_sandboxes.pop(project_id, None)
        self.sandbox_info.pop(project_id, None)
        
        return {"status": "stopped", "message": "Sandbox terminated"}
    
    async def cleanup_all(self):
        """Cleanup all active sandboxes (for shutdown)."""
        for project_id in list(self.active_sandboxes.keys()):
            await self.stop_sandbox(project_id)


# Singleton instance
_e2b_service: Optional[E2BService] = None


def get_e2b_service() -> E2BService:
    """Get the singleton E2B service instance."""
    global _e2b_service
    if _e2b_service is None:
        _e2b_service = E2BService()
    return _e2b_service
