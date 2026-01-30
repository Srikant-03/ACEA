import os
from pathlib import Path
from typing import Dict

# Move up 4 levels: app -> core -> backend -> ACEA -> generated_projects
BASE_PROJECTS_DIR = Path(__file__).parent.parent.parent.parent / "generated_projects"

def write_project_files(project_id: str, files: Dict[str, str]) -> str:
    """
    Writes the dictionary of filename->content to disk under generated_projects/{project_id}.
    Returns the absolute path to the project directory.
    """
    project_dir = BASE_PROJECTS_DIR / project_id
    os.makedirs(project_dir, exist_ok=True)
    
    for relative_path, content in files.items():
        # Handle subdirectories in legacy paths if any
        file_path = project_dir / relative_path
        os.makedirs(file_path.parent, exist_ok=True)
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
            
    return str(project_dir.absolute())

def read_project_files(project_id: str) -> Dict[str, str]:
    """
    Reads files from disk (for sending to Frontend or Analysis).
    """
    project_dir = BASE_PROJECTS_DIR / project_id
    files = {}
    
    if not project_dir.exists():
        return {}
        
    for root, _, filenames in os.walk(project_dir):
        for name in filenames:
            full_path = Path(root) / name
            rel_path = full_path.relative_to(project_dir)
            
            # Skip hidden files or venv
            if ".git" in str(rel_path) or "__pycache__" in str(rel_path):
                continue
                
            with open(full_path, "r", encoding="utf-8") as f:
                files[str(rel_path)] = f.read()
                
    return files

def read_file(project_id: str, file_path: str) -> str:
    """
    Reads a single file content.
    """
    full_path = BASE_PROJECTS_DIR / project_id / file_path
    
    if not full_path.exists():
        return None
        
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None

def update_file_content(project_id: str, path: str, content: str) -> bool:
    """
    Updates a specific file's content. Returns True on success.
    """
    full_path = BASE_PROJECTS_DIR / project_id / path
    
    # Security check: Ensure we don't write outside project dir
    try:
        full_path.resolve().relative_to((BASE_PROJECTS_DIR / project_id).resolve())
    except ValueError:
        return False
        
    try:
        os.makedirs(full_path.parent, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"Error updating file {path}: {e}")
        return False

import shutil

def archive_project(project_id: str) -> str:
    """
    Creates a ZIP archive of the project. 
    Returns the absolute path to the zip file.
    """
    project_dir = BASE_PROJECTS_DIR / project_id
    zip_base = BASE_PROJECTS_DIR / f"{project_id}"
    
    if not project_dir.exists():
        return None
        
    # Create zip (shutil adds .zip extension automatically)
    archive_path = shutil.make_archive(str(zip_base), 'zip', root_dir=str(project_dir))
    return archive_path
