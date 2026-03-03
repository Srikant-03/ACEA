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
        
        # 1. ARCHITECT DECISION (Authoritative)
        architect_type = blueprint.get("project_type", "dynamic")
        architect_stack = blueprint.get("primary_stack", "")
        
        # If Architect explicitly says STATIC, trust it (but verify it's not actually a framework)
        if architect_type == "static":
            return {
                "install_cmd": "",
                "run_cmd": "python3 -m http.server 3000 --directory frontend",
                "port": 3000,
                "project_type": "static",
                "work_dir": "/home/user/project"
            }

        # 2. EXPLICIT CONFIG FILES (Framework Detection)
        # Check for specific files
        has_package_json = any("package.json" in f for f in files.keys())
        has_requirements_txt = any("requirements.txt" in f for f in files.keys())
        has_server_js = any(f.endswith("server.js") for f in files.keys())
        has_gemfile = any("Gemfile" in f for f in files.keys())
        has_cargo = any("Cargo.toml" in f for f in files.keys())
        has_composer = any("composer.json" in f for f in files.keys())
        has_csproj = any(f.endswith(".csproj") for f in files.keys())
        has_cmake = any("CMakeLists.txt" in f for f in files.keys())
        
        # Parse package.json scripts if available
        pkg_scripts = {}
        if has_package_json:
            import json as _json
            for f_name, f_content in files.items():
                if f_name.endswith("package.json") and "/" not in f_name.replace("\\", "/").lstrip("/"):
                    # Root-level package.json
                    try:
                        pkg_data = _json.loads(f_content)
                        pkg_scripts = pkg_data.get("scripts", {})
                    except Exception:
                        pass
                    break
        
        # Determine best run command from scripts
        def best_run_cmd(scripts: dict) -> str:
            """Pick the best available run command from package.json scripts."""
            if "dev" in scripts:
                return "npm run dev"
            if "start" in scripts:
                return "npm start"
            if "serve" in scripts:
                return "npm run serve"
            # If server.js exists, run it directly
            if has_server_js:
                return "node server.js"
            return "npm start"
        
        # Detect framework from files
        is_nextjs = any("next.config" in f for f in files.keys()) or "next" in tech_stack
        is_vite = any("vite.config" in f for f in files.keys()) or "vite" in tech_stack
        is_flask = has_requirements_txt and ("flask" in tech_stack or any("app.py" in f for f in files.keys()))
        is_fastapi = "fastapi" in tech_stack or any("main.py" in f and "fastapi" in files.get(f, "").lower() for f in files.keys())
        is_django = "django" in tech_stack or any("manage.py" in f for f in files.keys())
        is_vue = any("vue" in f.lower() for f in files.keys()) or "vue" in tech_stack
        
        # Default config (Dynamic Fallback)
        config = {
            "install_cmd": "npm install" if has_package_json else "",
            "run_cmd": best_run_cmd(pkg_scripts) if has_package_json else "echo 'No run command found'",
            "port": 3000,
            "work_dir": "/home/user/project",
            "project_type": "nodejs" if has_package_json else "unknown",
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
                "run_cmd": best_run_cmd(pkg_scripts),
                "port": 3000,
                "project_type": "react",
                "env_vars": {"CHOKIDAR_USEPOLLING": "true", "PORT": "3000"}
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
        # Python script (Generic)
        elif any(f.endswith(".py") for f in files.keys()):
            entrypoint = blueprint.get("entrypoint", "main.py")
            config.update({
                "install_cmd": "pip install -r requirements.txt" if has_requirements_txt else "",
                "run_cmd": f"python {entrypoint}",
                "port": 8000,
                "project_type": "python"
            })
        # Ruby on Rails
        elif has_gemfile:
            # Set GEM_HOME/BUNDLE_PATH to user-writable dir to avoid permission errors
            gem_env = "export GEM_HOME=$HOME/.gems && export BUNDLE_PATH=$HOME/.gems && export PATH=$HOME/.gems/bin:$PATH"
            config.update({
                # Force fresh lockfile generation for Linux to avoid platform conflicts
                # chmod +x bin/* ensures Rails executables are runnable
                "install_cmd": f"{gem_env} && chmod +x bin/* || true && rm -f Gemfile.lock && bundle install",
                # Use ; for db:migrate so migration failure (no DB) doesn't block server startup
                "run_cmd": f"{gem_env} && bundle exec rails db:migrate 2>/dev/null; {gem_env} && bundle exec rails server -b 0.0.0.0 -p 3000",
                "port": 3000,
                "project_type": "rails"
            })
        # Rust (Axum/Actix)
        elif has_cargo:
            config.update({
                "install_cmd": "cargo build",
                "run_cmd": "cargo run",
                "port": 3000, # Default, can be overridden by env
                "project_type": "rust",
                "env_vars": {"PORT": "3000"}
            })
        # PHP (Laravel)
        elif has_composer:
            config.update({
                "install_cmd": "composer install",
                "run_cmd": "php artisan serve --host=0.0.0.0 --port=8000",
                "port": 8000,
                "project_type": "php"
            })
        # .NET Core
        elif has_csproj:
            config.update({
                "install_cmd": "dotnet restore",
                "run_cmd": "dotnet run --urls=http://0.0.0.0:5000",
                "port": 5000,
                "project_type": "dotnet"
            })
        # C++ (CMake)
        elif has_cmake:
            config.update({
                "install_cmd": "cmake . && make",
                "run_cmd": "./main", # Assumption: executable named main
                "port": 8080,
                "project_type": "cpp"
            })
        # Express / Node.js with server.js (no framework)
        # Express / Node.js with server.js (no framework)
        elif has_server_js:
            config.update({
                "install_cmd": "npm install" if has_package_json else "",
                "run_cmd": "node server.js",
                "port": 3000,
                "project_type": "express"
            })
        # Generic Node.js (Fallback for package.json without known framework)
        elif has_package_json:
            config.update({
                "install_cmd": "npm install",
                "run_cmd": best_run_cmd(pkg_scripts),
                "port": 3000,
                "project_type": "nodejs"
            })
        
        # Apply defensive patterns to all commands
        config["install_cmd"] = self._make_command_defensive(config["install_cmd"], config["project_type"])
        config["run_cmd"] = self._make_command_defensive(config["run_cmd"], config["project_type"])
        
        return config
    
    def _make_command_defensive(self, cmd: str, project_type: str) -> str:
        """
        Make install/run commands non-blocking and defensive.
        Prevents failures due to missing files.
        """
        if not cmd:
            return cmd
        
        # Rails: Use bundle exec for rails commands
        if project_type == "rails":
            # Don't double up || true — config already includes it
            if "chmod +x bin/* ||" not in cmd:
                cmd = cmd.replace("chmod +x bin/*", "chmod +x bin/* || true")
            cmd = cmd.replace("bin/rails", "bundle exec rails")
            cmd = cmd.replace("bin/bundle", "bundle")
        
        # Django: Check for manage.py before using it
        elif project_type == "django":
            if "manage.py" in cmd:
                # If manage.py works use it, otherwise fallback to module
                cmd = f"test -f manage.py && {cmd} || python3 -m django {cmd.split('manage.py', 1)[1].strip()}"
        
        # Node: Add fallbacks for missing scripts
        elif project_type in ["nodejs", "nextjs", "react", "vite", "vue", "svelte", "remix", "angular"]:
            if "npm run" in cmd:
                # If script doesn't exist, try alternatives. Do NOT silence errors.
                cmd = f"{cmd} || npm start || node index.js || node server.js"
        
        # PHP/Laravel: Check for artisan
        elif project_type == "laravel":
            if "artisan" in cmd:
                cmd = f"test -f artisan && {cmd} || php -S 0.0.0.0:8000 -t public"

        # Python Script: Check for main.py
        elif project_type == "python":
            if "main.py" in cmd:
                cmd = f"test -f main.py && {cmd} || echo 'main.py not found, running directory listing...'"

        return cmd

    
    def _sanitize_gemfile(self, content: str) -> str:
        """Sanitize Gemfile content to be Linux-compatible and fix common LLM gem errors."""
        import re
        # Remove platforms block: platforms :mingw, ... do ... end
        content = re.sub(r'platforms\s+:[a-zA-Z0-9_,\s]+mingw[a-zA-Z0-9_,\s]*do.*?end', '', content, flags=re.DOTALL)
        
        # Fix common LLM gem name errors
        gem_replacements = {
            'hotwire-rails': ('turbo-rails', 'stimulus-rails'),
        }
        
        # Collect all existing gem names for dedup
        gem_name_pattern = re.compile(r"""gem\s+['"]([^'"]+)['"]""")
        existing_gems = set()
        for line in content.split('\n'):
            m = gem_name_pattern.search(line)
            if m:
                existing_gems.add(m.group(1))
        
        lines = content.split('\n')
        cleaned_lines = []
        seen_gems = set()
        
        for line in lines:
            if "gem" in line and ("wdm" in line or "tzinfo-data" in line):
                continue
            if "platforms" in line and "mingw" in line:
                continue
            
            replaced = False
            for bad_gem, replacements in gem_replacements.items():
                if bad_gem in line and "gem" in line:
                    for replacement in replacements:
                        if replacement not in existing_gems and replacement not in seen_gems:
                            cleaned_lines.append(f"gem '{replacement}'")
                            seen_gems.add(replacement)
                    replaced = True
                    logger.info(f"Gemfile sanitizer: replaced '{bad_gem}' with {replacements}")
                    break
            
            if not replaced:
                m = gem_name_pattern.search(line)
                if m:
                    gem_name = m.group(1)
                    if gem_name in seen_gems:
                        logger.info(f"Gemfile sanitizer: removed duplicate gem '{gem_name}'")
                        continue
                    seen_gems.add(gem_name)
                cleaned_lines.append(line)
            
        return '\n'.join(cleaned_lines)

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
                import inspect
                result = on_progress(msg)
                if inspect.isawaitable(result):
                    asyncio.ensure_future(result)
        
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
                sandbox = Sandbox.create(api_key=E2B_API_KEY, timeout=E2B_TIMEOUT_SECONDS)
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
            sandbox.commands.run(f"mkdir -p {work_dir}")  # Ensure work_dir exists
            uploaded = 0
            
            for file_path, content in project_files.items():
                if file_path == "blueprint.json":
                    continue
                
                
                # Normalize Windows backslashes to forward slashes for Linux sandbox
                file_path_linux = file_path.replace("\\", "/")
                full_path = f"{work_dir}/{file_path_linux}"
                
                # SANITIZATION: Fix Gemfile for Linux environment
                if file_path.endswith("Gemfile"):
                    content = self._sanitize_gemfile(content)
                    log(f"🧹 Sanitized Gemfile for Linux compatibility")

                try:
                    parent_dir = str(Path(full_path).parent)
                    sandbox.commands.run(f"mkdir -p {parent_dir}")
                    sandbox.files.write(full_path, content)
                    uploaded += 1
                except Exception as e:
                    log(f"Failed to upload {file_path}: {str(e)[:50]}")
            
            log(f"✅ Uploaded {uploaded} files")
            
            # === Install System Dependencies (Pre-install) ===
            ptype = config.get("project_type")
            log(f"🔧 Checking system dependencies for {ptype}...")
            
            if ptype == "rails":
                 # Install Ruby, Bundler, and build tools
                 log("📦 Installing Ruby/Rails system dependencies...")
                 sys_inst = sandbox.commands.run(
                     "sudo apt-get update && sudo apt-get install -y ruby-full build-essential libsqlite3-dev libyaml-dev libpq-dev nodejs && sudo gem install bundler",
                     timeout=300
                 )
                 if sys_inst.exit_code != 0:
                     log(f"⚠️ System install failed: {sys_inst.stderr[:200]}")
                 else:
                     log("✅ Ruby dependencies installed")

                 # Configure gem paths to be user-writable (avoid permission errors on bundle install)
                 sandbox.commands.run(
                     r'echo "export GEM_HOME=\$HOME/.gems" >> ~/.bashrc && '
                     r'echo "export BUNDLE_PATH=\$HOME/.gems" >> ~/.bashrc && '
                     r'echo "export PATH=\$HOME/.gems/bin:\$PATH" >> ~/.bashrc',
                     timeout=10
                 )
                 log("✅ Configured gem paths to user-writable directory")

                 # Ensure we start fresh
                 sandbox.commands.run(f"rm -f {work_dir}/Gemfile.lock")
                 sandbox.commands.run(f"rm -rf {work_dir}/.bundle")

            elif ptype == "rust":
                 # Install Rust (if not present)
                 log("📦 Checking Rust installation...")
                 check_rust = sandbox.commands.run("cargo --version")
                 if check_rust.exit_code != 0:
                     log("📦 Installing Rust...")
                     sys_inst = sandbox.commands.run(
                         "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y",
                         timeout=300
                     )
                     # Add source to profile for subsequent commands
                     config["env_vars"]["PATH"] = "$HOME/.cargo/bin:$PATH"
                 else:
                     log("✅ Rust is already installed")

            elif ptype == "php":
                 # Install PHP and Composer
                 log("📦 Installing PHP/Composer...")
                 sys_inst = sandbox.commands.run(
                     "sudo apt-get update && sudo apt-get install -y php php-cli php-mbstring unzip curl && "
                     "curl -sS https://getcomposer.org/installer | php && "
                     "sudo mv composer.phar /usr/local/bin/composer",
                     timeout=300
                 )
                 if sys_inst.exit_code != 0:
                     log(f"⚠️ PHP install failed: {sys_inst.stderr[:200]}")
            
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
            install_success = True  # Track install result to gate server start
            if config["install_cmd"]:
                install_cmd = config["install_cmd"]
                # Use --legacy-peer-deps for robustness
                if install_cmd == "npm install":
                    install_cmd = "npm install --legacy-peer-deps"
                log(f"📦 Installing dependencies: {install_cmd}")
                try:
                    result = sandbox.commands.run(
                        install_cmd,
                        cwd=work_dir,
                        timeout=300
                    )
                    if result.exit_code != 0:
                        error_detail = result.stderr or result.stdout or 'check logs'
                        log(f"⚠️ Install error (exit {result.exit_code}): {error_detail[:500]}")
                        install_success = False
                    else:
                        log("✅ Dependencies installed")
                except Exception as e:
                    log(f"⚠️ Install error: {str(e)[:200]}")
                    install_success = False
            
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
            if config["run_cmd"] and not install_success:
                log(f"⚠️ Skipping dev server — dependency install failed. Fix the errors above and restart.")
            elif config["run_cmd"]:
                log(f"🏃 Starting dev server: {config['run_cmd']}")
                
                # 1. Kill anything on the port first
                try:
                    sandbox.commands.run(f"fuser -k {port}/tcp || true") 
                except:
                    pass

                try:
                    env_str = " ".join(f"{k}={v}" for k, v in config.get("env_vars", {}).items())
                    # Use setsid to prevent process from dying if shell disconnects (robustness)
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
            app_ready = False
            for attempt in range(15): # Increased wait time
                check_result = sandbox.commands.run(f"ss -tlnp | grep :{port} || echo ''")
                if check_result.stdout and str(port) in check_result.stdout:
                    log(f"✅ App ready on port {port}")
                    app_ready = True
                    break
                await asyncio.sleep(2)
            
            if not app_ready:
                # RETRIEVE CRASH LOGS
                log(f"❌ App failed to bind port {port}. retrieving logs...")
                try:
                    log_content = sandbox.commands.run("cat /tmp/app.log").stdout
                    log(f"\n=== APPLICATION CRASH LOG ===\n{log_content[-1000:]}\n===========================")
                except:
                    log("Could not read /tmp/app.log")
            
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
                "project_type": config["project_type"],
                "port": port,
                "timeout": E2B_TIMEOUT_SECONDS
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
    
    async def delete_file_in_sandbox(self, project_id: str, filepath: str) -> bool:
        """Delete a file in the active E2B sandbox."""
        sandbox = self.active_sandboxes.get(project_id)
        if not sandbox:
            return False
        
        try:
            info = self.sandbox_info.get(project_id, {})
            work_dir = info.get("config", {}).get("work_dir", "/home/user/project")
            full_path = f"{work_dir}/{filepath}"
            
            # Delete file
            sandbox.commands.run(f"rm -rf {full_path}")
            logger.info(f"Deleted {filepath} in sandbox {project_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete {filepath} in sandbox: {e}")
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
