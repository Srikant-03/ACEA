# ACEA Sentinel - Release Agent
# Validates and prepares projects for download

import os
from pathlib import Path
from typing import Dict, List
from app.core.filesystem import BASE_PROJECTS_DIR, archive_project


class ReleaseAgent:
    """Validates and prepares projects for release."""
    
    def __init__(self):
        pass
    
    def prepare_release(self, project_id: str, blueprint: dict = None) -> Dict:
        """
        Validate and prepare project for download.
        """
        project_path = BASE_PROJECTS_DIR / project_id
        
        if not project_path.exists():
            return {
                "ready": False,
                "missing_files": [],
                "warnings": ["Project directory does not exist"],
                "file_count": 0
            }
        
        # Get all files
        files = list(project_path.glob("**/*"))
        file_list = [f for f in files if f.is_file()]
        
        # Run validations
        warnings = self._validate_files(file_list)
        missing = self._validate_blueprint(project_path, blueprint)
        
        # Generate .gitignore if missing
        gitignore_path = project_path / ".gitignore"
        if not gitignore_path.exists():
            self._generate_gitignore(project_path, blueprint)
        
        return {
            "ready": len(missing) == 0,
            "missing_files": missing,
            "warnings": warnings,
            "file_count": len(file_list)
        }

    def _validate_files(self, file_list: List[Path]) -> List[str]:
        """Check for essential files and common issues."""
        warnings = []
        
        # Check for essential files
        essential = ["package.json", "requirements.txt", "main.py", "app.py", "index.html"]
        if not any(f.name in essential for f in file_list):
            warnings.append("No standard entry point file found")
        
        # Check for README
        if not any(f.name.lower() == "readme.md" for f in file_list):
            warnings.append("No README.md found")
        
        # Check for empty files
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
                if not (project_path / expected).exists():
                    missing.append(expected)
        return missing
    
    def _generate_gitignore(self, project_path: Path, blueprint: dict = None):
        """Generate appropriate .gitignore."""
        stack = (blueprint or {}).get("tech_stack", "").lower()
        
        gitignore_content = """# Dependencies
node_modules/
venv/
__pycache__/
*.pyc

# Build outputs
dist/
build/
.next/
out/

# Environment
.env
.env.local

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
        
        with open(project_path / ".gitignore", "w") as f:
            f.write(gitignore_content)
    
    def create_archive(self, project_id: str) -> str:
        """Create ZIP archive. Returns path to ZIP file."""
        return archive_project(project_id)
