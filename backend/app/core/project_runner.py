# ACEA Sentinel - Project Runner Utility
# Runs generated projects and captures output/errors
# Cross-platform: works on both Windows and Linux (Railway)

import asyncio
import subprocess
import os
import sys
import signal
import threading
from pathlib import Path
from typing import Optional, Dict, Any
from app.core.sandbox_guard import SandboxGuard
import logging

logger = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"


def _kill_process_tree(pid: int):
    """Kill a process and all its children — cross-platform."""
    try:
        if IS_WINDOWS:
            # Windows: taskkill with /T kills child processes
            subprocess.run(
                f"taskkill /F /T /PID {pid}",
                shell=True,
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL
            )
        else:
            # Linux/Mac: kill the process group
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
    except Exception:
        pass


def _kill_port_occupants(port: int):
    """Kill whatever is using a given port — cross-platform."""
    try:
        if IS_WINDOWS:
            cmd = f"netstat -ano | findstr :{port}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if result.stdout:
                for line in result.stdout.strip().splitlines():
                    parts = line.split()
                    if parts:
                        pid = parts[-1]
                        if pid.isdigit() and int(pid) > 0:
                            subprocess.run(
                                f"taskkill /F /PID {pid}",
                                shell=True,
                                stderr=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL
                            )
        else:
            # Linux: use fuser or lsof
            result = subprocess.run(
                f"lsof -ti :{port}",
                shell=True,
                capture_output=True,
                text=True
            )
            if result.stdout.strip():
                for pid in result.stdout.strip().splitlines():
                    if pid.strip().isdigit():
                        try:
                            os.kill(int(pid.strip()), signal.SIGTERM)
                        except ProcessLookupError:
                            pass
    except Exception:
        pass


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
        self.logs = []
        self.frontend_path = self._detect_frontend_path()
        self.frontend_process: Optional[subprocess.Popen] = None
        self.frontend_port = self._find_available_port()
        self.project_id = project_id
        
        # Sandbox guard scoped to this project's directory
        self.guard = SandboxGuard(
            project_root=str(self.project_path),
            max_commands_per_minute=30,
            allow_network=False
        )
        
        # Store instance if ID provided
        if project_id:
            ProjectRunner._instances[project_id] = self

    def _detect_frontend_path(self) -> Path:
        """
        Auto-detect whether the project uses a nested frontend/ directory
        or a flat structure where everything is at the project root.
        """
        frontend_dir = self.project_path / "frontend"
        
        # Check if frontend/ has real project files
        if frontend_dir.is_dir():
            has_pkg = (frontend_dir / "package.json").exists()
            has_server = (frontend_dir / "server.js").exists() or (frontend_dir / "index.js").exists()
            has_html = (frontend_dir / "index.html").exists()
            
            # Framework-specific checks for nested struct
            has_rails = (frontend_dir / "Gemfile").exists() or (frontend_dir / "config" / "routes.rb").exists()
            has_django = (frontend_dir / "manage.py").exists()
            has_laravel = (frontend_dir / "artisan").exists()
            
            if has_pkg or has_server or has_html or has_rails or has_django or has_laravel:
                logger.info(f"[ProjectRunner] Frontend path: {frontend_dir} (nested structure)")
                return frontend_dir
        
        # Check project root for flat structure
        # Extended detection for non-NPM projects (Rails, Rust, etc.)
        # If ANY of these exist in root, it's a flat project.
        root_indicators = [
            # Node/JS
            "package.json", "server.js", "index.js", "index.html", "vite.config.js", "vite.config.ts", "next.config.js", "next.config.mjs",
            
            # Python
            "requirements.txt", "app.py", "main.py", "manage.py", "Pipfile", "pyproject.toml",
            
            # Ruby/Rails
            "Gemfile", "config/routes.rb", "bin/rails", "config.ru",
            
            # PHP/Laravel
            "composer.json", "artisan", "index.php",
            
            # Go
            "go.mod", "main.go",
            
            # Rust
            "Cargo.toml", 
            
            # Java
            "pom.xml", "build.gradle",
            
            # .NET
            "Program.cs", "Startup.cs",
            
            # C++
            "CMakeLists.txt", "Makefile",
        ]
        
        has_flat_structure = False
        for indicator in root_indicators:
            # Handle nested paths in indicators list (e.g. config/routes.rb)
            check_path = self.project_path / indicator
            if check_path.exists():
                logger.info(f"[ProjectRunner] Detected flat structure ({indicator} found)")
                has_flat_structure = True
                break
        
        # Check for .csproj (glob)
        if not has_flat_structure and list(self.project_path.glob("*.csproj")):
            logger.info("[ProjectRunner] Detected flat structure (.csproj found)")
            has_flat_structure = True

        # DEBUG: List directory contents to see why detection fails
        try:
            files_in_root = [f.name for f in self.project_path.iterdir()]
            logger.info(f"[ProjectRunner] Files in {self.project_path}: {files_in_root}")
        except Exception as e:
            logger.error(f"[ProjectRunner] Failed to list files in {self.project_path}: {e}")

        if has_flat_structure:
            return self.project_path
        
        # Fallback Logic:
        # If frontend/ DOES NOT exist, use root as fallback to avoid "Directory not found" error.
        if not frontend_dir.exists():
             logger.warning(f"[ProjectRunner] 'frontend/' directory missing. Defaulting to root: {self.project_path}")
             return self.project_path
        
        # If frontend/ exists but is empty/unknown, default to it for backward compatibility
        logger.info(f"[ProjectRunner] Defaulting to {frontend_dir} (legacy fallback)")
        return frontend_dir

    @staticmethod
    def _find_available_port(start: int = 3100, end: int = 3200) -> int:
        """
        Find an available port in the range [start, end).
        Starts at 3100 to avoid conflict with ACEA's own Next.js frontend on 3000.
        """
        import socket
        for port in range(start, end):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.1)
                    result = s.connect_ex(('localhost', port))
                    if result != 0:  # Port is NOT in use
                        return port
            except OSError:
                continue
        # Fallback if all ports are busy (unlikely)
        return start

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

    async def setup_frontend(self, install_cmd: str = "npm install") -> Dict[str, Any]:
        """Install dependencies using the provided command."""
        if not self.frontend_path.exists():
            return {"success": False, "error": "Frontend directory not found"}
        
        # If no install command provided (e.g. static), just return success
        if not install_cmd:
             self._log("No install command needed.")
             return {"success": True, "message": "No installation needed"}

        if install_cmd.startswith("npm install") and not (self.frontend_path / "package.json").exists():
             # Check for other manifests
             if (self.frontend_path / "Cargo.toml").exists():
                 install_cmd = "cargo build"
                 self._log("Detected Cargo.toml, switching to: cargo build")
             elif (self.frontend_path / "Gemfile").exists():
                 install_cmd = "bundle install"
                 self._log("Detected Gemfile, switching to: bundle install")
             elif (self.frontend_path / "composer.json").exists():
                 install_cmd = "composer install"
                 self._log("Detected composer.json, switching to: composer install")
             elif list(self.frontend_path.glob("*.csproj")):
                 install_cmd = "dotnet restore"
                 self._log("Detected .csproj, switching to: dotnet restore")
             elif (self.frontend_path / "CMakeLists.txt").exists():
                 # basic cmake setup
                 install_cmd = "cmake ."
                 self._log("Detected CMakeLists.txt, switching to: cmake .")
             else:
                 self._log("No recognized manifest found. Skipping install.")
                 return {"success": True, "message": "No installation needed (static/unknown)"}


        # Auto-add --legacy-peer-deps for npm to handle version conflicts gracefully
        if install_cmd.startswith("npm install") and "--legacy-peer-deps" not in install_cmd:
            install_cmd = install_cmd + " --legacy-peer-deps"

        # Check if the required tool exists (e.g., bundle, cargo, composer)
        # Extract binary name: "bundle install" -> "bundle"
        tool_bin = install_cmd.split()[0]
        if tool_bin not in ["npm", "npx"]: # Assume npm/npx are present or handled by shell fallback
            # Simple check: try 'tool --version'
            try:
                subprocess.run(
                    f"{tool_bin} --version", 
                    shell=True, 
                    stdout=subprocess.DEVNULL, 
                    stderr=subprocess.DEVNULL, 
                    check=True
                )
            except subprocess.CalledProcessError:
                self._log(f"Tool '{tool_bin}' not found in environment.")
                return {"success": False, "error": f"Required tool '{tool_bin}' is not installed.", "code": "MISSING_TOOL"}

        self._log(f"Installing dependencies ({install_cmd})... this may take a minute.")
        try:
            # SandboxGuard: validate command before execution
            allowed, reason = self.guard.check_command(install_cmd)
            if not allowed:
                self._log(f"SandboxGuard DENIED: {reason}")
                return {"success": False, "error": f"Command blocked by SandboxGuard: {reason}"}
            
            # Use shell=True for compatibility with npm on both Windows and Linux
            # output is captured via PIPEs
            process = subprocess.Popen(
                install_cmd,
                cwd=str(self.frontend_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True
            )
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                err_msg = stderr.decode()
                stdout_msg = stdout.decode()
                full_log = f"{stdout_msg}\n{err_msg}"
                self._log(f"Install failed: {err_msg[:200]}")
                return {"success": False, "error": full_log[:3000]}
            
            self._log("Dependencies installed successfully.")
            return {"success": True, "message": "Dependencies installed"}
        except Exception as e:
            self._log(f"Setup Exception: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def _preflight_check(self) -> Optional[str]:
        """
        Pre-flight structural validation before starting the dev server.
        Returns None if OK, or an error message string if structure is invalid.
        """
        import json as _json
        
        pkg_path = self.frontend_path / "package.json"
        if not pkg_path.exists():
            # Check if there's a server.js or index.html directly (non-npm project)
            has_server = (self.frontend_path / "server.js").exists() or (self.frontend_path / "index.js").exists()
            has_html = (self.frontend_path / "index.html").exists()
            if has_server or has_html:
                return None  # Valid non-npm project
            return f"No package.json found in {self.frontend_path}"
        
        # Detect if this is a Next.js project
        try:
            with open(pkg_path, "r", encoding="utf-8") as f:
                pkg = _json.load(f)
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            is_nextjs = "next" in deps
        except Exception:
            is_nextjs = False
        
        if is_nextjs:
            has_app = (self.frontend_path / "app").is_dir()
            has_pages = (self.frontend_path / "pages").is_dir()
            has_src_app = (self.frontend_path / "src" / "app").is_dir()
            
            if not (has_app or has_pages or has_src_app):
                misplaced = []
                for d in ["app", "pages", "src"]:
                    if (self.project_path / d).is_dir():
                        misplaced.append(str(self.project_path / d))
                hint = f" Found misplaced directory at: {', '.join(misplaced)}" if misplaced else ""
                return (
                    f"Next.js requires 'app/' or 'pages/' directory under {self.frontend_path}, "
                    f"but none was found.{hint} "
                    f"This is a file structure generation error — the AI placed files outside frontend/."
                )
        
        return None  # All OK
    
    def resolve_run_command(self, run_cmd: str) -> str:
        """
        Resolve the best available run command by checking package.json scripts.
        If 'npm run dev' is requested but 'dev' doesn't exist, fall back to alternatives.
        """
        import json as _json
        
        # Only resolve npm commands
        if not run_cmd.startswith("npm"):
            return run_cmd
        
        pkg_path = self.frontend_path / "package.json"
        if not pkg_path.exists():
            return run_cmd
        
        try:
            with open(pkg_path, "r", encoding="utf-8") as f:
                pkg = _json.load(f)
            scripts = pkg.get("scripts", {})
        except Exception:
            return run_cmd
        
        # If requesting 'npm run dev' but 'dev' doesn't exist
        if run_cmd == "npm run dev" and "dev" not in scripts:
            # Priority: start > dev:frontend > node server.js
            if "start" in scripts:
                self._log(f"Script 'dev' not found, using 'start': {scripts['start']}")
                return "npm start"
            elif "dev:frontend" in scripts:
                self._log(f"Script 'dev' not found, using 'dev:frontend': {scripts['dev:frontend']}")
                return "npm run dev:frontend"
            else:
                # Direct execution fallback
                server_js = self.frontend_path / "server.js"
                index_js = self.frontend_path / "index.js"
                if server_js.exists():
                    self._log("Script 'dev' not found, falling back to 'node server.js'")
                    return "node server.js"
                elif index_js.exists():
                    self._log("Script 'dev' not found, falling back to 'node index.js'")
                    return "node index.js"
        
        # Check for static HTML project (no package.json, but has index.html)
        if not pkg_path.exists() and (self.frontend_path / "index.html").exists():
            self._log("Static HTML project detected. Using Python HTTP server.")
            # We will return a placeholder, actual command constructed in _inject_port_into_command or caller
            return "python -m http.server"
        
        # Check for non-npm projects if command is default "npm run dev"
        if run_cmd == "npm run dev":
            if (self.frontend_path / "Cargo.toml").exists():
                return "cargo run"
            elif (self.frontend_path / "Gemfile").exists():
                return "rails server" # Default to rails, user can override
            elif (self.frontend_path / "composer.json").exists():
                 if (self.frontend_path / "artisan").exists():
                     return "php artisan serve"
            elif list(self.frontend_path.glob("*.csproj")):
                return "dotnet run"
            elif (self.frontend_path / "CMakeLists.txt").exists():
                # Naive C++ run - assumes executable output named 'main' or similar
                # Ideally user provides specific command
                return "./main" if not IS_WINDOWS else "main.exe"

        return run_cmd
    
    def _patch_package_json_port(self, port: int):
        """
        Patch the 'dev' script in package.json to use our port.
        Handles Next.js `-p 3000` and generic `--port 3000` patterns.
        """
        import re, json
        pkg_path = self.frontend_path / "package.json"
        if not pkg_path.exists():
            return
        
        try:
            with open(pkg_path, "r", encoding="utf-8") as f:
                pkg = json.load(f)
            
            scripts = pkg.get("scripts", {})
            dev_script = scripts.get("dev", "")
            
            if not dev_script:
                return
            
            original = dev_script
            dev_script = re.sub(r'-p\s+\d+', f'-p {port}', dev_script)
            dev_script = re.sub(r'--port\s+\d+', f'--port {port}', dev_script)
            
            if dev_script != original:
                scripts["dev"] = dev_script
                pkg["scripts"] = scripts
                with open(pkg_path, "w", encoding="utf-8") as f:
                    json.dump(pkg, f, indent=2)
                self._log(f"Patched package.json dev script port → {port}")
        except Exception as e:
            self._log(f"Warning: Could not patch package.json port: {e}")

    def _inject_port_into_command(self, run_cmd: str, port: int) -> str:
        """
        Inject --port flag into the run command.
        Vite, Next.js, webpack-dev-server, and most tools honor --port.
        This is the most reliable way to ensure the server uses our port.
        """
        import re as _re
        
        # Don't inject if --port or -p is already present
        if _re.search(r'--port\s+\d+', run_cmd) or _re.search(r'-p\s+\d+', run_cmd):
            # Replace existing port value with ours
            run_cmd = _re.sub(r'--port\s+\d+', f'--port {port}', run_cmd)
            run_cmd = _re.sub(r'-p\s+\d+', f'-p {port}', run_cmd)
            self._log(f"Port flag updated to {port}")
            return run_cmd
        
        # For npm/npx commands, append -- --port NNNN
        # npm run dev -- --port 3100 passes --port to the underlying tool
        if run_cmd.startswith("npm run"):
            run_cmd = f"{run_cmd} -- --port {port}"
            self._log(f"Injected port {port} via npm -- passthrough")
        elif run_cmd.startswith("npx "):
            run_cmd = f"{run_cmd} --port {port}"
            self._log(f"Injected port {port} for npx command")
        elif run_cmd.startswith("vite") or "vite" in run_cmd:
            run_cmd = f"{run_cmd} --port {port}"
            self._log(f"Injected port {port} for Vite")
        elif run_cmd.startswith("next"):
            run_cmd = f"{run_cmd} -p {port}"
            self._log(f"Injected port {port} for Next.js")
        elif run_cmd.startswith("node "):
            # For plain Node.js servers, PORT env var is typically used
            # Don't append --port since it's not a standard Node flag
            self._log(f"Node.js server — will use PORT={port} env var")
        elif run_cmd.startswith("python") and "http.server" in run_cmd:
            # Python http.server accepts port as positional argument: python -m http.server 3000
            run_cmd = f"{run_cmd} {port}"
            self._log(f"Injected port {port} for Python HTTP server")
        elif run_cmd == "npm start":
            # npm start might run a custom script — PORT env var is our best bet
            self._log(f"npm start — will use PORT={port} env var")
        elif "cargo run" in run_cmd:
            # Axum/Actix usually look for PORT env var, or we can try passing as arg if needed.
            # For now rely on PORT env var matching the 'env' dict below.
            self._log(f"Rust project — will use PORT={port} env var")
        elif "dotnet run" in run_cmd:
             # ASP.NET Core uses ASPNETCORE_URLS
             # We handle this by setting the env var in start_frontend
             pass
        elif "php artisan serve" in run_cmd:
            run_cmd = f"{run_cmd} --port={port}"
            self._log(f"Injected port {port} for Laravel")
        elif "rails server" in run_cmd:
            run_cmd = f"{run_cmd} -p {port}"
            self._log(f"Injected port {port} for Rails")
        
        return run_cmd
    
    def _detect_port_from_logs(self) -> Optional[int]:
        """
        Scan captured stdout/stderr logs for the actual port the server started on.
        Returns the detected port, or None if not found.
        
        Patterns detected:
        - Vite:    "Local:   http://localhost:5173/"
        - Next.js: "started server on 0.0.0.0:3000"
        - CRA:     "On Your Network:  http://192.168.x.x:3000"
        - Express: "listening on port 3000" / "Server running on http://localhost:3000"
        - Generic: "http://localhost:XXXX"
        """
        import re as _re
        
        # Check recent logs (last 30 lines)
        recent = self.logs[-30:]
        
        for line in recent:
            # Pattern 1: "Local:   http://localhost:5173/" (Vite)
            match = _re.search(r'Local:\s+https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0):(\d+)', line)
            if match:
                return int(match.group(1))
            
            # Pattern 2: "started server on 0.0.0.0:3000" (Next.js)
            match = _re.search(r'started server on\s+[\w.:]+:(\d+)', line)
            if match:
                return int(match.group(1))
            
            # Pattern 3: "listening on port 3000" (Express)
            match = _re.search(r'listening on port\s+(\d+)', line, _re.IGNORECASE)
            if match:
                return int(match.group(1))
            
            # Pattern 4: "Server running on http://localhost:3000"
            match = _re.search(r'(?:running|available|started)\s+(?:on|at)\s+https?://[\w.]+:(\d+)', line, _re.IGNORECASE)
            if match:
                return int(match.group(1))
            
            # Pattern 5: Generic "http://localhost:NNNN" (last resort)
            match = _re.search(r'https?://localhost:(\d+)', line)
            if match:
                detected = int(match.group(1))
                # Skip common false positives (HMR websocket ports, etc.)
                if 1024 <= detected <= 65535:
                    return detected
        
        return None
    
    async def start_frontend(self, run_cmd: str = "npm run dev") -> Dict[str, Any]:
        """Start the dev server using the provided command, enforcing self.frontend_port."""
        if self.frontend_process and self.frontend_process.poll() is None:
            return {"success": True, "message": "Already running", "port": self.frontend_port, "url": f"http://localhost:{self.frontend_port}"}
        
        try:
            # Pre-flight: Validate project structure before starting
            preflight_error = self._preflight_check()
            if preflight_error:
                self._log(f"Pre-flight FAILED: {preflight_error}")
                return {"success": False, "error": preflight_error}
            
            port = self.frontend_port
            self._log(f"Starting server on port {port}...")
            
            # Patch package.json to replace any hardcoded port with ours
            self._patch_package_json_port(port)
            
            # Kill anything running on this port (cross-platform)
            try:
                _kill_port_occupants(port)
            except Exception as kill_err:
                self._log(f"Warning: Failed to clear port {port}: {kill_err}")

            # Resolve the run command (handles missing 'dev' script)
            run_cmd = self.resolve_run_command(run_cmd)
            
            # --- PORT INJECTION ---
            # Ensure the dev server uses our port. Different tools need different flags.
            run_cmd = self._inject_port_into_command(run_cmd, port)
            self._log(f"Running: {run_cmd}")
            
            # SandboxGuard: validate command before execution
            allowed, reason = self.guard.check_command(run_cmd)
            if not allowed:
                self._log(f"SandboxGuard DENIED: {reason}")
                return {"success": False, "error": f"Command blocked by SandboxGuard: {reason}"}
            
            # Set PORT env var as well (honored by Vite, CRA, some tools)
            env = os.environ.copy()
            env["PORT"] = str(port)
            env["ASPNETCORE_URLS"] = f"http://localhost:{port}" # For .NET Core
            
            cmd_parts = run_cmd.split()
            
            # On Linux, start a new process group so we can kill the tree later
            popen_kwargs = {
                "cwd": str(self.frontend_path),
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "shell": True,
                "env": env,
            }
            if not IS_WINDOWS:
                popen_kwargs["preexec_fn"] = os.setsid
            
            self.frontend_process = subprocess.Popen(
                run_cmd,
                **popen_kwargs
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
            actual_port = port  # May be updated by runtime detection
            
            for i in range(30):  # Retry for 30 seconds
                # Check if process died FIRST (faster failure)
                if self.frontend_process.poll() is not None:
                    await asyncio.sleep(0.5)
                    captured = "\n".join(self.logs[-20:])
                    self._log("Server stopped immediately.")
                    return {
                        "success": False, 
                        "error": f"Server crashed on startup. Logs:\n{captured}",
                        "logs": captured
                    }
                
                # --- RUNTIME PORT DETECTION ---
                # Scan stdout for actual port if server started on a different one
                if i >= 2 and actual_port == port:  # Check after 2s of startup
                    detected = self._detect_port_from_logs()
                    if detected and detected != port:
                        self._log(f"Detected server on port {detected} (expected {port}), adjusting...")
                        actual_port = detected
                        self.frontend_port = detected
                
                try:
                    with urllib.request.urlopen(f"http://localhost:{actual_port}", timeout=1) as response:
                        if response.status < 500:
                            server_ready = True
                            break
                except Exception:
                    await asyncio.sleep(1)
            
            if not server_ready:
                captured = "\n".join(self.logs[-20:])
                self._log("Server start timed out (30s).")
                if self.frontend_process.poll() is not None:
                    self._log("Server process is no longer running.")
                    return {
                        "success": False, 
                        "error": f"Server crashed during startup (timed out). Logs:\n{captured}",
                        "logs": captured
                    }
                return {
                    "success": False, 
                    "error": f"Server started but not responding on port {actual_port} after 30s. Logs:\n{captured}",
                    "logs": captured
                }
            else:
                self._log("Server is responsive!")
            
            url = f"http://localhost:{actual_port}"
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
        """Stop the frontend dev server — cross-platform."""
        if self.frontend_process:
            self._log("Stopping server...")
            _kill_process_tree(self.frontend_process.pid)
            self.frontend_process = None
            self._log("Server stopped.")
            
    def get_captured_logs(self) -> str:
        return "\n".join(self.logs)

    def cleanup(self):
        self.stop_frontend()
