"""
Stack Profiles — Data-driven tech-stack detection and rule registry.

Instead of hardcoding Next.js / Tailwind / React rules into every agent prompt,
each stack registers a profile here. Agents call get_stack_profile() and inject
only the relevant rules.

Adding a new stack is as simple as adding a new dict to STACK_PROFILES.
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class StackProfile:
    """A single tech-stack profile with rules for each agent."""
    
    id: str                              # e.g. "nextjs", "python-flask"
    display_name: str                    # e.g. "Next.js", "Flask"
    category: str                        # "frontend", "backend", "fullstack", "static"
    is_web: bool = True                  # Whether browser validation should run
    
    # Detection: keywords in user prompt / tech_stack field that trigger this profile
    detect_keywords: List[str] = field(default_factory=list)
    
    # Dependency manifest to generate (path relative to project root)
    dependency_manifest: str = "package.json"
    
    # Required config files: {relative_path: description}
    config_files: Dict[str, str] = field(default_factory=dict)
    
    # File structure prefixes (e.g. "frontend/" for web, "" for Python)
    source_prefix: str = ""
    
    # Architecture constraints
    max_files_simple: int = 8
    max_files_medium: int = 15
    max_files_complex: int = 25
    
    # Primary stack identifier for blueprint
    primary_stack: str = ""
    
    # Default project type
    default_project_type: str = "dynamic"
    
    # Agent-specific rules (injected into prompts dynamically)
    architect_rules: List[str] = field(default_factory=list)
    virtuoso_rules: List[str] = field(default_factory=list)
    
    # Validation rules for _validate_file_structure
    validation_rules: List[str] = field(default_factory=list)
    
    # Example prompts for the architect
    example_prompts: List[Dict[str, str]] = field(default_factory=list)
    
    def get_architect_rules_text(self) -> str:
        """Format architect rules for prompt injection."""
        if not self.architect_rules:
            return ""
        return "\n".join(f"   - {r}" for r in self.architect_rules)
    
    def get_virtuoso_rules_text(self) -> str:
        """Format virtuoso rules for prompt injection."""
        if not self.virtuoso_rules:
            return ""
        return "\n".join(f"   {i+1}. {r}" for i, r in enumerate(self.virtuoso_rules))
    
    def get_config_files_list(self) -> List[Dict[str, str]]:
        """Return config files as list of {path, description} dicts."""
        return [
            {"path": path, "description": desc}
            for path, desc in self.config_files.items()
        ]


# ─────────────────────────────────────────────────────────────
#  STACK PROFILES REGISTRY
# ─────────────────────────────────────────────────────────────

STACK_PROFILES: Dict[str, StackProfile] = {}


def _register(profile: StackProfile):
    STACK_PROFILES[profile.id] = profile


# ── Next.js ──────────────────────────────────────────────────
_register(StackProfile(
    id="nextjs",
    display_name="Next.js",
    category="fullstack",
    is_web=True,
    detect_keywords=["next.js", "nextjs", "next js", "next 14", "next 15", "app router"],
    dependency_manifest="frontend/package.json",
    source_prefix="frontend/",
    primary_stack="nextjs",
    config_files={
        "frontend/package.json": "Package manifest with Next.js dependencies",
        "frontend/tailwind.config.ts": "Tailwind CSS configuration",
        "frontend/postcss.config.mjs": "PostCSS configuration",
        "frontend/next.config.js": "Next.js configuration",
        "frontend/tsconfig.json": "TypeScript configuration",
    },
    architect_rules=[
        "Use App Router (app/ directory) by default, not Pages Router.",
        "All files go under frontend/ unless they are backend files.",
        "Strip src/ for App Router: frontend/app/page.tsx, NOT frontend/src/app/page.tsx.",
        "CRITICAL: Must include frontend/package.json and frontend/next.config.mjs.",
    ],
    virtuoso_rules=[
        "IF using Tailwind CSS: include 'tailwindcss' (v4), 'postcss', AND '@tailwindcss/postcss' in package.json dependencies. DO NOT forget 'tailwindcss'.",
        "IF generating 'postcss.config.mjs': Use 'export default { plugins: { \"@tailwindcss/postcss\": {} } };'",
        "IF generating 'frontend/app/globals.css': Use '@import \"tailwindcss\";' AND define custom theme variables using '@theme { --color-primary: ...; }'.",
        "DO NOT use 'tailwind.config.ts' for colors if using v4. Define them in globals.css @theme block.",
        "Use minimal Next.js config: 'module.exports = { reactStrictMode: true };'",
        "DO NOT add custom 'webpack' rules unless explicitly requested (avoids Turbopack conflicts).",
        "'frontend/app/layout.tsx' MUST include <html> and <body> tags wrapping children.",
        "ALL Page components (page.tsx) MUST have an 'export default function'.",
        "Next.js pages MUST be in 'frontend/app/' directory, NOT 'frontend/src/'.",
        "If using hooks (useState) in 'page.tsx', you MUST add \"use client\"; at the TOP.",
        "Use '@/' alias for ALL cross-directory imports (e.g. '@/components/ProductCard').",
        "NEVER use '../../' in Next.js imports. The '@/' alias maps to the 'frontend/' directory.",
        "tsconfig.json MUST include: {\"compilerOptions\": {\"paths\": {\"@/*\": [\"./*\"]} } }",
        "Use a recent stable major version for all dependencies (e.g. \"^18.0.0\"). NEVER use \"latest\".",
        "Do NOT assume any dependencies are pre-installed. You are the sole dependency manager.",
    ],
    validation_rules=[
        "check_package_json_exists",
        "check_app_dir_exists",
        "check_postcss_tailwind",
        "check_globals_css_v4",
        "check_misplaced_files",
    ],
    example_prompts=[
        {"prompt": "Make a portfolio", "project_type": "dynamic", "primary_stack": "nextjs"},
        {"prompt": "Build a dashboard", "project_type": "dynamic", "primary_stack": "nextjs"},
    ],
))

# ── Vite + React ─────────────────────────────────────────────
_register(StackProfile(
    id="vite",
    display_name="Vite + React",
    category="frontend",
    is_web=True,
    detect_keywords=["vite", "vite react", "react vite"],
    dependency_manifest="frontend/package.json",
    source_prefix="frontend/",
    primary_stack="vite",
    config_files={
        "frontend/package.json": "Package manifest with Vite dependencies",
        "frontend/vite.config.js": "Vite configuration",
        "frontend/tailwind.config.js": "Tailwind CSS configuration",
        "frontend/postcss.config.js": "PostCSS configuration",
    },
    architect_rules=[
        "All source files go under frontend/src/.",
        "Entry point is frontend/src/main.jsx or main.tsx.",
        "CRITICAL: Must include frontend/index.html, frontend/vite.config.js, and frontend/package.json.",
    ],
    virtuoso_rules=[
        "IF using Tailwind CSS: include 'tailwindcss' (v4), 'postcss', AND '@tailwindcss/postcss' in package.json dependencies. DO NOT forget 'tailwindcss'.",
        "Use a recent stable major version for all dependencies. NEVER use \"latest\".",
        "Do NOT assume any dependencies are pre-installed.",
    ],
    validation_rules=["check_package_json_exists", "check_postcss_tailwind"],
    example_prompts=[
        {"prompt": "Single page app with Vite", "project_type": "dynamic", "primary_stack": "vite"},
    ],
))

# ── Vue.js ───────────────────────────────────────────────────
_register(StackProfile(
    id="vue",
    display_name="Vue.js",
    category="frontend",
    is_web=True,
    detect_keywords=["vue", "vue.js", "vuejs", "vue 3", "nuxt"],
    dependency_manifest="frontend/package.json",
    source_prefix="frontend/",
    primary_stack="vue",
    config_files={
        "frontend/package.json": "Package manifest with Vue dependencies",
        "frontend/vite.config.js": "Vite configuration with Vue plugin",
    },
    architect_rules=[
        "Use Vue 3 Composition API by default.",
        "All source files go under frontend/src/.",
    ],
    virtuoso_rules=[
        "Use Vue 3 <script setup> syntax for components.",
        "Use a recent stable major version for all dependencies. NEVER use \"latest\".",
        "DO NOT use React/JSX syntax in .vue files.",
    ],
    validation_rules=["check_package_json_exists"],
    example_prompts=[
        {"prompt": "Vue dashboard", "project_type": "dynamic", "primary_stack": "vue"},
    ],
))

# ── Svelte ───────────────────────────────────────────────────
_register(StackProfile(
    id="svelte",
    display_name="SvelteKit",
    category="frontend",
    is_web=True,
    detect_keywords=["svelte", "sveltekit", "svelte kit"],
    dependency_manifest="frontend/package.json",
    source_prefix="frontend/",
    primary_stack="svelte",
    config_files={
        "frontend/package.json": "Package manifest with SvelteKit dependencies",
        "frontend/svelte.config.js": "SvelteKit configuration",
    },
    architect_rules=["Use SvelteKit with file-based routing."],
    virtuoso_rules=[
        "Use Svelte component syntax (.svelte files).",
        "Use a recent stable major version for all dependencies. NEVER use \"latest\".",
    ],
    validation_rules=["check_package_json_exists"],
))

# ── Python + FastAPI ─────────────────────────────────────────
_register(StackProfile(
    id="python-fastapi",
    display_name="Python FastAPI",
    category="backend",
    is_web=False,
    detect_keywords=["fastapi", "fast api", "python api", "python backend"],
    dependency_manifest="requirements.txt",
    source_prefix="",
    primary_stack="python",
    default_project_type="dynamic",
    config_files={
        "requirements.txt": "Python dependencies",
    },
    architect_rules=[
        "Structure: main.py as entry point, models/, routes/, services/ for organization.",
        "Include a requirements.txt with pinned versions.",
    ],
    virtuoso_rules=[
        "Generate requirements.txt with pinned versions (e.g. fastapi==0.109.0).",
        "DO NOT generate package.json for Python-only projects.",
        "Include proper type hints in all function signatures.",
        "Use async def for route handlers.",
    ],
    validation_rules=["check_requirements_txt_exists"],
    example_prompts=[
        {"prompt": "REST API for todos", "project_type": "dynamic", "primary_stack": "python"},
    ],
))

# ── Python + Flask ───────────────────────────────────────────
_register(StackProfile(
    id="python-flask",
    display_name="Python Flask",
    category="backend",
    is_web=False,
    detect_keywords=["flask", "python flask"],
    dependency_manifest="requirements.txt",
    source_prefix="",
    primary_stack="python",
    config_files={"requirements.txt": "Python dependencies"},
    architect_rules=[
        "Structure: app.py as entry point, templates/ for Jinja2, static/ for assets.",
    ],
    virtuoso_rules=[
        "Generate requirements.txt with pinned versions (e.g. flask==3.0.0).",
        "DO NOT generate package.json for Python-only projects.",
    ],
    validation_rules=["check_requirements_txt_exists"],
))

# ── Python + Django ──────────────────────────────────────────
_register(StackProfile(
    id="python-django",
    display_name="Python Django",
    category="backend",
    is_web=False,
    detect_keywords=["django", "python django"],
    dependency_manifest="requirements.txt",
    source_prefix="",
    primary_stack="python",
    config_files={
        "requirements.txt": "Python dependencies",
        "manage.py": "Django management script",
    },
    architect_rules=[
        "Follow Django project structure: manage.py, project/, apps/.",
        "Include a requirements.txt with pinned versions.",
        "CRITICAL: Must include manage.py as entry point.",
    ],
    virtuoso_rules=[
        "Generate requirements.txt with pinned versions (e.g. django==5.0).",
        "DO NOT generate package.json for Python-only projects.",
        "Follow Django conventions for models, views, urls, and templates.",
    ],
    validation_rules=["check_requirements_txt_exists"],
))

# ── Node.js Ecosystem (Enhanced) ─────────────────────────────
_register(StackProfile(
    id="nestjs",
    display_name="NestJS",
    category="backend",
    is_web=False,
    detect_keywords=["nestjs", "nest js", "nest.js", "node enterprise"],
    dependency_manifest="package.json",
    source_prefix="",
    primary_stack="nest",
    config_files={
        "package.json": "Package manifest",
        "nest-cli.json": "NestCLI info",
        "tsconfig.json": "TypeScript config",
    },
    architect_rules=[
        "Standard NestJS structure: src/main.ts, src/app.module.ts.",
        "Use modules, controllers, and providers.",
    ],
    virtuoso_rules=[
        "Use TypeScript with decorators.",
        "Follow NestJS dependency injection patterns.",
    ],
    validation_rules=["check_package_json_exists"],
))

_register(StackProfile(
    id="express-ts",
    display_name="Express (TypeScript)",
    category="backend",
    is_web=False,
    detect_keywords=["express ts", "express typescript", "node ts", "node typescript"],
    dependency_manifest="package.json",
    source_prefix="",
    primary_stack="node",
    config_files={
        "package.json": "Package manifest",
        "tsconfig.json": "TypeScript config",
    },
    architect_rules=[
        "Structure: src/server.ts, src/routes/, src/controllers/.",
    ],
    virtuoso_rules=[
        "Use TypeScript for all backend logic.",
        "Include type definitions (@types/express, etc.).",
    ],
    validation_rules=["check_package_json_exists"],
))
_register(StackProfile(
    id="node-express",
    display_name="Node.js Express",
    category="backend",
    is_web=False,
    detect_keywords=["express", "node express", "node.js api", "nodejs backend", "express.js"],
    dependency_manifest="package.json",
    source_prefix="",
    primary_stack="node",
    config_files={"package.json": "Package manifest with Express dependencies"},
    architect_rules=[
        "Structure: server.js or index.js as entry, routes/, middleware/, models/.",
    ],
    virtuoso_rules=[
        "Use a recent stable major version for all dependencies. NEVER use \"latest\".",
        "Include proper error handling middleware.",
    ],
    validation_rules=["check_package_json_exists"],
))

# ── Go ───────────────────────────────────────────────────────
_register(StackProfile(
    id="go",
    display_name="Go",
    category="backend",
    is_web=False,
    detect_keywords=["golang", "go lang", "go api", "gin", "fiber"],
    dependency_manifest="go.mod",
    source_prefix="",
    primary_stack="go",
    config_files={"go.mod": "Go module definition"},
    architect_rules=["Standard Go project layout: cmd/, internal/, pkg/."],
    virtuoso_rules=[
        "Generate go.mod with proper module path.",
        "DO NOT generate package.json or requirements.txt for Go projects.",
        "Follow Go conventions: exported names are PascalCase.",
    ],
    validation_rules=[],
))

# ── Java + Spring Boot ───────────────────────────────────────
_register(StackProfile(
    id="java-spring",
    display_name="Java Spring Boot",
    category="backend",
    is_web=False,
    detect_keywords=["spring", "spring boot", "java api", "java backend"],
    dependency_manifest="pom.xml",
    source_prefix="src/main/java/",
    primary_stack="java",
    config_files={
        "pom.xml": "Maven project descriptor",
        "src/main/resources/application.properties": "Spring Boot configuration",
    },
    architect_rules=[
        "Follow Spring Boot conventions: @RestController, @Service, @Repository.",
        "Use Maven (pom.xml) for dependency management.",
    ],
    virtuoso_rules=[
        "Generate pom.xml with proper Spring Boot parent and dependencies.",
        "DO NOT generate package.json or requirements.txt for Java projects.",
        "Use proper package structure: com.example.project.",
    ],
    validation_rules=[],
))

# ── Static HTML ──────────────────────────────────────────────
_register(StackProfile(
    id="static-html",
    display_name="Static HTML/CSS/JS",
    category="static",
    is_web=True,
    detect_keywords=["static html", "static site", "html css", "html css js", "html css javascript",
                     "using html", "landing page", "no framework", "without framework",
                     "plain html", "vanilla html", "vanilla javascript", "vanilla js",
                     "simple page", "basic website", "simple website", "html only", "css only",
                     "pure html", "pure css", "pure javascript", "just html"],
    dependency_manifest="",  # No manifest needed
    source_prefix="frontend/",
    primary_stack="static",
    default_project_type="static",
    config_files={},
    architect_rules=["No build tools needed. Direct HTML/CSS/JS files."],
    virtuoso_rules=[
        "Generate clean, semantic HTML5.",
        "Use vanilla CSS (no preprocessors unless requested).",
        "Use vanilla JavaScript (no npm packages).",
        "DO NOT generate package.json for static sites unless a build tool is needed.",
    ],
    validation_rules=[],
))

# ── Python Script (simple) ───────────────────────────────────
_register(StackProfile(
    id="python-script",
    display_name="Python Script",
    category="backend",
    is_web=False,
    detect_keywords=["python script", "python program", "python cli", "python tool"],
    dependency_manifest="requirements.txt",
    source_prefix="",
    primary_stack="python",
    max_files_simple=5,
    max_files_medium=10,
    max_files_complex=15,
    config_files={
        "main.py": "Main entry point",
        "requirements.txt": "Python dependencies (optional)",
    },
    architect_rules=[
        "Keep it simple: main.py as entry point.",
        "Only include requirements.txt if external packages are needed.",
    ],
    virtuoso_rules=[
        "Generate clean, well-documented Python code.",
        "Include if __name__ == '__main__': guard in entry scripts.",
        "DO NOT generate package.json for Python projects.",
    ],
    validation_rules=[],
))



# ── React Ecosystem (Enhanced) ───────────────────────────────
_register(StackProfile(
    id="react-vite-ts",
    display_name="React + Vite (TypeScript)",
    category="frontend",
    is_web=True,
    detect_keywords=["react ts", "react typescript", "vite ts", "modern react"],
    dependency_manifest="frontend/package.json",
    source_prefix="frontend/",
    primary_stack="react",
    config_files={
        "frontend/package.json": "Package manifest",
        "frontend/vite.config.ts": "Vite configuration",
        "frontend/tsconfig.json": "TypeScript configuration",
        "frontend/tailwind.config.js": "Tailwind configuration (if needed)",
        "frontend/postcss.config.js": "PostCSS configuration",
    },
    architect_rules=[
        "Use Vite + TypeScript template structure.",
        "Entry point: frontend/src/main.tsx.",
        "Components in frontend/src/components/.",
    ],
    virtuoso_rules=[
        "Use TypeScript for all components (.tsx) and logic (.ts).",
        "Define clear interfaces for props and state.",
        "Use functional components with hooks.",
    ],
    validation_rules=["check_package_json_exists"],
))

_register(StackProfile(
    id="remix",
    display_name="Remix",
    category="fullstack",
    is_web=True,
    detect_keywords=["remix", "remix run", "remix framework"],
    dependency_manifest="package.json",
    source_prefix="",
    primary_stack="remix",
    config_files={
        "package.json": "Package manifest",
        "remix.config.js": "Remix configuration",
        "tsconfig.json": "TypeScript configuration",
    },
    architect_rules=[
        "Follow Remix App folder structure (app/routes, app/root.tsx).",
        "Use loader/action functions for data loading and mutations.",
    ],
    virtuoso_rules=[
        "Use standard HTML forms for mutations where possible.",
        "Keep client-side JavaScript minimal; leverage server-side logic.",
    ],
    validation_rules=["check_package_json_exists"],
))

# ── Angular ──────────────────────────────────────────────────
_register(StackProfile(
    id="angular",
    display_name="Angular",
    category="frontend",
    is_web=True,
    detect_keywords=["angular", "angularjs", "ng", "mean stack"],
    dependency_manifest="frontend/package.json",
    source_prefix="frontend/",
    primary_stack="angular",
    config_files={
        "frontend/package.json": "Package manifest",
        "frontend/angular.json": "Angular workspace configuration",
        "frontend/tsconfig.json": "TypeScript configuration",
    },
    architect_rules=[
        "Standard Angular CLI structure: src/app/.",
        "Separate logic (.ts), template (.html), and styles (.css/.scss).",
    ],
    virtuoso_rules=[
        "Use TypeScript classes with decorators (@Component, @Injectable).",
        "Follow Angular Style Guide strictly.",
        "Use RxJS for reactive data handling.",
    ],
    validation_rules=["check_package_json_exists"],
))

# ── Rust (Axum/Tokio) ────────────────────────────────────────
_register(StackProfile(
    id="rust",
    display_name="Rust (Axum)",
    category="backend",
    is_web=False,
    detect_keywords=["rust", "rustlang", "axum", "actix", "tokio"],
    dependency_manifest="Cargo.toml",
    source_prefix="",
    primary_stack="rust",
    config_files={
        "Cargo.toml": "Rust package manifest",
    },
    architect_rules=[
        "Standard Cargo layout: src/main.rs, src/lib.rs.",
        "Use modules (mod.rs) for organization.",
    ],
    virtuoso_rules=[
        "Generate idiomatic Rust code (Safety, Borrow Checker compatible).",
        "Use 'axum' for web server, 'tokio' for async runtime.",
        "Include [dependencies] in Cargo.toml.",
    ],
    validation_rules=[],
))

# ── Ruby on Rails ────────────────────────────────────────────
_register(StackProfile(
    id="rails",
    display_name="Ruby on Rails",
    category="fullstack",
    is_web=True,
    detect_keywords=["ruby", "rails", "ruby on rails", "ror"],
    dependency_manifest="Gemfile",
    source_prefix="",
    primary_stack="ruby",
    config_files={
        "Gemfile": "Dependency manifest",
        "config/routes.rb": "Routes definition",
        "bin/rails": "Rails executable script",
        "bin/bundle": "Bundler executable script",
        "bin/setup": "Setup script",
    },
    architect_rules=[
        "Standard Rails MVC structure: app/models, app/controllers, app/views.",
        "Use config/routes.rb for routing.",
        "CRITICAL: Must include bin/ directory with executable scripts (rails, bundle, setup).",
    ],
    virtuoso_rules=[
        "Follow standard Rails conventions (Convention over Configuration).",
        "Use ERB for views.",
        "IMPORTANT: Generate migration files with VALID timestamps (e.g., 20231027100000_create_users.rb). DO NOT use placeholders like YYYYMMDD.",
        "IMPORTANT: Do NOT include `platforms :mingw, :mswin, :x64_mingw` blocks in Gemfile. Use generic configuration.",
        "IMPORTANT: The gem 'hotwire-rails' does NOT exist. Use 'turbo-rails' and 'stimulus-rails' separately instead.",
        "CRITICAL: MUST generate bin/rails, bin/bundle, and bin/setup scripts with proper shebang (#!/usr/bin/env ruby) and Rails load code.",
        "CRITICAL: bin/ scripts MUST start with: #!/usr/bin/env ruby\nrequire 'bundler/setup'\nload Gem.bin_path('rails', 'rails')",
    ],
    validation_rules=["check_bin_scripts_exist"],
))

# ── PHP (Laravel) ────────────────────────────────────────────
_register(StackProfile(
    id="laravel",
    display_name="PHP Laravel",
    category="fullstack",
    is_web=True,
    detect_keywords=["php", "laravel", "lumen", "lamp stack"],
    dependency_manifest="composer.json",
    source_prefix="",
    primary_stack="php",
    config_files={
        "composer.json": "PHP dependencies",
        "artisan": "Laravel CLI entry point",
    },
    architect_rules=[
        "Standard Laravel structure: app/Http/Controllers, routes/web.php, resources/views.",
        "CRITICAL: Must include artisan script and composer.json.",
    ],
    virtuoso_rules=[
        "Use Blade templates for views.",
        "Follow PSR coding standards.",
    ],
    validation_rules=[],
))

# ── C# (.NET Core) ───────────────────────────────────────────
_register(StackProfile(
    id="dotnet",
    display_name=".NET Core (C#)",
    category="backend",
    is_web=False,
    detect_keywords=["c#", ".net", "dotnet", "asp.net", "csharp"],
    dependency_manifest="Project.csproj",
    source_prefix="",
    primary_stack="dotnet",
    config_files={
        "Project.csproj": "Project definition",
        "Program.cs": "Entry point",
        "appsettings.json": "Configuration",
    },
    architect_rules=[
        "ASP.NET Core structure: Controllers/, Models/, Services/.",
        "Program.cs for setup and middleware pipeline.",
    ],
    virtuoso_rules=[
        "Use clean C# syntax with proper namespaces.",
        "Use Dependency Injection as per ASP.NET Core patterns.",
    ],
    validation_rules=[],
))

# ── C++ (CMake) ──────────────────────────────────────────────
_register(StackProfile(
    id="cpp",
    display_name="C++ (CMake)",
    category="backend",
    is_web=False,
    detect_keywords=["c++", "cpp", "cmake", "cplusplus"],
    dependency_manifest="CMakeLists.txt",
    source_prefix="",
    primary_stack="cpp",
    config_files={
        "CMakeLists.txt": "Build configuration",
    },
    architect_rules=[
        "Standard CMake project: src/, include/, CMakeLists.txt.",
        "Separate header (.h/.hpp) and implementation (.cpp) files.",
    ],
    virtuoso_rules=[
        "Use modern C++ (C++17/20) features.",
        "Ensure memory safety where possible (smart pointers).",
    ],
    validation_rules=[],
))

# ── React (Legacy/Simple) ────────────────────────────────────
_register(StackProfile(
    id="react",
    display_name="React (Simple)",
    category="frontend",
    is_web=True,
    detect_keywords=["react", "create react app", "react spa", "reactjs", "react simple", "react legacy"],
    dependency_manifest="frontend/package.json",
    source_prefix="frontend/",
    primary_stack="react",
    config_files={
        "frontend/package.json": "Package manifest",
    },
    architect_rules=[
        "Use Vite as standard build tool.",
    ],
    virtuoso_rules=[
        "Use functional components.",
    ],
    validation_rules=["check_package_json_exists"],
))


# ─────────────────────────────────────────────────────────────
#  DETECTION & LOOKUP
# ─────────────────────────────────────────────────────────────

# Default fallback profile
# Default fallback profile (matches Next.js profile to ensure quality)
DEFAULT_PROFILE = StackProfile(
    id="auto",
    display_name="Auto-detected (Next.js)",
    category="fullstack",
    is_web=True,
    primary_stack="nextjs",
    dependency_manifest="frontend/package.json",
    source_prefix="frontend/",
    config_files={
        "frontend/package.json": "Package manifest (Next.js)",
        "frontend/tailwind.config.ts": "Tailwind CSS configuration",
        "frontend/postcss.config.mjs": "PostCSS configuration",
    },
    architect_rules=[
        "Use Next.js App Router (app/ directory) by default.",
        "DO NOT use react-scripts (Create React App). Use Next.js.",
        "All files go under frontend/ unless they are backend files.",
        "Strip src/ for App Router: frontend/app/page.tsx.",
    ],
    virtuoso_rules=[
        "IF using Tailwind CSS: include 'tailwindcss' (v4), 'postcss', AND '@tailwindcss/postcss' in package.json dependencies.",
        "IF generating 'frontend/app/globals.css': Use '@import \"tailwindcss\";' AND define custom theme variables using '@theme { --color-primary: ...; }'.",
        "DO NOT use 'tailwind.config.ts' for colors if using v4. Define them in globals.css @theme block.",
        "Use minimal Next.js config.",
        "Use a recent stable major version for all dependencies. NEVER use \"latest\".",
    ],
    validation_rules=["check_package_json_exists", "check_postcss_tailwind"],
)


def detect_stack(user_prompt: str, tech_stack: str = "Auto-detect") -> StackProfile:
    """
    Detect the best stack profile from user prompt and tech_stack hint.
    
    Priority:
    1. Exact match on tech_stack (e.g. "nextjs", "python-flask")
    2. Keyword match on tech_stack string
    3. Keyword match on user_prompt
    4. Default profile
    """
    prompt_lower = user_prompt.lower()
    # Normalize: strip commas and common punctuation so "html, css" matches keyword "html css"
    import re as _re
    prompt_normalized = _re.sub(r'[,;:!?()\[\]{}]', ' ', prompt_lower)
    prompt_normalized = ' '.join(prompt_normalized.split())  # collapse whitespace
    
    if isinstance(tech_stack, list):
        tech_stack = " ".join(tech_stack)
    tech_lower = tech_stack.lower() if tech_stack else ""
    
    # 1. Exact match on tech_stack
    if tech_lower in STACK_PROFILES:
        logger.info(f"Stack detected (exact): {tech_lower}")
        return STACK_PROFILES[tech_lower]
    
    # 2. Keyword match on tech_stack
    for profile in STACK_PROFILES.values():
        for keyword in profile.detect_keywords:
            if keyword in tech_lower:
                logger.info(f"Stack detected (tech_stack keyword '{keyword}'): {profile.id}")
                return profile
    
    # 3. Keyword match on user prompt (longer keywords first for specificity)
    all_profiles_sorted = sorted(
        STACK_PROFILES.values(),
        key=lambda p: max((len(k) for k in p.detect_keywords), default=0),
        reverse=True,
    )
    for profile in all_profiles_sorted:
        for keyword in profile.detect_keywords:
            if keyword in prompt_normalized:
                logger.info(f"Stack detected (prompt keyword '{keyword}'): {profile.id}")
                return profile
    
    logger.info("Stack detection: no match, using default profile")
    return DEFAULT_PROFILE


def get_stack_profile(tech_stack: str = "Auto-detect") -> StackProfile:
    """
    Get profile by exact ID. For detection from user prompt, use detect_stack().
    """
    if tech_stack.lower() in STACK_PROFILES:
        return STACK_PROFILES[tech_stack.lower()]
    return DEFAULT_PROFILE


def detect_stack_from_blueprint(blueprint: dict) -> StackProfile:
    """
    Detect stack from an already-generated blueprint dict.
    Uses primary_stack and tech_stack fields.
    """
    primary = blueprint.get("primary_stack", "").lower()
    tech = blueprint.get("tech_stack", "")
    if isinstance(tech, list):
        tech = " ".join(tech)
    tech = tech.lower()
    
    # Direct match on primary_stack
    if primary in STACK_PROFILES:
        return STACK_PROFILES[primary]
    
    # Keyword match
    for profile in STACK_PROFILES.values():
        for keyword in profile.detect_keywords:
            if keyword in primary or keyword in tech:
                return profile
    
    return DEFAULT_PROFILE


def get_supported_stacks() -> List[str]:
    """Return list of all supported stack IDs."""
    return list(STACK_PROFILES.keys())


def get_primary_stack_options() -> List[str]:
    """Return list of unique primary_stack values for the architect prompt."""
    return list(set(p.primary_stack for p in STACK_PROFILES.values()))
