# ACEA Sentinel - Release Agent (Enhanced)
# Validates, packages, and generates deployment artifacts

import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field, asdict
from enum import Enum
from app.core.filesystem import BASE_PROJECTS_DIR, archive_project


class DeployTarget(Enum):
    """Supported deployment targets."""
    VERCEL = "vercel"
    NETLIFY = "netlify"
    RAILWAY = "railway"
    DOCKER = "docker"
    GITHUB_PAGES = "github_pages"
    CUSTOM = "custom"


@dataclass
class DeploymentArtifact:
    """Represents a deployment configuration artifact."""
    target: DeployTarget
    filename: str
    content: str
    description: str


@dataclass
class ReleaseReport:
    """Comprehensive release report."""
    project_id: str
    project_name: str
    ready: bool
    file_count: int
    total_size_bytes: int
    missing_files: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    generated_artifacts: List[str] = field(default_factory=list)
    deploy_targets: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ReleaseAgent:
    """
    Enhanced Release Agent for ACEA Sentinel.
    
    Features:
    - Project validation and readiness checks
    - Deployment artifact generation (Dockerfile, vercel.json, netlify.toml)
    - CI/CD configuration templates
    - Comprehensive release reports
    - Archive creation with all artifacts
    """
    
    def __init__(self):
        self.deploy_generators = {
            DeployTarget.VERCEL: self._generate_vercel_config,
            DeployTarget.NETLIFY: self._generate_netlify_config,
            DeployTarget.RAILWAY: self._generate_railway_config,
            DeployTarget.DOCKER: self._generate_dockerfile,
            DeployTarget.GITHUB_PAGES: self._generate_github_pages_config,
        }
    
    async def prepare_release(
        self,
        project_id: str,
        blueprint: dict = None,
        deploy_targets: List[DeployTarget] = None,
        generate_readme: bool = True,
        generate_cicd: bool = True
    ) -> ReleaseReport:
        """
        Comprehensive release preparation.
        
        Args:
            project_id: Project identifier
            blueprint: Project blueprint with tech stack info
            deploy_targets: List of deployment targets to generate configs for
            generate_readme: Whether to generate/update README
            generate_cicd: Whether to generate CI/CD configs
        """
        from app.core.socket_manager import SocketManager
        sm = SocketManager()
        
        project_path = BASE_PROJECTS_DIR / project_id
        
        await sm.emit("agent_log", {
            "agent_name": "RELEASE",
            "message": "Preparing release package..."
        })
        
        if not project_path.exists():
            return ReleaseReport(
                project_id=project_id,
                project_name=blueprint.get("project_name", "Unknown") if blueprint else "Unknown",
                ready=False,
                file_count=0,
                total_size_bytes=0,
                warnings=["Project directory does not exist"]
            )
        
        # Get all files and calculate size
        files = list(project_path.glob("**/*"))
        file_list = [f for f in files if f.is_file()]
        total_size = sum(f.stat().st_size for f in file_list)
        
        # Run validations
        warnings = self._validate_files(file_list)
        missing = self._validate_blueprint(project_path, blueprint)
        
        # Determine tech stack
        tech_stack = self._detect_tech_stack(project_path, blueprint)
        
        # Generate artifacts
        generated = []
        
        # 1. Generate .gitignore if missing
        if not (project_path / ".gitignore").exists():
            self._generate_gitignore(project_path, tech_stack)
            generated.append(".gitignore")
        
        # 2. Generate README if requested
        if generate_readme and not any(f.name.lower() == "readme.md" for f in file_list):
            await self._generate_readme(project_path, blueprint)
            generated.append("README.md")
        
        # 3. Generate deployment configs
        targets_used = []
        if deploy_targets:
            for target in deploy_targets:
                if target in self.deploy_generators:
                    artifact = self.deploy_generators[target](project_path, tech_stack, blueprint)
                    if artifact:
                        self._write_artifact(project_path, artifact)
                        generated.append(artifact.filename)
                        targets_used.append(target.value)
        else:
            # Auto-detect best deployment target
            auto_target = self._auto_detect_deploy_target(tech_stack)
            if auto_target and auto_target in self.deploy_generators:
                artifact = self.deploy_generators[auto_target](project_path, tech_stack, blueprint)
                if artifact:
                    self._write_artifact(project_path, artifact)
                    generated.append(artifact.filename)
                    targets_used.append(auto_target.value)
        
        # 4. Generate CI/CD configs
        if generate_cicd:
            cicd_artifacts = self._generate_cicd_configs(project_path, tech_stack)
            for artifact in cicd_artifacts:
                self._write_artifact(project_path, artifact)
                generated.append(artifact.filename)
        
        # 5. Generate release manifest
        manifest = self._generate_release_manifest(project_id, blueprint, tech_stack, targets_used)
        manifest_path = project_path / "release.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        generated.append("release.json")
        
        await sm.emit("agent_log", {
            "agent_name": "RELEASE",
            "message": f"✅ Generated {len(generated)} artifacts: {', '.join(generated[:5])}"
        })
        
        return ReleaseReport(
            project_id=project_id,
            project_name=blueprint.get("project_name", "Project") if blueprint else "Project",
            ready=len(missing) == 0,
            file_count=len(file_list),
            total_size_bytes=total_size,
            missing_files=missing,
            warnings=warnings,
            generated_artifacts=generated,
            deploy_targets=targets_used
        )
    
    def _detect_tech_stack(self, project_path: Path, blueprint: dict = None) -> dict:
        """Detect project tech stack from files."""
        stack = {
            "type": "unknown",
            "framework": None,
            "language": "javascript",
            "has_backend": False,
            "has_frontend": True
        }
        
        if blueprint:
            bp_stack = blueprint.get("tech_stack", "")
            if isinstance(bp_stack, str):
                bp_stack = bp_stack.lower()
            else:
                bp_stack = str(bp_stack).lower()
            
            if "react" in bp_stack or "next" in bp_stack:
                stack["framework"] = "nextjs" if "next" in bp_stack else "react"
                stack["type"] = "frontend"
            elif "vue" in bp_stack:
                stack["framework"] = "vue"
                stack["type"] = "frontend"
            elif "python" in bp_stack or "flask" in bp_stack or "fastapi" in bp_stack:
                stack["language"] = "python"
                stack["framework"] = "fastapi" if "fastapi" in bp_stack else "flask"
                stack["type"] = "backend"
                stack["has_backend"] = True
            elif "node" in bp_stack or "express" in bp_stack:
                stack["framework"] = "express"
                stack["type"] = "backend"
                stack["has_backend"] = True
        
        # File-based detection
        if (project_path / "package.json").exists():
            try:
                with open(project_path / "package.json") as f:
                    pkg = json.load(f)
                    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                    if "next" in deps:
                        stack["framework"] = "nextjs"
                    elif "react" in deps:
                        stack["framework"] = "react"
                    elif "vue" in deps:
                        stack["framework"] = "vue"
            except:
                pass
        
        if (project_path / "requirements.txt").exists():
            stack["language"] = "python"
            stack["has_backend"] = True
        
        return stack
    
    def _auto_detect_deploy_target(self, tech_stack: dict) -> Optional[DeployTarget]:
        """Auto-detect best deployment target based on tech stack."""
        framework = tech_stack.get("framework", "")
        
        if framework in ["nextjs", "react", "vue"]:
            return DeployTarget.VERCEL
        elif tech_stack.get("language") == "python":
            return DeployTarget.DOCKER
        elif tech_stack.get("type") == "frontend":
            return DeployTarget.NETLIFY
        else:
            return DeployTarget.DOCKER
    
    def _generate_vercel_config(self, project_path: Path, tech_stack: dict, blueprint: dict) -> DeploymentArtifact:
        """Generate vercel.json configuration."""
        framework = tech_stack.get("framework", "")
        
        config = {
            "version": 2,
            "name": blueprint.get("project_name", "project").lower().replace(" ", "-") if blueprint else "project",
            "builds": [],
            "routes": []
        }
        
        if framework == "nextjs":
            config["framework"] = "nextjs"
        elif framework == "react":
            config["builds"] = [{"src": "package.json", "use": "@vercel/static-build"}]
            config["routes"] = [{"src": "/(.*)", "dest": "/index.html"}]
        else:
            config["builds"] = [{"src": "**/*", "use": "@vercel/static"}]
        
        return DeploymentArtifact(
            target=DeployTarget.VERCEL,
            filename="vercel.json",
            content=json.dumps(config, indent=2),
            description="Vercel deployment configuration"
        )
    
    def _generate_netlify_config(self, project_path: Path, tech_stack: dict, blueprint: dict) -> DeploymentArtifact:
        """Generate netlify.toml configuration."""
        framework = tech_stack.get("framework", "")
        
        if framework == "nextjs":
            config = """[build]
  command = "npm run build"
  publish = ".next"

[[plugins]]
  package = "@netlify/plugin-nextjs"
"""
        elif framework == "react":
            config = """[build]
  command = "npm run build"
  publish = "build"

[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200
"""
        else:
            config = """[build]
  publish = "dist"

[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200
"""
        
        return DeploymentArtifact(
            target=DeployTarget.NETLIFY,
            filename="netlify.toml",
            content=config,
            description="Netlify deployment configuration"
        )
    
    def _generate_railway_config(self, project_path: Path, tech_stack: dict, blueprint: dict) -> DeploymentArtifact:
        """Generate railway.json configuration."""
        config = {
            "$schema": "https://railway.app/railway.schema.json",
            "build": {
                "builder": "NIXPACKS"
            },
            "deploy": {
                "numReplicas": 1,
                "restartPolicyType": "ON_FAILURE",
                "restartPolicyMaxRetries": 10
            }
        }
        
        return DeploymentArtifact(
            target=DeployTarget.RAILWAY,
            filename="railway.json",
            content=json.dumps(config, indent=2),
            description="Railway deployment configuration"
        )
    
    def _generate_dockerfile(self, project_path: Path, tech_stack: dict, blueprint: dict) -> DeploymentArtifact:
        """Generate Dockerfile based on tech stack."""
        language = tech_stack.get("language", "javascript")
        framework = tech_stack.get("framework", "")
        
        if language == "python":
            dockerfile = """# Python Application Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Expose port
EXPOSE 8000

# Run application
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
"""
        elif framework == "nextjs":
            dockerfile = """# Next.js Application Dockerfile
FROM node:20-alpine AS base

# Install dependencies only when needed
FROM base AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

# Build the application
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# Production image
FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
ENV PORT=3000
CMD ["node", "server.js"]
"""
        else:
            dockerfile = """# Node.js Application Dockerfile
FROM node:20-alpine

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm ci --only=production

# Copy application
COPY . .

# Build if needed
RUN npm run build --if-present

# Expose port
EXPOSE 3000

# Run application
CMD ["npm", "start"]
"""
        
        return DeploymentArtifact(
            target=DeployTarget.DOCKER,
            filename="Dockerfile",
            content=dockerfile,
            description="Docker container configuration"
        )
    
    def _generate_github_pages_config(self, project_path: Path, tech_stack: dict, blueprint: dict) -> DeploymentArtifact:
        """Generate GitHub Pages workflow."""
        workflow = """name: Deploy to GitHub Pages

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - run: npm ci
      - run: npm run build
      - uses: actions/upload-pages-artifact@v3
        with:
          path: ./dist

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/deploy-pages@v4
        id: deployment
"""
        
        return DeploymentArtifact(
            target=DeployTarget.GITHUB_PAGES,
            filename=".github/workflows/deploy.yml",
            content=workflow,
            description="GitHub Pages deployment workflow"
        )
    
    def _generate_cicd_configs(self, project_path: Path, tech_stack: dict) -> List[DeploymentArtifact]:
        """Generate CI/CD configuration files."""
        artifacts = []
        
        # GitHub Actions CI
        language = tech_stack.get("language", "javascript")
        
        if language == "python":
            ci_workflow = """name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pip install pytest
      - run: pytest --tb=short
"""
        else:
            ci_workflow = """name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - run: npm ci
      - run: npm run lint --if-present
      - run: npm test --if-present
      - run: npm run build
"""
        
        artifacts.append(DeploymentArtifact(
            target=DeployTarget.CUSTOM,
            filename=".github/workflows/ci.yml",
            content=ci_workflow,
            description="GitHub Actions CI workflow"
        ))
        
        return artifacts
    
    def _generate_release_manifest(
        self,
        project_id: str,
        blueprint: dict,
        tech_stack: dict,
        deploy_targets: List[str]
    ) -> dict:
        """Generate release.json manifest."""
        return {
            "version": "1.0.0",
            "project_id": project_id,
            "project_name": blueprint.get("project_name", "Project") if blueprint else "Project",
            "generated_by": "ACEA Sentinel",
            "generated_at": datetime.now().isoformat(),
            "tech_stack": tech_stack,
            "deploy_targets": deploy_targets,
            "entry_points": {
                "frontend": "index.html" if tech_stack.get("type") == "frontend" else None,
                "backend": "main.py" if tech_stack.get("language") == "python" else "index.js"
            }
        }
    
    async def _generate_readme(self, project_path: Path, blueprint: dict):
        """Generate README.md using Documenter agent."""
        from app.agents.documenter import DocumenterAgent
        
        documenter = DocumenterAgent()
        files = [str(f.relative_to(project_path)) for f in project_path.glob("**/*") if f.is_file()]
        
        readme = await documenter.generate_readme(
            blueprint or {},
            files,
            blueprint.get("description", "") if blueprint else ""
        )
        
        with open(project_path / "README.md", "w") as f:
            f.write(readme)
    
    def _write_artifact(self, project_path: Path, artifact: DeploymentArtifact):
        """Write artifact to project directory."""
        artifact_path = project_path / artifact.filename
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        with open(artifact_path, "w") as f:
            f.write(artifact.content)
    
    def _validate_files(self, file_list: List[Path]) -> List[str]:
        """Check for essential files and common issues."""
        warnings = []
        
        essential = ["package.json", "requirements.txt", "main.py", "app.py", "index.html"]
        if not any(f.name in essential for f in file_list):
            warnings.append("No standard entry point file found")
        
        if not any(f.name.lower() == "readme.md" for f in file_list):
            warnings.append("No README.md found")
        
        empty_files = [f for f in file_list if f.stat().st_size == 0]
        if empty_files:
            warnings.append(f"{len(empty_files)} empty file(s) found")
        
        return warnings
    
    def _validate_blueprint(self, project_path: Path, blueprint: dict) -> List[str]:
        """Check if all blueprint files exist."""
        missing = []
        if blueprint:
            expected_files = [f.get("path") for f in blueprint.get("file_structure", [])]
            for expected in expected_files:
                if expected and not (project_path / expected).exists():
                    missing.append(expected)
        return missing
    
    def _generate_gitignore(self, project_path: Path, tech_stack: dict):
        """Generate appropriate .gitignore."""
        language = tech_stack.get("language", "javascript")
        
        base_content = """# Dependencies
node_modules/
venv/
__pycache__/
*.pyc
.env
.env.local

# Build outputs
dist/
build/
.next/
out/

# IDE
.idea/
.vscode/
*.swp

# OS
.DS_Store
Thumbs.db

# Logs
*.log
npm-debug.log*
"""
        
        if language == "python":
            base_content += """
# Python
*.egg-info/
.eggs/
.pytest_cache/
htmlcov/
.coverage
"""
        
        with open(project_path / ".gitignore", "w") as f:
            f.write(base_content)
    
    def create_archive(self, project_id: str) -> str:
        """Create ZIP archive. Returns path to ZIP file."""
        return archive_project(project_id)


# Singleton instance
_release_agent = None

def get_release_agent() -> ReleaseAgent:
    """Get singleton Release Agent instance."""
    global _release_agent
    if _release_agent is None:
        _release_agent = ReleaseAgent()
    return _release_agent

