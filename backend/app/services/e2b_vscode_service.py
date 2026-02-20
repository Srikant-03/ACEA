# E2B VS Code Service
# Creates VS Code environments with code-server in E2B cloud sandboxes

import os
import asyncio
import logging
from typing import Dict, Optional, Any, Callable
from pathlib import Path
from datetime import datetime

from e2b_code_interpreter import Sandbox

from app.core.filesystem import read_project_files

logger = logging.getLogger(__name__)

# E2B Configuration
E2B_API_KEY = os.getenv("E2B_API_KEY", "")
E2B_TIMEOUT_SECONDS = int(os.getenv("E2B_TIMEOUT", "600"))  # 10 min default


class E2BVSCodeService:
    """Manages VS Code environments via code-server in E2B cloud sandboxes."""
    
    def __init__(self):
        self.active_sandboxes: Dict[str, Sandbox] = {}  # project_id -> sandbox
        self.sandbox_info: Dict[str, Dict] = {}  # project_id -> {sandbox_id, vscode_url, preview_url, etc}
        
        if E2B_API_KEY:
            logger.info(f"E2BVSCodeService: API key configured, timeout={E2B_TIMEOUT_SECONDS}s")
        else:
            logger.warning("E2BVSCodeService: No E2B_API_KEY found in environment!")
    
    def _detect_project_config(self, blueprint: dict, files: Dict[str, str]) -> Dict[str, Any]:
        """Detect project type and return install/run commands with hot-reload."""
        tech_stack = blueprint.get("tech_stack", "")
        if isinstance(tech_stack, list):
            tech_stack = " ".join(tech_stack).lower()
        else:
            tech_stack = str(tech_stack).lower()
        
        # Check for specific files
        has_package_json = any("package.json" in f for f in files.keys())
        has_requirements_txt = any("requirements.txt" in f for f in files.keys())
        has_index_html = any("index.html" in f for f in files.keys())
        
        # Detect framework from files
        is_nextjs = any("next.config" in f for f in files.keys()) or "next" in tech_stack
        is_vite = any("vite.config" in f for f in files.keys()) or "vite" in tech_stack
        is_flask = has_requirements_txt and ("flask" in tech_stack or any("app.py" in f for f in files.keys()))
        is_fastapi = "fastapi" in tech_stack or any("main.py" in f and "fastapi" in files.get(f, "").lower() for f in files.keys())
        is_django = "django" in tech_stack or any("manage.py" in f for f in files.keys())
        is_vue = any("vue" in f.lower() for f in files.keys()) or "vue" in tech_stack
        
        # Default config
        config = {
            "install_cmd": "",
            "run_cmd": "",
            "port": 3000,
            "work_dir": "/home/user/project",
            "project_type": "unknown",
            "env_vars": {}
        }
        
        # Next.js with turbo
        if is_nextjs:
            config.update({
                "install_cmd": "npm install",
                "run_cmd": "npm run dev -- --turbo -p 3000",
                "port": 3000,
                "project_type": "nextjs",
                "env_vars": {}
            })
        # Vite (React/Vue with Vite)
        elif is_vite:
            config.update({
                "install_cmd": "npm install",
                "run_cmd": "npm run dev -- --host 0.0.0.0 --port 3000",
                "port": 3000,
                "project_type": "vite",
                "env_vars": {"CHOKIDAR_USEPOLLING": "true"}
            })
        # Vue CLI
        elif is_vue and has_package_json:
            config.update({
                "install_cmd": "npm install",
                "run_cmd": "npm run serve -- --port 3000",
                "port": 3000,
                "project_type": "vue",
                "env_vars": {"CHOKIDAR_USEPOLLING": "true"}
            })
        # React (CRA or generic React)
        elif has_package_json and ("react" in tech_stack or any(".tsx" in f or ".jsx" in f for f in files.keys())):
            config.update({
                "install_cmd": "npm install",
                "run_cmd": "npm start",
                "port": 3000,
                "project_type": "react",
                "env_vars": {"CHOKIDAR_USEPOLLING": "true", "PORT": "3000"}
            })
        # Generic Node.js
        elif has_package_json:
            config.update({
                "install_cmd": "npm install",
                "run_cmd": "npm start",
                "port": 3000,
                "project_type": "nodejs"
            })
        # FastAPI
        elif is_fastapi:
            config.update({
                "install_cmd": "pip install -r requirements.txt" if has_requirements_txt else "pip install fastapi uvicorn",
                "run_cmd": "uvicorn main:app --reload --host 0.0.0.0 --port 8000",
                "port": 8000,
                "project_type": "fastapi"
            })
        # Flask
        elif is_flask:
            config.update({
                "install_cmd": "pip install -r requirements.txt" if has_requirements_txt else "pip install flask",
                "run_cmd": "flask run --host=0.0.0.0 --port=5000",
                "port": 5000,
                "project_type": "flask",
                "env_vars": {"FLASK_ENV": "development", "FLASK_DEBUG": "1"}
            })
        # Django
        elif is_django:
            config.update({
                "install_cmd": "pip install -r requirements.txt" if has_requirements_txt else "pip install django",
                "run_cmd": "python manage.py runserver 0.0.0.0:8000",
                "port": 8000,
                "project_type": "django"
            })
        # Static HTML
        elif has_index_html:
            config.update({
                "install_cmd": "",
                "run_cmd": "python3 -m http.server 3000",
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
    
    def _create_instructions_file(self, preview_url: str, vscode_url: str, config: dict, files: dict) -> str:
        """Generate helpful INSTRUCTIONS.md content."""
        project_type = config.get("project_type", "unknown")
        port = config.get("port", 3000)
        run_cmd = config.get("run_cmd", "")
        
        file_list = "\n".join(f"- `{f}`" for f in sorted(files.keys())[:20])
        if len(files) > 20:
            file_list += f"\n- ... and {len(files) - 20} more files"
        
        content = f"""# 🚀 Welcome to Your ACEA Studio Project!

## Quick Links
- **Preview URL:** [{preview_url}]({preview_url})
- **VS Code URL:** [{vscode_url}]({vscode_url})

## 🏃 Your App is Running!
Your {project_type} app is already running on port {port}.

Hot-reload is **enabled** - just edit any file and save (Ctrl+S) to see changes instantly!

## 📁 Project Structure
{file_list}

## 🔧 Helpful Commands

Open the terminal with **Ctrl+`** (backtick) and run:

```bash
# Restart the development server
{run_cmd}

# Install a new package
{"npm install <package>" if "npm" in config.get("install_cmd", "") else "pip install <package>"}
```

## 💡 Tips
1. **Edit files** in the file explorer on the left
2. **Save** with Ctrl+S to trigger hot-reload
3. **Terminal** opens with Ctrl+` (backtick)
4. **Preview** your app at the URL above

## 🆘 Troubleshooting

**App not loading?**
- Check the terminal for errors
- Try running: `{run_cmd}`

**Port already in use?**
- Kill existing processes: `pkill -f node` or `pkill -f python`
- Then restart: `{run_cmd}`

---
*Generated by ACEA Studio - Autonomous Code Evolution Agent*
"""
        return content
    
    def _create_vscode_settings(self) -> str:
        """Create VS Code settings.json with dark theme and good defaults."""
        settings = """{
    "workbench.colorTheme": "Default Dark+",
    "editor.fontSize": 14,
    "editor.fontFamily": "'Fira Code', 'Droid Sans Mono', 'monospace'",
    "editor.tabSize": 2,
    "editor.wordWrap": "on",
    "editor.formatOnSave": true,
    "editor.minimap.enabled": false,
    "terminal.integrated.fontSize": 13,
    "terminal.integrated.shell.linux": "/bin/bash",
    "files.autoSave": "afterDelay",
    "files.autoSaveDelay": 1000,
    "workbench.startupEditor": "readme",
    "explorer.confirmDelete": false,
    "explorer.confirmDragAndDrop": false
}"""
        return settings
    
    async def create_vscode_environment(
        self, 
        project_id: str, 
        blueprint: dict,
        on_progress: Optional[Callable[[str], None]] = None
    ) -> Dict[str, Any]:
        """
        Create a VS Code environment with code-server in E2B sandbox.
        
        Returns:
            {
                "status": "ready" | "error",
                "vscode_url": "https://...",
                "preview_url": "https://...",
                "sandbox_id": "...",
                "message": str,
                "logs": str
            }
        """
        logs = []
        
        def log(msg: str):
            logs.append(msg)
            logger.info(f"[VSCode:{project_id}] {msg}")
            if on_progress:
                on_progress(msg)
        
        def error_response(message: str, user_message: str = None) -> Dict[str, Any]:
            return {
                "status": "error",
                "vscode_url": None,
                "preview_url": None,
                "sandbox_id": None,
                "message": user_message or message,
                "logs": "\n".join(logs)
            }
        
        # === API Key Check ===
        if not E2B_API_KEY:
            return error_response(
                "E2B_API_KEY not configured",
                "E2B API key missing. Add E2B_API_KEY to your .env file."
            )
        
        # === Close existing sandbox for this project ===
        if project_id in self.active_sandboxes:
            log("Closing existing sandbox...")
            await self.stop_sandbox(project_id)
        
        try:
            # === Read project files ===
            project_files = read_project_files(project_id)
            if not project_files:
                return error_response("No project files found", "Project is empty - nothing to run.")
            
            log(f"📁 Found {len(project_files)} files")
            
            # === Detect project configuration ===
            config = self._detect_project_config(blueprint, project_files)
            log(f"🔍 Detected: {config['project_type']}")
            
            # === Create sandbox ===
            log("🚀 Creating E2B sandbox...")
            try:
                sandbox = Sandbox.create(api_key=E2B_API_KEY)
                sandbox_id = sandbox.sandbox_id
                log(f"✅ Sandbox ready: {sandbox_id[:8]}...")
            except Exception as e:
                error_str = str(e).lower()
                if "unauthorized" in error_str or "invalid" in error_str:
                    return error_response(str(e), "Invalid E2B API key. Please check your .env file.")
                elif "rate limit" in error_str:
                    return error_response(str(e), "E2B rate limit reached. Please try again.")
                else:
                    return error_response(str(e), f"Failed to create sandbox: {str(e)}")
            
            # === Install code-server ===
            log("📦 Installing code-server (this takes ~30 seconds)...")
            try:
                # Install code-server
                install_result = sandbox.commands.run(
                    "curl -fsSL https://code-server.dev/install.sh | sh",
                    timeout=120
                )
                if install_result.exit_code != 0:
                    log(f"⚠️ code-server install warning: {install_result.stderr[:200] if install_result.stderr else 'unknown'}")
                else:
                    log("✅ code-server installed")
            except Exception as e:
                log(f"⚠️ code-server install error: {str(e)[:100]}")
                # Continue anyway - might already be installed
            
            # === Upload files ===
            log("📤 Uploading project files...")
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
            
            log(f"✅ Uploaded {uploaded} files")
            
            # === Create VS Code settings ===
            log("⚙️ Configuring VS Code theme...")
            try:
                sandbox.commands.run("mkdir -p /home/user/.local/share/code-server/User")
                sandbox.files.write(
                    "/home/user/.local/share/code-server/User/settings.json",
                    self._create_vscode_settings()
                )
            except Exception as e:
                log(f"⚠️ Settings config error: {str(e)[:50]}")
            
            # === Install dependencies ===
            if config["install_cmd"]:
                log(f"📦 Installing dependencies: {config['install_cmd']}")
                try:
                    result = sandbox.commands.run(
                        config["install_cmd"],
                        cwd=work_dir,
                        timeout=300
                    )
                    if result.exit_code != 0:
                        log(f"⚠️ Install warning: {result.stderr[:200] if result.stderr else 'check logs'}")
                    else:
                        log("✅ Dependencies installed")
                except Exception as e:
                    log(f"⚠️ Install error: {str(e)[:100]}")
            
            # === Start code-server ===
            log("🖥️ Starting VS Code server...")
            vscode_port = 8080
            try:
                # Build environment string for hot-reload
                env_str = " ".join(f"{k}={v}" for k, v in config.get("env_vars", {}).items())
                
                # Start code-server in background
                sandbox.commands.run(
                    f"code-server --bind-addr 0.0.0.0:{vscode_port} --auth none {work_dir} > /tmp/code-server.log 2>&1 &",
                    background=True
                )
                log(f"✅ VS Code starting on port {vscode_port}")
            except Exception as e:
                log(f"⚠️ code-server start error: {str(e)[:100]}")
            
            # === Start dev server ===
            port = config["port"]
            if config["run_cmd"]:
                log(f"🏃 Starting dev server: {config['run_cmd']}")
                try:
                    env_str = " ".join(f"{k}={v}" for k, v in config.get("env_vars", {}).items())
                    run_cmd = f"cd {work_dir} && {env_str} {config['run_cmd']} > /tmp/app.log 2>&1 &"
                    sandbox.commands.run(run_cmd, background=True)
                    log(f"✅ Dev server starting on port {port}")
                except Exception as e:
                    log(f"⚠️ Dev server start error: {str(e)[:100]}")
            
            # === Wait for ports ===
            log(f"⏳ Waiting for services to start...")
            await asyncio.sleep(5)  # Give servers time to start
            
            # Check code-server port
            for attempt in range(10):
                check_result = sandbox.commands.run(f"ss -tlnp | grep :{vscode_port} || echo ''")
                if check_result.stdout and str(vscode_port) in check_result.stdout:
                    log(f"✅ VS Code ready on port {vscode_port}")
                    break
                await asyncio.sleep(2)
            
            # Check app port
            for attempt in range(10):
                check_result = sandbox.commands.run(f"ss -tlnp | grep :{port} || echo ''")
                if check_result.stdout and str(port) in check_result.stdout:
                    log(f"✅ App ready on port {port}")
                    break
                await asyncio.sleep(2)
            
            # === Construct URLs ===
            vscode_host = sandbox.get_host(vscode_port)
            vscode_url = f"https://{vscode_host}"
            
            preview_host = sandbox.get_host(port)
            preview_url = f"https://{preview_host}"
            
            log(f"🌐 VS Code: {vscode_url}")
            log(f"🌐 Preview: {preview_url}")
            
            # === Create INSTRUCTIONS.md ===
            try:
                instructions = self._create_instructions_file(preview_url, vscode_url, config, project_files)
                sandbox.files.write(f"{work_dir}/INSTRUCTIONS.md", instructions)
                log("📝 Created INSTRUCTIONS.md")
            except Exception as e:
                log(f"⚠️ Could not create INSTRUCTIONS.md: {str(e)[:50]}")
            
            # === Store sandbox reference ===
            self.active_sandboxes[project_id] = sandbox
            self.sandbox_info[project_id] = {
                "sandbox_id": sandbox_id,
                "vscode_url": vscode_url,
                "preview_url": preview_url,
                "port": port,
                "vscode_port": vscode_port,
                "config": config,
                "created_at": datetime.now().isoformat(),
                "logs": "\n".join(logs)
            }
            
            return {
                "status": "ready",
                "vscode_url": vscode_url,
                "preview_url": preview_url,
                "sandbox_id": sandbox_id,
                "message": f"VS Code ready ({config['project_type']})",
                "logs": "\n".join(logs),
                "project_type": config["project_type"],
                "port": port
            }
            
        except Exception as e:
            error_msg = str(e)
            log(f"❌ Error: {error_msg}")
            logger.exception(f"E2B VS Code error for project {project_id}")
            
            return error_response(error_msg, f"Failed to create VS Code environment: {error_msg[:100]}")
    
    async def sync_file_to_sandbox(self, project_id: str, filepath: str, content: str) -> bool:
        """Sync a file update to the active E2B sandbox."""
        sandbox = self.active_sandboxes.get(project_id)
        if not sandbox:
            return False
        
        try:
            info = self.sandbox_info.get(project_id, {})
            work_dir = info.get("config", {}).get("work_dir", "/home/user/project")
            full_path = f"{work_dir}/{filepath}"
            
            # Ensure parent directory exists
            parent_dir = str(Path(full_path).parent)
            sandbox.commands.run(f"mkdir -p {parent_dir}")
            
            # Write file
            sandbox.files.write(full_path, content)
            logger.info(f"Synced {filepath} to sandbox {project_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to sync {filepath} to sandbox: {e}")
            return False
    
    def get_sandbox(self, project_id: str) -> Optional[Dict]:
        """Get info about an active sandbox."""
        return self.sandbox_info.get(project_id)
    
    async def get_sandbox_status(self, project_id: str) -> Dict[str, Any]:
        """Get current status of sandbox."""
        info = self.sandbox_info.get(project_id)
        sandbox = self.active_sandboxes.get(project_id)
        
        if not info or not sandbox:
            return {
                "status": "not_found",
                "message": "No active sandbox for this project"
            }
        
        try:
            # Check if sandbox is still alive
            result = sandbox.commands.run("echo 'alive'", timeout=5)
            if result.stdout and "alive" in result.stdout:
                return {
                    "status": "running",
                    "sandbox_id": info.get("sandbox_id"),
                    "vscode_url": info.get("vscode_url"),
                    "preview_url": info.get("preview_url"),
                    "created_at": info.get("created_at"),
                    "project_type": info.get("config", {}).get("project_type")
                }
        except Exception:
            pass
        
        # Sandbox is dead, clean up
        await self.stop_sandbox(project_id)
        return {
            "status": "stopped",
            "message": "Sandbox has expired or stopped"
        }
    
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

    async def get_logs(self, project_id: str) -> str:
        """Get logs for an active sandbox."""
        info = self.sandbox_info.get(project_id)
        if not info:
            return ""
        return info.get("logs", "")
    
    async def cleanup_all(self):
        """Cleanup all active sandboxes (for shutdown)."""
        for project_id in list(self.active_sandboxes.keys()):
            await self.stop_sandbox(project_id)


# Singleton instance
_e2b_vscode_service: Optional[E2BVSCodeService] = None


def get_e2b_vscode_service() -> E2BVSCodeService:
    """Get the singleton E2B VS Code service instance."""
    global _e2b_vscode_service
    if _e2b_vscode_service is None:
        _e2b_vscode_service = E2BVSCodeService()
    return _e2b_vscode_service
