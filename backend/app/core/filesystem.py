import os
import shutil
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
            # Safety: ensure content is a string (LLM repair can leak dicts)
            if not isinstance(content, str):
                import json as _json
                content = _json.dumps(content, indent=2) if isinstance(content, dict) else str(content)
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
        
    # Directories to skip (avoid overwhelming LLM context and binary crashes)
    SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".next", "dist", "build"}
    
    # Binary file extensions to skip
    BINARY_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".woff", ".woff2",
                   ".ttf", ".eot", ".mp4", ".mp3", ".zip", ".tar", ".gz", ".pyc",
                   ".pyd", ".so", ".dll", ".exe", ".bin", ".pdf", ".lock"}
    
    for root, dirs, filenames in os.walk(project_dir):
        # Prune skip directories in-place (prevents os.walk from descending)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        
        for name in filenames:
            full_path = Path(root) / name
            rel_path = full_path.relative_to(project_dir)
            
            # Skip binary files by extension
            if full_path.suffix.lower() in BINARY_EXTS:
                continue
            
            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    files[str(rel_path)] = f.read()
            except Exception:
                # Skip unreadable files (binary, locked, etc.)
                pass
                
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

def delete_file(project_id: str, path: str) -> bool:
    """
    Deletes a specific file. Returns True on success.
    """
    full_path = BASE_PROJECTS_DIR / project_id / path
    
    # Security check: Ensure we don't delete outside project dir
    try:
        full_path.resolve().relative_to((BASE_PROJECTS_DIR / project_id).resolve())
    except ValueError:
        return False
        
    try:
        if full_path.exists():
            if full_path.is_dir():
                shutil.rmtree(full_path)
            else:
                os.remove(full_path)
            return True
        return False
    except Exception as e:
        print(f"Error deleting file {path}: {e}")
        return False

# shutil is now imported at the top of the file

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

def organize_files(filenames):
    """
    Organize files into a nested dictionary structure.
    Optimized to O(n*m) complexity instead of O(n*m*k).
    """
    organized = {}
    for name in filenames:
        parts = name.split('/')
        current_level = organized
        for part in parts:
            if part not in current_level:
                current_level[part] = {}
            current_level = current_level[part]
    return organized

